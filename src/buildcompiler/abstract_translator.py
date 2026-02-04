import sbol2
import itertools
from typing import Dict, List
from .constants import FUSION_SITES


class Plasmid:
    def __init__(
        self,
        definition: sbol2.ComponentDefinition,
        strain_definition: sbol2.ModuleDefinition,
        doc: sbol2.document,
    ):
        self.definition = definition
        self.strain_definition = strain_definition
        self.fusion_sites = self.match_fusion_sites(doc)
        self.name = definition.displayId + "".join(f"_{s}" for s in self.fusion_sites)
        self.antibiotic_resistance = None

    def match_fusion_sites(self, doc: sbol2.document) -> List[str]:
        fusion_site_definitions = extract_fusion_sites(self.definition, doc)
        fusion_sites = []
        for site in fusion_site_definitions:
            sequence_obj = doc.getSequence(site.sequences[0])
            sequence = sequence_obj.elements

            for key, seq in FUSION_SITES.items():
                if seq == sequence.upper():
                    fusion_sites.append(key)

        fusion_sites.sort()
        return fusion_sites

    def __repr__(self) -> str:
        return (
            f"Plasmid:\n"
            f"  Name: {self.name}\n"
            f"  Definition: {self.definition.identity}\n"
            f"  Strain: {getattr(self.strain_definition, 'identity', 'None')}\n"
            f"  Fusion Sites: {self.fusion_sites or 'Not found'}"
            f"  Antibiotic Resistance: {self.antibiotic_resistance}\n"
        )

    def __eq__(self, other):
        if not isinstance(other, Plasmid):
            return False
        return self.definition == other.definition

    def __hash__(self):
        return hash(self.definition)


def extract_fusion_sites(
    plasmid: sbol2.ComponentDefinition, doc: sbol2.Document
) -> List[sbol2.ComponentDefinition]:
    """
    Returns all fusion site component definitions from a plasmid.

    Args:
        plasmid: :class:`sbol2.ComponentDefinition` representing the plasmid.
        doc: :class:`sbol2.Document` containing component definitions.

    Returns:
        A list of fusion site component definitions.
    """
    fusion_sites = []
    for component in plasmid.components:
        definition = doc.getComponentDefinition(component.definition)
        if "http://identifiers.org/so/SO:0001953" in definition.roles:
            fusion_sites.append(definition)

    return fusion_sites


def extract_design_parts(
    design: sbol2.ComponentDefinition, doc: sbol2.Document
) -> List[sbol2.ComponentDefinition]:
    """
    Returns definitions of parts in a design in sequential order.

    Args:
        design: :class:`sbol2.ComponentDefinition` to extract parts from.
        doc: :class:`sbol2.Document` containing all component definitions.

    Returns:
        A list of component definitions in sequential order.
    """
    component_list = [c for c in design.getInSequentialOrder()]
    return [
        doc.getComponentDefinition(component.definition) for component in component_list
    ]


def copy_sequences(component_definition, target_doc, collection_doc):
    """Copy all sequences referenced by a ComponentDefinition into target_doc."""
    subdefinitions = extract_design_parts(component_definition, collection_doc)

    for seq_uri in component_definition.sequences:
        seq_obj = component_definition.doc.find(seq_uri)
        if seq_obj is not None:
            seq_obj.copy(target_doc)

    for subdefinition in subdefinitions:
        print(subdefinition.displayId)
        subdefinition.copy(target_doc)
        for seq_uri in subdefinition.sequences:
            seq_obj = component_definition.doc.find(seq_uri)
            if seq_obj is not None:
                seq_obj.copy(target_doc)


