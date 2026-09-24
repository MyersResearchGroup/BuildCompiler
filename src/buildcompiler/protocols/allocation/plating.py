"""Export the plated sample graph without recalculating a second plate layout."""

from buildcompiler.protocols.allocation.models import AllocatedProtocolPlan


def plating_layout(
    allocation: AllocatedProtocolPlan, *, dilution_factor: float
) -> dict:
    samples = {s.id: s for s in allocation.protocol.samples}
    locations = {p.sample_id: p.location for p in allocation.placements}
    plates = {}
    outputs = [samples[sid] for sid in allocation.protocol.output_sample_ids]
    # PUDU's export groups dilution first, then construct and replicate.
    for sample in sorted(outputs, key=lambda s: s.dilution):
        source = samples[sample.parent_ids[0]]
        while source.role == "dilution":
            source = samples[source.parent_ids[0]]
        location = locations[sample.id]
        plate = location.container_id.replace("agar_", "plate_")
        factor = dilution_factor**sample.dilution
        factor = int(factor) if float(factor).is_integer() else factor
        entry = plates.setdefault(plate, {}).setdefault(
            f"dilution_{sample.dilution}", {"ratio": f"1/{factor}", "wells": {}}
        )
        entry["wells"][location.well_name] = {
            "construct": ", ".join(source.contents),
            "source_well": locations[source.id].well_name,
            "replicate": sample.replicate,
        }
    return {"agar_plates": plates}
