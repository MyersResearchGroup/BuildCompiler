from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from typing import Any

from buildcompiler.domain import BuildStatus, FullBuildResult


@dataclass
class BuildSummary:
    status: BuildStatus
    final_product_count: int
    missing_input_count: int
    required_approval_count: int
    warning_count: int

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["status"] = self.status.value
        return data

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), sort_keys=True)

    def to_markdown(self) -> str:
        return "\n".join(
            [
                "# Build Summary",
                f"- Status: `{self.status.value}`",
                f"- Final products: `{self.final_product_count}`",
                f"- Missing inputs: `{self.missing_input_count}`",
                f"- Required approvals: `{self.required_approval_count}`",
                f"- Warnings: `{self.warning_count}`",
            ]
        )


def build_summary(result: FullBuildResult) -> BuildSummary:
    return BuildSummary(
        status=result.status,
        final_product_count=len(result.final_products),
        missing_input_count=len(result.missing_inputs),
        required_approval_count=len(result.required_approvals),
        warning_count=len(result.warnings),
    )
