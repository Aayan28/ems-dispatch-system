# Karachi EMS Command & Dispatch System

An event-driven Emergency Medical Services (EMS) triage, routing, and hospital-matching simulation platform modeled on **Karachi, Pakistan**. The system combines local Large Language Model (LLM) natural language triage with custom spatial and graph data structures to dispatch ambulances and reserve hospital beds in real time - operating with zero external paid APIs.

## System Architecture

The simulation engine integrates four core computational modules:

### 1. Block A - Local AI Triage Agent (`triage_agent.py`)

* **Structured NLP Classification:** Connects to a local **Ollama** server running `llama3.2:1b` to convert unstructured emergency caller notes into validated **Pydantic** schemas (`TriageSchema`), assigning an acuity level (`1` to `5`), required ambulance tier (`ICU` vs. `Basic`), and a concise clinical summary.

* **Resilient Offline Fallback:** Includes a retry loop for schema enforcement and automatically falls back to a deterministic clinical keyword classifier if the local Ollama service is offline or toggled off in the UI.

### 2. Block B - Dynamic Priority Min-Heap (`data_structures/min_heap.py`)

* **Acuity-First Dispatch with Anti-Starvation Aging:** Incoming calls are managed in a custom binary Min-Heap ordered by dynamic priority:

```text
Priority = (TriageLevel * w1) - (WaitTime * w2)
```

* Critical emergencies (e.g., Level `1` cardiac arrest) dispatch immediately ahead of lower-acuity calls, while waiting calls gradually accrue priority over time so non-critical cases never starve in the queue.

### 3. Block C - Spatial 2D KD-Tree & Peak-Aware A* Routing (`data_structures/kd_tree.py`, `data_structures/graph.py`)

* **Equipment-Partitioned Spatial Lookup:** Maintains separate 2D KD-Trees for `ICU` and `Basic` idle ambulances, enabling `O(log N)` nearest-neighbor queries based on caller GPS coordinates.

* **Dynamic Karachi Road Network:** Models key Karachi districts and arterial corridors (including Shahrah-e-Faisal, Clifton, PECHS, Gulshan-e-Iqbal, Saddar, Korangi, and Stadium Road) as a weighted graph. Edge weights dynamically scale during Karachi rush hours (**08:00-10:00 AM** and **05:00-08:00 PM**), updating `A*` shortest-path computations and ambulance travel speeds in real time.

### 4. Block D - Hospital Capacity & Matching Engine (`hospital_engine.py`)

* Evaluates both travel distance and live **ER / ICU bed availability** across major Karachi medical facilities (including AKUH, Civil Hospital, The Indus Hospital, LNH, JPMC, NICVD, Ziauddin Hospital, and Patel Hospital).

* Atomically reserves a matching bed upon ambulance dispatch and schedules automatic bed release once patient recovery duration elapses.

## Key Features

* **Interactive Command Center (`app.py`):** Built with **Streamlit** and **Folium** using API-free **OpenStreetMap** tiles to visualize live ambulance trajectories, hospital locations, caller pins, and active route polylines.

* **Full Fleet State Machine (`simulation_engine.py`):** Tracks every ambulance across four lifecycle states: `IDLE` -> `EN_ROUTE_TO_CALLER` -> `TRANSPORTING_TO_HOSPITAL` -> `RETURNING`.

* **Live Telemetry & Structured JSON Logging:** Computes real-time average queue wait times and triage/dispatch latencies while writing structured JSON audit logs (`CALL_INGESTED`, `CALL_DISPATCHED`, `AMBULANCE_TRANSITION`) to `dispatch_events.log`.

* **Automated Unit Test Suite (`test_system.py`):** Verifies Min-Heap aging, KD-Tree nearest-idle search, `A*` peak-hour routing, hospital bed reservation/release, and structured JSON logging via `pytest`.

## Project Structure

```text
ems-dispatch-system/
|-- app.py                     # Streamlit & Folium interactive command dashboard
|-- simulation_engine.py       # Discrete-time EMS simulation & state machine
|-- triage_agent.py            # Ollama LLM triage client with Pydantic validation
|-- hospital_engine.py         # Hospital scoring, bed reservation & recovery manager
|-- karachi_geo_data.py        # Karachi road network graph, hubs & hospital dataset
|-- test_system.py             # Automated pytest unit & integration test suite
|-- requirements.txt           # Python package dependencies
|-- README.md                  # Project documentation
`-- data_structures/
    |-- __init__.py
    |-- graph.py               # Weighted road graph & peak-aware A* pathfinding
    |-- kd_tree.py             # 2D KD-Tree for O(log N) spatial ambulance lookup
    `-- min_heap.py            # Priority Min-Heap with wait-time aging
```

## Quick Start Guide

### 1. Prerequisites

* **Python 3.10+**

* **Ollama** (optional for live LLM triage; available at [ollama.com](https://ollama.com))

### 2. Pull the Local Triage Model

Start the Ollama application in the background, then pull the lightweight `llama3.2:1b` model:

```bash
ollama pull llama3.2:1b
```

### 3. Install Python Dependencies

Open a terminal inside the `ems-dispatch-system` directory and install the required packages:

```bash
python -m pip install -r requirements.txt
```

### 4. Run the Automated Test Suite

Verify that all data structures, routing algorithms, and logging pipelines pass:

```bash
python -m pytest test_system.py
```

### 5. Launch the Interactive Dashboard

```bash
python -m streamlit run app.py
```

Your default browser will open `http://localhost:8501`.

## Testing Scenarios

Once the dashboard is running at `http://localhost:8501`, use the left **EMS Dispatch Console** to test core system behaviors:

1. **Critical ICU Dispatch:** Keep **Use Ollama AI Triage** checked, enter *"60yo male experiencing severe chest pain and shortness of breath"*, and click **Ingest & Triage Call**. Observe an `ICU` ambulance dispatch and a corresponding deduction in available ICU beds.

2. **Fleet Movement & Lifecycle:** Set **Time-Step Delta** to `60` seconds and click **Play** (or advance single steps) to watch ambulances travel along the Karachi road network and transition from pickup to hospital drop-off and base return.

3. **Priority Queue Preemption:** Pause the simulation, submit a minor injury call first (e.g., *"Minor wrist sprain"*), submit a cardiac arrest call second, and advance one step - verifying that the Min-Heap dispatches the critical patient first.

4. **Offline Keyword Mode:** Uncheck **Use Ollama AI Triage** to test zero-latency deterministic classification without an active Ollama server.