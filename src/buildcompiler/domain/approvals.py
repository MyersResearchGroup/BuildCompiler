"""Approval contracts for expected gated processes."""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class ApprovalStatus(str, Enum):
    """Minimal approval state used by RequiredApproval."""

    REQUIRED = "required"
    APPROVED = "approved"


@dataclass
class RequiredApproval:
    """Approval record for a process required to proceed."""

    status: ApprovalStatus
    process: str
    reason: str
    metadata: dict[str, Any] = field(default_factory=dict)
