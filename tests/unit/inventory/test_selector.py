from buildcompiler.api import BuildOptions
from buildcompiler.domain import IndexedPlasmid, MaterialState
from buildcompiler.inventory import CompatibilitySelector, Inventory


def _plasmid(
    identity: str, insert: str, *, state=MaterialState.PLANNED, source="collection"
) -> IndexedPlasmid:
    return IndexedPlasmid(
        identity=identity,
        state=state,
        metadata={
            "insert_identities": [insert],
            "source": source,
            "antibiotic": "Ampicillin",
        },
    )


def test_lvl1_missing_parts_are_reported_not_raised():
    inv = Inventory(plasmids=[_plasmid("https://e/p1", "https://e/part1")])
    sel = CompatibilitySelector(inv)
    route = sel.select_lvl1_route(
        request_id="r1", part_identities=["https://e/part1", "https://e/part2"]
    ).selected
    assert route is not None
    assert route.missing_part_identities == ("https://e/part2",)


def test_lvl1_prefers_existing_material_in_tie():
    inv = Inventory(
        plasmids=[
            _plasmid(
                "https://e/a",
                "https://e/part",
                source="generated",
                state=MaterialState.GENERATED,
            ),
            _plasmid(
                "https://e/b",
                "https://e/part",
                source="collection",
                state=MaterialState.GENERATED,
            ),
        ]
    )
    sel = CompatibilitySelector(inv)
    route = sel.select_lvl1_route(
        request_id="r1", part_identities=["https://e/part"]
    ).selected
    assert route.selected_part_plasmids[0].identity == "https://e/b"


def test_lvl1_hard_constraints_override_selection_preference():
    inv = Inventory(
        plasmids=[_plasmid("https://e/a", "https://e/part", source="generated")]
    )
    opts = BuildOptions()
    opts.selection.prefer_existing_collection_material = True
    sel = CompatibilitySelector(inv, options=opts)
    route = sel.select_lvl1_route(
        request_id="r1",
        part_identities=["https://e/part"],
        constraints={"allowed_identities": ["https://e/a"]},
    ).selected
    assert route.selected_part_plasmids[0].identity == "https://e/a"


def test_lvl2_large_order_search_not_silent_without_opt_in():
    inv = Inventory()
    sel = CompatibilitySelector(inv)
    out = sel.select_lvl2_route(
        request_id="r2", region_identities=["a", "b", "c", "d", "e"]
    )
    assert out.selected is None
    assert out.rejected


def test_lvl2_rejected_alternatives_capped_at_3():
    inv = Inventory(
        plasmids=[_plasmid(f"https://e/p{i}", f"https://e/r{i}") for i in range(4)]
    )
    sel = CompatibilitySelector(inv)
    out = sel.select_lvl2_route(
        request_id="r3",
        region_identities=[
            "https://e/r0",
            "https://e/r1",
            "https://e/r2",
            "https://e/r3",
        ],
    )
    assert out.selected is not None
    assert len(out.rejected) == 3


def test_lvl2_constrained_order_must_match_requested_regions():
    inv = Inventory(
        plasmids=[
            _plasmid("https://e/p0", "https://e/r0"),
            _plasmid("https://e/p1", "https://e/r1"),
        ]
    )
    sel = CompatibilitySelector(inv)
    out = sel.select_lvl2_route(
        request_id="r4",
        region_identities=["https://e/r0", "https://e/r1"],
        constraints={"region_order": ["https://e/r0"]},
    )
    assert out.selected is None
    assert out.rejected
    assert out.rejected[0].missing_region_identities == ("https://e/r0", "https://e/r1")
