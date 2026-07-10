from buildcompiler.api import BuildOptions, ProtocolMode


def test_build_options_defaults_match_contract():
    options = BuildOptions()

    assert options.execution.max_iterations == 5
    assert options.execution.continue_on_error is False
    assert options.protocol.mode == ProtocolMode.NONE
    assert options.protocol.simulate is False
    assert options.reagents.allow_reagent_purchase is False
    assert options.reagents.default_restriction_enzyme == "BsaI"
    assert options.reagents.default_ligase == "T4_DNA_ligase"
    assert options.domestication.allow_sequence_domestication_edits is False
    assert options.transformation.enabled is False
    assert options.transformation.chassis_identity is None
    assert options.transformation.chassis_display_id is None
    assert options.planning.combinatorial.max_variants == 256
    assert options.planning.combinatorial.allow_large_expansion is False
    assert options.planning.lvl2_search.max_exhaustive_region_count == 4
    assert options.planning.lvl2_search.allow_large_order_search is False
    assert options.reporting.include_rejected_routes is True
    assert options.reporting.max_rejected_routes == 3
    assert options.approvals.approved_processes == set()
    assert options.approvals.approved_approval_ids == set()


def test_mutable_defaults_are_isolated_across_instances():
    left = BuildOptions()
    right = BuildOptions()

    left.approvals.approved_processes.add("biosafety")
    left.approvals.approved_approval_ids.add("approval-1")
    left.planning.combinatorial.max_variants = 1024
    left.reporting.max_rejected_routes = 10
    left.transformation.chassis_identity = "dh5alpha"

    assert right.approvals.approved_processes == set()
    assert right.approvals.approved_approval_ids == set()
    assert right.planning.combinatorial.max_variants == 256
    assert right.reporting.max_rejected_routes == 3
    assert right.transformation.chassis_identity is None
