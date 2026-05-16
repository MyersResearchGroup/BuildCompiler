import sbol2
from Bio import Restriction
from Bio.Seq import Seq
from pydna.dseqrecord import Dseqrecord
from itertools import product
from buildcompiler.plasmid import Plasmid
from typing import List, Union, Tuple
from .constants import (
    CIRCULAR,
    DNA_TYPES,
    ENGINEERED_INSERT,
    ENGINEERED_PLASMID,
    FIVE_PRIME_OVERHANG,
    FUSION_SITES,
    LINEAR,
    PLASMID_VECTOR,
    RESTRICTION_ENZYME,
    RESTRICTION_ENZYME_ASSEMBLY_SCAR,
    SINGLE_STRANDED,
    THREE_PRIME_OVERHANG,
)

sbol2.Config.setHomespace("http://buildcompiler.org")
sbol2.Config.setOption(sbol2.ConfigOptions.SBOL_COMPLIANT_URIS, True)
sbol2.Config.setOption(sbol2.ConfigOptions.SBOL_TYPED_URIS, False)


class Assembly:
    """Creates an Assembly Plan.

    :param part_plasmids: List of part-in-backbone plasmids to be assembled.
    :param backbone_plasmid: Acceptor backbone into which parts are inserted.
    :param restriction_enzyme: SBOL Implementation representing the restriction enzyme
        (e.g. BsaI) used to digest parts during assembly.
    :param ligase: SBOL Implementation representing the ligase (e.g. T4) used to
        ligate digested parts.
    :param source_document: SBOL Document containing the source part/plasmid definitions.
    :param final_document: SBOL Document where assembled composite plasmid definitions
        will be written.
    :param composite_prefix: Prefix used when naming composite plasmid definitions.
        Defaults to 'composite'.

    """

    def __init__(  # TODO add fields for activity/agent/plan
        self,
        part_plasmids: List[Plasmid],
        backbone_plasmid: Plasmid,
        restriction_enzyme: sbol2.Implementation,
        ligase: sbol2.Implementation,
        source_document: sbol2.Document,
        final_document: sbol2.Document,
        composite_prefix: str = "composite",
    ):
        self.part_plasmids = part_plasmids
        self.backbone = backbone_plasmid
        self.restriction_enzyme = restriction_enzyme
        self.ligase = ligase
        self.extracted_parts = []  # list of tuples [ComponentDefinition, Sequence]
        self.source_document = source_document
        self.final_document = final_document
        self.composite_prefix = composite_prefix
        self.assembly_activity = self.initialize_assembly_activity()
        self.composites = []

    def run(
        self, include_extracted_parts: bool = False
    ) -> Tuple[List[Plasmid], sbol2.Document]:
        """Run the full Golden Gate assembly simulation.

        Executes the following steps in order:

        1. Calls :func:`part_digestion` on each plasmid in ``part_plasmids`` using
           ``restriction_enzyme``, appending extracted parts to ``source_document``.
        2. Calls :func:`backbone_digestion` on the first implementation of ``backbone``,
           appending the linearised backbone to ``source_document``.
        3. Calls :func:`ligation` on all extracted parts and the backbone to produce
           composite plasmid implementations, written to ``final_document``.
        4. Wraps each composite implementation in a :class:`Plasmid` object and returns
           the full list alongside the populated ``final_document``.

        :param include_extracted_parts: If ``True``, extracted part and backbone
            definitions are also written to ``final_document`` in addition to
            ``source_document``. Defaults to ``False``.
        :return: A tuple of (composite plasmids, final document), where composite
            plasmids is a list of :class:`Plasmid` objects built from the ligated
            implementations, and final document is the populated ``sbol2.Document``
            containing all assembly outputs.
        """
        for plasmid in self.part_plasmids:
            extracts_tuple_list, _ = part_digestion(
                plasmid,
                [self.restriction_enzyme],
                self.assembly_activity,
                self.source_document,
            )
            append_extracts_to_doc(extracts_tuple_list, self.source_document)
            if include_extracted_parts:
                append_extracts_to_doc(extracts_tuple_list, self.final_document)
            self.extracted_parts.append(extracts_tuple_list[0][0])

        extracts_tuple_list, _ = backbone_digestion(
            self.backbone,
            [self.restriction_enzyme],
            self.assembly_activity,
            self.source_document,
        )

        append_extracts_to_doc(extracts_tuple_list, self.source_document)
        if include_extracted_parts:
            append_extracts_to_doc(extracts_tuple_list, self.final_document)
        self.extracted_parts.append(extracts_tuple_list[0][0])

        self.composites = ligation(
            self.extracted_parts,
            self.assembly_activity,
            self.composite_prefix,
            self.source_document,
            self.final_document,
            self.ligase,
        )

        self.final_document.add(self.assembly_activity)

        composite_plasmid_objs = [
            Plasmid(
                self.final_document.get(impl.built),
                None,
                [impl],
                [None],
                self.source_document,
            )
            for impl in self.composites
        ]

        return composite_plasmid_objs, self.final_document

    def initialize_assembly_activity(self):
        activity = sbol2.Activity(f"{self.composite_prefix}_assembly")

        activity.name = "DNA Assembly"
        activity.types = "http://sbols.org/v2#build"

        activity_association = sbol2.Association("assemble_")

        assembly_plan = sbol2.Plan("assembly_plan")

        assembly_plan.description = "MoClo DNA Assembly With Opentrons OT2"

        activity_association.plan = assembly_plan

        activity_agent = sbol2.Agent("BuildCompiler")
        activity_association.agent = activity_agent

        activity.associations = [activity_association]

        return activity


