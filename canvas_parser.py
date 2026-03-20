"""
canvas_parser.py — Obsidian .canvas 플로우차트 파서
=========================================================
플로우차트/ 폴더의 .canvas (JSON) 파일에서 처방 간 관계를 추출합니다.

캔버스 구조:
  nodes: [{id, type, text, x, y, width, height, color?}]
  edges: [{id, fromNode, toNode, fromSide, toSide, color?}]

노드 텍스트 패턴:
  [[중통-017 향소산]]  → vault 링크 처방
  백통탕                → vault에 없는 참조 처방
"""

import json
import re
from collections import defaultdict
from pathlib import Path
from typing import Optional


# ── 노드 텍스트에서 처방명 추출 정규식 ────────────────────────────────────────
_LINK_RE = re.compile(r"\[\[(?:(?:상통|중통|하통)-\d{3}(?:-\d{3})?\s+)?(.+?)\]\]")


class CanvasParser:
    """
    플로우차트/*.canvas 에서 처방 관계 그래프를 추출합니다.

    사용:
        cp = CanvasParser("플로우차트")
        related = cp.get_related("향소산")
        # → [{"name": "궁지향소산", "direction": "child", "color": "2", ...}, ...]
    """

    def __init__(self, canvas_dir: str = "플로우차트"):
        self.canvas_dir = Path(canvas_dir)
        self._nodes: dict[str, dict] = {}      # {처방명: {code, color, canvas, node_id}}
        self._edges: list[dict] = []            # [{from, to, canvas, color}]
        self._adjacency: dict[str, set] = defaultdict(set)  # {처방명: {연결된 처방들}}
        self._node_id_map: dict[str, str] = {}  # {canvas_file::node_id: 처방명}
        self._loaded = False

    def _ensure_loaded(self):
        if not self._loaded:
            self._load_all()
            self._loaded = True

    def _load_all(self):
        """모든 .canvas 파일 파싱"""
        if not self.canvas_dir.exists():
            return

        for f in sorted(self.canvas_dir.glob("*.canvas")):
            try:
                data = json.loads(f.read_text(encoding="utf-8"))
                canvas_name = f.stem.replace(" 플로우차트", "")
                self._parse_canvas(data, canvas_name, f.name)
            except (json.JSONDecodeError, KeyError) as e:
                continue

    def _parse_canvas(self, data: dict, canvas_name: str, filename: str):
        """단일 캔버스 파싱"""
        nodes = data.get("nodes", [])
        edges = data.get("edges", [])

        # 노드 파싱 — node_id → 처방명 매핑
        local_map = {}  # node_id → 처방명
        for node in nodes:
            node_id = node.get("id", "")
            text = node.get("text", "").strip()
            if not text:
                continue

            # [[코드 처방명]] 형태
            m = _LINK_RE.search(text)
            if m:
                name = m.group(1)
                # 코드 추출
                code_m = re.search(r"((?:상통|중통|하통)-\d{3}(?:-\d{3})?)", text)
                code = code_m.group(1) if code_m else ""
            else:
                # 링크 없는 일반 텍스트 (예: "백통탕", "대함흉탕")
                name = text
                code = ""

            color = str(node.get("color", ""))
            local_map[node_id] = name

            # 글로벌 노드 등록
            if name not in self._nodes:
                self._nodes[name] = {
                    "code": code,
                    "color": color,
                    "canvas": canvas_name,
                    "x": node.get("x", 0),
                    "y": node.get("y", 0),
                }
            self._node_id_map[f"{filename}::{node_id}"] = name

        # 엣지 파싱
        for edge in edges:
            from_id = edge.get("fromNode", "")
            to_id = edge.get("toNode", "")
            from_name = local_map.get(from_id)
            to_name = local_map.get(to_id)

            if from_name and to_name and from_name != to_name:
                edge_color = str(edge.get("color", ""))
                self._edges.append({
                    "from": from_name,
                    "to": to_name,
                    "canvas": canvas_name,
                    "color": edge_color,
                })
                self._adjacency[from_name].add(to_name)
                self._adjacency[to_name].add(from_name)

    # ── 공개 API ──────────────────────────────────────────────────────────────

    def get_related(self, prescription_name: str) -> list[dict]:
        """
        특정 처방과 캔버스에서 연결된 모든 처방 목록.

        Returns:
            [{"name": "궁지향소산", "code": "중통-017-001",
              "relation": "child"|"parent"|"sibling",
              "color": "2", "canvas": "향소산"}, ...]
        """
        self._ensure_loaded()
        related = []
        seen = set()

        for edge in self._edges:
            other = None
            relation = "sibling"

            if edge["from"] == prescription_name:
                other = edge["to"]
                relation = "child"  # 이 처방에서 나가는 화살표
            elif edge["to"] == prescription_name:
                other = edge["from"]
                relation = "parent"  # 이 처방으로 들어오는 화살표

            if other and other not in seen:
                seen.add(other)
                node_info = self._nodes.get(other, {})
                related.append({
                    "name": other,
                    "code": node_info.get("code", ""),
                    "relation": relation,
                    "color": node_info.get("color", ""),
                    "canvas": edge["canvas"],
                })

        return related

    def get_all_connections(self, prescription_name: str) -> set[str]:
        """처방과 연결된 모든 처방명 (방향 무관)"""
        self._ensure_loaded()
        return set(self._adjacency.get(prescription_name, set()))

    def get_network_data(self, prescription_name: str, max_depth: int = 2) -> dict:
        """
        BFS로 처방 중심 네트워크 데이터 추출 (최대 depth 단계까지).

        Returns:
            {
                "nodes": [{"name": "향소산", "depth": 0, "color": "", "code": "중통-017"}, ...],
                "edges": [{"from": "향소산", "to": "궁지향소산", "color": "2"}, ...],
            }
        """
        self._ensure_loaded()

        if prescription_name not in self._adjacency:
            return {"nodes": [], "edges": []}

        visited = {prescription_name: 0}
        queue = [prescription_name]
        result_nodes = []
        result_edges = []

        while queue:
            current = queue.pop(0)
            depth = visited[current]

            node_info = self._nodes.get(current, {})
            result_nodes.append({
                "name": current,
                "depth": depth,
                "color": node_info.get("color", ""),
                "code": node_info.get("code", ""),
            })

            if depth < max_depth:
                for neighbor in self._adjacency.get(current, set()):
                    if neighbor not in visited:
                        visited[neighbor] = depth + 1
                        queue.append(neighbor)

        # 방문한 노드 간의 엣지만 추출
        visited_names = set(visited.keys())
        for edge in self._edges:
            if edge["from"] in visited_names and edge["to"] in visited_names:
                result_edges.append({
                    "from": edge["from"],
                    "to": edge["to"],
                    "color": edge["color"],
                    "canvas": edge["canvas"],
                })

        return {"nodes": result_nodes, "edges": result_edges}

    def has_canvas_data(self, prescription_name: str) -> bool:
        """이 처방이 캔버스에 존재하는지 확인"""
        self._ensure_loaded()
        return prescription_name in self._adjacency

    def get_all_canvas_prescriptions(self) -> list[str]:
        """캔버스에 등장하는 모든 처방명"""
        self._ensure_loaded()
        return sorted(self._nodes.keys())

    @property
    def stats(self) -> dict:
        """통계"""
        self._ensure_loaded()
        return {
            "canvas_files": len(set(e["canvas"] for e in self._edges)) if self._edges else 0,
            "total_nodes": len(self._nodes),
            "total_edges": len(self._edges),
            "prescriptions_with_connections": len(self._adjacency),
        }
