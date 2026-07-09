"""Status enums and contract-level semantics helpers."""

from enum import Enum


class StageStatus(str, Enum):
    """Status for a single stage result.

    BLOCKED means expected inputs or approvals can unblock this stage later.
    FAILED means the request cannot proceed without changing design/options/
    collections/approval state.
    """

    SUCCESS = "success"
    PARTIAL_SUCCESS = "partial_success"
    BLOCKED = "blocked"
    FAILED = "failed"


class BuildStatus(str, Enum):
    """Status for full-build aggregate results."""

    SUCCESS = "success"
    PARTIAL_SUCCESS = "partial_success"
    FAILED = "failed"