def rebase_restriction_enzyme(name: str, **kwargs) -> sbol2.ComponentDefinition:
    """Creates an ComponentDefinition Restriction Enzyme Component from rebase.

    :param name: Name of the SBOL ExternallyDefined, used by PyDNA. Case sensitive, follow standard restriction enzyme nomenclature, i.e. 'BsaI'
    :param kwargs: Keyword arguments of any other ComponentDefinition attribute.
    :return: A ComponentDefinition object.
    """
    definition = f"http://rebase.neb.com/rebase/enz/{name}.html"  # TODO: replace with getting the URI from Enzyme when REBASE identifiers become available in biopython 1.8
    cd = sbol2.ComponentDefinition(name)
    cd.types = [sbol2.BIOPAX_PROTEIN]
    cd.name = name
    cd.roles = [RESTRICTION_ENZYME]
    cd.wasDerivedFrom = definition
    cd.description = f"Restriction enzyme {name} from REBASE."
    return cd


def dna_componentdefinition_with_sequence(
    identity: str, sequence: str, molecule: bool = False, **kwargs
) -> Tuple[sbol2.ComponentDefinition, sbol2.Sequence]:
    """Creates a DNA ComponentDefinition and its Sequence.

    :param identity: The identity of the Component. The identity of Sequence is also identity with the suffix '_seq'.
    :param sequence: The DNA sequence of the Component encoded in IUPAC.
    :param molecule: Boolean value: true if type should be DNA molecule, false if DNA region
    :param kwargs: Keyword arguments of any other Component attribute.
    :return: A tuple of ComponentDefinition and Sequence.
    """
    comp_seq = sbol2.Sequence(
        f"{identity}_seq", elements=sequence, encoding=sbol2.SBOL_ENCODING_IUPAC
    )
    dna_comp = sbol2.ComponentDefinition(
        identity,
        "http://www.biopax.org/release/biopax-level3.owl#Dna"
        if molecule
        else sbol2.BIOPAX_DNA,
        **kwargs,
    )
    dna_comp.sequences = [comp_seq]

    return dna_comp, comp_seq


def part_in_backbone_from_sbol(
    identity: Union[str, None],
    sbol_comp: sbol2.ComponentDefinition,
    part_location: List[int],
    part_roles: List[str],
    fusion_site_length: int,
    document: sbol2.Document,
    linear: bool = False,
    **kwargs,
) -> Tuple[sbol2.ComponentDefinition, sbol2.Sequence]:
    """Restructures a plasmid ComponentDefinition to follow the part-in-backbone pattern with scars following BP011.
    It overwrites the SBOL2 ComponentDefinition provided.
    A part inserted into a backbone is represented by a Component that includes both the part insert
    as a feature that is a SubComponent and the backbone as another SubComponent.
    For more information about BP011 visit https://github.com/SynBioDex/SBOL-examples/tree/main/SBOL/best-practices/BP011

    :param identity: The identity of the Component, is its a String it build a new SBOL Component, if None it adds on top of the input. The identity of Sequence is also identity with the suffix '_seq'.
    :param sbol_comp: The SBOL2 Component that will be used to create the part in backbone Component and Sequence.
    :param part_location: List of 2 integers that indicates the start and the end of the unitary part. Note that the index of the first location is 1, as is typical practice in biology, rather than 0, as is typical practice in computer science.
    :param part_roles: List of strings that indicates the roles to add on the part.
    :param fusion_site_length: Integer of the length of the fusion sites (eg. BsaI fusion site lenght is 4, SapI fusion site lenght is 3)
    :param linear: Boolean than indicates if the backbone is linear, defaults to False (cicular topology).
    :param kwargs: Keyword arguments of any other Component attribute.
    :return: ModuleDefinition in the form that sbolcanvas would output
    """
    if len(part_location) != 2:
        raise ValueError("The part_location only accepts 2 int values in a list.")
    if len(sbol_comp.sequences) != 1:
        raise ValueError(
            f"The reactant needs to have precisely one sequence. The input reactant has {len(sbol_comp.sequences)} sequences"
        )
    sequence = document.find(sbol_comp.sequences[0]).elements
    if identity is None:
        part_in_backbone_component = sbol_comp
        part_in_backbone_seq = document.find(sbol_comp.sequences[0]).elements
        part_in_backbone_component.sequences = [part_in_backbone_seq]
    else:
        part_in_backbone_component, part_in_backbone_seq = (
            dna_componentdefinition_with_sequence(identity, sequence, **kwargs)
        )
    # double stranded
    part_in_backbone_component.addRole("http://identifiers.org/so/SO:0000985")
    for part_role in part_roles:
        part_in_backbone_component.addRole(part_role)

    # creating part annotation
    part_location_comp = sbol2.Range(start=part_location[0], end=part_location[1])
    insertion_site_location1 = sbol2.Range(
        uri="insertloc1",
        start=part_location[0],
        end=part_location[0] + fusion_site_length,
    )  # order 1
    insertion_site_location2 = sbol2.Range(
        uri="insertloc2",
        start=part_location[1] - fusion_site_length,
        end=part_location[1],
    )  # order 3

    part_sequence_annotation = sbol2.SequenceAnnotation("part_sequence_annotation")
    part_sequence_annotation.roles = part_roles
    part_sequence_annotation.locations.add(part_location_comp)

    part_sequence_annotation.addRole(
        "https://identifiers.org/SO:0000915"
    )  # engineered insert
    insertion_sites_annotation = sbol2.SequenceAnnotation("insertion_sites_annotation")

    insertion_sites_annotation.locations.add(insertion_site_location1)
    insertion_sites_annotation.locations.add(insertion_site_location2)

    insertion_sites_annotation.roles = [
        "https://identifiers.org/so/SO:0000366"
    ]  # insertion site
    if linear:
        part_in_backbone_component.addRole(
            "http://identifiers.org/so/SO:0000987"
        )  # linear
        part_in_backbone_component.addRole(
            "http://identifiers.org/so/SO:0000804"
        )  # engineered region
        # creating backbone feature
        open_backbone_location1 = sbol2.Range(
            start=1, end=part_location[0] + fusion_site_length - 1
        )  # order 1
        open_backbone_location2 = sbol2.Range(
            start=part_location[1] - fusion_site_length, end=len(sequence)
        )  # order 3
        open_backbone_annotation = sbol2.SequenceAnnotation(
            locations=[open_backbone_location1, open_backbone_location2]
        )
    else:
        part_in_backbone_component.addRole(CIRCULAR)
        part_in_backbone_component.addRole(PLASMID_VECTOR)
        # creating backbone feature
        open_backbone_location1 = sbol2.Range(
            uri="backboneloc1", start=1, end=part_location[0] + fusion_site_length - 1
        )  # order 2
        open_backbone_location2 = sbol2.Range(
            uri="backboneloc2",
            start=part_location[1] - fusion_site_length,
            end=len(sequence),
        )  # order 1
        open_backbone_annotation = sbol2.SequenceAnnotation("open_backbone_annotation")
        open_backbone_annotation.locations.add(open_backbone_location1)
        open_backbone_annotation.locations.add(open_backbone_location2)

    part_in_backbone_component.sequenceAnnotations.add(part_sequence_annotation)
    part_in_backbone_component.sequenceAnnotations.add(insertion_sites_annotation)
    part_in_backbone_component.sequenceAnnotations.add(open_backbone_annotation)
    # use sequenceconstrait with precedes
    # backbone_dropout_meets = sbol3.Constraint(restriction='http://sbols.org/v3#meets', subject=part_sequence_annotation, object=open_backbone_annotation) #????
    backbone_dropout_meets = sbol2.sequenceconstraint.SequenceConstraint(
        uri="backbone_dropout_meets", restriction=sbol2.SBOL_RESTRICTION_PRECEDES
    )  # might need to add uri as param 2
    backbone_dropout_meets.subject = part_sequence_annotation
    backbone_dropout_meets.object = open_backbone_annotation

    part_in_backbone_component.sequenceConstraints.add(backbone_dropout_meets)
    # TODO: Add a branch to create a component without overwriting the WHOLE input component
    # removing repeated types and roles
    part_in_backbone_component.types = set(part_in_backbone_component.types)
    part_in_backbone_component.roles = set(part_in_backbone_component.roles)
    return part_in_backbone_component, part_in_backbone_seq


