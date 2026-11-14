import math
import heapq
from typing import Dict, List, Tuple, Optional


class Node:
    def __init__(self, node_id: str, x: float, y: float):
        self.id = node_id
        self.x = x
        self.y = y


class Edge:
    def __init__(self, target: str, distance: float, peak_multiplier: float = 1.5):
        self.target = target
        self.distance = distance
        self.peak_multiplier = peak_multiplier

    def get_weight(self, is_peak_hour: bool) -> float:
        return self.distance * self.peak_multiplier if is_peak_hour else self.distance


class Graph:
    """Adjacency list routing graph with traffic adjustments, Dijkstra, and A* algorithms."""

    def __init__(self):
        self.nodes: Dict[str, Node] = {}
        self.adj: Dict[str, List[Edge]] = {}

    def add_node(self, node_id: str, x: float, y: float) -> None:
        self.nodes[node_id] = Node(node_id, x, y)
        if node_id not in self.adj:
            self.adj[node_id] = []

    def add_edge(
        self,
        u: str,
        v: str,
        distance: float,
        peak_multiplier: float = 1.5,
        bidirectional: bool = True,
    ) -> None:
        self.adj[u].append(Edge(v, distance, peak_multiplier))
        if bidirectional:
            self.adj[v].append(Edge(u, distance, peak_multiplier))

    def euclidean_heuristic(self, n1_id: str, n2_id: str) -> float:
        """Admissible Euclidean heuristic for A* pathfinding."""
        n1, n2 = self.nodes[n1_id], self.nodes[n2_id]
        return math.hypot(n1.x - n2.x, n1.y - n2.y)

    def dijkstra(
        self, start_id: str, target_id: str, is_peak_hour: bool = False
    ) -> Tuple[float, List[str]]:
        """Calculates shortest path using standard Dijkstra algorithm."""
        distances: Dict[str, float] = {node: float("inf") for node in self.nodes}
        previous: Dict[str, Optional[str]] = {node: None for node in self.nodes}

        distances[start_id] = 0.0
        pq: List[Tuple[float, str]] = [(0.0, start_id)]

        while pq:
            current_dist, u = heapq.heappop(pq)

            if current_dist > distances[u]:
                continue

            if u == target_id:
                break

            for edge in self.adj[u]:
                weight = edge.get_weight(is_peak_hour)
                new_dist = current_dist + weight

                if new_dist < distances[edge.target]:
                    distances[edge.target] = new_dist
                    previous[edge.target] = u
                    heapq.heappush(pq, (new_dist, edge.target))

        return distances[target_id], self._reconstruct_path(previous, target_id)

    def a_star(
        self, start_id: str, target_id: str, is_peak_hour: bool = False
    ) -> Tuple[float, List[str]]:
        """Calculates shortest path using A* search guided by spatial heuristic."""
        g_score: Dict[str, float] = {node: float("inf") for node in self.nodes}
        f_score: Dict[str, float] = {node: float("inf") for node in self.nodes}
        previous: Dict[str, Optional[str]] = {node: None for node in self.nodes}

        g_score[start_id] = 0.0
        f_score[start_id] = self.euclidean_heuristic(start_id, target_id)

        pq: List[Tuple[float, str]] = [(f_score[start_id], start_id)]

        while pq:
            _, u = heapq.heappop(pq)

            if u == target_id:
                break

            for edge in self.adj[u]:
                weight = edge.get_weight(is_peak_hour)
                tentative_g = g_score[u] + weight

                if tentative_g < g_score[edge.target]:
                    previous[edge.target] = u
                    g_score[edge.target] = tentative_g
                    h = self.euclidean_heuristic(edge.target, target_id)
                    f_score[edge.target] = tentative_g + h
                    heapq.heappush(pq, (f_score[edge.target], edge.target))

        return g_score[target_id], self._reconstruct_path(previous, target_id)

    def _reconstruct_path(
        self, previous: Dict[str, Optional[str]], target_id: str
    ) -> List[str]:
        path = []
        curr: Optional[str] = target_id
        while curr is not None:
            path.append(curr)
            curr = previous[curr]
        path.reverse()
        return path if path and path[0] == list(self.nodes.keys())[0] or len(path) > 0 else []


if __name__ == "__main__":
    g = Graph()
    g.add_node("Depot", 0.0, 0.0)
    g.add_node("IntersectionA", 2.0, 1.0)
    g.add_node("IntersectionB", 1.0, 4.0)
    g.add_node("Hospital", 5.0, 5.0)

    # Distance in km, peak_multiplier=2.0 on congested main artery
    g.add_edge("Depot", "IntersectionA", distance=3.0, peak_multiplier=1.2)
    g.add_edge("Depot", "IntersectionB", distance=4.0, peak_multiplier=2.5)
    g.add_edge("IntersectionA", "Hospital", distance=6.0, peak_multiplier=1.1)
    g.add_edge("IntersectionB", "Hospital", distance=2.0, peak_multiplier=1.0)

    # Off-peak route calculation
    cost_normal, path_normal = g.a_star("Depot", "Hospital", is_peak_hour=False)
    print(f"Off-Peak Path (A*): {path_normal} with travel weight {cost_normal:.2f}")

    # Peak-hour route calculation (Dijkstra vs A*)
    cost_peak, path_peak = g.dijkstra("Depot", "Hospital", is_peak_hour=True)
    print(f"Peak-Hour Path (Dijkstra): {path_peak} with travel weight {cost_peak:.2f}")