"""
simulation_engine.py
Core event-driven simulation engine for the Karachi EMS Triage & Dispatch System.
Integrates AI Triage, PriorityMinHeap, KDTree2D, Graph routing, HospitalManager,
and structured JSON event logging.
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
import json
import logging
import math
import os
import time
from typing import Any, Dict, List, Literal, Optional, Tuple

from data_structures.graph import Graph
from hospital_engine import HospitalManager
from karachi_geo_data import KARACHI_GEO_DATA
from data_structures.kd_tree import Ambulance as KDAmbulance, KDTree2D
from data_structures.min_heap import Patient, PriorityMinHeap

# Import Block A AI Triage Agent (supports triage_agent.py or fallback if standalone)
try:
    from triage_agent import TriageSchema, query_triage, query_triage_with_meta
except ImportError:
    from pydantic import BaseModel, Field

    class TriageSchema(BaseModel):  # type: ignore[no-redef]
        triage_level: int = Field(..., ge=1, le=5)
        equipment_needed: Literal["ICU", "Basic"]
        clinical_summary: str

    def query_triage(  # type: ignore[no-redef]
        patient_notes: str,
        host: str = os.getenv("OLLAMA_HOST", "http://localhost:11434"),
        model: str = "llama3.2:1b",
        max_retries: int = 3,
    ) -> TriageSchema:
        raise RuntimeError("triage_agent.py module not found in PYTHONPATH.")


class _AutoCloseFileHandler(logging.FileHandler):
    """FileHandler that flushes and closes the stream after each emit so Windows
    does not hold file locks during temporary directory cleanup in unit tests.
    """

    def emit(self, record: logging.LogRecord) -> None:
        super().emit(record)
        self.close()


class AmbulanceState(str, Enum):
    IDLE = "IDLE"
    EN_ROUTE_TO_CALLER = "EN_ROUTE_TO_CALLER"
    TRANSPORTING_TO_HOSPITAL = "TRANSPORTING_TO_HOSPITAL"
    RETURNING = "RETURNING"


@dataclass
class FleetAmbulance:
    amb_id: str
    name: str
    equipment_type: Literal["ICU", "Basic"]
    home_coords: Tuple[float, float]
    coords: Tuple[float, float]
    state: AmbulanceState = AmbulanceState.IDLE
    base_speed_kmh: float = 50.0
    waypoints: List[Tuple[float, float]] = field(default_factory=list)
    assigned_call_id: Optional[str] = None
    target_hospital_id: Optional[str] = None
    target_hospital_coords: Optional[Tuple[float, float]] = None
    kd_entity: KDAmbulance = field(init=False)

    def __post_init__(self) -> None:
        self.kd_entity = KDAmbulance(
            amb_id=self.amb_id,
            coords=self.coords,
            is_idle=(self.state == AmbulanceState.IDLE),
        )

    def sync_kd_entity(self) -> None:
        """Synchronizes spatial coordinates and idle status with the KD-Tree node."""
        self.kd_entity.coords = self.coords
        self.kd_entity.is_idle = self.state == AmbulanceState.IDLE


@dataclass
class EmergencyCall:
    call_id: str
    caller_coords: Tuple[float, float]
    patient_notes: str
    triage: TriageSchema
    arrival_time: float
    status: Literal["QUEUED", "DISPATCHED", "IN_TRANSIT", "COMPLETED"] = "QUEUED"
    assigned_amb_id: Optional[str] = None
    assigned_hospital_id: Optional[str] = None
    dispatch_time: Optional[float] = None
    completion_time: Optional[float] = None
    fallback_used: bool = False
    triage_latency_ms: float = 0.0


@dataclass
class ActiveAdmission:
    hospital_id: str
    bed_type: Literal["ICU", "Basic"]
    discharge_time: float


class EMSSimulator:
    """Discrete-time EMS dispatch and fleet movement simulator."""

    def __init__(
        self,
        graph: Optional[Graph] = None,
        hospital_manager: Optional[HospitalManager] = None,
        fleet: Optional[List[FleetAmbulance]] = None,
        start_hour: float = 7.75,  # Default 07:45 AM (just before 8-10 AM peak window)
        w1: float = 10.0,
        w2: float = 0.05,  # Aging weight per second of wait time (3.0 pts/min)
        ollama_host: str = os.getenv("OLLAMA_HOST", "http://localhost:11434"),
        ollama_model: str = "llama3.2:1b",
        bed_recovery_seconds: float = 1800.0,
        log_file: Optional[str] = "dispatch_events.log",
    ) -> None:
        self.graph: Graph = graph if graph is not None else self._build_default_karachi_graph()
        self.hospital_manager: HospitalManager = (
            hospital_manager if hospital_manager is not None else HospitalManager()
        )
        self.priority_queue = PriorityMinHeap(w1=w1, w2=w2)
        self.ollama_host = ollama_host
        self.ollama_model = ollama_model
        self.bed_recovery_seconds = bed_recovery_seconds
        self.log_file = log_file

        # Configure structured JSON event logger
        self.logger: Optional[logging.Logger] = None
        if self.log_file:
            log_dir = os.path.dirname(os.path.abspath(self.log_file))
            if log_dir:
                os.makedirs(log_dir, exist_ok=True)
            logger = logging.getLogger(f"ems.simulator.{id(self)}")
            logger.setLevel(logging.INFO)
            logger.propagate = False
            logger.handlers.clear()
            handler = _AutoCloseFileHandler(
                self.log_file, mode="a", encoding="utf-8", delay=True
            )
            handler.setFormatter(logging.Formatter("%(message)s"))
            logger.addHandler(handler)
            self.logger = logger
        self.event_logger = self.logger if self.logger is not None else logging.getLogger(f"ems.simulator.{id(self)}")

        # Simulation clock in seconds from midnight (00:00:00)
        self.current_time_seconds: float = start_hour * 3600.0
        self.is_peak_hour: bool = self._check_peak_hour(self.current_time_seconds)
        self.dynamic_edge_weights: Dict[Tuple[str, str], float] = {}

        # Initialize fleet
        fleet_list = fleet if fleet is not None else self._build_default_karachi_fleet()
        self.fleet: Dict[str, FleetAmbulance] = {amb.amb_id: amb for amb in fleet_list}

        # Separate 2D KD-Trees per equipment tier for O(log N) matching lookups
        self.kd_trees: Dict[Literal["ICU", "Basic"], Optional[KDTree2D]] = {
            "ICU": None,
            "Basic": None,
        }
        self._rebuild_kd_trees()

        # Call and bed tracking
        self.calls: Dict[str, EmergencyCall] = {}
        self.active_admissions: List[ActiveAdmission] = []
        self._call_counter: int = 0

        # Apply initial traffic weights to road graph
        self._update_road_network_weights()

    def _log_event(self, payload: Dict[str, Any]) -> None:
        """Emits a single structured JSON line to the configured log file."""
        if self.logger is None:
            return
        record = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "sim_clock": self.get_formatted_time(),
            **payload,
        }
        self.logger.info(json.dumps(record))

    # -------------------------------------------------------------------------
    # INITIALIZATION HELPERS
    # -------------------------------------------------------------------------

    @staticmethod
    def _build_default_karachi_graph() -> Graph:
        g = Graph()
        spec = KARACHI_GEO_DATA["district_road_graph"]
        for node_id, info in spec["nodes"].items():
            g.add_node(node_id, info["coords"][0], info["coords"][1])
        for edge in spec["edges"]:
            g.add_edge(
                edge["u"],
                edge["v"],
                distance=edge["distance_km"],
                peak_multiplier=edge["peak_multiplier"],
                bidirectional=True,
            )
        return g

    @staticmethod
    def _build_default_karachi_fleet() -> List[FleetAmbulance]:
        """Creates a mixed ICU and Basic ambulance fleet across Karachi dispatch hubs."""
        fleet: List[FleetAmbulance] = []
        hubs = list(KARACHI_GEO_DATA["ambulance_hubs"].items())
        for idx, (hub_id, info) in enumerate(hubs):
            eq_type: Literal["ICU", "Basic"] = "ICU" if idx % 3 == 0 else "Basic"
            amb_id = f"AMB-{idx + 1:03d}"
            coords = tuple(info["coords"])
            fleet.append(
                FleetAmbulance(
                    amb_id=amb_id,
                    name=f"{info['name']} Unit",
                    equipment_type=eq_type,
                    home_coords=coords,
                    coords=coords,
                )
            )
        return fleet

    # -------------------------------------------------------------------------
    # CLOCK & DYNAMIC TRAFFIC WEIGHTS
    # -------------------------------------------------------------------------

    @staticmethod
    def _check_peak_hour(sim_seconds: float) -> bool:
        """Returns True during Karachi peak traffic windows: 8–10 AM and 5–8 PM."""
        hour_of_day = (sim_seconds / 3600.0) % 24.0
        morning_peak = 8.0 <= hour_of_day < 10.0
        evening_peak = 17.0 <= hour_of_day < 20.0
        return morning_peak or evening_peak

    def get_formatted_time(self) -> str:
        total_secs = int(self.current_time_seconds) % 86400
        hours = total_secs // 3600
        minutes = (total_secs % 3600) // 60
        seconds = total_secs % 60
        return f"{hours:02d}:{minutes:02d}:{seconds:02d}"

    def _update_road_network_weights(self) -> None:
        """Dynamically updates effective edge weights on the road graph for current traffic."""
        self.is_peak_hour = self._check_peak_hour(self.current_time_seconds)
        self.dynamic_edge_weights.clear()

        for u, edges in self.graph.adj.items():
            for edge in edges:
                effective_weight = edge.get_weight(self.is_peak_hour)
                edge.effective_weight = effective_weight
                self.dynamic_edge_weights[(u, edge.target)] = effective_weight

    # -------------------------------------------------------------------------
    # SPATIAL KD-TREE & ROUTE WAYPOINT GENERATION
    # -------------------------------------------------------------------------

    def _rebuild_kd_trees(self) -> None:
        """Rebuilds equipment-partitioned 2D KD-Trees from current ambulance states."""
        for eq_type in ("ICU", "Basic"):
            matching_kd_nodes = [
                amb.kd_entity
                for amb in self.fleet.values()
                if amb.equipment_type == eq_type and amb.state == AmbulanceState.IDLE
            ]
            # Pass shallow copy because KDTree2D._build_tree sorts in-place
            self.kd_trees[eq_type] = (
                KDTree2D(list(matching_kd_nodes)) if matching_kd_nodes else None
            )

    @staticmethod
    def _haversine_km(c1: Tuple[float, float], c2: Tuple[float, float]) -> float:
        earth_r = 6371.0
        lat1, lon1 = math.radians(c1[0]), math.radians(c1[1])
        lat2, lon2 = math.radians(c2[0]), math.radians(c2[1])
        dlat, dlon = lat2 - lat1, lon2 - lon1
        a = (
            math.sin(dlat / 2.0) ** 2
            + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2.0) ** 2
        )
        return 2.0 * earth_r * math.asin(math.sqrt(a))

    def _nearest_graph_node(self, coords: Tuple[float, float]) -> str:
        return min(
            self.graph.nodes.keys(),
            key=lambda nid: self._haversine_km(
                coords, (self.graph.nodes[nid].x, self.graph.nodes[nid].y)
            ),
        )

    def _compute_route_waypoints(
        self,
        origin: Tuple[float, float],
        destination: Tuple[float, float],
        segment_resolution_km: float = 0.25,
    ) -> List[Tuple[float, float]]:
        """Computes shortest A* path over the road graph and subdivides into waypoints."""
        start_node = self._nearest_graph_node(origin)
        end_node = self._nearest_graph_node(destination)

        _, path_nodes = self.graph.a_star(
            start_node, end_node, is_peak_hour=self.is_peak_hour
        )

        # Build coarse polyline: origin -> district nodes -> destination
        coarse_points: List[Tuple[float, float]] = [origin]
        for nid in path_nodes:
            node = self.graph.nodes[nid]
            node_coord = (node.x, node.y)
            if self._haversine_km(coarse_points[-1], node_coord) > 0.05:
                coarse_points.append(node_coord)
        if self._haversine_km(coarse_points[-1], destination) > 0.01:
            coarse_points.append(destination)

        # Interpolate fine-grained waypoints for smooth step-by-step movement
        waypoints: List[Tuple[float, float]] = []
        for i in range(len(coarse_points) - 1):
            p1 = coarse_points[i]
            p2 = coarse_points[i + 1]
            leg_km = self._haversine_km(p1, p2)
            num_steps = max(1, int(math.ceil(leg_km / segment_resolution_km)))
            for s in range(1, num_steps + 1):
                ratio = s / float(num_steps)
                lat = p1[0] + ratio * (p2[0] - p1[0])
                lon = p1[1] + ratio * (p2[1] - p1[1])
                waypoints.append((lat, lon))

        return waypoints if waypoints else [destination]

    # -------------------------------------------------------------------------
    # EMERGENCY CALL INGESTION & AI TRIAGE
    # -------------------------------------------------------------------------

    @staticmethod
    def _fallback_triage(patient_notes: str) -> TriageSchema:
        """Deterministic fallback classifier if local Ollama server is unavailable."""
        text = patient_notes.lower()
        if any(w in text for w in ("cardiac", "chest pain", "unconscious", "stroke", "arrest")):
            return TriageSchema(
                triage_level=1,
                equipment_needed="ICU",
                clinical_summary="Critical presentation requiring immediate ICU intervention.",
            )
        if any(w in text for w in ("shortness of breath", "seizure", "trauma", "hemorrhage")):
            return TriageSchema(
                triage_level=2,
                equipment_needed="ICU",
                clinical_summary="High-acuity emergency requiring advanced life support.",
            )
        if any(w in text for w in ("fracture", "abdominal", "burn", "laceration")):
            return TriageSchema(
                triage_level=3,
                equipment_needed="Basic",
                clinical_summary="Urgent condition suitable for Basic ambulance transport.",
            )
        return TriageSchema(
            triage_level=4,
            equipment_needed="Basic",
            clinical_summary="Non-critical presentation routed to standard ER care.",
        )

    def ingest_call(
        self,
        caller_coords: Tuple[float, float],
        patient_notes: str,
        use_llm: bool = True,
        triage_override: Optional[TriageSchema] = None,
    ) -> EmergencyCall:
        """Triages an incoming emergency call and pushes it into the PriorityMinHeap."""
        ingest_start = time.perf_counter()
        self._call_counter += 1
        call_id = f"CALL-{self._call_counter:04d}"

        fallback_used = False
        if triage_override is not None:
            triage_result = triage_override
        elif use_llm:
            try:
                triage_result, meta = query_triage_with_meta(
                    patient_notes=patient_notes,
                    host=self.ollama_host,
                    model=self.ollama_model,
                )
                fallback_used = bool(meta.get("fallback_used", False))
            except Exception:
                triage_result = self._fallback_triage(patient_notes)
                fallback_used = True
        else:
            triage_result = self._fallback_triage(patient_notes)
            fallback_used = True

        call = EmergencyCall(
            call_id=call_id,
            caller_coords=caller_coords,
            patient_notes=patient_notes,
            triage=triage_result,
            arrival_time=self.current_time_seconds,
            fallback_used=fallback_used,
        )
        self.calls[call_id] = call

        patient = Patient(
            patient_id=call_id,
            triage_level=triage_result.triage_level,
            arrival_time=self.current_time_seconds,
        )
        self.priority_queue.push(patient, current_time=self.current_time_seconds)

        triage_latency_ms = round((time.perf_counter() - ingest_start) * 1000.0, 3)
        call.triage_latency_ms = triage_latency_ms
        self._log_event(
            {
                "event": "CALL_INGESTED",
                "event_type": "CALL_INGESTED",
                "call_id": call_id,
                "triage_level": triage_result.triage_level,
                "equipment_needed": triage_result.equipment_needed,
                "triage_latency_ms": triage_latency_ms,
            }
        )
        return call

    # -------------------------------------------------------------------------
    # DISPATCH & FLEET MOVEMENT EXECUTION
    # -------------------------------------------------------------------------

    def _dispatch_queued_calls(self) -> List[Dict[str, Any]]:
        """Matches highest-priority queued calls with nearest idle matching ambulances
        and optimal hospitals.
        """
        dispatched_events: List[Dict[str, Any]] = []
        deferred_patients: List[Patient] = []

        while not self.priority_queue.is_empty():
            dispatch_start = time.perf_counter()
            patient = self.priority_queue.pop_min()
            if patient is None:
                break

            call = self.calls[patient.patient_id]
            eq_needed = call.triage.equipment_needed
            kd_tree = self.kd_trees.get(eq_needed)

            # 1. Query 2D KD-Tree for nearest IDLE ambulance with matching equipment
            if kd_tree is None:
                deferred_patients.append(patient)
                continue

            nearest_results = kd_tree.find_nearest_k_idle(call.caller_coords, k=1)
            if not nearest_results:
                deferred_patients.append(patient)
                continue

            _, kd_amb = nearest_results[0]
            ambulance = self.fleet[kd_amb.id]

            # 2. Query HospitalManager for optimal receiving hospital with matching bed
            optimal_hosp = self.hospital_manager.find_optimal_hospital(
                caller_coords=call.caller_coords,
                equipment_needed=eq_needed,
                graph=self.graph,
                is_peak_hour=self.is_peak_hour,
            )
            if optimal_hosp is None:
                deferred_patients.append(patient)
                continue

            # 3. Reserve hospital bed and assign ambulance
            hospital_id = optimal_hosp["hospital_id"]
            if not self.hospital_manager.reserve_bed(hospital_id, eq_needed):
                deferred_patients.append(patient)
                continue

            # Compute route from ambulance's current position to caller
            to_caller_waypoints = self._compute_route_waypoints(
                origin=ambulance.coords,
                destination=call.caller_coords,
            )

            ambulance.state = AmbulanceState.EN_ROUTE_TO_CALLER
            ambulance.assigned_call_id = call.call_id
            ambulance.target_hospital_id = hospital_id
            ambulance.target_hospital_coords = tuple(optimal_hosp["coords"])
            ambulance.waypoints = to_caller_waypoints
            ambulance.sync_kd_entity()

            call.status = "DISPATCHED"
            call.assigned_amb_id = ambulance.amb_id
            call.assigned_hospital_id = hospital_id
            call.dispatch_time = self.current_time_seconds

            # Rebuild KD-Tree for this equipment tier so unit isn't double-assigned
            self._rebuild_kd_trees()

            wait_time_seconds = round(self.current_time_seconds - call.arrival_time, 3)
            dispatch_latency_ms = round((time.perf_counter() - dispatch_start) * 1000.0, 3)

            event_payload = {
                "event": "CALL_DISPATCHED",
                "event_type": "CALL_DISPATCHED",
                "call_id": call.call_id,
                "ambulance_id": ambulance.amb_id,
                "equipment": eq_needed,
                "triage_level": call.triage.triage_level,
                "hospital_id": hospital_id,
                "hospital_name": optimal_hosp["name"],
                "queue_wait_time": wait_time_seconds,
                "queue_wait_time_seconds": wait_time_seconds,
                "wait_time_seconds": wait_time_seconds,
                "dispatch_latency": dispatch_latency_ms,
                "dispatch_latency_ms": dispatch_latency_ms,
                "latency_ms": dispatch_latency_ms,
            }
            self._log_event(event_payload)

            dispatched_events.append(
                {
                    "call_id": call.call_id,
                    "ambulance_id": ambulance.amb_id,
                    "equipment": eq_needed,
                    "triage_level": call.triage.triage_level,
                    "hospital_id": hospital_id,
                    "hospital_name": optimal_hosp["name"],
                }
            )

        # Re-queue any calls that could not be dispatched due to resource constraints
        for deferred in deferred_patients:
            self.priority_queue.push(deferred, current_time=self.current_time_seconds)

        return dispatched_events

    def _advance_ambulance(self, amb: FleetAmbulance, time_delta: float) -> Optional[str]:
        """Moves an active ambulance along its waypoints for `time_delta` seconds.
        Returns a transition description if a state change occurs.
        """
        if amb.state == AmbulanceState.IDLE or not amb.waypoints:
            return None

        # Reduce effective travel speed during peak traffic hours
        traffic_factor = 1.6 if self.is_peak_hour else 1.0
        effective_speed_kmh = amb.base_speed_kmh / traffic_factor
        remaining_distance_km = effective_speed_kmh * (time_delta / 3600.0)

        while remaining_distance_km > 0.0 and amb.waypoints:
            next_wp = amb.waypoints[0]
            dist_to_wp = self._haversine_km(amb.coords, next_wp)

            if dist_to_wp <= remaining_distance_km:
                amb.coords = next_wp
                amb.waypoints.pop(0)
                remaining_distance_km -= dist_to_wp
            else:
                ratio = remaining_distance_km / dist_to_wp
                lat = amb.coords[0] + ratio * (next_wp[0] - amb.coords[0])
                lon = amb.coords[1] + ratio * (next_wp[1] - amb.coords[1])
                amb.coords = (lat, lon)
                remaining_distance_km = 0.0

        amb.sync_kd_entity()

        # Check if current route leg completed -> handle state machine transition
        if not amb.waypoints:
            return self._handle_arrival_transition(amb)

        return None

    def _handle_arrival_transition(self, amb: FleetAmbulance) -> str:
        """Transitions ambulance state when reaching the end of a route leg."""
        if amb.state == AmbulanceState.EN_ROUTE_TO_CALLER:
            assert amb.assigned_call_id is not None
            assert amb.target_hospital_coords is not None

            call = self.calls[amb.assigned_call_id]
            call.status = "IN_TRANSIT"

            amb.state = AmbulanceState.TRANSPORTING_TO_HOSPITAL
            amb.waypoints = self._compute_route_waypoints(
                origin=amb.coords,
                destination=amb.target_hospital_coords,
            )
            amb.sync_kd_entity()
            msg = f"{amb.amb_id} picked up {call.call_id} -> TRANSPORTING_TO_HOSPITAL ({amb.target_hospital_id})"
            self._log_event(
                {
                    "event": "AMBULANCE_TRANSITION",
                    "event_type": "AMBULANCE_TRANSITION",
                    "ambulance_id": amb.amb_id,
                    "call_id": call.call_id,
                    "new_state": amb.state.value,
                    "details": msg,
                }
            )
            return msg

        if amb.state == AmbulanceState.TRANSPORTING_TO_HOSPITAL:
            assert amb.assigned_call_id is not None
            assert amb.target_hospital_id is not None

            call = self.calls[amb.assigned_call_id]
            call.status = "COMPLETED"
            call.completion_time = self.current_time_seconds

            # Schedule patient discharge / bed release
            self.active_admissions.append(
                ActiveAdmission(
                    hospital_id=amb.target_hospital_id,
                    bed_type=call.triage.equipment_needed,
                    discharge_time=self.current_time_seconds + self.bed_recovery_seconds,
                )
            )

            amb.state = AmbulanceState.RETURNING
            amb.waypoints = self._compute_route_waypoints(
                origin=amb.coords,
                destination=amb.home_coords,
            )
            amb.sync_kd_entity()
            msg = f"{amb.amb_id} delivered {call.call_id} to {amb.target_hospital_id} -> RETURNING"
            self._log_event(
                {
                    "event": "AMBULANCE_TRANSITION",
                    "event_type": "AMBULANCE_TRANSITION",
                    "ambulance_id": amb.amb_id,
                    "call_id": call.call_id,
                    "new_state": amb.state.value,
                    "details": msg,
                }
            )
            return msg

        if amb.state == AmbulanceState.RETURNING:
            amb.state = AmbulanceState.IDLE
            amb.assigned_call_id = None
            amb.target_hospital_id = None
            amb.target_hospital_coords = None
            amb.waypoints = []
            amb.sync_kd_entity()
            msg = f"{amb.amb_id} returned to base -> IDLE"
            self._log_event(
                {
                    "event": "AMBULANCE_TRANSITION",
                    "event_type": "AMBULANCE_TRANSITION",
                    "ambulance_id": amb.amb_id,
                    "new_state": amb.state.value,
                    "details": msg,
                }
            )
            return msg

        return ""

    def _process_bed_discharges(self) -> int:
        """Releases hospital beds for patients whose recovery duration has elapsed."""
        still_admitted: List[ActiveAdmission] = []
        released_count = 0

        for admission in self.active_admissions:
            if self.current_time_seconds >= admission.discharge_time:
                self.hospital_manager.release_bed(
                    admission.hospital_id, admission.bed_type
                )
                released_count += 1
            else:
                still_admitted.append(admission)

        self.active_admissions = still_admitted
        return released_count

    # -------------------------------------------------------------------------
    # MAIN SIMULATION STEP
    # -------------------------------------------------------------------------

    def step(self, time_delta: float = 60.0) -> Dict[str, Any]:
        """Advances the simulation by `time_delta` seconds.

        1. Updates simulation clock & dynamic peak traffic road edge weights.
        2. Processes hospital bed discharges.
        3. Moves active ambulances along route waypoints and transitions states.
        4. Updates Min-Heap call priorities using the aging formula.
        5. Dispatches queued calls using 2D KD-Tree + HospitalManager.
        """
        if time_delta <= 0:
            raise ValueError("time_delta must be positive.")

        prev_peak = self.is_peak_hour
        self.current_time_seconds += time_delta
        self._update_road_network_weights()
        traffic_regime_changed = prev_peak != self.is_peak_hour

        # Release beds for discharged patients
        beds_released = self._process_bed_discharges()

        # Advance fleet positions and collect state transitions
        transitions: List[str] = []
        for amb in self.fleet.values():
            event = self._advance_ambulance(amb, time_delta)
            if event:
                transitions.append(event)

        # Refresh spatial KD-Trees after movement and IDLE transitions
        self._rebuild_kd_trees()

        # Update Min-Heap priorities via aging formula: (TriageLevel * w1) - (WaitTime * w2)
        self.priority_queue.update_all_priorities(self.current_time_seconds)

        # Dispatch waiting emergency calls
        dispatches = self._dispatch_queued_calls()

        state_counts = {state.value: 0 for state in AmbulanceState}
        for amb in self.fleet.values():
            state_counts[amb.state.value] += 1

        return {
            "clock": self.get_formatted_time(),
            "is_peak_hour": self.is_peak_hour,
            "traffic_regime_changed": traffic_regime_changed,
            "queued_calls": len(self.priority_queue.heap),
            "dispatches": dispatches,
            "transitions": transitions,
            "beds_released": beds_released,
            "fleet_states": state_counts,
        }


if __name__ == "__main__":
    # Start simulation at 07:55 AM to demonstrate transition into 08:00 AM peak traffic
    sim = EMSSimulator(start_hour=7 + 55 / 60)

    # Ingest two emergency calls (offline keyword fallback enabled if Ollama isn't running)
    c1 = sim.ingest_call(
        caller_coords=(24.8697, 67.0656),  # PECHS
        patient_notes="62yo male with crushing chest pain and cardiac arrest signs.",
        use_llm=False,
    )
    c2 = sim.ingest_call(
        caller_coords=(24.8138, 67.0315),  # Clifton
        patient_notes="28yo cyclist with suspected forearm fracture and minor laceration.",
        use_llm=False,
    )
    print(f"[{sim.get_formatted_time()}] Ingested {c1.call_id} ({c1.triage.equipment_needed}) & {c2.call_id} ({c2.triage.equipment_needed})")

    # Run 25 simulation steps of 60 seconds each (07:55 AM -> 08:20 AM)
    for tick in range(1, 26):
        summary = sim.step(time_delta=60.0)
        if summary["traffic_regime_changed"]:
            print(f"\n>>> [{summary['clock']}] TRAFFIC ALERT: Entered Peak Hour (Edge weights scaled!) <<<\n")
        for d in summary["dispatches"]:
            print(
                f"[{summary['clock']}] DISPATCH: {d['call_id']} -> {d['ambulance_id']} "
                f"({d['equipment']}) -> {d['hospital_name']}"
            )
        for t in summary["transitions"]:
            print(f"[{summary['clock']}] TRANSITION: {t}")