# helper function
def is_circular(obj: sbol2.ComponentDefinition) -> bool:
    """Check if an SBOL Component or Feature is circular.

    :param obj: design to be checked
    :return: true if circular
    """
    return any(n == sbol2.SO_CIRCULAR for n in obj.types) or any(
        n == ENGINEERED_PLASMID for n in obj.roles
    )  # temporarily allowing 'engineered plasmid' role to qualify as circular


def part_digestion(
    reactant: Plasmid,
    restriction_enzymes: List[sbol2.Implementation],
    assembly_activity: sbol2.Activity,
    document: sbol2.Document,
) -> Tuple[List[Tuple[sbol2.ComponentDefinition, sbol2.Sequence]], sbol2.Activity]:
    """Simulate restriction digestion of a part plasmid and extract the insert.

    Uses PyDNA to cut the reactant sequence, then constructs SBOL representations
    of the extracted part, its 5' and 3' overhangs, and any derived scar sequences.
    Each enzyme and the reactant implementation are recorded as usages on
    ``assembly_activity``.

    Expects the reactant to be circular with 2 digest products, or linear with 3
    (backbone | part | backbone). The shorter circular product or middle linear
    product is taken as the extracted insert.

    :param reactant: Part-in-backbone plasmid to digest.
    :param restriction_enzymes: Restriction enzyme implementations; the corresponding
        ``ComponentDefinition.name`` must match a PyDNA/ReBase enzyme name (e.g. ``'BsaI'``).
    :param assembly_activity: SBOL Activity to record reactant and enzyme usages on.
    :param document: Source SBOL document used to resolve referenced definitions and sequences.
    :return: A tuple of (extracts, activity), where extracts is a list of
        ``(ComponentDefinition, Sequence)`` pairs covering the extracted part,
        overhangs, and scar definitions, and activity is the updated ``assembly_activity``.
    :raises TypeError: If the reactant has no recognised DNA type.
    :raises ValueError: If the reactant does not have exactly one sequence, or if
        the number of digest products is unsupported for the reactant topology.
    """
    reactant_impl = reactant.plasmid_implementations[0]
    reactant_component_definition = reactant.plasmid_definition
    reactant_displayId = reactant_component_definition.displayId

    types = set(reactant_component_definition.types or [])

    if not types.intersection(DNA_TYPES):
        raise TypeError(
            f"The reactant should have a DNA type. Types found: {reactant_component_definition.types}."
        )
    if len(reactant_component_definition.sequences) != 1:
        raise ValueError(
            f"The reactant needs to have precisely one sequence. The input reactant has {len(reactant_component_definition.sequences)} sequences"
        )
    extracts_list = []
    restriction_enzymes_pydna = []

    assembly_activity.usages.add(
        sbol2.Usage(
            uri=f"{reactant_impl.displayId}",
            entity=reactant_impl.identity,
            role="http://sbols.org/v2#build",
        )
    )

    for enzyme_implmentation in restriction_enzymes:
        enzyme_definition = document.get(enzyme_implmentation.built)

        enzyme = Restriction.__dict__[enzyme_definition.name]
        restriction_enzymes_pydna.append(enzyme)

        enzyme_in_activity = False

        for usage in assembly_activity.usages:
            entity_URI = usage.entity
            # entity = document.get(entity_URI)

            if entity_URI == enzyme_implmentation.identity:
                enzyme_in_activity = True

        if not enzyme_in_activity:
            assembly_activity.usages.add(
                sbol2.Usage(
                    uri=f"{enzyme_definition.name}_enzyme",
                    entity=enzyme_implmentation.identity,
                    role="http://sbols.org/v2#build",
                )
            )

    # Inform topology to PyDNA, if not found assuming linear.
    if is_circular(reactant_component_definition):
        circular = True
        linear = False
    else:
        circular = False
        linear = True

    reactant_seq = reactant_component_definition.sequences[0]
    reactant_seq = document.getSequence(reactant_seq).elements
    # Dseqrecord is from PyDNA package with reactant sequence
    ds_reactant = Dseqrecord(reactant_seq, circular=circular)
    digested_reactant = ds_reactant.cut(restriction_enzymes_pydna)

    if len(digested_reactant) < 2 or len(digested_reactant) > 3:
        raise ValueError(
            f"Not supported number of products. Found{len(digested_reactant)}"
        )
    elif circular and len(digested_reactant) == 2:
        part_extract, _ = sorted(digested_reactant, key=len)
    elif linear and len(digested_reactant) == 3:
        _, part_extract, _ = digested_reactant
    else:
        raise ValueError(
            f"Reactant {reactant_component_definition.displayId} has no valid topology type, with {len(digested_reactant)} digested products, types: {reactant_component_definition.types}, and roles: {reactant_component_definition.roles}"
        )

    # Compute the length of single strand sticky ends or fusion sites
    product_5_prime_ss_strand, product_5_prime_ss_end = (
        part_extract.seq.five_prime_end()
    )
    product_3_prime_ss_strand, product_3_prime_ss_end = (
        part_extract.seq.three_prime_end()
    )
    product_sequence = str(part_extract.seq)
    prod_component_definition, prod_seq = dna_componentdefinition_with_sequence(
        identity=f"{reactant_component_definition.displayId}_extracted_part",
        sequence=product_sequence,
    )
    prod_component_definition.wasDerivedFrom = reactant_component_definition.identity
    extracts_list.append((prod_component_definition, prod_seq))

    # TODO explore how much granulatity in overhang representation is needed to preserve final composite annotations/components

    # five prime overhang
    five_prime_oh_definition = sbol2.ComponentDefinition(
        uri=f"{reactant_displayId}_five_prime_oh"
    )
    five_prime_oh_definition.addRole(FIVE_PRIME_OVERHANG)
    five_prime_oh_location = sbol2.Range(
        uri="five_prime_oh_location", start=1, end=len(product_5_prime_ss_end)
    )
    five_prime_oh_component = sbol2.Component(
        uri=f"{reactant_displayId}_five_prime_oh_component"
    )
    five_prime_oh_component.definition = five_prime_oh_definition
    five_prime_overhang_annotation = sbol2.SequenceAnnotation(uri="five_prime_overhang")
    five_prime_overhang_annotation.locations.add(five_prime_oh_location)

    # extracted part => point straight to part of interest
    part_location = sbol2.Range(
        uri=f"{reactant_displayId}_part_location",
        start=len(product_5_prime_ss_end) + 1,
        end=len(product_sequence) - len(product_3_prime_ss_end),
    )
    part_extract_annotation = sbol2.SequenceAnnotation(uri=f"{reactant_displayId}_part")
    part_extract_annotation.locations.add(part_location)

    # three prime overhang
    three_prime_oh_definition = sbol2.ComponentDefinition(
        uri=f"{reactant_displayId}_three_prime_oh"
    )
    three_prime_oh_definition.addRole(THREE_PRIME_OVERHANG)
    three_prime_oh_location = sbol2.Range(
        uri="three_prime_oh_location",
        start=len(product_sequence) - len(product_3_prime_ss_end) + 1,
        end=len(product_sequence),
    )
    three_prime_oh_component = sbol2.Component(
        uri=f"{reactant_displayId}_three_prime_oh_component"
    )
    three_prime_oh_component.definition = three_prime_oh_definition
    three_prime_overhang_annotation = sbol2.SequenceAnnotation(
        uri="three_prime_overhang"
    )
    three_prime_overhang_annotation.locations.add(three_prime_oh_location)

    prod_component_definition.components = [
        five_prime_oh_component,
        three_prime_oh_component,
    ]
    three_prime_overhang_annotation.component = three_prime_oh_component
    five_prime_overhang_annotation.component = five_prime_oh_component

    original_part_def_URI = ""

    # enccode ontologies of overhangs (may no longer be necessary)
    for definition in document.componentDefinitions:
        for seqURI in definition.sequences:
            seq = document.getSequence(seqURI)
            if seq.elements.lower() == Seq(product_3_prime_ss_end).reverse_complement():
                three_prime_oh_definition.wasDerivedFrom = definition.identity
                three_prime_sequence = sbol2.Sequence(
                    uri=f"{three_prime_oh_definition.displayId}_sequence",
                    elements=seq.elements,
                )
                three_prime_sequence.wasDerivedFrom = seq.identity
                three_prime_oh_definition.sequences = [three_prime_sequence]
                three_prime_oh_definition.types.append(SINGLE_STRANDED)

                extracts_list.append((three_prime_oh_definition, three_prime_sequence))
                extracts_list.append((definition, seq))  # add scars to list

            elif seq.elements.lower() == product_sequence[4:-4].lower():
                original_part_def_URI = definition.identity
                extracts_list.append((definition, seq))

            elif seq.elements.lower() == product_5_prime_ss_end:
                five_prime_oh_definition.wasDerivedFrom = definition.identity
                five_prime_sequence = sbol2.Sequence(
                    uri=f"{five_prime_oh_definition.displayId}_sequence",
                    elements=seq.elements,
                )
                five_prime_sequence.wasDerivedFrom = seq.identity
                five_prime_oh_definition.sequences = [five_prime_sequence]
                five_prime_oh_definition.types.append(SINGLE_STRANDED)

                extracts_list.append((five_prime_oh_definition, five_prime_sequence))
                extracts_list.append((definition, seq))

    # find + add original component to product def & annotation
    for comp in reactant_component_definition.components:
        if comp.definition == original_part_def_URI:
            new_comp = prod_component_definition.components.create(comp.displayId)
            new_comp.definition = comp.definition
            part_extract_annotation.component = new_comp

            original_cd = document.getComponentDefinition(comp.definition)
            seq = document.get(original_cd.sequences[0])

            new_seq = sbol2.Sequence(
                uri=f"{reactant_component_definition.displayId}_extracted_part_seq",
                elements=seq.elements,
                encoding=seq.encoding,
            )
            prod_component_definition.sequences.append(new_seq)
            extracts_list.append((new_comp, new_seq))

    prod_component_definition.sequenceAnnotations.add(three_prime_overhang_annotation)
    prod_component_definition.sequenceAnnotations.add(five_prime_overhang_annotation)
    prod_component_definition.sequenceAnnotations.add(part_extract_annotation)
    prod_component_definition.addRole(ENGINEERED_INSERT)
    prod_component_definition.addType(LINEAR)

    return extracts_list, assembly_activity


