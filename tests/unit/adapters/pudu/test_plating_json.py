from buildcompiler.adapters.pudu import plating_to_pudu_json


def test_plating_to_pudu_json_shape_and_values():
    payload = plating_to_pudu_json(
        bacterium_locations={"strain_b": "B2", "strain_a": "A1"},
        advanced_parameters={"replicates": 2},
    )

    assert payload == {
        "bacterium_locations": {"strain_a": "A1", "strain_b": "B2"},
        "advanced_parameters": {"replicates": 2},
    }


def test_plating_to_pudu_json_defaults_advanced_parameters():
    payload = plating_to_pudu_json(bacterium_locations={"strain_a": "A1"})

    assert payload["advanced_parameters"] == {}
