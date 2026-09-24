"""Legacy JSON entry points backed by BuildCompiler's native protocol compiler."""

from dataclasses import fields

from buildcompiler.protocols import (
    OpentronsPlatingProfile,
    PlatingConfig,
    PlatingRequest,
    ProtocolCompiler,
    assembly_request_from_json,
    bacterium_manifest_from_json,
    plasmid_manifest_from_json,
    transformation_request_from_json,
)


def compile_assembly_payload(payload, *, name):
    return ProtocolCompiler().compile(
        assembly_request_from_json(payload, request_id=name)
    )


def compile_transformation_payload(payload, *, plasmid_locations):
    request = transformation_request_from_json(
        payload, request_id="BuildCompiler Transformation"
    )
    inputs = (
        plasmid_manifest_from_json(plasmid_locations) if plasmid_locations else None
    )
    return ProtocolCompiler().compile(request, inputs=inputs)


def compile_plating_payload(payload, *, advanced_params=None):
    parameters = dict(payload)
    parameters.update(advanced_params or {})
    inputs = bacterium_manifest_from_json(parameters)
    parameters.pop("bacterium_locations")
    name = parameters.pop("protocol_name", "BuildCompiler Plating")
    config_names = {f.name for f in fields(PlatingConfig)}
    profile_names = {f.name for f in fields(OpentronsPlatingProfile)}
    config = PlatingConfig(
        **{key: value for key, value in parameters.items() if key in config_names}
    )
    profile = OpentronsPlatingProfile(
        **{key: value for key, value in parameters.items() if key in profile_names}
    )
    unknown = set(parameters) - config_names - profile_names
    if unknown:
        raise ValueError(
            f"Unsupported native plating parameters: {sorted(unknown)}. Use a supported target profile."
        )
    request = PlatingRequest(id=name, sample_ids=tuple(s.id for s in inputs.samples))
    return ProtocolCompiler(plating=config).compile(
        request, inputs=inputs, profile=profile
    )
