from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from typing import Any

from buildcompiler.domain import BuildStatus, FullBuildResult
from buildcompiler.reporting.graph import BuildGraph, build_graph


@dataclass
class StageReportSection:
    stage: str
    status: str
    request_ids: list[str]
    product_count: int
    missing_input_count: int
    approval_count: int
    warning_count: int
    logs: list[str] = field(default_factory=list)


@dataclass
class RouteReport:
    source_stage_result_id: str
    selected: bool
    route: dict[str, Any]


@dataclass
class RecommendedAction:
    code: str
    message: str
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class DependencyChainStep:
    source: str
    relationship: str
    target: str
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class BuildReport:
    status: BuildStatus
    executive_summary: str
    stage_sections: list[StageReportSection]
    selected_routes: list[RouteReport]
    rejected_alternatives: list[RouteReport]
    missing_inputs: list[dict[str, Any]]
    required_approvals: list[dict[str, Any]]
    warnings: list[dict[str, Any]]
    next_actions: list[RecommendedAction]
    dependency_chain: list[DependencyChainStep]
    graph_summary: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["status"] = self.status.value
        return data

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), sort_keys=True)

    def to_markdown(self) -> str:
        return "\n".join([
            "# Build Report",
            f"- Status: `{self.status.value}`",
            f"- Stage sections: `{len(self.stage_sections)}`",
            f"- Selected routes: `{len(self.selected_routes)}`",
            f"- Rejected alternatives: `{len(self.rejected_alternatives)}`",
            f"- Missing inputs: `{len(self.missing_inputs)}`",
            f"- Required approvals: `{len(self.required_approvals)}`",
            f"- Warnings: `{len(self.warnings)}`",
            "",
            "## Executive Summary",
            self.executive_summary,
        ])


def _recommended_actions(result: FullBuildResult) -> list[RecommendedAction]:
    actions: list[RecommendedAction] = []
    for missing in result.missing_inputs:
        kind = missing.missing_kind
        if kind == "engineered_region":
            actions.append(RecommendedAction("build_lvl1_engineered_region", "Build the missing engineered region through assembly level 1.", {"missing_identity": missing.missing_identity}))
        elif kind in {"promoter", "rbs", "cds", "terminator"}:
            actions.append(RecommendedAction("run_domestication", "Run domestication for missing part inputs.", {"missing_kind": kind, "missing_identity": missing.missing_identity}))
        elif kind == "chassis":
            actions.append(
                RecommendedAction(
                    "provide_chassis",
                    "Add a chassis identity for transformation.",
                    {"missing_identity": missing.missing_identity},
                )
            )
        elif kind in {"backbone", "restriction_enzyme", "ligase", "reagent"}:
            actions.append(RecommendedAction("provide_inventory_or_purchase", "Add missing inventory material or enable explicit purchase support.", {"missing_kind": kind, "missing_identity": missing.missing_identity}))
    for approval in result.required_approvals:
        actions.append(RecommendedAction("grant_required_approval", f"Grant required approval for process '{approval.process}'.", {"process": approval.process}))
    for warning in result.warnings:
        actions.append(RecommendedAction("inspect_warning", f"Inspect warning {warning.code} for details.", {"code": warning.code}))
    # deterministic de-dup
    unique: dict[tuple[str, str, str], RecommendedAction] = {}
    for action in actions:
        meta = json.dumps(action.metadata, sort_keys=True)
        unique[(action.code, action.message, meta)] = action
    return [unique[k] for k in sorted(unique)]


def build_report(result: FullBuildResult, graph: BuildGraph | None = None) -> BuildReport:
    report_graph = graph or build_graph(result)
    stage_sections = [
        StageReportSection(
            stage=sr.stage.value,
            status=sr.status.value,
            request_ids=sorted(sr.request_ids),
            product_count=len(sr.products),
            missing_input_count=len(sr.missing_inputs),
            approval_count=len(sr.required_approvals),
            warning_count=len(sr.warnings),
            logs=list(sr.logs),
        )
        for sr in result.stage_results
    ]
    selected_routes: list[RouteReport] = []
    rejected: list[RouteReport] = []
    for sr in result.stage_results:
        artifacts = sr.protocol_artifacts or {}
        sel = artifacts.get("selected_route")
        if isinstance(sel, dict):
            selected_routes.append(RouteReport(sr.id, True, sel))
        for route in artifacts.get("rejected_routes", []) or []:
            if isinstance(route, dict):
                rejected.append(RouteReport(sr.id, False, route))

    blocker_summary = f"{len(result.missing_inputs)} missing inputs and {len(result.required_approvals)} required approvals"
    if result.status == BuildStatus.FAILED:
        executive_summary = (
            f"Build failed with {blocker_summary}."
            if result.missing_inputs or result.required_approvals
            else "Build failed. Review stage logs and warnings for the root cause."
        )
    elif result.missing_inputs or result.required_approvals:
        executive_summary = f"Build is blocked by {blocker_summary}."
    else:
        executive_summary = "Build completed without unresolved blockers."
    dependency_chain = [
        DependencyChainStep(e.source, e.relationship, e.target, dict(e.metadata))
        for e in sorted(report_graph.edges, key=lambda x: (x.source, x.target, x.relationship))
        if e.relationship in {"blocks", "requires", "produces", "satisfies", "transforms", "plates"}
    ]
    return BuildReport(
        status=result.status,
        executive_summary=executive_summary,
        stage_sections=stage_sections,
        selected_routes=selected_routes,
        rejected_alternatives=rejected,
        missing_inputs=[asdict(x) | {"source_stage": x.source_stage.value, "required_stage": str(x.required_stage)} for x in result.missing_inputs],
        required_approvals=[asdict(x) | {"status": x.status.value} for x in result.required_approvals],
        warnings=[asdict(x) | {"stage": x.stage.value if x.stage else None} for x in result.warnings],
        next_actions=_recommended_actions(result),
        dependency_chain=dependency_chain,
        graph_summary=report_graph.summary(),
    )
