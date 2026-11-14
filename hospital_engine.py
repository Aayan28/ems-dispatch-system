"""
hospital_engine.py
Hospital capacity tracking, bed reservation management, and optimal facility routing
for the Karachi EMS Dispatch System.
"""

import math
from dataclasses import dataclass, field
from typing import Any, Dict, List, Literal, Optional, Tuple

from data_structures.graph import Graph

BedCategory = Literal["ICU", "Basic", "ICU_beds", "ER_beds", "ER"]


@dataclass
class BedPool:
    total: int
    available: int

    def __post_init__(self) -> None:
        if self.available < 0 or self.available > self.total:
            raise ValueError(
                f"Invalid bed count: available ({self.available}) must be between 0 and total ({self.total})."
            )

    @property
    def occupancy_rate(self) -> float:
        return 1.0 - (self.available / self.total) if self.total > 0 else 1.0


@dataclass
class HospitalRecord:
    hospital_id: str
    name: str
    district: str
    coords: Tuple[float, float]
    ER_beds: BedPool
    ICU_beds: BedPool
    specialties: List[str] = field(default_factory=list)


DEFAULT_KARACHI_HOSPITALS: List[Dict[str, Any]] = [
    {
        "hospital_id": "HOSP-001",
        "name": "Aga Khan University Hospital (AKUH)",
        "district": "Gulshan-e-Iqbal / Stadium Road",
        "coords": (24.8918, 67.0746),
        "ER_beds": {"total": 65, "available": 14},
        "ICU_beds": {"total": 45, "available": 6},
        "specialties": ["Trauma", "Cardiac", "Neuro"],
    },
    {
        "hospital_id": "HOSP-002",
        "name": "Dr. Ruth K. Pfau Civil Hospital Karachi",
        "district": "Saddar",
        "coords": (24.8580, 67.0117),
        "ER_beds": {"total": 110, "available": 18},
        "ICU_beds": {"total": 60, "available": 4},
        "specialties": ["Trauma", "Burns"],
    },
    {
        "hospital_id": "HOSP-003",
        "name": "The Indus Hospital",
        "district": "Korangi",
        "coords": (24.8197, 67.1188),
        "ER_beds": {"total": 80, "available": 12},
        "ICU_beds": {"total": 40, "available": 5},
        "specialties": ["Trauma", "General"],
    },
    {
        "hospital_id": "HOSP-004",
        "name": "Liaquat National Hospital (LNH)",
        "district": "Stadium Road",
        "coords": (24.8872, 67.0694),
        "ER_beds": {"total": 70, "available": 20},
        "ICU_beds": {"total": 35, "available": 8},
        "specialties": ["Trauma", "Neuro"],
    },
    {
        "hospital_id": "HOSP-005",
        "name": "Jinnah Postgraduate Medical Centre (JPMC)",
        "district": "Cantonment / Saddar",
        "coords": (24.8530, 67.0392),
        "ER_beds": {"total": 120, "available": 22},
        "ICU_beds": {"total": 55, "available": 7},
        "specialties": ["Trauma", "Neuro"],
    },
    {
        "hospital_id": "HOSP-006",
        "name": "National Institute of Cardiovascular Diseases (NICVD)",
        "district": "Cantonment",
        "coords": (24.8528, 67.0343),
        "ER_beds": {"total": 60, "available": 15},
        "ICU_beds": {"total": 50, "available": 11},
        "specialties": ["Cardiac"],
    },
    {
        "hospital_id": "HOSP-007",
        "name": "Ziauddin Hospital (Clifton Campus)",
        "district": "Clifton",
        "coords": (24.8166, 67.0279),
        "ER_beds": {"total": 40, "available": 11},
        "ICU_beds": {"total": 25, "available": 5},
        "specialties": ["General", "Cardiac"],
    },
    {
        "hospital_id": "HOSP-008",
        "name": "Patel Hospital",
        "district": "Gulshan-e-Iqbal Block 4",
        "coords": (24.9213, 67.0984),
        "ER_beds": {"total": 45, "available": 16},
        "ICU_beds": {"total": 20, "available": 4},
        "specialties": ["General"],
    },
    {
        "hospital_id": "HOSP-009",
        "name": "Ziauddin Hospital (North Nazimabad)",
        "district": "North Nazimabad",
        "coords": (24.9398, 67.0366),
        "ER_beds": {"total": 55, "available": 19},
        "ICU_beds": {"total": 30, "available": 9},
        "specialties": ["Trauma", "General"],
    },
    {
        "hospital_id": "HOSP-010",
        "name": "South City Hospital",
        "district": "Clifton Block 3",
        "coords": (24.8252, 67.0335),
        "ER_beds": {"total": 35, "available": 9},
        "ICU_beds": {"total": 20, "available": 3},
        "specialties": ["General", "Orthopedic"],
    },
]


