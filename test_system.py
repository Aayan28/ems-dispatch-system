"""
test_system.py
Automated verification suite for:
1. 2D KD-Tree nearest idle ambulance search
2. Min-Heap priority aging and dynamic triage escalation
3. Triage JSON schema validation, 2-retry recovery, and deterministic keyword fallback
4. End-to-end EMSSimulator structured JSON logging
"""

import json
import os
import tempfile
import unittest
from unittest.mock import MagicMock, patch

from pydantic import ValidationError

from data_structures.kd_tree import Ambulance, KDTree2D
from data_structures.min_heap import Patient, PriorityMinHeap
from simulation_engine import EMSSimulator
from triage_agent import (
    TriageSchema,
    keyword_fallback_triage,
    query_triage,
)


class TestKDTreeNearestSearch(unittest.TestCase):
    """Tests 2D spatial KD-Tree nearest-neighbor queries and idle state filtering."""

    def setUp(self) -> None:
        self.fleet = [
            Ambulance("AMB-SADDAR", (24.8600, 67.0195), is_idle=True),
            Ambulance("AMB-CLIFTON-BUSY", (24.8150, 67.0310), is_idle=False),
            Ambulance("AMB-PECHS", (24.8690, 67.0650), is_idle=True),
            Ambulance("AMB-GULSHAN", (24.9175, 67.0975), is_idle=True),
            Ambulance("AMB-KORANGI", (24.8250, 67.1140), is_idle=True),
        ]
        self.tree = KDTree2D(list(self.fleet))

    def test_nearest_idle_excludes_busy_closer_unit(self) -> None:
        # Incident right next to Clifton busy unit, so Saddar should be returned instead
        clifton_incident = (24.8140, 67.0315)
        nearest = self.tree.find_nearest_k_idle(clifton_incident, k=1)

        self.assertEqual(len(nearest), 1)
        dist, amb = nearest[0]
        self.assertEqual(amb.id, "AMB-SADDAR")
        self.assertTrue(amb.is_idle)
        self.assertGreater(dist, 0.0)

    def test_nearest_k_ordering_and_count(self) -> None:
        pechs_incident = (24.8700, 67.0660)
        nearest_three = self.tree.find_nearest_k_idle(pechs_incident, k=3)

        self.assertEqual(len(nearest_three), 3)
        ids = [amb.id for _, amb in nearest_three]
        dists = [dist for dist, _ in nearest_three]

        # Closest idle units to PECHS in ascending distance order
        self.assertEqual(ids, ["AMB-PECHS", "AMB-SADDAR", "AMB-GULSHAN"])
        self.assertEqual(dists, sorted(dists))


class TestMinHeapPriorityAging(unittest.TestCase):
    """Tests Min-Heap priority formula: Priority = (TriageLevel * w1) - (WaitTime * w2)."""

    def test_priority_aging_promotes_long_waiting_patient(self) -> None:
        w1, w2 = 10.0, 0.1
        heap = PriorityMinHeap(w1=w1, w2=w2)
        t0 = 1000.0

        # Patient A: Triage Level 3 (initial priority = 30.0) arrived at t0
        patient_a = Patient("P-LEVEL3-EARLY", triage_level=3, arrival_time=t0)
        heap.push(patient_a, current_time=t0)

        # Patient B: Triage Level 2 (initial priority = 20.0) arrived at t0 + 50s
        patient_b = Patient("P-LEVEL2-LATE", triage_level=2, arrival_time=t0 + 50.0)
        heap.push(patient_b, current_time=t0 + 50.0)

        # At t = 1050s:
        # Priority(A) = (3 * 10) - (50 * 0.1) = 25.0
        # Priority(B) = (2 * 10) - (0 * 0.1)  = 20.0 -> B is higher priority
        heap.update_all_priorities(t0 + 50.0)
        self.assertEqual(heap.heap[0].patient.patient_id, "P-LEVEL2-LATE")

        # Advance time to t = 1200s (150s later):
        # Priority(A) = (3 * 10) - (200 * 0.1) = 10.0
        # Priority(B) = (2 * 10) - (150 * 0.1) = 5.0 -> Wait, check 250s wait:
        # At t = 1250s:
        # Priority(A) = 30 - 25 = 5.0, Priority(B) = 20 - 20 = 0.0 -> need A to wait longer initially:
        # Let's test dynamic triage escalation & large wait gap explicitly:
        t_aged = t0 + 300.0
        # Push a brand new Level 2 patient at t_aged (Priority = 20.0)
        patient_c = Patient("P-LEVEL2-FRESH", triage_level=2, arrival_time=t_aged)
        heap.push(patient_c, current_time=t_aged)

        # Update aging at t_aged:
        # Priority(A) = (3 * 10) - (300 * 0.1) = 0.0 < Priority(C) = 20.0
        heap.update_all_priorities(t_aged)
        first_served = heap.pop_min()
        self.assertIsNotNone(first_served)
        self.assertEqual(first_served.patient_id, "P-LEVEL2-LATE")  # Priority = -5.0

        second_served = heap.pop_min()
        self.assertIsNotNone(second_served)
        self.assertEqual(second_served.patient_id, "P-LEVEL3-EARLY")  # Priority = 0.0 < 20.0

    def test_dynamic_triage_escalation(self) -> None:
        heap = PriorityMinHeap(w1=10.0, w2=0.05)
        t0 = 500.0
        heap.push(Patient("P-1", triage_level=4, arrival_time=t0), t0)
        heap.push(Patient("P-2", triage_level=2, arrival_time=t0), t0)

        # Escalate P-1 from Level 4 to Level 1
        heap.update_patient_triage("P-1", new_triage_level=1, current_time=t0)
        top = heap.pop_min()
        self.assertIsNotNone(top)
        self.assertEqual(top.patient_id, "P-1")


