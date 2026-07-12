from buildcompiler.adapters.pudu import plating_to_pudu_json


def test_plating_to_pudu_json_shape_and_values():
    payload = plating_to_pudu_json(
        bacterium_locations={"B2": "strain_b", "A1": "strain_a"},
        advanced_parameters={"replicates": 2},
    )

    assert payload == {
        "bacterium_locations": {"A1": "strain_a", "B2": "strain_b"},
        "replicates": 2,
    }


def test_plating_to_pudu_json_omits_empty_advanced_parameters():
    payload = plating_to_pudu_json(bacterium_locations={"A1": "strain_a"})

    assert payload == {"bacterium_locations": {"A1": "strain_a"}}