class HospitalManager:
    """Manages hospital bed inventory and selects optimal receiving hospitals."""

    def __init__(
        self,
        hospitals_data: Optional[List[Dict[str, Any]]] = None,
        avg_ambulance_speed_kmh: float = 45.0,
        capacity_penalty_weight: float = 15.0,
    ) -> None:
        self.avg_ambulance_speed_kmh = avg_ambulance_speed_kmh
        self.capacity_penalty_weight = capacity_penalty_weight
        self.hospitals: Dict[str, HospitalRecord] = {}

        source = hospitals_data if hospitals_data is not None else DEFAULT_KARACHI_HOSPITALS
        for item in source:
            h_id = item["hospital_id"]
            self.hospitals[h_id] = HospitalRecord(
                hospital_id=h_id,
                name=item["name"],
                district=item["district"],
                coords=tuple(item["coords"]),
                ER_beds=BedPool(
                    total=item["ER_beds"]["total"],
                    available=item["ER_beds"]["available"],
                ),
                ICU_beds=BedPool(
                    total=item["ICU_beds"]["total"],
                    available=item["ICU_beds"]["available"],
                ),
                specialties=item.get("specialties", []),
            )

    @staticmethod
    def _normalize_bed_type(bed_type: str) -> Literal["ICU_beds", "ER_beds"]:
        """Maps triage equipment labels ('ICU', 'Basic') or bed keys to canonical pool names."""
        normalized = bed_type.strip().upper()
        if normalized in {"ICU", "ICU_BEDS"}:
            return "ICU_beds"
        if normalized in {"BASIC", "ER", "ER_BEDS"}:
            return "ER_beds"
        raise ValueError(
            f"Unsupported bed_type '{bed_type}'. Expected 'ICU', 'Basic', 'ICU_beds', or 'ER_beds'."
        )

    @staticmethod
    def _haversine_km(coord1: Tuple[float, float], coord2: Tuple[float, float]) -> float:
        """Computes great-circle distance in kilometers between two (lat, lon) pairs."""
        earth_radius_km = 6371.0
        lat1, lon1 = math.radians(coord1[0]), math.radians(coord1[1])
        lat2, lon2 = math.radians(coord2[0]), math.radians(coord2[1])

        dlat = lat2 - lat1
        dlon = lon2 - lon1
        a = (
            math.sin(dlat / 2.0) ** 2
            + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2.0) ** 2
        )
        return 2.0 * earth_radius_km * math.asin(math.sqrt(a))

    def _nearest_graph_node(
        self, coords: Tuple[float, float], graph: Graph
    ) -> Tuple[str, float]:
        """Finds the closest node in `graph` to `coords` and returns (node_id, access_distance_km)."""
        if not graph.nodes:
            raise ValueError("Routing graph contains no nodes.")

        best_node_id = ""
        min_dist_km = float("inf")
        for node_id, node in graph.nodes.items():
            dist_km = self._haversine_km(coords, (node.x, node.y))
            if dist_km < min_dist_km:
                min_dist_km = dist_km
                best_node_id = node_id

        return best_node_id, min_dist_km

    def _compute_capacity_penalty(self, bed_pool: BedPool) -> float:
        """Calculates congestion penalty (in equivalent minutes) based on bed occupancy."""
        # Quadratic occupancy curve penalizes near-full facilities to prevent overload
        base_penalty = self.capacity_penalty_weight * (bed_pool.occupancy_rate ** 2)
        scarcity_surcharge = 5.0 if bed_pool.available == 1 else 0.0
        return base_penalty + scarcity_surcharge

    def find_optimal_hospital(
        self,
        caller_coords: Tuple[float, float],
        equipment_needed: str,
        graph: Graph,
        is_peak_hour: bool = False,
    ) -> Optional[Dict[str, Any]]:
        """Selects the best hospital with an available matching bed minimizing:
        Total Cost = Travel Time (mins) + Capacity Penalty (mins).

        Returns None if no hospital has available beds of the requested type.
        """
        pool_key = self._normalize_bed_type(equipment_needed)

        # 1. Filter hospitals with at least 1 available matching bed
        eligible_hospitals = [
            hosp
            for hosp in self.hospitals.values()
            if getattr(hosp, pool_key).available > 0
        ]

        if not eligible_hospitals:
            return None

        start_node, caller_access_km = self._nearest_graph_node(caller_coords, graph)
        peak_access_factor = 1.3 if is_peak_hour else 1.0

        best_selection: Optional[Dict[str, Any]] = None
        lowest_total_score = float("inf")

        for hosp in eligible_hospitals:
            end_node, hosp_access_km = self._nearest_graph_node(hosp.coords, graph)

            # 2. Compute shortest weighted road distance via graph.py (A*)
            arterial_weighted_km, route_nodes = graph.a_star(
                start_node, end_node, is_peak_hour=is_peak_hour
            )

            # Handle disconnected graph components gracefully
            if math.isinf(arterial_weighted_km):
                continue

            total_effective_km = (
                (caller_access_km * peak_access_factor)
                + arterial_weighted_km
                + (hosp_access_km * peak_access_factor)
            )
            travel_time_mins = (total_effective_km / self.avg_ambulance_speed_kmh) * 60.0

            # 3. Compute capacity penalty and total objective score
            bed_pool: BedPool = getattr(hosp, pool_key)
            capacity_penalty = self._compute_capacity_penalty(bed_pool)
            total_score = travel_time_mins + capacity_penalty

            if total_score < lowest_total_score:
                lowest_total_score = total_score
                best_selection = {
                    "hospital_id": hosp.hospital_id,
                    "name": hosp.name,
                    "district": hosp.district,
                    "coords": hosp.coords,
                    "bed_pool": pool_key,
                    "available_beds": bed_pool.available,
                    "total_beds": bed_pool.total,
                    "route_nodes": route_nodes,
                    "effective_distance_km": round(total_effective_km, 2),
                    "travel_time_mins": round(travel_time_mins, 2),
                    "capacity_penalty": round(capacity_penalty, 2),
                    "total_score": round(total_score, 2),
                }

        return best_selection

    def reserve_bed(self, hospital_id: str, bed_type: str) -> bool:
        """Decrements available bed count for a hospital upon ambulance dispatch.
        Returns True if reserved, False if no beds remain.
        """
        if hospital_id not in self.hospitals:
            raise KeyError(f"Unknown hospital_id: '{hospital_id}'.")

        pool_key = self._normalize_bed_type(bed_type)
        bed_pool: BedPool = getattr(self.hospitals[hospital_id], pool_key)

        if bed_pool.available <= 0:
            return False

        bed_pool.available -= 1
        return True

    def release_bed(self, hospital_id: str, bed_type: str) -> bool:
        """Increments available bed count when a patient is discharged or transferred.
        Returns True if released, False if pool is already at full capacity.
        """
        if hospital_id not in self.hospitals:
            raise KeyError(f"Unknown hospital_id: '{hospital_id}'.")

        pool_key = self._normalize_bed_type(bed_type)
        bed_pool: BedPool = getattr(self.hospitals[hospital_id], pool_key)

        if bed_pool.available >= bed_pool.total:
            return False

        bed_pool.available += 1
        return True

    def get_capacity_summary(self) -> List[Dict[str, Any]]:
        """Returns current ER and ICU availability across all registered hospitals."""
        return [
            {
                "hospital_id": h.hospital_id,
                "name": h.name,
                "ER_available": f"{h.ER_beds.available}/{h.ER_beds.total}",
                "ICU_available": f"{h.ICU_beds.available}/{h.ICU_beds.total}",
            }
            for h in self.hospitals.values()
        ]