class TestTriageSchemaAndFallback(unittest.TestCase):
    """Tests Pydantic validation, 2-retry recovery, and deterministic keyword fallback."""

    def test_pydantic_schema_validation_constraints(self) -> None:
        valid = TriageSchema(
            triage_level=1,
            equipment_needed="ICU",
            clinical_summary="Acute myocardial infarction.",
        )
        self.assertEqual(valid.triage_level, 1)
        self.assertEqual(valid.equipment_needed, "ICU")

        # Out-of-bounds triage_level (must be 1..5)
        with self.assertRaises(ValidationError):
            TriageSchema(
                triage_level=0,
                equipment_needed="ICU",
                clinical_summary="Invalid level 0",
            )

        with self.assertRaises(ValidationError):
            TriageSchema(
                triage_level=6,
                equipment_needed="Basic",
                clinical_summary="Invalid level 6",
            )

        # Invalid equipment_needed literal
        with self.assertRaises(ValidationError):
            TriageSchema(
                triage_level=2,
                equipment_needed="Helicopter",  # type: ignore[arg-type]
                clinical_summary="Invalid equipment tier",
            )

    def test_deterministic_keyword_fallback_rules(self) -> None:
        res_chest = keyword_fallback_triage("Patient has severe chest pain radiating to arm.")
        self.assertEqual(res_chest.triage_level, 1)
        self.assertEqual(res_chest.equipment_needed, "ICU")

        res_unconscious = keyword_fallback_triage("Found unconscious on the sidewalk.")
        self.assertEqual(res_unconscious.triage_level, 1)
        self.assertEqual(res_unconscious.equipment_needed, "ICU")

        res_bleeding = keyword_fallback_triage("Victim has moderate bleeding from leg.")
        self.assertEqual(res_bleeding.triage_level, 2)
        self.assertEqual(res_bleeding.equipment_needed, "ICU")

    @patch("triage_agent.ollama.Client")
    def test_query_triage_retries_and_falls_back_after_two_failures(
        self, mock_client_cls: MagicMock
    ) -> None:
        mock_client = MagicMock()
        mock_client_cls.return_value = mock_client

        # Simulate 2 consecutive malformed/invalid JSON responses from Ollama
        mock_client.chat.side_effect = [
            {"message": {"content": "NOT VALID JSON AT ALL"}},
            {"message": {"content": '{"triage_level": 99, "equipment_needed": "WRONG"}'}},
        ]

        result = query_triage(
            patient_notes="Elderly male unconscious after collapse.",
            max_retries=2,
        )

        self.assertEqual(mock_client.chat.call_count, 2)
        self.assertEqual(result.triage_level, 1)
        self.assertEqual(result.equipment_needed, "ICU")
        self.assertIn("Fallback Triage", result.clinical_summary)

    @patch("triage_agent.ollama.Client")
    def test_query_triage_recovers_on_second_attempt(
        self, mock_client_cls: MagicMock
    ) -> None:
        mock_client = MagicMock()
        mock_client_cls.return_value = mock_client

        mock_client.chat.side_effect = [
            {"message": {"content": "{malformed_json"}},
            {
                "message": {
                    "content": json.dumps(
                        {
                            "triage_level": 3,
                            "equipment_needed": "Basic",
                            "clinical_summary": "Closed forearm fracture, stable vitals.",
                        }
                    )
                }
            },
        ]

        result = query_triage("Suspected forearm fracture.", max_retries=2)
        self.assertEqual(mock_client.chat.call_count, 2)
        self.assertEqual(result.triage_level, 3)
        self.assertEqual(result.equipment_needed, "Basic")


class TestSimulatorStructuredLogging(unittest.TestCase):
    """Verifies dispatch_events.log records triage_level, queue_wait_time, and dispatch_latency."""

    def test_dispatch_events_logged_as_structured_json(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            log_path = os.path.join(tmpdir, "dispatch_events.log")
            sim = EMSSimulator(start_hour=9.0, log_file=log_path)

            sim.ingest_call(
                caller_coords=(24.8697, 67.0656),
                patient_notes="Patient complaining of acute chest pain.",
                use_llm=False,
            )
            sim.step(time_delta=60.0)

            # Flush file handlers
            for handler in sim.event_logger.handlers:
                handler.flush()
                handler.close()

            self.assertTrue(os.path.exists(log_path))
            with open(log_path, "r", encoding="utf-8") as f:
                lines = [json.loads(line) for line in f if line.strip()]

            dispatched_records = [
                rec for rec in lines if rec.get("event_type") == "CALL_DISPATCHED"
            ]
            self.assertEqual(len(dispatched_records), 1)
            record = dispatched_records[0]

            self.assertEqual(record["triage_level"], 1)
            self.assertIn("queue_wait_time", record)
            self.assertIn("dispatch_latency", record)
            self.assertAlmostEqual(record["queue_wait_time"], 60.0)


if __name__ == "__main__":
    unittest.main(verbosity=2)