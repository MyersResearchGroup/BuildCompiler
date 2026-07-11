import sbol2
from buildcompiler.api import BuildOptions
from buildcompiler.planning.combinatorial import expand_combinatorial_derivation

ROLE_URIS = [
    "http://identifiers.org/so/SO:0000167",
    "http://identifiers.org/so/SO:0000139",
    "http://identifiers.org/so/SO:0000316",
    "http://identifiers.org/so/SO:0000141",
]


def _build_comb(valid=True):
    sbol2.setHomespace("https://example.org")
    doc = sbol2.Document()
    template = sbol2.ComponentDefinition("https://example.org/template")
    doc.add(template)
    comb = sbol2.CombinatorialDerivation("https://example.org/comb", template.identity)
    doc.add(comb)
    roles = ROLE_URIS if valid else ROLE_URIS[:3]
    for i, role in enumerate(roles):
        vc = comb.variableComponents.create(f"https://example.org/var{i}")
        p = sbol2.ComponentDefinition(f"https://example.org/v{i}")
        p.roles = [role]
        doc.add(p)
        vc.variants = [p.identity]
    return comb


def test_expansion_and_blocking_behaviors():
    comb = _build_comb(valid=True)
    reqs, unsupported, warnings = expand_combinatorial_derivation(
        comb, options=BuildOptions()
    )
    assert len(reqs) == 1 and unsupported == [] and reqs[0].variant_index == 0
    limited = BuildOptions()
    limited.planning.combinatorial.max_variants = 0
    reqs2, unsupported2, warnings2 = expand_combinatorial_derivation(
        comb, options=limited
    )
    assert reqs2 == [] and unsupported2
    assert any(w.code == "planning.combinatorial.expansion_blocked" for w in warnings2)
    invalid = _build_comb(valid=False)
    reqs3, unsupported3, warnings3 = expand_combinatorial_derivation(
        invalid, options=BuildOptions()
    )
    assert reqs3 == [] and unsupported3
    assert any(w.code == "planning.combinatorial.invalid_variant" for w in warnings3)


def test_part_order_follows_template_sequence_not_variable_ids():
    sbol2.setHomespace("https://example.org")
    doc = sbol2.Document()
    template = sbol2.ComponentDefinition("https://example.org/template_seq")
    doc.add(template)
    template_components = []
    for idx in range(4):
        component = template.components.create(f"t_component_{idx}")
        component.definition = f"https://example.org/template_part_{idx}"
        template_components.append(component)
    comb = sbol2.CombinatorialDerivation(
        "https://example.org/comb_seq", template.identity
    )
    doc.add(comb)
    variable_specs = [
        ("var_z", template_components[0], ROLE_URIS[0], "p0"),
        ("var_y", template_components[1], ROLE_URIS[1], "p1"),
        ("var_x", template_components[2], ROLE_URIS[2], "p2"),
        ("var_w", template_components[3], ROLE_URIS[3], "p3"),
    ]
    expected_order = []
    for var_id, template_component, role, part_id in variable_specs:
        vc = comb.variableComponents.create(var_id)
        vc.variable = template_component.identity
        part = sbol2.ComponentDefinition(f"https://example.org/{part_id}")
        part.roles = [role]
        doc.add(part)
        expected_order.append(part.identity)
        vc.variants = [part.identity]
    reqs, unsupported, warnings = expand_combinatorial_derivation(
        comb, options=BuildOptions()
    )
    assert len(reqs) == 1 and unsupported == []
    assert reqs[0].constraints["part_order"] == expected_order