if __name__ == "__main__":
    from karachi_geo_data import KARACHI_GEO_DATA

    # Build district routing graph from karachi_geo_data.py
    city_graph = Graph()
    graph_spec = KARACHI_GEO_DATA["district_road_graph"]
    for node_id, node_info in graph_spec["nodes"].items():
        city_graph.add_node(node_id, node_info["coords"][0], node_info["coords"][1])
    for edge in graph_spec["edges"]:
        city_graph.add_edge(
            edge["u"],
            edge["v"],
            distance=edge["distance_km"],
            peak_multiplier=edge["peak_multiplier"],
        )

    manager = HospitalManager()

    # Example: Critical ICU emergency near PECHS / Nursery
    incident_coords = (24.8697, 67.0656)
    best_icu = manager.find_optimal_hospital(
        caller_coords=incident_coords,
        equipment_needed="ICU",
        graph=city_graph,
        is_peak_hour=True,
    )

    if best_icu:
        print("Optimal ICU Hospital Selected:")
        print(
            f" -> {best_icu['name']} ({best_icu['hospital_id']}) | "
            f"Travel: {best_icu['travel_time_mins']}m + Penalty: {best_icu['capacity_penalty']}m = "
            f"Score: {best_icu['total_score']} | Route: {best_icu['route_nodes']}"
        )

        # Reserve and later release the ICU bed
        reserved = manager.reserve_bed(best_icu["hospital_id"], "ICU")
        print(f"Bed Reserved: {reserved}")

        released = manager.release_bed(best_icu["hospital_id"], "ICU")
        print(f"Bed Released: {released}")