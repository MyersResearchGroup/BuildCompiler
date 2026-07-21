"""Stable JSON DTOs for the clean BuildCompiler API.

The serializers deliberately omit live SBOL objects, documents, clients,
adapters, and credentials. DTO schema version 1 is suitable for HTTP payloads.
"""

from __future__ import annotations

import json
import math
from dataclasses import fields, is_dataclass
from enum import Enum
from pathlib import Path, PurePath
from typing import Any

from buildcompiler.domain import (
    BuildRequest,
    BuildStage,
    BuildWarning,
    DesignKind,
    FullBuildResult,
    IndexedBackbone,
    IndexedPlasmid,
    IndexedReagent,
    IndexedStrain,
    MissingBuildInput,
    RequiredApproval,
    StageResult,
)
from buildcompiler.planning import BuildPlan, UnsupportedPlanningRecord

SCHEMA_VERSION = "1.0"

_OMITTED_FIELDS = {
    "adapter",
    "adapters",
    "auth_token",
    "authorization",
    "build_document",
    "client",
    "clients",
    "credential",
    "credentials",
    "password",
    "resolver",
    "sbol_component",
    "sbol_document",
    "sbol_module",
    "token",
    "username",
}


class SerializationError(TypeError):
    """A value cannot be represented by the public JSON DTO contract."""


def serialize_build_request(request: BuildRequest) -> dict[str, Any]:
    return _ordered(
        {
            "id": request.id,
            "stage": request.stage.value,
            "source_identity": request.source_identity,
            "source_display_id": request.source_display_id,
            "source_kind": request.source_kind.value,
            "parent_group": request.parent_group,
            "variant_index": request.variant_index,
            "constraints": _json_safe(request.constraints),
        }
    )


def serialize_unsupported_planning_record(
    record: UnsupportedPlanningRecord,
) -> dict[str, Any]:
    return _ordered(
        {
            "source_identity": record.source_identity,
            "source_display_id": record.source_display_id,
            "source_kind": record.source_kind.value,
            "reason": record.reason,
            "metadata": _json_safe(record.metadata),
        }
    )


def serialize_build_plan(plan: BuildPlan) -> dict[str, Any]:
    return _ordered(
        {
            "schema_version": SCHEMA_VERSION,
            "kind": "build_plan",
            "lvl2_requests": [
                serialize_build_request(item) for item in plan.lvl2_requests
            ],
            "lvl1_requests": [
                serialize_build_request(item) for item in plan.lvl1_requests
            ],
            "domestication_requests": [
                serialize_build_request(item) for item in plan.domestication_requests
            ],
            "unsupported": [
                serialize_unsupported_planning_record(item) for item in plan.unsupported
            ],
            "warnings": [serialize_warning(item) for item in plan.warnings],
        }
    )


def deserialize_build_plan(data: dict[str, Any]) -> BuildPlan:
    """Reconstruct a BuildPlan submitted from a schema-version-1 DTO."""

    if not isinstance(data, dict):
        raise SerializationError("BuildPlan DTO must be a dictionary.")
    if data.get("schema_version") != SCHEMA_VERSION:
        raise SerializationError("Unsupported BuildPlan schema_version.")
    if data.get("kind") != "build_plan":
        raise SerializationError("DTO kind must be 'build_plan'.")
    return BuildPlan(
        lvl2_requests=[
            _deserialize_build_request(item) for item in _list(data, "lvl2_requests")
        ],
        lvl1_requests=[
            _deserialize_build_request(item) for item in _list(data, "lvl1_requests")
        ],
        domestication_requests=[
            _deserialize_build_request(item)
            for item in _list(data, "domestication_requests")
        ],
        unsupported=[
            _deserialize_unsupported(item) for item in _list(data, "unsupported")
        ],
        warnings=[_deserialize_warning(item) for item in _list(data, "warnings")],
    )


def serialize_warning(warning: BuildWarning) -> dict[str, Any]:
    return _ordered(
        {
            "code": warning.code,
            "message": warning.message,
            "stage": warning.stage.value if warning.stage else None,
            "source_identity": warning.source_identity,
            "metadata": _json_safe(warning.metadata),
        }
    )


def serialize_missing_input(missing: MissingBuildInput) -> dict[str, Any]:
    required_stage = (
        missing.required_stage.value
        if isinstance(missing.required_stage, BuildStage)
        else missing.required_stage
    )
    return _ordered(
        {
            "source_stage": missing.source_stage.value,
            "source_design_identity": missing.source_design_identity,
            "missing_identity": missing.missing_identity,
            "missing_display_id": missing.missing_display_id,
            "missing_kind": missing.missing_kind,
            "required_stage": required_stage,
            "reason": missing.reason,
            "candidates_tried": list(missing.candidates_tried),
        }
    )


