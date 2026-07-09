import sbol2
from buildcompiler.planning.validation import (
    ordered_lvl1_parts,
    validate_lvl1_cardinality,
)

ROLE_URIS = [
    "http://identifiers.org/so/SO:0000167",
    "http://identifiers.org/so/SO:0000139",
    "http://identifiers.org/so/SO:0000316",
    "http://identifiers.org/so/SO:0000141",
]


def _mk_part(i, role, doc):
    p = sbol2.ComponentDefinition(f"https://example.org/p{i}")
    p.roles = [role]
    doc.add(p)
    return p


def _mk_lvl1(parts, doc):
    d = sbol2.ComponentDefinition("https://example.org/lvl1")
    for i, p in enumerate(parts):
        d.components.create(f"c{i}").definition = p.identity
    doc.add(d)
    return d


def test_validate_cardinality_and_order_fallback_and_warning():
    sbol2.setHomespace("https://example.org")
    doc = sbol2.Document()
    parts = [_mk_part(i, r, doc) for i, r in enumerate(ROLE_URIS)]
    lvl1 = _mk_lvl1(parts, doc)
    ok, warnings = validate_lvl1_cardinality(lvl1)
    assert ok is True
    assert warnings == []
    ordered, ow = ordered_lvl1_parts(lvl1)
    assert len(ordered) == 4


def test_validate_missing_or_duplicate_role_fails():
    sbol2.setHomespace("https://example.org")
    doc = sbol2.Document()
    p = _mk_part(0, ROLE_URIS[0], doc)
    lvl1 = _mk_lvl1([p, p, p, p], doc)
    ok, warnings = validate_lvl1_cardinality(lvl1)
    assert ok is False
    assert any(w.code == "lvl1.invalid_cardinality" for w in warnings)