def backbone_digestion(
    reactant: Plasmid,
    restriction_enzymes: List[sbol2.Implementation],
    assembly_activity: sbol2.Activity,
    document: sbol2.Document,
) -> Tuple[List[Tuple[sbol2.ComponentDefinition, sbol2.Sequence]], sbol2.Activity]:
    """Simulate restriction digestion of a backbone plasmid and extract the linearised vector.

    Mirrors :func:`part_digestion` but targets the backbone: for a circular reactant
    with 2 digest products the longer fragment is taken as the open backbone; for a
    linear reactant with 3 products the outer prefix/suffix fragments are used.
    The resulting open-backbone ``ComponentDefinition``, its 5' and 3' overhangs, and
    any matched scar sequences are returned as SBOL objects. The reactant implementation
    and each enzyme are recorded as usages on ``assembly_activity``.

    :param reactant: SBOL Implementation whose ``built`` URI resolves to the
        backbone ``ComponentDefinition`` in ``document``.
    :param restriction_enzymes: Restriction enzyme implementations; the corresponding
        ``ComponentDefinition.name`` must match a PyDNA/ReBase enzyme name (e.g. ``'BsaI'``).
    :param assembly_activity: SBOL Activity to record reactant and enzyme usages on.
    :param document: Source SBOL document used to resolve referenced definitions and sequences.
    :return: A tuple of (extracts, activity), where extracts is a list of
        ``(ComponentDefinition, Sequence)`` pairs covering the open backbone,
        overhangs, and scar definitions, and activity is the updated ``assembly_activity``.
    :raises TypeError: If the reactant has no recognised DNA type.
    :raises ValueError: If the reactant does not have exactly one sequence, or if
        the number of digest products is unsupported for the reactant topology.
    """
    reactant_impl = reactant.plasmid_implementations[0]
    reactant_component_definition = document.get(reactant_impl.built)
    reactant_displayId = reactant_component_definition.displayId

    types = set(reactant_component_definition.types or [])

    if not types.intersection(DNA_TYPES):
        raise TypeError(
            f"The reactant should have a DNA type. Types found: {reactant.types}."
        )
    if len(reactant_component_definition.sequences) != 1:
        raise ValueError(
            f"The reactant needs to have precisely one sequence. The input reactant has {len(reactant.sequences)} sequences"
        )
    extracts_list = []
    restriction_enzymes_pydna = []

    assembly_activity.usages.add(
        sbol2.Usage(
            uri=f"{reactant_impl.displayId}",
            entity=reactant_impl.identity,
            role="http://sbols.org/v2#build",
        )
    )

    for enzyme_implmentation in restriction_enzymes:
        enzyme_definition = document.get(enzyme_implmentation.built)

        enzyme = Restriction.__dict__[enzyme_definition.name]
        restriction_enzymes_pydna.append(enzyme)

        enzyme_in_activity = False

        for usage in assembly_activity.usages:
            entity_URI = usage.entity
            # entity = document.get(entity_URI)

            if entity_URI == enzyme_implmentation.identity:
                enzyme_in_activity = True

        if not enzyme_in_activity:
            assembly_activity.usages.add(
                sbol2.Usage(
                    uri=f"{enzyme_definition.name}_enzyme",
                    entity=enzyme_implmentation.identity,
                    role="http://sbols.org/v2#build",
                )
            )

    # Inform topology to PyDNA, if not found assuming linear.
    if is_circular(reactant_component_definition):
        circular = True
        linear = False
    else:
        circular = False
        linear = True

    reactant_seq = reactant_component_definition.sequences[0]
    reactant_seq = document.getSequence(reactant_seq).elements
    # Dseqrecord is from PyDNA package with reactant sequence
    ds_reactant = Dseqrecord(reactant_seq, circular=circular)
    digested_reactant = ds_reactant.cut(restriction_enzymes_pydna)

    if len(digested_reactant) < 2 or len(digested_reactant) > 3:
        raise ValueError(
            f"Not supported number of products. Found: {len(digested_reactant)} after digesting {reactant_displayId}"
        )
    # TODO select them based on content rather than size.
    elif circular and len(digested_reactant) == 2:
        _, backbone = sorted(digested_reactant, key=len)
    elif linear and len(digested_reactant) == 3:
        prefix, part_extract, suffix = digested_reactant
    else:
        raise ValueError(
            f"Reactant {reactant_component_definition.displayId} has no valid topology type, with {len(digested_reactant)} digested products, types: {reactant_component_definition.types}, and roles: {reactant_component_definition.roles}"
        )

    # Compute the length of single strand sticky ends or fusion sites
    product_5_prime_ss_strand, product_5_prime_ss_end = backbone.seq.five_prime_end()
    product_3_prime_ss_strand, product_3_prime_ss_end = backbone.seq.three_prime_end()
    product_sequence = str(backbone.seq)
    prod_backbone_definition, prod_seq = dna_componentdefinition_with_sequence(
        identity=f"{reactant_component_definition.displayId}_extracted_backbone",
        sequence=product_sequence,
    )
    prod_backbone_definition.wasDerivedFrom = reactant_component_definition.identity
    extracts_list.append((prod_backbone_definition, prod_seq))

    # five prime overhang
    five_prime_oh_definition = sbol2.ComponentDefinition(
        uri=f"{reactant_displayId}_five_prime_oh"
    )
    five_prime_oh_definition.addRole(FIVE_PRIME_OVERHANG)
    five_prime_oh_location = sbol2.Range(
        uri="five_prime_oh_location", start=1, end=len(product_5_prime_ss_end)
    )
    five_prime_oh_component = sbol2.Component(
        uri=f"{reactant_displayId}_five_prime_oh_component"
    )
    five_prime_oh_component.definition = five_prime_oh_definition
    five_prime_overhang_annotation = sbol2.SequenceAnnotation(uri="five_prime_overhang")
    five_prime_overhang_annotation.locations.add(five_prime_oh_location)

    # extracted backbone => point straight to backbone from sbolcanvas
    backbone_location = sbol2.Range(
        uri=f"{reactant_displayId}_backbone_location",
        start=len(product_5_prime_ss_end) + 1,
        end=len(product_sequence) - len(product_3_prime_ss_end),
    )
    backbone_extract_annotation = sbol2.SequenceAnnotation(
        uri=f"{reactant_displayId}_backbone"
    )
    backbone_extract_annotation.locations.add(backbone_location)

    # three prime overhang
    three_prime_oh_definition = sbol2.ComponentDefinition(
        uri=f"{reactant_displayId}_three_prime_oh"
    )
    three_prime_oh_definition.addRole(THREE_PRIME_OVERHANG)
    three_prime_oh_location = sbol2.Range(
        uri="three_prime_oh_location",
        start=len(product_sequence) - len(product_3_prime_ss_end) + 1,
        end=len(product_sequence),
    )
    three_prime_oh_component = sbol2.Component(
        uri=f"{reactant_displayId}_three_prime_oh_component"
    )
    three_prime_oh_component.definition = three_prime_oh_definition
    three_prime_overhang_annotation = sbol2.SequenceAnnotation(
        uri="three_prime_overhang"
    )
    three_prime_overhang_annotation.locations.add(three_prime_oh_location)

    prod_backbone_definition.components = [
        five_prime_oh_component,
        three_prime_oh_component,
    ]
    three_prime_overhang_annotation.component = three_prime_oh_component
    five_prime_overhang_annotation.component = five_prime_oh_component

    # check these lines
    original_backbone_def_URI = ""

    # enccode ontologies of overhangs
    for definition in document.componentDefinitions:
        for seqURI in definition.sequences:
            seq = document.getSequence(seqURI)
            if seq.elements.lower() == Seq(product_3_prime_ss_end).reverse_complement():
                three_prime_oh_definition.wasDerivedFrom = definition.identity
                three_prime_sequence = sbol2.Sequence(
                    uri=f"{three_prime_oh_definition.displayId}_sequence",
                    elements=seq.elements,
                )
                three_prime_sequence.wasDerivedFrom = seq.identity
                three_prime_oh_definition.sequences = [three_prime_sequence]
                three_prime_oh_definition.types.append(SINGLE_STRANDED)

                extracts_list.append((three_prime_oh_definition, three_prime_sequence))
                extracts_list.append((definition, seq))  # add scars to list

            elif seq.elements.lower() == product_sequence[4:-4].lower():
                original_backbone_def_URI = definition.identity
                extracts_list.append((definition, seq))

            elif seq.elements.lower() == product_5_prime_ss_end:
                five_prime_oh_definition.wasDerivedFrom = definition.identity
                five_prime_sequence = sbol2.Sequence(
                    uri=f"{five_prime_oh_definition.displayId}_sequence",
                    elements=seq.elements,
                )
                five_prime_sequence.wasDerivedFrom = seq.identity
                five_prime_oh_definition.sequences = [five_prime_sequence]
                five_prime_oh_definition.types.append(SINGLE_STRANDED)

                extracts_list.append((five_prime_oh_definition, five_prime_sequence))
                extracts_list.append((definition, seq))

    # find + add original component to product def & annotation
    for comp in reactant_component_definition.components:
        if comp.definition == original_backbone_def_URI:
            prod_backbone_definition.components.add(comp)
            backbone_extract_annotation.component = comp

    prod_backbone_definition.sequenceAnnotations.add(three_prime_overhang_annotation)
    prod_backbone_definition.sequenceAnnotations.add(five_prime_overhang_annotation)
    prod_backbone_definition.sequenceAnnotations.add(backbone_extract_annotation)
    prod_backbone_definition.addRole(PLASMID_VECTOR)

    return extracts_list, assembly_activity