def serialize_approval(approval: RequiredApproval) -> dict[str, Any]:
    return _ordered(
        {
            "status": approval.status.value,
            "process": approval.process,
            "reason": approval.reason,
            "metadata": _json_safe(approval.metadata),
        }
    )


def serialize_plasmid(plasmid: IndexedPlasmid) -> dict[str, Any]:
    return _ordered(
        {
            "kind": "plasmid",
            "identity": plasmid.identity,
            "display_id": plasmid.display_id,
            "name": plasmid.name,
            "state": plasmid.state.value,
            "roles": list(plasmid.roles),
            "metadata": _json_safe(plasmid.metadata),
        }
    )


def serialize_backbone(backbone: IndexedBackbone) -> dict[str, Any]:
    return _ordered(
        {
            "kind": "backbone",
            "identity": backbone.identity,
            "display_id": backbone.display_id,
            "name": backbone.name,
            "metadata": _json_safe(backbone.metadata),
        }
    )


def serialize_reagent(reagent: IndexedReagent) -> dict[str, Any]:
    return _ordered(
        {
            "kind": "reagent",
            "identity": reagent.identity,
            "display_id": reagent.display_id,
            "name": reagent.name,
            "reagent_type": reagent.reagent_type,
            "metadata": _json_safe(reagent.metadata),
        }
    )


def serialize_strain(strain: IndexedStrain) -> dict[str, Any]:
    return _ordered(
        {
            "kind": "strain",
            "identity": strain.identity,
            "display_id": strain.display_id,
            "name": strain.name,
            "state": strain.state.value,
            "roles": list(strain.roles),
            "metadata": _json_safe(strain.metadata),
        }
    )


def serialize_stage_result(result: StageResult) -> dict[str, Any]:
    return _ordered(
        {
            "id": result.id,
            "stage": result.stage.value,
            "status": result.status.value,
            "request_ids": list(result.request_ids),
            "products": [_serialize_product(item) for item in result.products],
            "missing_inputs": [
                serialize_missing_input(item) for item in result.missing_inputs
            ],
            "required_approvals": [
                serialize_approval(item) for item in result.required_approvals
            ],
            "warnings": [serialize_warning(item) for item in result.warnings],
            "json_intermediate": _json_safe(result.json_intermediate),
            "protocol_artifacts": _json_safe(result.protocol_artifacts),
            "logs": list(result.logs),
        }
    )


def serialize_build_result(result: FullBuildResult) -> dict[str, Any]:
    return _ordered(
        {
            "schema_version": SCHEMA_VERSION,
            "kind": "build_result",
            "status": result.status.value,
            "plan": serialize_build_plan(result.plan)
            if isinstance(result.plan, BuildPlan)
            else _json_safe(result.plan),
            "stage_results": [
                serialize_stage_result(item) for item in result.stage_results
            ],
            "final_products": [
                _serialize_product(item) for item in result.final_products
            ],
            "missing_inputs": [
                serialize_missing_input(item) for item in result.missing_inputs
            ],
            "required_approvals": [
                serialize_approval(item) for item in result.required_approvals
            ],
            "warnings": [serialize_warning(item) for item in result.warnings],
            "summary": serialize_summary(result.summary)
            if result.summary is not None
            else None,
            "report": serialize_report(result.report)
            if result.report is not None
            else None,
            "graph": _serialize_graph(result.graph),
        }
    )


def serialize_summary(summary: Any) -> dict[str, Any]:
    return _serialize_dataclass(summary, expected_name="BuildSummary")


def serialize_report(report: Any) -> dict[str, Any]:
    return _serialize_dataclass(report, expected_name="BuildReport")


def to_json_dto(value: Any) -> Any:
    """Serialize a supported clean-domain value to JSON-only data."""

    serializers = (
        (BuildPlan, serialize_build_plan),
        (BuildRequest, serialize_build_request),
        (UnsupportedPlanningRecord, serialize_unsupported_planning_record),
        (StageResult, serialize_stage_result),
        (FullBuildResult, serialize_build_result),
        (BuildWarning, serialize_warning),
        (MissingBuildInput, serialize_missing_input),
        (RequiredApproval, serialize_approval),
        (IndexedPlasmid, serialize_plasmid),
        (IndexedBackbone, serialize_backbone),
        (IndexedReagent, serialize_reagent),
        (IndexedStrain, serialize_strain),
    )
    for expected_type, serializer in serializers:
        if isinstance(value, expected_type):
            return serializer(value)
    return _json_safe(value)


def dumps_json_dto(value: Any, *, indent: int | None = None) -> str:
    """Encode a public DTO deterministically as strict JSON."""

    return json.dumps(
        to_json_dto(value),
        allow_nan=False,
        ensure_ascii=False,
        indent=indent,
        separators=None if indent is not None else (",", ":"),
        sort_keys=True,
    )