def extract_combinatorial_design_parts(
    design: sbol2.ComponentDefinition, doc: sbol2.Document, plasmid_doc
) -> Dict[str, List[sbol2.ComponentDefinition]]:
    """
    Extracts and returns a mapping of component definitions from a combinatorial design, in order.
    Variants of combinatinatorial components are entered in a list corresponding to the URI of the component in the abstract design.

    Args:
        design:
            The :class:`sbol2.ComponentDefinition` representing the top-level design
            from which to extract parts.
        doc:
            The primary :class:`sbol2.Document` containing the base component definitions
            and combinatorial derivations.
        plasmid_doc:
            An additional :class:`sbol2.Document` used to resolve component variants
            (plasmid-specific variants referenced by combinatorial derivations).

    Returns:
        Dict[str, List[sbol2.ComponentDefinition]]:
            A dictionary mapping component identities to lists
            of variable component definitions.

            - Sequential design components map to lists containing a single definition.
            - Combinatorial variable components map to lists of variant definitions.
    """
    component_list = [c for c in design.getInSequentialOrder()]
    component_dict = {
        component.identity: [doc.getComponentDefinition(component.definition)]
        for component in component_list
    }

    for deriv in doc.combinatorialderivations:
        for component in deriv.variableComponents:
            component_dict[component.variable] = [
                plasmid_doc.getComponentDefinition(var) for var in component.variants
            ]

    return component_dict


def extract_toplevel_definition(doc: sbol2.Document) -> sbol2.ComponentDefinition:
    return doc.componentDefinitions[0]


def enumerate_design_variants(component_dict):
    """
    Given a dict mapping variable component identities to lists of ComponentDefinitions,
    generate all possible design combinations as lists of ComponentDefinitions
    (in consistent order of keys).
    """
    keys = list(component_dict.keys())
    variant_lists = [component_dict[k] for k in keys]

    # Cartesian product across all variant lists
    all_variants = list(itertools.product(*variant_lists))

    all_variants = [list(combo) for combo in all_variants]

    return all_variants


def construct_plasmid_dict(
    part_list: List[sbol2.ComponentDefinition], plasmid_collection: sbol2.Document
) -> Dict[str, List[Plasmid]]:
    """
    Builds a mapping from part display IDs to lists of compatible Plasmid objects.

    For each part in the given list, this function searches the provided plasmid
    collection for plasmids that contain the part as a component.
    Each matching plasmid is wrapped in a `Plasmid` object and added to the
    dictionary under the part's display ID.

    Args:
        part_list:
            List of :class:`sbol2.ComponentDefinition` objects representing
            the parts to match.
        plasmid_collection:
            The :class:`sbol2.Document` containing plasmids to search through.

    Returns:
        Dict[str, List[Plasmid]]:
            A dictionary mapping each part display ID to a list of corresponding
            `Plasmid` objects found in the collection.
    """
    plasmid_dict = {}
    for part in part_list:
        for plasmid in plasmid_collection.componentDefinitions:
            if "http://identifiers.org/so/SO:0000637" in plasmid.roles:
                for component in plasmid.components:
                    if (
                        component.definition == str(part)
                    ):  # TODO make sure this is not a composite plasmid, i.e. plasmid just contains singular part of interest
                        fusion_sites = [
                            site.name
                            for site in extract_fusion_sites(
                                plasmid, plasmid_collection
                            )
                        ]
                        print(
                            f"found: {component.definition} in {plasmid} with {fusion_sites}"
                        )  # TODO switch to logger for backend tracing?
                        plasmid_dict.setdefault(part.displayId, [])

                        componentName = plasmid_collection.getComponentDefinition(
                            component.definition
                        ).name

                        plasmid_dict[part.displayId].append(
                            Plasmid(componentName, plasmid, plasmid_collection)
                        )

    return plasmid_dict


