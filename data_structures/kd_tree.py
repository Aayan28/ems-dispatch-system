import math
import heapq
from typing import List, Tuple, Optional


class Ambulance:
    def __init__(self, amb_id: str, coords: Tuple[float, float], is_idle: bool = True):
        self.id = amb_id
        self.coords = coords  # (x, y) or (latitude, longitude)
        self.is_idle = is_idle

    def __repr__(self) -> str:
        return f"Ambulance({self.id}, coords={self.coords}, idle={self.is_idle})"


class KDNode:
    def __init__(self, ambulance: Ambulance, axis: int):
        self.ambulance = ambulance
        self.point = ambulance.coords
        self.axis = axis
        self.left: Optional[KDNode] = None
        self.right: Optional[KDNode] = None


class KDTree2D:
    """2D Spatial KD-Tree for fast nearest-neighbor queries on ambulances."""

    def __init__(self, ambulances: Optional[List[Ambulance]] = None):
        self.root = self._build_tree(ambulances, depth=0) if ambulances else None

    def _build_tree(self, ambulances: List[Ambulance], depth: int) -> Optional[KDNode]:
        if not ambulances:
            return None

        axis = depth % 2
        # Sort along current split axis (0 for X/Lat, 1 for Y/Lon)
        ambulances.sort(key=lambda a: a.coords[axis])
        median = len(ambulances) // 2

        node = KDNode(ambulances[median], axis)
        node.left = self._build_tree(ambulances[:median], depth + 1)
        node.right = self._build_tree(ambulances[median + 1:], depth + 1)
        return node

    @staticmethod
    def euclidean_distance(p1: Tuple[float, float], p2: Tuple[float, float]) -> float:
        return math.hypot(p1[0] - p2[0], p1[1] - p2[1])

    def find_nearest_k_idle(
        self, target_coords: Tuple[float, float], k: int = 1
    ) -> List[Tuple[float, Ambulance]]:
        """Finds the K nearest idle ambulances to the target location in O(log N) average time."""
        # Max-heap tracking best K candidates: (-distance, Ambulance)
        best_candidates: List[Tuple[float, Ambulance]] = []

        def _search(node: Optional[KDNode]) -> None:
            if node is None:
                return

            # Consider node if ambulance is idle
            if node.ambulance.is_idle:
                dist = self.euclidean_distance(target_coords, node.point)
                if len(best_candidates) < k:
                    heapq.heappush(best_candidates, (-dist, node.ambulance))
                elif dist < -best_candidates[0][0]:
                    heapq.heapreplace(best_candidates, (-dist, node.ambulance))

            axis = node.axis
            diff = target_coords[axis] - node.point[axis]

            primary = node.left if diff < 0 else node.right
            secondary = node.right if diff < 0 else node.left

            # Search branch containing target point
            _search(primary)

            # Check secondary branch if splitting plane crosses candidate radius
            current_max_dist = (
                -best_candidates[0][0] if len(best_candidates) == k else float("inf")
            )
            if abs(diff) < current_max_dist:
                _search(secondary)

        _search(self.root)

        # Unpack heap into sorted ascending order by distance
        result = [(-dist, amb) for dist, amb in best_candidates]
        result.sort(key=lambda item: item[0])
        return result


if __name__ == "__main__":
    fleet = [
        Ambulance("Amb-1", (40.7128, -74.0060), is_idle=True),
        Ambulance("Amb-2", (40.7306, -73.9352), is_idle=False),
        Ambulance("Amb-3", (40.7589, -73.9851), is_idle=True),
        Ambulance("Amb-4", (40.7061, -74.0087), is_idle=True),
    ]

    tree = KDTree2D(fleet)
    incident_site = (40.7150, -74.0010)
    nearest_k = tree.find_nearest_k_idle(incident_site, k=2)

    print(f"Top idle ambulances near {incident_site}:")
    for dist, amb in nearest_k:
        print(f" - {amb.id} at distance {dist:.4f} units")