def _serialize_product(product: Any) -> dict[str, Any]:
    if isinstance(product, IndexedPlasmid):
        return serialize_plasmid(product)
    if isinstance(product, IndexedStrain):
        return serialize_strain(product)
    raise SerializationError(
        f"Unsupported product type for JSON DTO: {type(product).__name__}"
    )


def _serialize_graph(graph: Any) -> dict[str, Any] | None:
    if graph is None:
        return None
    if type(graph).__name__ != "BuildGraph" or not hasattr(graph, "to_dict"):
        raise SerializationError(f"Unsupported graph type: {type(graph).__name__}")
    return _json_safe(graph.to_dict())


def _serialize_dataclass(value: Any, *, expected_name: str) -> dict[str, Any]:
    if type(value).__name__ != expected_name or not is_dataclass(value):
        raise SerializationError(
            f"Expected {expected_name}, got {type(value).__name__}"
        )
    return _ordered(
        {
            field.name: _json_safe(getattr(value, field.name))
            for field in fields(value)
            if not _is_omitted_key(field.name)
        }
    )


def _json_safe(value: Any) -> Any:
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise SerializationError("Non-finite floats are not valid JSON DTO values.")
        return value
    if isinstance(value, Enum):
        return _json_safe(value.value)
    if isinstance(value, (Path, PurePath)):
        return str(value)
    if isinstance(value, dict):
        safe: dict[str, Any] = {}
        for key, item in value.items():
            normalized_key = key.value if isinstance(key, Enum) else key
            if not isinstance(normalized_key, str):
                raise SerializationError("JSON DTO dictionary keys must be strings.")
            if _is_omitted_key(normalized_key):
                continue
            safe[normalized_key] = _json_safe(item)
        return _ordered(safe)
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    if isinstance(value, (set, frozenset)):
        safe_items = [_json_safe(item) for item in value]
        return sorted(
            safe_items,
            key=lambda item: json.dumps(item, sort_keys=True, separators=(",", ":")),
        )
    if is_dataclass(value):
        return _ordered(
            {
                field.name: _json_safe(getattr(value, field.name))
                for field in fields(value)
                if not _is_omitted_key(field.name)
            }
        )
    raise SerializationError(
        f"Unsupported value type for JSON DTO: {type(value).__name__}"
    )


def _ordered(data: dict[str, Any]) -> dict[str, Any]:
    return {key: data[key] for key in sorted(data)}


def _is_omitted_key(key: str) -> bool:
    lowered = key.lower()
    return lowered in _OMITTED_FIELDS or any(
        marker in lowered for marker in ("password", "credential", "token")
    )


def _list(data: dict[str, Any], key: str) -> list[Any]:
    value = data.get(key, [])
    if not isinstance(value, list):
        raise SerializationError(f"BuildPlan field '{key}' must be a list.")
    return value


def _deserialize_build_request(data: Any) -> BuildRequest:
    if not isinstance(data, dict):
        raise SerializationError("BuildRequest DTO must be a dictionary.")
    constraints = data.get("constraints", {})
    if not isinstance(constraints, dict):
        raise SerializationError("BuildRequest constraints must be a dictionary.")
    try:
        return BuildRequest(
            id=data["id"],
            stage=BuildStage(data["stage"]),
            source_identity=data["source_identity"],
            source_display_id=data.get("source_display_id"),
            source_kind=DesignKind(data["source_kind"]),
            parent_group=data.get("parent_group"),
            variant_index=data.get("variant_index"),
            constraints=constraints,
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise SerializationError("Invalid BuildRequest DTO.") from exc


def _deserialize_unsupported(data: Any) -> UnsupportedPlanningRecord:
    if not isinstance(data, dict):
        raise SerializationError("UnsupportedPlanningRecord DTO must be a dictionary.")
    try:
        return UnsupportedPlanningRecord(
            source_identity=data["source_identity"],
            source_display_id=data.get("source_display_id"),
            source_kind=DesignKind(data["source_kind"]),
            reason=data["reason"],
            metadata=data.get("metadata", {}),
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise SerializationError("Invalid UnsupportedPlanningRecord DTO.") from exc


def _deserialize_warning(data: Any) -> BuildWarning:
    if not isinstance(data, dict):
        raise SerializationError("BuildWarning DTO must be a dictionary.")
    try:
        return BuildWarning(
            code=data["code"],
            message=data["message"],
            stage=BuildStage(data["stage"]) if data.get("stage") else None,
            source_identity=data.get("source_identity"),
            metadata=data.get("metadata", {}),
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise SerializationError("Invalid BuildWarning DTO.") from exc
