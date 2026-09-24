"""Private simulator worker, launched as a file so core imports never load the SDK.

The trace adapter is qualified against Opentrons 8.8.2. SDK calls are
observed, not substituted; the official simulate() entry point runs both sides.
"""

import functools
import inspect
import json
import sys
from importlib.metadata import version
from pathlib import Path


def main() -> None:
    """Run one protocol in isolation and write a deterministic simulator trace."""

    from opentrons import protocol_api, types
    from opentrons.legacy_broker import LegacyBroker
    from opentrons.protocol_api import module_contexts
    from opentrons.protocol_api.disposal_locations import TrashBin
    from opentrons.protocol_api.instrument_context import _Unset
    from opentrons.protocol_api.protocol_context import _Unset as _ContextUnset
    from opentrons.simulate import simulate

    if version("opentrons") != "8.8.2":
        raise RuntimeError("The structured trace adapter requires opentrons==8.8.2.")

    def normalize(value):
        """Strip unstable SDK object identity while preserving command semantics."""

        if value is None or type(value) in (str, int, float, bool):
            return value
        if value is protocol_api.OFF_DECK:
            return {"off_deck": True}
        if isinstance(value, (_Unset, _ContextUnset)):
            return {"unset": True}
        if isinstance(value, dict):
            return {key: normalize(item) for key, item in value.items()}
        if isinstance(value, types.Location):
            return {"point": list(value.point), "labware": str(value.labware)}
        if isinstance(value, protocol_api.InstrumentContext):
            return {
                "instrument": value.name,
                "model": value.model,
                "mount": value.mount,
            }
        if isinstance(value, protocol_api.labware.Well):
            return {"well": value.well_name, "labware": str(value.parent)}
        if isinstance(value, protocol_api.labware.Labware):
            return {"labware": str(value)}
        if isinstance(value, TrashBin):
            return {"trash": True}  # Its slot is also retained in the command text.
        if isinstance(value, (list, tuple)):
            return [normalize(item) for item in value]
        if isinstance(value, protocol_api.Liquid):
            return {
                "name": value.name,
                "description": value.description,
                "display_color": value.display_color,
            }
        raise TypeError(f"Unhandled simulator trace value: {type(value).__name__}")

    actions = []
    calls = []
    depth = 0
    publish = LegacyBroker.publish

    def capture(self, topic, message):
        """Observe nested commands without replacing SDK execution."""

        nonlocal depth
        if topic == "command":
            if message["$"] == "before":
                if message["name"] != "command.COMMENT":
                    actions.append(
                        {
                            "name": message["name"],
                            "level": depth,
                            "payload": normalize(message["payload"]),
                        }
                    )
                depth += 1
            else:
                depth -= 1
        return publish(self, topic, message)

    LegacyBroker.publish = capture

    def observe(cls, method_name):
        """Capture bound SDK arguments that the ordinary command log omits."""

        original = getattr(cls, method_name)
        signature = inspect.signature(original)

        @functools.wraps(original)
        def wrapper(*args, **kwargs):
            """Record resolved arguments before delegating to the SDK method."""
            bound = signature.bind(*args, **kwargs)
            bound.apply_defaults()
            parameters = {
                key: value for key, value in bound.arguments.items() if key != "self"
            }
            calls.append(
                {
                    "method": f"{cls.__name__}.{method_name}",
                    "parameters": normalize(parameters),
                }
            )
            return original(*args, **kwargs)

        setattr(cls, method_name, wrapper)

    for cls, method in (
        (protocol_api.ProtocolContext, "load_module"),
        (protocol_api.ProtocolContext, "load_labware"),
        (protocol_api.ProtocolContext, "load_instrument"),
        (protocol_api.ProtocolContext, "define_liquid"),
        (module_contexts.TemperatureModuleContext, "load_labware"),
        (module_contexts.ThermocyclerContext, "load_labware"),
        (module_contexts.ThermocyclerContext, "execute_profile"),
        (protocol_api.InstrumentContext, "touch_tip"),
        (protocol_api.labware.Well, "load_liquid"),
    ):
        observe(cls, method)
    with Path("protocol.py").open(encoding="utf-8") as source:
        simulate(source)
    Path("trace.json").write_text(
        json.dumps(
            {
                "simulator_version": version("opentrons"),
                "actions": actions,
                "sdk_calls": calls,
            },
            indent=2,
            sort_keys=True,
        ),
        encoding="utf-8",
    )


if __name__ == "__main__":
    # Resolve the installed SDK, not the sibling opentrons.py source renderer.
    if sys.path[0] == str(Path(__file__).resolve().parent):
        del sys.path[0]
    main()
