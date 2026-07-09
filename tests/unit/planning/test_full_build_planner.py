import sbol2

from buildcompiler.planning import FullBuildPlanner


def test_planner_mixed_inputs_returns_queues_and_warnings():
    sbol2.setHomespace("https://example.org")
    mod = sbol2.ModuleDefinition("https://example.org/mod")
    multi = sbol2.ComponentDefinition("https://example.org/multi")
    p = sbol2.ComponentDefinition("https://example.org/p")
    p.roles = ["http://identifiers.org/so/SO:0000167"]
    r = sbol2.ComponentDefinition("https://example.org/r")
    r.roles = ["http://identifiers.org/so/SO:0000139"]
    c = sbol2.ComponentDefinition("https://example.org/c")
    c.roles = ["http://identifiers.org/so/SO:0000316"]
    t = sbol2.ComponentDefinition("https://example.org/t")
    t.roles = ["http://identifiers.org/so/SO:0000141"]
    multi.components.create("c1").definition = p.identity
    multi.components.create("c2").definition = r.identity
    multi.components.create("c3").definition = c.identity
    multi.components.create("c4").definition = t.identity
    dom = sbol2.ComponentDefinition("https://example.org/dom")
    dom.roles = ["http://identifiers.org/so/SO:0000139"]

    planner = FullBuildPlanner()
    plan = planner.plan([mod, multi, dom, object()])

    assert len(plan.lvl2_requests) == 1
    assert len(plan.lvl1_requests) == 1
    assert len(plan.domestication_requests) == 1
    assert len(plan.unsupported) == 1