def number_to_suffix(n):
    """Helper function for generating scar suffixes of the form: :math:`S=(A,B,C,…,Z,AA,AB,AC,…,AZ,BA,BB,…, S_n)`

    :param n: Number to convert to character suffix
    :return: Character suffix corresponding to n
    """
    suffix = ""
    while n > 0:
        n -= 1
        remainder = n % 26
        suffix = chr(ord("A") + remainder) + suffix
        n = n // 26
    return suffix


def ligation(
    reactants: List[sbol2.ComponentDefinition],
    assembly_activity: sbol2.Activity,
    composite_prefix: str,
    source_document: sbol2.Document,
    final_document: sbol2.Document,
    ligase: sbol2.Implementation,
) -> List[sbol2.Implementation]:
    """Ligates Components using base complementarity and creates product Components and a ligation Interaction.

    :param reactants: Extracted part and backbone ``ComponentDefinition`` objects to ligate.
    :param assembly_activity: SBOL activity to track assembly inputs & outputs
    :param composite_prefix: Prefix used when naming composite ``ComponentDefinition``
        and ``Implementation`` identities.
    :param source_document: SBOL Document containing all reactant definitions.
    :param final_document: SBOL Document that receives composite definitions and implementations.
    :param ligase: SBOL Implementation of the ligase (e.g. T4).
    :return: List of ``sbol2.Implementation`` objects, one per composite plasmid generated.
    """
    enzyme_definition = source_document.get(ligase.built)

    assembly_activity.usages.add(
        sbol2.Usage(
            uri=f"{enzyme_definition.name}",
            entity=ligase.identity,
            role="http://sbols.org/v2#build",
        )
    )

    # Create a dictionary that maps each first and last 4 letters to a list of strings that have those letters.
    reactant_parts = []
    fusion_sites_set = set()
    for reactant in reactants:
        fusion_site_3prime_length = (
            reactant.sequenceAnnotations[0].locations[0].end
            - reactant.sequenceAnnotations[0].locations[0].start
        )
        fusion_site_5prime_length = (
            reactant.sequenceAnnotations[1].locations[0].end
            - reactant.sequenceAnnotations[1].locations[0].start
        )
        if fusion_site_3prime_length == fusion_site_5prime_length:
            fusion_site_length = (
                fusion_site_3prime_length + 1
            )  # if the fusion site is 4 bp long, the start will be 1 and end 4, 4-1 = 3, so we add 1 to get 4.
            fusion_sites_set.add(fusion_site_length)
            if len(fusion_sites_set) > 1:
                raise ValueError(
                    f"Fusion sites of different length within different parts. Check {reactant.identity} "
                )
        else:
            raise ValueError(
                f"Fusion sites of different length within the same part. Check {reactant.identity}"
            )
        if PLASMID_VECTOR in reactant.roles:
            reactant_parts.append(reactant)
        elif ENGINEERED_INSERT in reactant.roles:
            reactant_parts.append(reactant)
        else:
            raise ValueError(f"Part {reactant.identity} does not have a valid role")

    # remove the backbones if any from the reactants, to create the composite
    groups = {}
    for reactant in reactant_parts:
        reactant_seq = reactant.sequences[0]
        first_four_letters = (
            source_document.getSequence(reactant_seq)
            .elements[:fusion_site_length]
            .lower()
        )
        last_four_letters = (
            source_document.getSequence(reactant_seq)
            .elements[-fusion_site_length:]
            .lower()
        )
        part_syntax = f"{first_four_letters}_{last_four_letters}"
        if part_syntax not in groups:
            groups[part_syntax] = []
            groups[part_syntax].append(reactant)
        else:
            groups[part_syntax].append(reactant)
    # groups is a dictionary of lists of parts that have the same first and last 4 letters
    # list_of_combinations_per_assembly is a list of tuples of parts that can be ligated together
    list_of_parts_per_combination = list(product(*groups.values()))  # cartesian product
    # create list_of_composites_per_assembly from list_of_combinations_per_assembly
    list_of_composites_per_assembly = []
    for combination in list_of_parts_per_combination:
        list_of_parts_per_composite = [combination[0]]
        insert_sequence_uri = combination[0].sequences[0]
        insert_sequence = source_document.getSequence(insert_sequence_uri).elements
        remaining_parts = list(combination[1:])
        insert_3prime_match_id = None
        it = 1
        while remaining_parts:
            remaining_parts_before = len(remaining_parts)
            for part in remaining_parts:
                # match insert sequence 5' to part 3'
                part_sequence_uri = part.sequences[0]
                # check reverse match
                if (
                    source_document.getSequence(part_sequence_uri)
                    .elements[-fusion_site_length:]
                    .lower()
                    == insert_sequence[:fusion_site_length].lower()
                ):
                    insert_3prime_match_id = part.identity
                if (
                    source_document.getSequence(part_sequence_uri)
                    .elements[:fusion_site_length]
                    .lower()
                    == insert_sequence[-fusion_site_length:].lower()
                ):
                    if (
                        len(remaining_parts) == 1
                        and part.identity == insert_3prime_match_id
                    ):  # check flag and match backbone 5' on final part 3'
                        insert_sequence = (
                            insert_sequence[:-fusion_site_length]
                            + source_document.getSequence(part_sequence_uri).elements
                        )
                        list_of_parts_per_composite.append(part)
                        remaining_parts.remove(part)
                    elif len(remaining_parts) > 1:
                        insert_sequence = (
                            insert_sequence[:-fusion_site_length]
                            + source_document.getSequence(part_sequence_uri).elements
                        )
                        list_of_parts_per_composite.append(part)
                        remaining_parts.remove(part)
                # match backbone 5' to insert sequence 3', set flag
                remaining_parts_after = len(remaining_parts)

            if remaining_parts_before == remaining_parts_after:
                it += 1
            if it > 5:  # 5 was chosen arbitrarily to avoid infinite loops
                print(groups)
                raise ValueError(
                    "No match found, check the parts and their fusion sites"
                )
        list_of_composites_per_assembly.append(list_of_parts_per_composite)

    # transform list_of_parts_per_assembly into list of composites
    product_impl_list = []
    composite_number = 0

    for composite in list_of_composites_per_assembly:  # a composite of the form [A,B,C]
        # calculate sequence
        composite_sequence_str = ""
        prev_three_prime = (
            composite[len(composite) - 1].components[1].definition
        )  # componentdefinitionuri
        prev_three_prime_definition = source_document.getComponentDefinition(
            prev_three_prime
        )
        anno_list = []

        part_extract_definitions = []
        for part_extract in composite:
            part_extract_sequence_uri = part_extract.sequences[0]
            part_extract_sequence = source_document.getSequence(
                part_extract_sequence_uri
            ).elements
            temp_extract_components = []

            for comp in part_extract.components:
                if (
                    FIVE_PRIME_OVERHANG
                    in source_document.getComponentDefinition(comp.definition).roles
                ):
                    sequence = source_document.getSequence(
                        prev_three_prime_definition.sequences[0]
                    ).elements

                    fusion_site = None

                    for (
                        key,
                        seq,
                    ) in (
                        FUSION_SITES.items()
                    ):  # TODO error handling for fusion site not found?
                        if seq == sequence.upper():
                            fusion_site = key

                    scar_definition = sbol2.ComponentDefinition(
                        uri=f"Ligation_Scar_{fusion_site}"
                    )
                    scar_sequence = sbol2.Sequence(
                        uri=f"Ligation_Scar_{fusion_site}_sequence",
                        elements=sequence,
                    )
                    scar_definition.sequences = [scar_sequence]
                    scar_definition.wasDerivedFrom = [comp.definition, prev_three_prime]
                    scar_definition.roles = [RESTRICTION_ENZYME_ASSEMBLY_SCAR]
                    temp_extract_components.append(scar_definition.identity)

                    add_object_to_doc(scar_definition, source_document)
                    add_object_to_doc(scar_sequence, source_document)

                    add_object_to_doc(scar_definition, final_document)
                    add_object_to_doc(scar_sequence, final_document)

                    scar_location = sbol2.Range(
                        uri=f"Ligation_Scar_{fusion_site}_location",
                        start=len(composite_sequence_str) + 1,
                        end=len(composite_sequence_str) + fusion_site_length,
                    )
                    scar_anno = sbol2.SequenceAnnotation(
                        uri=f"Ligation_Scar_{fusion_site}_annotation"
                    )
                    scar_anno.locations.add(scar_location)
                    anno_list.append(scar_anno)
                elif (
                    THREE_PRIME_OVERHANG
                    in source_document.getComponentDefinition(comp.definition).roles
                ):  # three prime
                    prev_three_prime = comp.definition
                    prev_three_prime_definition = (
                        source_document.getComponentDefinition(prev_three_prime)
                    )
                else:
                    anno_prefix = comp.displayId

                    matching_anno_prefix = [
                        a.displayId
                        for a in anno_list
                        if a.displayId.startswith(f"{comp.displayId}_")
                    ]
                    if matching_anno_prefix:
                        anno_prefix = f"{comp.displayId}_{len(matching_anno_prefix)}"

                    temp_extract_components.append(comp.definition)
                    comp_location = sbol2.Range(
                        uri=f"{anno_prefix}_location",
                        start=len(composite_sequence_str) + fusion_site_length + 1,
                        end=len(composite_sequence_str)
                        + len(part_extract_sequence[:-4]),
                    )
                    comp_anno = sbol2.SequenceAnnotation(
                        uri=f"{anno_prefix}_annotation"
                    )
                    comp_anno.locations.add(comp_location)
                    anno_list.append(comp_anno)

            part_extract_definitions.extend(temp_extract_components)

            composite_sequence_str = (
                composite_sequence_str + part_extract_sequence[:-fusion_site_length]
            )  # needs a version for linear

        suffix = f"_{composite_number}" if composite_number > 0 else ""

        # create dna component and sequence
        composite_component_definition, composite_seq = (
            dna_componentdefinition_with_sequence(
                f"{composite_prefix}{suffix}",
                composite_sequence_str,
                molecule=True,
            )
        )
        composite_component_definition.name = f"{composite_prefix}{suffix}"
        composite_component_definition.addRole(ENGINEERED_PLASMID)
        composite_component_definition.addType(CIRCULAR)

        prev_part_extract = None

        for i, definition in enumerate(part_extract_definitions):
            def_object = source_document.getComponentDefinition(definition)
            comp = sbol2.Component(uri=def_object.displayId)
            comp.definition = definition

            composite_component_definition.components.add(comp)
            anno_list[i].component = comp

            if prev_part_extract:
                _create_precedes_restriction(
                    composite_component_definition, prev_part_extract, comp
                )

            prev_part_extract = comp

        composite_component_definition.sequenceAnnotations = anno_list

        composite_implementation = sbol2.Implementation(
            f"{composite_component_definition.displayId}_impl"
        )
        composite_implementation.built = composite_component_definition.identity
        composite_implementation.wasGeneratedBy = assembly_activity.identity

        source_document.add_list(
            [composite_component_definition, composite_seq, composite_implementation]
        )

        final_document.add_list(
            [composite_component_definition, composite_seq, composite_implementation]
        )

        product_impl_list.append(composite_implementation)
        composite_number += 1

    return product_impl_list  # TODO instead of returning list of products CDs to append to doc, append all CDs and return list of their implementations


