from buildcompiler.domain import BuildStatus
from buildcompiler.reporting import BuildSummary, build_summary


def test_build_summary_counts_and_serializes(fake_full_build_result):
    result = fake_full_build_result(status=BuildStatus.PARTIAL_SUCCESS)
    summary = build_summary(result)
    assert isinstance(summary, BuildSummary)
    assert summary.status == BuildStatus.PARTIAL_SUCCESS
    assert summary.final_product_count == len(result.final_products)
    assert summary.missing_input_count == len(result.missing_inputs)
    assert summary.required_approval_count == len(result.required_approvals)
    assert summary.warning_count == len(result.warnings)
    assert summary.to_dict()["status"] == "partial_success"
    assert '"warning_count"' in summary.to_json()
    assert "# Build Summary" in summary.to_markdown()


def test_build_summary_deterministic(fake_full_build_result):
    result = fake_full_build_result()
    assert build_summary(result).to_json() == build_summary(result).to_json()
