import time
from typing import Dict, Optional


class Patient:
    def __init__(self, patient_id: str, triage_level: int, arrival_time: float):
        self.patient_id = patient_id
        self.triage_level = triage_level  # Range: 1 (Urgent) to 5 (Non-Urgent)
        self.arrival_time = arrival_time

    def calculate_priority(
        self, current_time: float, w1: float = 10.0, w2: float = 1.0
    ) -> float:
        wait_time = max(0.0, current_time - self.arrival_time)
        return (self.triage_level * w1) - (wait_time * w2)

    def __repr__(self) -> str:
        return f"Patient({self.patient_id}, Triage={self.triage_level})"


class HeapEntry:
    def __init__(self, patient: Patient, priority: float):
        self.patient = patient
        self.priority = priority


class PriorityMinHeap:
    """Custom Min-Heap with hash-map index tracking for dynamic updates."""

    def __init__(self, w1: float = 10.0, w2: float = 1.0):
        self.heap: list[HeapEntry] = []
        self.pos_map: Dict[str, int] = {}  # patient_id -> heap index
        self.w1 = w1
        self.w2 = w2

    def is_empty(self) -> bool:
        return len(self.heap) == 0

    def push(self, patient: Patient, current_time: float) -> None:
        priority = patient.calculate_priority(current_time, self.w1, self.w2)
        entry = HeapEntry(patient, priority)
        self.heap.append(entry)
        idx = len(self.heap) - 1
        self.pos_map[patient.patient_id] = idx
        self._sift_up(idx)

    def pop_min(self) -> Optional[Patient]:
        if not self.heap:
            return None

        self._swap(0, len(self.heap) - 1)
        min_entry = self.heap.pop()
        del self.pos_map[min_entry.patient.patient_id]

        if self.heap:
            self._sift_down(0)
        return min_entry.patient

    def update_all_priorities(self, current_time: float) -> None:
        """Recalculates all patient priority scores based on elapsed wait time."""
        for entry in self.heap:
            entry.priority = entry.patient.calculate_priority(
                current_time, self.w1, self.w2
            )
        # Re-heapify in O(N) time
        for i in reversed(range(len(self.heap) // 2)):
            self._sift_down(i)

    def update_patient_triage(
        self, patient_id: str, new_triage_level: int, current_time: float
    ) -> None:
        """Modifies a specific patient's triage level dynamically in O(log N) time."""
        if patient_id not in self.pos_map:
            raise KeyError(f"Patient ID {patient_id} not found in heap.")

        idx = self.pos_map[patient_id]
        entry = self.heap[idx]
        old_priority = entry.priority

        entry.patient.triage_level = new_triage_level
        entry.priority = entry.patient.calculate_priority(
            current_time, self.w1, self.w2
        )

        if entry.priority < old_priority:
            self._sift_up(idx)
        else:
            self._sift_down(idx)

    def _sift_up(self, idx: int) -> None:
        while idx > 0:
            parent = (idx - 1) // 2
            if self.heap[idx].priority < self.heap[parent].priority:
                self._swap(idx, parent)
                idx = parent
            else:
                break

    def _sift_down(self, idx: int) -> None:
        n = len(self.heap)
        while True:
            smallest = idx
            left = 2 * idx + 1
            right = 2 * idx + 2

            if left < n and self.heap[left].priority < self.heap[smallest].priority:
                smallest = left
            if right < n and self.heap[right].priority < self.heap[smallest].priority:
                smallest = right

            if smallest != idx:
                self._swap(idx, smallest)
                idx = smallest
            else:
                break

    def _swap(self, i: int, j: int) -> None:
        self.heap[i], self.heap[j] = self.heap[j], self.heap[i]
        self.pos_map[self.heap[i].patient.patient_id] = i
        self.pos_map[self.heap[j].patient.patient_id] = j


if __name__ == "__main__":
    t0 = time.time()
    queue = PriorityMinHeap(w1=10.0, w2=2.0)

    # Add initial patients
    queue.push(Patient("P-NonCritical", triage_level=4, arrival_time=t0 - 300), t0)
    queue.push(Patient("P-Severe", triage_level=2, arrival_time=t0 - 50), t0)

    # Simulate 100 seconds passing; update priorities based on wait times
    t1 = t0 + 100
    queue.update_all_priorities(t1)

    # Escalation: Patient condition deteriorates
    queue.update_patient_triage("P-NonCritical", new_triage_level=1, current_time=t1)

    print("Next dispatch priority sequence:")
    while not queue.is_empty():
        print(" Served:", queue.pop_min())