def append_extracts_to_doc(
    extract_tuples: List[Tuple[sbol2.ComponentDefinition, sbol2.Sequence]],
    doc: sbol2.Document,
) -> None:
    """Helper function for batch adding :class:`sbol2.ComponentDefinition` and :class:`sbol2.Sequence` to an :class:`sbol2.Document`

    :param extract_tuples: list of tuples of :class:`sbol2.ComponentDefinition` and :class:`sbol2.Sequence`
    :param doc: document which the content is to be added to
    """
    for extract, sequence in extract_tuples:
        try:
            add_object_to_doc(extract, doc)
            add_object_to_doc(sequence, doc)
        except Exception as e:
            if "<SBOLErrorCode.SBOL_ERROR_URI_NOT_UNIQUE: 17>" in str(e):
                pass
            else:
                raise e


def add_object_to_doc(
    obj: sbol2.SBOLObject,
    doc: sbol2.Document,
) -> None:
    try:
        doc.add(obj)
    except Exception as e:
        if "<SBOLErrorCode.SBOL_ERROR_URI_NOT_UNIQUE: 17>" in str(e):
            pass
        else:
            raise e


def _create_precedes_restriction(
    parent_definition: sbol2.ComponentDefinition,
    subject: sbol2.Component,
    object: sbol2.Component,
):
    constraint = parent_definition.sequenceConstraints.create(
        f"{object.displayId}_{subject.displayId}"
    )
    constraint.subject = subject
    constraint.object = object
    constraint.restriction = sbol2.SBOL_RESTRICTION_PRECEDES
