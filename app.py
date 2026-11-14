"""
app.py - Karachi Emergency Medical Service (EMS) Command & Simulation Dashboard
Wires EMSSimulator, AI Triage Agent, 2D KD-Tree Dispatch, Priority Min-Heap,
HospitalManager, and live structured dispatch logging into Streamlit + Folium.
"""

import json
import os
import time
from typing import Any, Dict, List
import folium
import streamlit as st
from streamlit_folium import st_folium

from simulation_engine import AmbulanceState, EMSSimulator

OLLAMA_HOST = os.getenv("OLLAMA_HOST", "http://localhost:11434")
DISPATCH_LOG_PATH = "dispatch_events.log"

PRESET_CALLER_LOCATIONS: Dict[str, tuple[float, float]] = {
    "PECHS / Shahrah-e-Faisal": (24.8697, 67.0656),
    "Clifton Block 4": (24.8138, 67.0315),
    "Saddar Downtown": (24.8560, 67.0180),
    "Gulshan-e-Iqbal Block 13": (24.9180, 67.0970),
    "Korangi Industrial Area": (24.8280, 67.1150),
    "North Nazimabad Block H": (24.9350, 67.0370),
    "DHA Phase 5": (24.8050, 67.0620),
    "Gulistan-e-Johar": (24.9120, 67.1310),
}

AMBULANCE_STATE_STYLES: Dict[AmbulanceState, Dict[str, str]] = {
    AmbulanceState.IDLE: {"color": "blue", "label": "IDLE (Available)", "route_color": "#2A80B9"},
    AmbulanceState.EN_ROUTE_TO_CALLER: {
        "color": "darkblue",
        "label": "EN_ROUTE_TO_CALLER",
        "route_color": "#E67E22",
    },
    AmbulanceState.TRANSPORTING_TO_HOSPITAL: {
        "color": "purple",
        "label": "TRANSPORTING_TO_HOSPITAL",
        "route_color": "#C0392B",
    },
    AmbulanceState.RETURNING: {
        "color": "cadetblue",
        "label": "RETURNING",
        "route_color": "#27AE60",
    },
}


# =============================================================================
# HELPER FUNCTIONS: LOGS & METRICS
# =============================================================================


