from buildcompiler.reporting import BuildGraph, build_graph


def test_build_graph_contains_expected_nodes_edges(fake_full_build_result):
    result = fake_full_build_result(with_duplicates=True)
    graph = build_graph(result)
    assert isinstance(graph, BuildGraph)
    node_ids = {n.id for n in graph.nodes}
    assert any(i.startswith("stage_result:") for i in node_ids)
    assert any(i.startswith("missing:") for i in node_ids)
    assert any(i.startswith("approval:") for i in node_ids)
    rels = {(e.source, e.target, e.relationship) for e in graph.edges}
    assert any(r[2] == "produces" for r in rels)
    assert any(r[2] == "blocks" for r in rels)


def test_graph_dedup_and_json_safe_and_reporting_only(fake_full_build_result):
    result = fake_full_build_result(with_duplicates=True)
    before_stage_results = list(result.stage_results)
    graph = build_graph(result)
    assert len(graph.nodes) == len({n.id for n in graph.nodes})
    data = graph.to_dict()
    assert isinstance(data["nodes"], list)
    assert isinstance(graph.summary()["relationship_counts"], dict)
    assert result.stage_results == before_stage_results
