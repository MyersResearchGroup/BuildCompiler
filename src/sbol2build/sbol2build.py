import sbol2
from Bio import Restriction
from Bio.Seq import Seq
from pydna.dseqrecord import Dseqrecord
from itertools import product
from typing import List, Union, Tuple
from .constants import DNA_TYPES

sbol2.Config.setHomespace("https://SBOL2Build.org")
sbol2.Config.setOption(sbol2.ConfigOptions.SBOL_COMPLIANT_URIS, True)
sbol2.Config.setOption(sbol2.ConfigOptions.SBOL_TYPED_URIS, False)


def rebase_restriction_enzyme(name: str, **kwargs) -> sbol2.ComponentDefinition:
    """Creates an ComponentDefinition Restriction Enzyme Component from rebase.

    :param name: Name of the SBOL ExternallyDefined, used by PyDNA. Case sensitive, follow standard restriction enzyme nomenclature, i.e. 'BsaI'
    :param kwargs: Keyword arguments of any other ComponentDefinition attribute.
    :return: A ComponentDefinition object.
    """
    definition = f"http://rebase.neb.com/rebase/enz/{name}.html"  # TODO: replace with getting the URI from Enzyme when REBASE identifiers become available in biopython 1.8
    cd = sbol2.ComponentDefinition(name)
    cd.types = sbol2.BIOPAX_PROTEIN
    cd.name = name
    cd.roles = ["http://identifiers.org/obi/OBI:0000732"]
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
        part_in_backbone_component.addRole(
            "http://identifiers.org/so/SO:0000988"
        )  # circular
        part_in_backbone_component.addRole(
            "https://identifiers.org/so/SO:0000755"
        )  # plasmid vector
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
        n == "http://identifiers.org/so/SO:0000637" for n in obj.roles
    )  # temporarily allowing 'engineered plasmid' role to qualify as circular