def load_recent_dispatch_logs(log_path: str, limit: int = 25) -> List[Dict[str, Any]]:
    """Reads the most recent structured JSON events from `dispatch_events.log`."""
    if not os.path.exists(log_path):
        return []

    records: List[Dict[str, Any]] = []
    try:
        with open(log_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    records.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    except OSError:
        return []

    return list(reversed(records[-limit:]))


def compute_wait_and_latency_metrics(sim: EMSSimulator) -> Dict[str, float]:
    """Computes average queue wait time (seconds) and dispatch latency (ms)."""
    wait_times_sec: List[float] = []
    latencies_ms: List[float] = []

    for call in sim.calls.values():
        latencies_ms.append(call.triage_latency_ms)
        if call.dispatch_time is not None:
            wait_times_sec.append(max(0.0, call.dispatch_time - call.arrival_time))
        elif call.status == "QUEUED":
            wait_times_sec.append(max(0.0, sim.current_time_seconds - call.arrival_time))

    avg_wait_sec = sum(wait_times_sec) / len(wait_times_sec) if wait_times_sec else 0.0
    avg_latency_ms = sum(latencies_ms) / len(latencies_ms) if latencies_ms else 0.0
    return {
        "avg_wait_sec": avg_wait_sec,
        "avg_latency_ms": avg_latency_ms,
    }


def reset_simulation() -> None:
    """Closes active log handlers, clears log file, and re-initializes EMSSimulator."""
    if "simulator" in st.session_state:
        old_sim: EMSSimulator = st.session_state.simulator
        for handler in list(old_sim.event_logger.handlers):
            handler.flush()
            handler.close()
            old_sim.event_logger.removeHandler(handler)

    if os.path.exists(DISPATCH_LOG_PATH):
        try:
            with open(DISPATCH_LOG_PATH, "w", encoding="utf-8"):
                pass
        except OSError:
            pass

    st.session_state.simulator = EMSSimulator(
        start_hour=7 + 55 / 60,  # 07:55 AM (transitions into 08:00 AM peak traffic)
        ollama_host=OLLAMA_HOST,
        log_file=DISPATCH_LOG_PATH,
    )
    st.session_state.is_playing = False
    st.session_state.last_step_summary = None


# =============================================================================
# STREAMLIT PAGE & SESSION STATE INITIALIZATION
# =============================================================================

st.set_page_config(
    page_title="Karachi EMS AI Triage & Dispatch",
    page_icon="🚑",
    layout="wide",
)

if "simulator" not in st.session_state:
    st.session_state.simulator = EMSSimulator(
        start_hour=7 + 55 / 60,
        ollama_host=OLLAMA_HOST,
        log_file=DISPATCH_LOG_PATH,
    )

if "is_playing" not in st.session_state:
    st.session_state.is_playing = False

if "time_step_sec" not in st.session_state:
    st.session_state.time_step_sec = 30

if "last_step_summary" not in st.session_state:
    st.session_state.last_step_summary = None

sim: EMSSimulator = st.session_state.simulator


# =============================================================================
# SIDEBAR: CALL SUBMISSION, SIMULATION CONTROLS, METRICS & LIVE LOGS
# =============================================================================

st.sidebar.title("🚨 EMS Dispatch Console")

# 1. Emergency Call Submission Form
st.sidebar.subheader("1. Incoming Emergency Call")

selected_preset = st.sidebar.selectbox(
    "Karachi District Preset",
    options=list(PRESET_CALLER_LOCATIONS.keys()),
)
preset_lat, preset_lon = PRESET_CALLER_LOCATIONS[selected_preset]

with st.sidebar.form("emergency_call_form", clear_on_submit=False):
    patient_notes = st.text_area(
        "Caller Symptoms / Clinical Notes",
        value="58yo male experiencing severe chest pain and shortness of breath.",
        height=75,
    )
    c_lat, c_lon = st.columns(2)
    caller_lat = c_lat.number_input("Latitude", value=preset_lat, format="%.4f")
    caller_lon = c_lon.number_input("Longitude", value=preset_lon, format="%.4f")
    use_llm = st.checkbox("Use Ollama AI Triage (with keyword fallback)", value=True)

    submitted_call = st.form_submit_button(
        "📞 Ingest & Triage Call",
        type="primary",
        use_container_width=True,
    )

if submitted_call:
    if not patient_notes.strip():
        st.sidebar.warning("Please enter symptom notes before submitting a call.")
    else:
        with st.spinner("Running AI Triage & queuing emergency call..."):
            ingested = sim.ingest_call(
                caller_coords=(float(caller_lat), float(caller_lon)),
                patient_notes=patient_notes.strip(),
                use_llm=use_llm,
            )
            # Advance 1 second so the newly queued call dispatches immediately if a unit is idle
            st.session_state.last_step_summary = sim.step(time_delta=1.0)

        mode_tag = "Keyword Fallback" if ingested.fallback_used else "Ollama LLM"
        st.sidebar.success(
            f"**{ingested.call_id}** | Triage **L{ingested.triage.triage_level}** "
            f"({ingested.triage.equipment_needed}) via {mode_tag}"
        )

st.sidebar.markdown("---")

# 2. Simulation Playback & Time-Step Controls
st.sidebar.subheader("2. Simulation Controls")

time_step_sec = st.sidebar.slider(
    "Time-Step Delta (seconds / tick)",
    min_value=10,
    max_value=300,
    value=st.session_state.time_step_sec,
    step=10,
)
st.session_state.time_step_sec = time_step_sec

ctrl_col1, ctrl_col2, ctrl_col3 = st.sidebar.columns(3)
if ctrl_col1.button("▶️ Play", use_container_width=True):
    st.session_state.is_playing = True
if ctrl_col2.button("⏸️ Pause", use_container_width=True):
    st.session_state.is_playing = False
if ctrl_col3.button("⏭️ Step", use_container_width=True):
    st.session_state.is_playing = False
    st.session_state.last_step_summary = sim.step(time_delta=float(time_step_sec))

if st.sidebar.button("🔄 Reset Simulation", use_container_width=True):
    reset_simulation()
    st.rerun()

st.sidebar.markdown("---")

# 3. Live Wait-Time Metrics & Dispatch Event Log Feed
st.sidebar.subheader("3. Live Dispatch Telemetry & Logs")

metrics = compute_wait_and_latency_metrics(sim)
m_col1, m_col2 = st.sidebar.columns(2)
m_col1.metric("Avg Queue Wait", f"{metrics['avg_wait_sec']:.1f}s")
m_col2.metric("Avg Triage/Dispatch", f"{metrics['avg_latency_ms']:.1f}ms")

recent_logs = load_recent_dispatch_logs(DISPATCH_LOG_PATH, limit=15)
if recent_logs:
    with st.sidebar.container(height=270):
        for entry in recent_logs:
            ev_type = entry.get("event_type", "EVENT")
            clock = entry.get("sim_clock", "--:--:--")
            call_id = entry.get("call_id", "")
            t_lvl = entry.get("triage_level", "-")
            wait_s = entry.get("queue_wait_time", 0.0)
            lat_ms = entry.get("dispatch_latency", 0.0)
            msg = entry.get("message", "")

            badge = "🟡" if ev_type == "CALL_TRIAGED" else ("🚑" if ev_type == "CALL_DISPATCHED" else "✅")
            st.markdown(
                f"{badge} **`[{clock}]` {ev_type}** (`{call_id}` | L{t_lvl})  \n"
                f"<small>{msg}<br>Wait: `{wait_s}s` | Latency: `{lat_ms}ms`</small>",
                unsafe_allow_html=True,
            )
            st.divider()
else:
    st.sidebar.caption("No dispatch events logged yet. Ingest a call to begin.")


# =============================================================================
# MAIN DASHBOARD: KPI HEADER, INTERACTIVE FOLIUM MAP & FLEET/HOSPITAL TABLES
# =============================================================================

st.title("🚑 Karachi EMS Command & Dispatch Center")

traffic_label = "PEAK TRAFFIC (8–10 AM / 5–8 PM)" if sim.is_peak_hour else "OFF-PEAK TRAFFIC"
st.caption(
    f"Sim Clock: **{sim.get_formatted_time()}** | Regime: **{traffic_label}** | "
    f"Mode: **{'RUNNING' if st.session_state.is_playing else 'PAUSED'}**"
)

# Top KPI Bar
idle_units = sum(1 for a in sim.fleet.values() if a.state == AmbulanceState.IDLE)
active_units = len(sim.fleet) - idle_units
total_er_avail = sum(h.ER_beds.available for h in sim.hospital_manager.hospitals.values())
total_icu_avail = sum(h.ICU_beds.available for h in sim.hospital_manager.hospitals.values())
queued_calls_count = len(sim.priority_queue.heap)

k1, k2, k3, k4, k5 = st.columns(5)
k1.metric("Sim Clock", sim.get_formatted_time(), delta="Peak Traffic" if sim.is_peak_hour else "Normal Flow")
k2.metric("Idle Ambulances", f"{idle_units} / {len(sim.fleet)}", delta=f"{active_units} Active")
k3.metric("Available ICU Beds", total_icu_avail)
k4.metric("Available ER Beds", total_er_avail)
k5.metric("Queued Calls", queued_calls_count, delta=f"{len(sim.calls)} Total Calls")

# Build Folium Map centered on Karachi
karachi_map = folium.Map(location=[24.8680, 67.0550], zoom_start=12, tiles="OpenStreetMap")

# 1. Render Hospitals (Red pins with live ER & ICU bed counts)
for hosp in sim.hospital_manager.hospitals.values():
    er_str = f"{hosp.ER_beds.available}/{hosp.ER_beds.total}"
    icu_str = f"{hosp.ICU_beds.available}/{hosp.ICU_beds.total}"
    popup_html = (
        f"<b>{hosp.name}</b> ({hosp.hospital_id})<br>"
        f"District: {hosp.district}<br>"
        f"<b>ER Beds:</b> {er_str} available<br>"
        f"<b>ICU Beds:</b> {icu_str} available"
    )
    folium.Marker(
        location=list(hosp.coords),
        popup=folium.Popup(popup_html, max_width=280),
        tooltip=f"{hosp.name} | ER: {er_str} | ICU: {icu_str}",
        icon=folium.Icon(color="red", icon="plus-square", prefix="fa"),
    ).add_to(karachi_map)

# 2. Render Caller Emergency Locations (Yellow/Orange pins)
for call in sim.calls.values():
    if call.status == "COMPLETED":
        continue

    pin_color = "orange" if call.status == "QUEUED" else "beige"
    popup_html = (
        f"<b>Emergency {call.call_id}</b><br>"
        f"Status: <b>{call.status}</b><br>"
        f"Triage Level: <b>L{call.triage.triage_level}</b> ({call.triage.equipment_needed})<br>"
        f"Assigned Unit: {call.assigned_amb_id or 'Pending'}<br>"
        f"Summary: {call.triage.clinical_summary}"
    )
    folium.Marker(
        location=list(call.caller_coords),
        popup=folium.Popup(popup_html, max_width=280),
        tooltip=f"{call.call_id} [L{call.triage.triage_level} - {call.status}]",
        icon=folium.Icon(color=pin_color, icon="exclamation-circle", prefix="fa"),
    ).add_to(karachi_map)

# 3. Render Ambulances (Blue/State pins) & Highlighted Shortest Routes
for amb in sim.fleet.values():
    style = AMBULANCE_STATE_STYLES[amb.state]
    popup_html = (
        f"<b>{amb.amb_id}</b> ({amb.name})<br>"
        f"Equipment: <b>{amb.equipment_type}</b><br>"
        f"State: <b>{amb.state.value}</b><br>"
        f"Assigned Call: {amb.assigned_call_id or 'None'}<br>"
        f"Target Hospital: {amb.target_hospital_id or 'None'}"
    )
    folium.Marker(
        location=list(amb.coords),
        popup=folium.Popup(popup_html, max_width=260),
        tooltip=f"{amb.amb_id} [{amb.equipment_type}] - {amb.state.value}",
        icon=folium.Icon(color=style["color"], icon="ambulance", prefix="fa"),
    ).add_to(karachi_map)

    # Render remaining active route waypoints
    if amb.state != AmbulanceState.IDLE and amb.waypoints:
        route_coords = [list(amb.coords)] + [list(wp) for wp in amb.waypoints]
        folium.PolyLine(
            locations=route_coords,
            color=style["route_color"],
            weight=4,
            opacity=0.85,
            tooltip=f"{amb.amb_id} active path ({amb.state.value})",
        ).add_to(karachi_map)

        # Preview second leg (Caller -> Hospital) while en route to pickup
        if (
            amb.state == AmbulanceState.EN_ROUTE_TO_CALLER
            and amb.assigned_call_id in sim.calls
            and amb.target_hospital_coords is not None
        ):
            caller_pt = list(sim.calls[amb.assigned_call_id].caller_coords)
            hosp_pt = list(amb.target_hospital_coords)
            folium.PolyLine(
                locations=[caller_pt, hosp_pt],
                color="#C0392B",
                weight=3,
                opacity=0.55,
                dash_array="6, 8",
                tooltip=f"{amb.amb_id} planned hospital leg ({amb.target_hospital_id})",
            ).add_to(karachi_map)

# Render Map (returned_objects=[] prevents map pan/zoom from triggering simulation reruns)
st_folium(karachi_map, width=None, height=500, returned_objects=[])

# Detailed Operational Tabs
tab_calls, tab_hospitals, tab_fleet = st.tabs(
    ["📋 Emergency Calls", "🏥 Hospital Bed Capacities", "🚑 Ambulance Fleet"]
)

with tab_calls:
    if sim.calls:
        call_rows = []
        for call in reversed(list(sim.calls.values())):
            wait_sec = (
                max(0.0, call.dispatch_time - call.arrival_time)
                if call.dispatch_time is not None
                else max(0.0, sim.current_time_seconds - call.arrival_time)
            )
            call_rows.append(
                {
                    "Call ID": call.call_id,
                    "Status": call.status,
                    "Triage": f"Level {call.triage.triage_level}",
                    "Equipment": call.triage.equipment_needed,
                    "Queue Wait (s)": round(wait_sec, 1),
                    "Ambulance": call.assigned_amb_id or "Queued",
                    "Hospital": call.assigned_hospital_id or "Pending",
                    "Source": "Fallback" if call.fallback_used else "Ollama LLM",
                    "Clinical Summary": call.triage.clinical_summary,
                }
            )
        st.dataframe(call_rows, use_container_width=True, hide_index=True)
    else:
        st.info("No emergency calls ingested yet. Submit a call from the sidebar.")

with tab_hospitals:
    hosp_rows = [
        {
            "Hospital ID": h.hospital_id,
            "Name": h.name,
            "District": h.district,
            "ER Available": f"{h.ER_beds.available} / {h.ER_beds.total}",
            "ICU Available": f"{h.ICU_beds.available} / {h.ICU_beds.total}",
            "ER Occupancy": f"{h.ER_beds.occupancy_rate * 100:.0f}%",
            "ICU Occupancy": f"{h.ICU_beds.occupancy_rate * 100:.0f}%",
        }
        for h in sim.hospital_manager.hospitals.values()
    ]
    st.dataframe(hosp_rows, use_container_width=True, hide_index=True)

with tab_fleet:
    fleet_rows = [
        {
            "Unit ID": a.amb_id,
            "Hub / Name": a.name,
            "Equipment": a.equipment_type,
            "State": a.state.value,
            "Latitude": round(a.coords[0], 4),
            "Longitude": round(a.coords[1], 4),
            "Active Call": a.assigned_call_id or "-",
            "Target Hospital": a.target_hospital_id or "-",
            "Waypoints Left": len(a.waypoints),
        }
        for a in sim.fleet.values()
    ]
    st.dataframe(fleet_rows, use_container_width=True, hide_index=True)


# =============================================================================
# CONTINUOUS SIMULATION PLAYBACK LOOP
# =============================================================================

if st.session_state.is_playing:
    time.sleep(0.8)
    st.session_state.last_step_summary = sim.step(time_delta=float(st.session_state.time_step_sec))
    st.rerun()