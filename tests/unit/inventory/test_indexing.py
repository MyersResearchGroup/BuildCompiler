import sbol2

from buildcompiler.constants import (
    ENGINEERED_PLASMID,
    FUSION_SITES,
    RESTRICTION_ENZYME_ASSEMBLY_SCAR,
)
from buildcompiler.inventory import index_collections


def _add_child(
    document: sbol2.Document,
    parent: sbol2.ComponentDefinition,
    *,
    display_id: str,
    role: str,
    sequence: str,
    start: int,
) -> sbol2.ComponentDefinition:
    definition = sbol2.ComponentDefinition(display_id)
    definition.roles = [role]
    child_sequence = sbol2.Sequence(f"{display_id}_sequence")
    child_sequence.elements = sequence
    child_sequence.encoding = sbol2.SBOL_ENCODING_IUPAC
    document.addSequence(child_sequence)
    definition.sequences = [child_sequence.identity]
    document.addComponentDefinition(definition)
    child = parent.components.create(f"{display_id}_component")
    child.definition = definition.identity
    annotation = parent.sequenceAnnotations.create(f"{display_id}_annotation")
    annotation.component = child.identity
    location = annotation.locations.createRange(f"{display_id}_range")
    location.start = start
    location.end = start + len(sequence) - 1
    return definition


def test_indexing_orders_fusion_sites_by_sequence_location_and_detects_acceptor():
    document = sbol2.Document()
    acceptor = sbol2.ComponentDefinition("acceptor")
    acceptor.roles = [ENGINEERED_PLASMID]
    document.addComponentDefinition(acceptor)
    _add_child(
        document,
        acceptor,
        display_id="Fusion_Site_B",
        role=RESTRICTION_ENZYME_ASSEMBLY_SCAR,
        sequence=FUSION_SITES["B"],
        start=40,
    )
    _add_child(
        document,
        acceptor,
        display_id="LacZ_placeholder",
        role="http://identifiers.org/so/SO:0000804",
        sequence="AAAA",
        start=5,
    )
    _add_child(
        document,
        acceptor,
        display_id="Fusion_Site_A",
        role=RESTRICTION_ENZYME_ASSEMBLY_SCAR,
        sequence=FUSION_SITES["A"],
        start=1,
    )
    implementation = sbol2.Implementation("acceptor_implementation")
    implementation.built = acceptor.identity
    document.addImplementation(implementation)

    inventory = index_collections(document)

    indexed = inventory.backbones_by_identity[acceptor.identity]
    assert indexed.metadata["fusion_sites"] == ("A", "B")
    assert acceptor.identity not in inventory.plasmids_by_identity