def part_digestion(
    reactant: Union[sbol2.ComponentDefinition, sbol2.ModuleDefinition],
    restriction_enzymes: List[sbol2.ComponentDefinition],
    assembly_plan: sbol2.ModuleDefinition,
    document: sbol2.Document,
    **kwargs,
) -> Tuple[
    List[Tuple[sbol2.ComponentDefinition, sbol2.Sequence]], sbol2.ModuleDefinition
]:
    """Runs a simulated digestion on the top level sequence in the reactant ComponentDefinition or ModuleDefinition with the given restriciton enzymes, creating a extracted part ComponentDefinition, a digestion Interaction, and converts existing scars to 5' and 3' overhangs.
    The product ComponentDefinition is assumed the open backbone in this case.

    Written for use with the SBOL2.3 output of https://sbolcanvas.org

    :param reactant: DNA to be digested as SBOL ComponentDefinition or ModuleDefinition, usually a part_in_backbone. ComponentDefinition is the best-practice type for plasmids..
    :param restriction_enzymes: Restriction enzymes as :class:`sbol2.ComponentDefinition`
                                (generate with :func:`rebase_restriction_enzyme`).
    :param assembly_plan: SBOL ModuleDefinition to contain the functional components, interactions, and participations
    :param document: original SBOL2 document to be used to extract referenced objects.
    :return: A tuple of a list ComponentDefinitions and Sequences, and an assembly plan ModuleDefinition.
    """
    if type(reactant) is sbol2.ModuleDefinition:
        # extract component definition from module
        reactant_displayId = reactant.functionalComponents[0].displayId
        reactant_def_URI = reactant.functionalComponents[0].definition
        reactant_component_definition = document.getComponentDefinition(
            reactant_def_URI
        )
    else:
        reactant_displayId = reactant.displayId
        reactant_component_definition = reactant

    types = set(reactant_component_definition.types or [])

    if not types.intersection(DNA_TYPES):
        raise TypeError(
            f"The reactant should have a DNA type. Types found: {reactant.types}."
        )
    if len(reactant_component_definition.sequences) != 1:
        raise ValueError(
            f"The reactant needs to have precisely one sequence. The input reactant has {len(reactant.sequences)} sequences"
        )
    participations = []
    extracts_list = []
    restriction_enzymes_pydna = []

    for re in restriction_enzymes:
        enzyme = Restriction.__dict__[re.name]
        restriction_enzymes_pydna.append(enzyme)

        enzyme_component = sbol2.FunctionalComponent(uri=f"{re.name}_enzyme")
        enzyme_component.definition = re
        enzyme_component.displayID = f"{re.name}_enzyme"
        enzyme_in_module = False

        for comp in assembly_plan.functionalComponents:
            if comp.displayId == enzyme_component.displayID:
                enzyme_component = comp
                enzyme_in_module = True

        if not enzyme_in_module:
            assembly_plan.functionalComponents.add(enzyme_component)

        modifier_participation = sbol2.Participation(uri="restriction")
        modifier_participation.participant = enzyme_component
        modifier_participation.roles = [
            "http://identifiers.org/biomodels.sbo/SBO:0000019"
        ]
        participations.append(modifier_participation)

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
        part_extract, backbone = sorted(digested_reactant, key=len)
    elif linear and len(digested_reactant) == 3:
        prefix, part_extract, suffix = digested_reactant
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
        identity=f"{reactant.displayId if isinstance(reactant, sbol2.ComponentDefinition) else reactant.functionalComponents[0].displayId}_extracted_part",
        sequence=product_sequence,
        **kwargs,
    )
    prod_component_definition.wasDerivedFrom = reactant_component_definition.identity
    extracts_list.append((prod_component_definition, prod_seq))

    # five prime overhang
    five_prime_oh_definition = sbol2.ComponentDefinition(
        uri=f"{reactant_displayId}_five_prime_oh"
    )  # TODO: ensure circular type is preserved for sbh visualization
    five_prime_oh_definition.addRole("http://identifiers.org/so/SO:0001932")
    five_prime_oh_location = sbol2.Range(
        uri="five_prime_oh_location", start=1, end=len(product_5_prime_ss_end)
    )
    five_prime_oh_component = sbol2.Component(
        uri=f"{reactant_displayId}_five_prime_oh_component"
    )
    five_prime_oh_component.definition = five_prime_oh_definition
    five_prime_overhang_annotation = sbol2.SequenceAnnotation(uri="five_prime_overhang")
    five_prime_overhang_annotation.locations.add(five_prime_oh_location)

    # extracted part => point straight to part from sbolcanvas
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
    three_prime_oh_definition.addRole("http://identifiers.org/so/SO:0001933")
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
                three_prime_oh_definition.types.append(
                    "http://identifiers.org/so/SO:0000984"
                )  # single-stranded for overhangs

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
                five_prime_oh_definition.types.append(
                    "http://identifiers.org/so/SO:0000984"
                )  # single-stranded for overhangs

                extracts_list.append((five_prime_oh_definition, five_prime_sequence))
                extracts_list.append((definition, seq))

    # find + add original component to product def & annotation
    for comp in reactant_component_definition.components:
        if comp.definition == original_part_def_URI:
            prod_component_definition.components.add(comp)
            part_extract_annotation.component = comp

    prod_component_definition.sequenceAnnotations.add(three_prime_overhang_annotation)
    prod_component_definition.sequenceAnnotations.add(five_prime_overhang_annotation)
    prod_component_definition.sequenceAnnotations.add(part_extract_annotation)
    prod_component_definition.addRole(
        "https://identifiers.org/so/SO:0000915"
    )  # engineered insert
    prod_component_definition.addType("http://identifiers.org/so/SO:0000987")  # linear

    # Add reference to part in backbone
    reactant_component = sbol2.FunctionalComponent(uri=f"{reactant_displayId}_reactant")
    reactant_component.definition = reactant_component_definition
    assembly_plan.functionalComponents.add(reactant_component)

    # Create reactant Participation.
    reactant_participation = sbol2.Participation(uri=f"{reactant_displayId}_reactant")
    reactant_participation.participant = reactant_component
    reactant_participation.roles = [sbol2.SBO_REACTANT]
    participations.append(reactant_participation)

    prod_component = sbol2.FunctionalComponent(
        uri=f"{reactant_displayId}_digestion_product"
    )
    prod_component.definition = prod_component_definition
    assembly_plan.functionalComponents.add(prod_component)

    product_participation = sbol2.Participation(uri=f"{reactant_displayId}_product")
    product_participation.participant = prod_component
    product_participation.roles = [sbol2.SBO_PRODUCT]
    participations.append(product_participation)

    # Make Interaction
    interaction = sbol2.Interaction(
        uri=f"{reactant_displayId}_digestion",
        interaction_type="http://identifiers.org/biomodels.sbo/SBO:0000178",
    )
    interaction.participations = participations
    assembly_plan.interactions.add(interaction)

    return extracts_list, assembly_plan


