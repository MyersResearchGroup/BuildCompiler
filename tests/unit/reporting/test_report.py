from buildcompiler.reporting import BuildReport, build_graph, build_report


def test_build_report_includes_sections_routes_blockers_and_serialization(fake_full_build_result):
    result = fake_full_build_result(with_routes=True)
    graph = build_graph(result)
    report = build_report(result, graph=graph)
    assert isinstance(report, BuildReport)
    assert report.stage_sections
    assert report.selected_routes
    assert report.rejected_alternatives
    assert report.missing_inputs
    assert report.required_approvals
    assert report.warnings
    assert report.next_actions
    assert report.dependency_chain
    assert report.graph_summary["node_count"] >= 1
    assert "blocked" in report.executive_summary.lower()
    assert '"status"' in report.to_json()
    assert "# Build Report" in report.to_markdown()


def test_build_report_deterministic(fake_full_build_result):
    result = fake_full_build_result(with_routes=True)
    graph = build_graph(result)
    assert build_report(result, graph=graph).to_json() == build_report(result, graph=graph).to_json()


def test_build_report_failed_status_mentions_failure_without_blockers(fake_full_build_result):
    result = fake_full_build_result(with_routes=False)
    result.missing_inputs = []
    result.required_approvals = []
    result.status = result.status.FAILED

    report = build_report(result)

    assert "failed" in report.executive_summary.lower()
    assert "completed" not in report.executive_summary.lower()
