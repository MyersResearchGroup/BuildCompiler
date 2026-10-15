"""Lab methods and their shared input validation and well binding.

Each method module keeps its input decoders, configuration and hardware profile
beside its planner and allocator. Planners describe samples and operations without
well locations; allocators return a new plan with those locations filled in.
The helpers here share input-shape validation and well binding while each method
chooses its sample order, replicate expansion and liquid-handling steps.
"""

from collections.abc import Iterable, Iterator, Mapping, Sequence

from buildcompiler.protocols.models import OutputManifest, Sample, WellGrid, WellRef


def reaction_entries(
    payload: object, *, method: str, required: set[str]
) -> Iterator[tuple[int, Mapping[str, object]]]:
    """Validate the reaction-list envelope and yield entries in their input order.

    Methods still decode their own fields. Validation happens entry by entry so
    errors in an earlier reaction are reported before inspecting later ones.
    """
    if isinstance(payload, (str, bytes)) or not isinstance(payload, Sequence):
        raise TypeError(
            f"{method.capitalize()} JSON must be a sequence of reaction objects."
        )
    for index, entry in enumerate(payload):
        if not isinstance(entry, Mapping):
            raise TypeError(f"Each {method} entry must be an object.")
        if missing := required - entry.keys():
            raise ValueError(
                f"{method.capitalize()} {index} is missing {sorted(missing)}."
            )
        yield index, entry


def sequential_wells(
    sample_ids: Iterable[str],
    *,
    container_id: str,
    grid: WellGrid,
    start: int = 0,
) -> dict[str, WellRef]:
    """Place samples in the supplied order, rejecting positions outside the grid.

    The method chooses the sample order and starting offset. Existing plan
    validation guarantees unique sample IDs and checks the combined placements.
    """
    return {
        sample_id: WellRef(container_id=container_id, well_name=grid.name(index))
        for index, sample_id in enumerate(sample_ids, start)
    }


def bind_source_wells(
    samples: Iterable[Sample],
    inputs: OutputManifest,
    *,
    container_id: str,
    grid: WellGrid,
) -> dict[str, WellRef]:
    """Bind local samples to one upstream plate, preserving their source wells.

    Only the selected samples participate in the single-plate check. The new
    container ID describes the plate's role in this protocol; source sample IDs
    identify the physical aliquots even when material identities are shared.
    """
    upstream = {sample.id: sample.location for sample in inputs.samples}
    containers = set()
    locations = {}
    for sample in samples:
        if sample.source_sample_id not in upstream:
            raise ValueError(f"Missing upstream location for sample {sample.id}.")
        source = upstream[sample.source_sample_id]
        grid.index(source.well_name)
        containers.add(source.container_id)
        locations[sample.id] = WellRef(
            container_id=container_id, well_name=source.well_name
        )
    if len(containers) != 1:
        raise ValueError("Mapped samples must come from one source plate.")
    return locations