def backbone_digestion(
    reactant: Union[sbol2.ComponentDefinition, sbol2.ModuleDefinition],
    restriction_enzymes: List[sbol2.ComponentDefinition],
    assembly_plan: sbol2.ModuleDefinition,
    document: sbol2.Document,
    **kwargs,
) -> Tuple[
    List[Tuple[sbol2.ComponentDefinition, sbol2.Sequence]], sbol2.ModuleDefinition
]:
    """Runs a simulated digestion on the top level sequence in the reactant ComponentDefinition or ModuleDefinition with the given restriciton enzymes, creating an open backbone ComponentDefinition, a digestion Interaction, and converts existing scars to 5' and 3' overhangs.
    The product ComponentDefinition is assumed the open backbone in this case.

    Written for use with the SBOL2.3 output of https://sbolcanvas.org

    :param reactant: DNA to be digested as SBOL ComponentDefinition or ModuleDefinition, usually a part_in_backbone. ComponentDefinition is the best-practice type for plasmids.
    :param restriction_enzymes: Restriction enzymes as :class:`sbol2.ComponentDefinition`
                                (generate with :func:`rebase_restriction_enzyme`).
    :param assembly_plan: SBOL ModuleDefinition to contain the functional components, interactions, and participations
    :param document: original SBOL2 document to be used to extract referenced objects.
    :return: A tuple of a list ComponentDefinitions and Sequences, and an assembly plan ModuleDefinition.
    """
    if type(reactant) is sbol2.ModuleDefinition:
        # extract component definition from module
        reactant_displayId = reactant.functionalComponents[0].displayId
        reactant_def_URI = reactant.functionalComponents[0].definition
        reactant_component_definition = document.getComponentDefinition(
            reactant_def_URI
        )
    else:
        reactant_displayId = reactant.displayId
        reactant_component_definition = reactant

    types = set(reactant_component_definition.types or [])

    if not types.intersection(DNA_TYPES):
        raise TypeError(
            f"The reactant should have a DNA type. Types found: {reactant.types}."
        )
    if len(reactant_component_definition.sequences) != 1:
        raise ValueError(
            f"The reactant needs to have precisely one sequence. The input reactant has {len(reactant.sequences)} sequences"
        )
    participations = []
    extracts_list = []
    restriction_enzymes_pydna = []

    for re in restriction_enzymes:
        enzyme = Restriction.__dict__[re.name]
        restriction_enzymes_pydna.append(enzyme)

        enzyme_component = sbol2.FunctionalComponent(uri=f"{re.name}_enzyme")
        enzyme_component.definition = re
        enzyme_component.displayID = f"{re.name}_enzyme"
        enzyme_in_module = False

        for comp in assembly_plan.functionalComponents:
            if comp.displayId == enzyme_component.displayID:
                enzyme_component = comp
                enzyme_in_module = True

        if not enzyme_in_module:
            assembly_plan.functionalComponents.add(enzyme_component)

        modifier_participation = sbol2.Participation(uri="restriction")
        modifier_participation.participant = enzyme_component
        modifier_participation.roles = [
            "http://identifiers.org/biomodels.sbo/SBO:0000019"
        ]  # modifier
        participations.append(modifier_participation)

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
    digested_reactant = ds_reactant.cut(
        restriction_enzymes_pydna
    )  # TODO see if ds_reactant.cut is working, causing problems downstream

    if len(digested_reactant) < 2 or len(digested_reactant) > 3:
        raise ValueError(
            f"Not supported number of products. Found: {len(digested_reactant)}"
        )  # TODO make more specific for buildplanner
    # TODO select them based on content rather than size.
    elif circular and len(digested_reactant) == 2:
        part_extract, backbone = sorted(digested_reactant, key=len)
    elif linear and len(digested_reactant) == 3:
        prefix, part_extract, suffix = digested_reactant
    else:
        raise ValueError("The reactant has no valid topology type")

    # Compute the length of single strand sticky ends or fusion sites
    product_5_prime_ss_strand, product_5_prime_ss_end = backbone.seq.five_prime_end()
    product_3_prime_ss_strand, product_3_prime_ss_end = backbone.seq.three_prime_end()
    product_sequence = str(backbone.seq)
    prod_backbone_definition, prod_seq = dna_componentdefinition_with_sequence(
        identity=f"{reactant_component_definition.displayId}_extracted_backbone",
        sequence=product_sequence,
        **kwargs,
    )
    prod_backbone_definition.wasDerivedFrom = reactant_component_definition.identity
    extracts_list.append((prod_backbone_definition, prod_seq))

    # five prime overhang
    five_prime_oh_definition = sbol2.ComponentDefinition(
        uri=f"{reactant_displayId}_five_prime_oh"
    )  # TODO: ensure circular type is preserved for sbh visualization
    five_prime_oh_definition.addRole(
        "http://identifiers.org/so/SO:0001932"
    )  # overhang 5 prime
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
    three_prime_oh_definition.addRole(
        "http://identifiers.org/so/SO:0001933"
    )  # overhang 3 prime
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
                three_prime_oh_definition.types.append(
                    "http://identifiers.org/so/SO:0000984"
                )  # single-stranded for overhangs

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
                five_prime_oh_definition.types.append(
                    "http://identifiers.org/so/SO:0000984"
                )  # single-stranded for overhangs

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
    prod_backbone_definition.addRole("https://identifiers.org/so/SO:0000755")

    # Add reference to part in backbone
    reactant_component = sbol2.FunctionalComponent(
        uri=f"{reactant_component_definition.displayId}_backbone_reactant"
    )
    reactant_component.definition = reactant_component_definition
    assembly_plan.functionalComponents.add(reactant_component)

    # Create reactant Participation.
    reactant_participation = sbol2.Participation(
        uri=f"{reactant_component_definition.displayId}_backbone_reactant"
    )
    reactant_participation.participant = reactant_component
    reactant_participation.roles = [sbol2.SBO_REACTANT]
    participations.append(reactant_participation)

    prod_component = sbol2.FunctionalComponent(
        uri=f"{reactant_component_definition.displayId}_backbone_digestion_product"
    )
    prod_component.definition = prod_backbone_definition
    assembly_plan.functionalComponents.add(prod_component)

    product_participation = sbol2.Participation(
        uri=f"{reactant_component_definition.displayId}_backbone_product"
    )
    product_participation.participant = prod_component
    product_participation.roles = [sbol2.SBO_PRODUCT]
    participations.append(product_participation)

    # Make Interaction
    interaction = sbol2.Interaction(
        uri=f"{reactant_component_definition.displayId}_digestion",
        interaction_type="http://identifiers.org/biomodels.sbo/SBO:0000178",
    )
    interaction.participations = participations
    assembly_plan.interactions.add(interaction)

    return extracts_list, assembly_plan


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
    assembly_plan: sbol2.ModuleDefinition,
    document: sbol2.Document,
    ligase: sbol2.ComponentDefinition = None,
) -> List[Tuple[sbol2.ComponentDefinition, sbol2.Sequence]]:
    """Ligates Components using base complementarity and creates product Components and a ligation Interaction.

    :param reactants: DNA parts to be ligated as SBOL ModuleDefinition.
    :param assembly_plan: SBOL ModuleDefinition to contain the functional components, interactions, and participants
    :param document: SBOL2 document containing all reactant ComponentDefinitions.
    :param ligase: as SBOL ComponentDefinition, optional (defaults to T4 ligase)
    :return: List of all composites generated, in the form of tuples of ComponentDefinition and Sequence.
    """
    if ligase is None:
        ligase = sbol2.ComponentDefinition(uri="T4_Ligase")
        ligase.name = "T4_Ligase"
        ligase.types = sbol2.BIOPAX_PROTEIN
        document.add(ligase)

    ligase_component = sbol2.FunctionalComponent(uri="T4_Ligase")
    ligase_component.definition = ligase
    ligase_component.roles = ["http://identifiers.org/ncit/NCIT:C16796"]
    assembly_plan.functionalComponents.add(ligase_component)

    modifier_participation = sbol2.Participation(uri="ligation")
    modifier_participation.participant = ligase_component
    modifier_participation.roles = [
        "http://identifiers.org/biomodels.sbo/SBO:0000019"
    ]  # modifier

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
        if "https://identifiers.org/so/SO:0000755" in reactant.roles:
            reactant_parts.append(reactant)
        elif "https://identifiers.org/so/SO:0000915" in reactant.roles:
            reactant_parts.append(reactant)
        else:
            raise ValueError(f"Part {reactant.identity} does not have a valid role")

    # remove the backbones if any from the reactants, to create the composite
    groups = {}
    for reactant in reactant_parts:
        reactant_seq = reactant.sequences[0]
        first_four_letters = (
            document.getSequence(reactant_seq).elements[:fusion_site_length].lower()
        )
        last_four_letters = (
            document.getSequence(reactant_seq).elements[-fusion_site_length:].lower()
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
        insert_sequence = document.getSequence(insert_sequence_uri).elements
        remaining_parts = list(combination[1:])
        it = 1
        while remaining_parts:
            remaining_parts_before = len(remaining_parts)
            for part in remaining_parts:
                # match insert sequence 5' to part 3'
                part_sequence_uri = part.sequences[0]
                if (
                    document.getSequence(part_sequence_uri)
                    .elements[:fusion_site_length]
                    .lower()
                    == insert_sequence[-fusion_site_length:].lower()
                ):
                    insert_sequence = (
                        insert_sequence[:-fusion_site_length]
                        + document.getSequence(part_sequence_uri).elements
                    )
                    list_of_parts_per_composite.append(
                        part
                    )  # add sequence annotation here, index based on insert_sequence
                    remaining_parts.remove(part)
                # match insert sequence 3' to part 5'
                elif (
                    document.getSequence(part_sequence_uri)
                    .elements[-fusion_site_length:]
                    .lower()
                    == insert_sequence[:fusion_site_length].lower()
                ):
                    insert_sequence = (
                        document.getSequence(part_sequence_uri).elements
                        + insert_sequence[fusion_site_length:]
                    )
                    list_of_parts_per_composite.insert(0, part)
                    remaining_parts.remove(part)
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
    products_list = []
    participations = []
    composite_number = 1
    participations.append(modifier_participation)

    for composite in list_of_composites_per_assembly:  # a composite of the form [A,B,C]
        # calculate sequence
        composite_sequence_str = ""
        participations = []
        prev_three_prime = (
            composite[len(composite) - 1].components[1].definition
        )  # componentdefinitionuri
        prev_three_prime_definition = document.getComponentDefinition(prev_three_prime)
        scar_index = 1
        anno_list = []

        part_extract_definitions = []
        for part_extract in composite:
            part_extract_sequence_uri = part_extract.sequences[0]
            part_extract_sequence = document.getSequence(
                part_extract_sequence_uri
            ).elements
            temp_extract_components = []
            reactant_component = sbol2.FunctionalComponent(
                uri=f"{part_extract.displayId}_reactant"
            )
            reactant_component.definition = part_extract
            for fc in assembly_plan.functionalComponents:
                if fc.definition == reactant_component.definition:
                    reactant_component = fc

            reactant_participation = sbol2.Participation(
                uri=f"{part_extract.displayId}_ligation"
            )
            reactant_participation.participant = reactant_component
            reactant_participation.roles = [sbol2.SBO_REACTANT]
            participations.append(reactant_participation)

            for comp in part_extract.components:
                if (
                    "http://identifiers.org/so/SO:0001932"
                    in document.getComponentDefinition(comp.definition).roles
                ):  # five prime
                    scar_definition = sbol2.ComponentDefinition(
                        uri=f"Ligation_Scar_{number_to_suffix(scar_index)}"
                    )
                    scar_sequence = sbol2.Sequence(
                        uri=f"Ligation_Scar_{number_to_suffix(scar_index)}_sequence",
                        elements=document.getSequence(
                            prev_three_prime_definition.sequences[0]
                        ).elements,
                    )
                    scar_definition.sequences = [scar_sequence]
                    scar_definition.wasDerivedFrom = [comp.definition, prev_three_prime]
                    scar_definition.roles = ["http://identifiers.org/so/SO:0001953"]
                    temp_extract_components.append(scar_definition.identity)

                    add_object_to_doc(scar_definition, document)
                    add_object_to_doc(scar_sequence, document)

                    scar_location = sbol2.Range(
                        uri=f"Ligation_Scar_{number_to_suffix(scar_index)}_location",
                        start=len(composite_sequence_str) + 1,
                        end=len(composite_sequence_str) + fusion_site_length,
                    )
                    scar_anno = sbol2.SequenceAnnotation(
                        uri=f"Ligation_Scar_{number_to_suffix(scar_index)}_annotation"
                    )
                    scar_anno.locations.add(scar_location)
                    anno_list.append(scar_anno)
                    scar_index += 1
                elif (
                    "http://identifiers.org/so/SO:0001933"
                    in document.getComponentDefinition(comp.definition).roles
                ):  # three prime
                    prev_three_prime = comp.definition
                    prev_three_prime_definition = document.getComponentDefinition(
                        prev_three_prime
                    )
                else:
                    temp_extract_components.append(comp.definition)
                    comp_location = sbol2.Range(
                        uri=f"{comp.displayId}_location",
                        start=len(composite_sequence_str) + fusion_site_length + 1,
                        end=len(composite_sequence_str)
                        + len(part_extract_sequence[:-4]),
                    )
                    comp_anno = sbol2.SequenceAnnotation(
                        uri=f"{comp.displayId}_annotation"
                    )
                    comp_anno.locations.add(comp_location)
                    anno_list.append(comp_anno)

            part_extract_definitions.extend(temp_extract_components)

            composite_sequence_str = (
                composite_sequence_str + part_extract_sequence[:-fusion_site_length]
            )  # needs a version for linear

        # create dna component and sequence
        composite_component_definition, composite_seq = (
            dna_componentdefinition_with_sequence(
                f"composite_{composite_number}", composite_sequence_str, molecule=True
            )
        )
        composite_component_definition.name = f"composite_{composite_number}"
        composite_component_definition.addRole(
            "http://identifiers.org/so/SO:0000804"
        )  # engineered region
        composite_component_definition.addType("http://identifiers.org/so/SO:0000988")

        for i, definition in enumerate(part_extract_definitions):
            def_object = document.getComponentDefinition(definition)
            comp = sbol2.Component(uri=def_object.displayId)
            comp.definition = definition
            composite_component_definition.components.add(comp)

            anno_list[i].component = comp

        composite_component_definition.sequenceAnnotations = anno_list

        prod_functional_component = sbol2.FunctionalComponent(
            uri=f"{composite_component_definition.name}"
        )
        prod_functional_component.definition = composite_component_definition
        assembly_plan.functionalComponents.add(prod_functional_component)

        product_participation = sbol2.Participation(
            uri=f"{composite_component_definition.name}_product"
        )
        product_participation.participant = prod_functional_component
        product_participation.roles = [sbol2.SBO_PRODUCT]
        participations.append(product_participation)

        # Make Interaction
        interaction = sbol2.Interaction(
            uri=f"{composite_component_definition.name}_ligation",
            interaction_type="http://identifiers.org/biomodels.sbo/SBO:0000695",
        )
        interaction.participations = participations
        assembly_plan.interactions.add(interaction)

        products_list.append([composite_component_definition, composite_seq])
        composite_number += 1
    return products_list


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
            print("adding: " + extract.displayId)
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


class golden_gate_assembly_plan:
    """Creates an Assembly Plan.

    :param name: Name of the assembly plan ModuleDefinition.
    :param parts_in_backbone: Parts in backbone to be assembled.
    :param plasmid_acceptor_backbone:  Backbone in which parts are inserted on the assembly.
    :param restriction_enzyme: Restriction enzyme name used by PyDNA. Case sensitive, follow standard restriction enzyme nomenclature, i.e. 'BsaI'
    :param document: SBOL Document where the assembly plan will be created.
    """

    def __init__(
        self,
        name: str,
        parts_in_backbone: List[sbol2.Document],
        plasmid_acceptor_backbone: sbol2.Document,
        restriction_enzyme: str,
        document: sbol2.Document,
    ):
        self.name = name
        self.parts_in_backbone = parts_in_backbone
        self.backbone = plasmid_acceptor_backbone
        self.restriction_enzyme = rebase_restriction_enzyme(restriction_enzyme)
        self.extracted_parts = []  # list of tuples [ComponentDefinition, Sequence]
        self.document = document

        self.assembly_plan = sbol2.ModuleDefinition(name)
        self.document.add(self.assembly_plan)
        self.document.add(self.restriction_enzyme)
        self.composites = []

    def run(
        self, plasmids_in_module_definitions=False
    ) -> List[Tuple[sbol2.ComponentDefinition, sbol2.Sequence]]:
        """Runs full assembly simulation.

        `document` parameter of golden_gate_assembly_plan object is updated by reference to include assembly plan ModuleDefinition and all related information.

        Runs :func:`part_digestion` for all `parts_in_backbone` and :func:`backbone_digestion` for `plasmid_acceptor_backbone` with `restriction_enzyme`. Then runs :func:`ligation` with these parts to form composites.

        :return: List of all composites generated, in the form of tuples of ComponentDefinition and Sequence.
        """
        for part_doc in self.parts_in_backbone:
            if plasmids_in_module_definitions:
                topLevel = part_doc.getModuleDefinition(
                    "https://sbolcanvas.org/module1"
                )  # TODO change to toplevel or some other index?
            else:
                topLevel = part_doc.componentDefinitions[0]
            extracts_tuple_list, _ = part_digestion(
                topLevel, [self.restriction_enzyme], self.assembly_plan, part_doc
            )  # make sure assembly plan is pass-by-reference

            append_extracts_to_doc(extracts_tuple_list, self.document)
            self.extracted_parts.append(extracts_tuple_list[0][0])

        if plasmids_in_module_definitions:
            topLevel = self.backbone.getModuleDefinition(
                "https://sbolcanvas.org/module1"
            )  # TODO change to toplevel or some other index?
        else:
            topLevel = self.backbone.componentDefinitions[0]
        extracts_tuple_list, _ = backbone_digestion(
            topLevel, [self.restriction_enzyme], self.assembly_plan, self.backbone
        )

        append_extracts_to_doc(extracts_tuple_list, self.document)
        self.extracted_parts.append(extracts_tuple_list[0][0])

        self.composites = ligation(
            self.extracted_parts, self.assembly_plan, self.document
        )

        self._add_assembly_activity()

        append_extracts_to_doc(self.composites, self.document)

        return self.composites

    def _add_assembly_activity(self):
        for composite in self.composites:
            composite_component_definition = composite[0]

            assembly_activity = sbol2.Activity(
                f"assemble_{composite_component_definition.name}"
            )
            assembly_activity.name = "Golden Gate Assembly"
            assembly_activity.types = "http://sbols.org/v2#build"

            assembly_usage = sbol2.Usage(
                uri=f"assemble_{composite_component_definition.name}_design",
                entity=self.assembly_plan.identity,
                role="http://sbols.org/v2#design",
            )
            assembly_activity.usages = [assembly_usage]

            assembly_activity_association = sbol2.Association(
                f"assemble_{composite_component_definition.name}_association"
            )

            assembly_activity_plan = sbol2.Plan(
                f"{composite_component_definition.name}_assembly_plan"
            )  # TODO refine this plan
            assembly_activity_association.plan = assembly_activity_plan

            assembly_activity_agent = sbol2.Agent("buildcompiler")
            assembly_activity_association.agent = assembly_activity_agent

            assembly_activity.associations = [assembly_activity_association]

            composite_component_definition.wasGeneratedBy = assembly_activity

            for obj in [
                assembly_activity_plan,
                assembly_activity_agent,
                assembly_activity,
                assembly_usage,
            ]:
                add_object_to_doc(obj, self.document)
