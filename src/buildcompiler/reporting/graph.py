from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from buildcompiler.domain import FullBuildResult


@dataclass(frozen=True)
class BuildGraphNode:
    id: str
    kind: str
    label: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class BuildGraphEdge:
    source: str
    target: str
    relationship: str
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class BuildGraph:
    nodes: list[BuildGraphNode] = field(default_factory=list)
    edges: list[BuildGraphEdge] = field(default_factory=list)

    def add_node(self, node: BuildGraphNode) -> None:
        if node.id not in {n.id for n in self.nodes}:
            self.nodes.append(node)

    def add_edge(self, edge: BuildGraphEdge) -> None:
        key = (edge.source, edge.target, edge.relationship, tuple(sorted(edge.metadata.items())))
        keys = {
            (e.source, e.target, e.relationship, tuple(sorted(e.metadata.items())))
            for e in self.edges
        }
        if key not in keys:
            self.edges.append(edge)

    def to_dict(self) -> dict[str, object]:
        return {
            "nodes": [
                {
                    "id": n.id,
                    "kind": n.kind,
                    "label": n.label,
                    "metadata": n.metadata,
                }
                for n in sorted(self.nodes, key=lambda x: x.id)
            ],
            "edges": [
                {
                    "source": e.source,
                    "target": e.target,
                    "relationship": e.relationship,
                    "metadata": e.metadata,
                }
                for e in sorted(
                    self.edges,
                    key=lambda x: (x.source, x.target, x.relationship, sorted(x.metadata.items())),
                )
            ],
        }

    def summary(self) -> dict[str, object]:
        relationship_counts: dict[str, int] = {}
        for edge in self.edges:
            relationship_counts[edge.relationship] = relationship_counts.get(edge.relationship, 0) + 1
        return {
            "node_count": len(self.nodes),
            "edge_count": len(self.edges),
            "relationship_counts": dict(sorted(relationship_counts.items())),
        }


def _kind_for_identity(identity: str) -> str:
    value = identity.lower()
    if "moduledefinition" in value or "/module/" in value:
        return "abstract_design"
    if "engineered" in value or "region" in value:
        return "engineered_region"
    if "plasmid" in value:
        return "plasmid"
    if "strain" in value:
        return "strain"
    if "plate" in value:
        return "plate"
    return "part"


def build_graph(result: FullBuildResult) -> BuildGraph:
    graph = BuildGraph()

    for stage_result in result.stage_results:
        stage_node_id = f"stage_result:{stage_result.id}"
        graph.add_node(BuildGraphNode(id=stage_node_id, kind="stage_result", label=stage_result.stage.value))
        for request_id in sorted(stage_result.request_ids):
            graph.add_node(BuildGraphNode(id=f"request:{request_id}", kind="abstract_design", label=request_id))
            graph.add_edge(BuildGraphEdge(source=f"request:{request_id}", target=stage_node_id, relationship="requires"))
        for product in stage_result.products:
            graph.add_node(BuildGraphNode(id=product.identity, kind=_kind_for_identity(product.identity), label=product.display_id))
            graph.add_edge(BuildGraphEdge(source=stage_node_id, target=product.identity, relationship="produces"))
        for missing in stage_result.missing_inputs:
            node_id = f"missing:{missing.missing_identity}"
            graph.add_node(BuildGraphNode(id=node_id, kind="missing_input", label=missing.missing_display_id, metadata={"kind": missing.missing_kind}))
            graph.add_edge(BuildGraphEdge(source=stage_node_id, target=node_id, relationship="blocks", metadata={"required_stage": str(missing.required_stage)}))
        for approval in stage_result.required_approvals:
            approval_id = f"approval:{approval.process}"
            graph.add_node(BuildGraphNode(id=approval_id, kind="approval", label=approval.process, metadata={"status": approval.status.value}))
            graph.add_edge(BuildGraphEdge(source=stage_node_id, target=approval_id, relationship="requires"))

    for product in result.final_products:
        graph.add_node(BuildGraphNode(id=product.identity, kind=_kind_for_identity(product.identity), label=product.display_id))

    for missing in result.missing_inputs:
        graph.add_node(BuildGraphNode(id=f"missing:{missing.missing_identity}", kind="missing_input", label=missing.missing_display_id, metadata={"kind": missing.missing_kind}))

    for approval in result.required_approvals:
        graph.add_node(BuildGraphNode(id=f"approval:{approval.process}", kind="approval", label=approval.process, metadata={"status": approval.status.value}))

    return graph