def get_compatible_plasmids(
    plasmid_dict: Dict[str, List[Plasmid]], backbone: Plasmid
) -> List[Plasmid]:
    """
    Returns a list of Plasmid objects that can form a compatible assembly
    with the given backbone plasmid. The function selects one plasmid from each
    entry in the dictionary, ensuring that adjacent plasmids have matching MoClo fusion sites,
    and that the first and last plasmids are compatible with the backbone.

    Args:
        plasmid_dict: A dictionary mapping assembly positions or categories to lists
            of Plasmid objects.
        backbone: The backbone Plasmid whose fusion sites define compatibility.

    Returns:
        A list of compatible Plasmid objects forming a sequential assembly.
    """
    selected_plasmids = []
    match_to = backbone
    match_idx = 0

    for i, key in enumerate(plasmid_dict):
        for plasmid in plasmid_dict[key]:
            if (
                i == len(plasmid_dict) - 1
                and plasmid.fusion_sites[0] == match_to.fusion_sites[match_idx]
                and plasmid.fusion_sites[1] == backbone.fusion_sites[1]
            ):
                print(
                    f"matched final component {plasmid.name} with {match_to.name} and {backbone.name} on fusion sites ({plasmid.fusion_sites[0]}, {plasmid.fusion_sites[1]})!"
                )
                selected_plasmids.append(plasmid)
                break
            elif (
                i < len(plasmid_dict) - 1
                and plasmid.fusion_sites[0] == match_to.fusion_sites[match_idx]
            ):  # TODO add error handling if no compatible plasmid found
                print(
                    f"matched {plasmid.name} with {match_to.name} on fusion site {plasmid.fusion_sites[0]}!"
                )
                selected_plasmids.append(plasmid)
                match_to = plasmid
                match_idx = 1
                break
            # TODO edge case where second fusion site does not match terminator fusion site will not be caught by current logic
            # 10/14: rethink implementation, will likely need to be different for combinatorial designs

    return selected_plasmids


def translate_abstract_to_plasmids(
    abstract_design_doc: sbol2.Document,
    plasmid_collection: sbol2.Document,
    backbone_doc: sbol2.Document,
) -> List[Plasmid]:
    """
    Translates an abstract SBOLCanvas design into a set of compatible MoClo plasmid assemblies.

    Takes an abstract design, identifies the appropriate component
    definitions and combinatorial derivations, and produces all possible plasmid
    combinations that can be assembled using the provided backbone and plasmid
    collection.

    Args:
        abstract_design_doc:
            The :class:`sbol2.Document` representing the abstract genetic design.
            May include either a single component definition (generic design) or
            one or more combinatorial derivations (combinatorial design).
        plasmid_collection:
            The :class:`sbol2.Document` containing the available MoClo plasmid
            components used for matching and assembly.
        backbone_doc:
            The :class:`sbol2.Document` defining the backbone plasmid into which
            parts are assembled.

    Returns:
        List[Plasmid]:
            - For combinatorial designs: a list of unique compatible plasmids
              (`Plasmid` objects) representing all enumerated design variants.
            - For generic designs: a list of compatible plasmids for the single
              design instance.
    """
    backbone_def = extract_toplevel_definition(backbone_doc)
    backbone_plasmid = Plasmid(backbone_def.displayId, backbone_def, backbone_doc)

    # combinatorial design
    if len(abstract_design_doc.combinatorialderivations) > 0:
        abstract_design_def = abstract_design_doc.getComponentDefinition(
            abstract_design_doc.combinatorialderivations[0].masterTemplate
        )

        combinatorial_part_dict = extract_combinatorial_design_parts(
            abstract_design_def, abstract_design_doc, plasmid_collection
        )
        enumerated_part_list = enumerate_design_variants(combinatorial_part_dict)

        seen = set()
        ordered_unique_plasmids = []

        for design in enumerated_part_list:
            plasmid_dict = construct_plasmid_dict(design, plasmid_collection)
            compatible_plasmids = get_compatible_plasmids(
                plasmid_dict, backbone_plasmid
            )

            for plasmid in compatible_plasmids:
                if plasmid not in seen:
                    seen.add(plasmid)
                    ordered_unique_plasmids.append(plasmid)

        return ordered_unique_plasmids

    # generic design
    else:
        abstract_design_def = extract_toplevel_definition(abstract_design_doc)

        ordered_part_definitions = extract_design_parts(
            abstract_design_def, abstract_design_doc
        )

        plasmid_dict = construct_plasmid_dict(
            ordered_part_definitions, plasmid_collection
        )

        return get_compatible_plasmids(plasmid_dict, backbone_plasmid)
