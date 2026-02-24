import sbol2
import re
from typing import Union, List, Dict
from .abstract_translator import (
    extract_fusion_sites,
    get_or_pull,
    get_compatible_plasmids,
)
from .constants import (
    ANTIBIOTIC_MAP,
    FUSION_SITES,
    AMP,
    KAN,
    PART_ROLES,
    RESTRICTION_ENZYME_ASSEMBLY_SCAR,
    ANTIBIOTIC_RESISTANCE,
    ENGINEERED_PLASMID,
    PLASMID_CLONING_VECTOR,
    ORGANISM_STRAIN,
)


class Plasmid:
    def __init__(
        self,
        definition: sbol2.ComponentDefinition,
        strain_definition: sbol2.ModuleDefinition,
        doc: sbol2.document,
    ):
        self.plasmid_definition = definition
        self.strain_definitions = [strain_definition]
        self.plasmid_implementations = []
        self.strain_implementations = []
        self.fusion_sites = self._match_fusion_sites(doc)
        self.name = definition.displayId + "".join(f"_{s}" for s in self.fusion_sites)
        self.antibiotic_resistance = self._get_antibiotic_resistance(doc)

    def _match_fusion_sites(self, doc: sbol2.document) -> List[str]:
        fusion_site_definitions = extract_fusion_sites(self.plasmid_definition, doc)
        fusion_sites = []
        for site in fusion_site_definitions:
            sequence_obj = doc.getSequence(site.sequences[0])
            sequence = sequence_obj.elements

            for key, seq in FUSION_SITES.items():
                if seq == sequence.upper():
                    fusion_sites.append(key)

        fusion_sites.sort()
        return fusion_sites

    def _get_antibiotic_resistance(self, doc: sbol2.Document) -> str:
        for component in (
            self.plasmid_definition.components
        ):  # go a level deeper, within the backbone core component
            definition = doc.get(component.definition)
            for subcomponent in definition.components:
                subcomponent_def = doc.get(subcomponent.definition)
                if ANTIBIOTIC_RESISTANCE in subcomponent_def.roles:
                    match = re.search(
                        r"\b(" + "|".join(ANTIBIOTIC_MAP) + r")_",
                        subcomponent_def.displayId,
                        re.IGNORECASE,
                    )
                    if match:
                        return ANTIBIOTIC_MAP[match.group(1).lower()]
                    return "Unknown"

        return None

    def __repr__(self) -> str:
        strain_ids = (
            [getattr(s, "identity", "None") for s in self.strain_definitions]
            if self.strain_definitions
            else ["None"]
        )

        plasmid_impl_ids = (
            [getattr(p, "identity", "None") for p in self.plasmid_implementations]
            if self.plasmid_implementations
            else []
        )

        strain_impl_ids = (
            [getattr(s, "identity", "None") for s in self.strain_implementations]
            if self.strain_implementations
            else []
        )

        return (
            f"Plasmid:\n"
            f"  Name: {self.name}\n"
            f"  Plasmid Definition: {getattr(self.plasmid_definition, 'identity', 'None')}\n"
            f"  Strain Definitions: {strain_ids}\n"
            f"  Plasmid Implementations: {plasmid_impl_ids or 'None'}\n"
            f"  Strain Implementations: {strain_impl_ids or 'None'}\n"
            f"  Fusion Sites: {self.fusion_sites or 'Not found'}\n"
            f"  Antibiotic Resistance: {self.antibiotic_resistance or 'None'}\n"
        )

    def __eq__(self, other):
        if not isinstance(other, Plasmid):
            return False
        return self.plasmid_definition == other.plasmid_definition

    def __hash__(self):
        return hash(self.plasmid_definition)


class BuildCompiler:
    """Orchestrates the full build workflow for an SBOL design.

    This class owns the build state (indexed plasmids/backbones) and provides a
    high-level API to execute the full workflow: collection indexing, domestication,
    lvl1 and lvl2 assembly, transformation, and plating.

    :ivar design: SBOL design (ComponentDefinition, ModuleDefinition, or CombinatorialDerivation).
    :type design: sbol2.ComponentDefinition | sbol2.ModuleDefinition | sbol2.CombinatorialDerivation
    :ivar plasmids: Indexed plasmids linked to strains/collections.
    :type plasmids: list[Plasmid]
    """

    def __init__(
        self,
        abstract_design: Union[
            sbol2.ComponentDefinition,
            sbol2.ModuleDefinition,
            sbol2.CombinatorialDerivation,
        ],
        sbh_registry: str,
        auth_token: str,
        sbol_doc: sbol2.Document,
    ):
        self.abstract_design = abstract_design
        self.sbh = sbol2.PartShop(sbh_registry)
        self.sbh.key = auth_token

        self.sbol_doc = (
            sbol_doc  # if None, create new document (to fill with collection contents)
        )
        self.collections = None
        self.indexed_plasmids = []
        self.indexed_backbones = []

    # def index_collections(
    #     self, collections: list[sbol2.Collection]
    # ) -> dict[
    #     str, sbol2.Collection
    # ]:  # TODO add support for collection object and sbh URI?
    #     """Index input collections into plasmids and backbones.

    #     Parses the provided collections (which may contain plasmids, backbones, or strains)
    #     and normalizes them into internal Plasmid/Backbone records that remain linked to
    #     their originating strain definitions.

    #     :param collections: Iterable of user-provided collections/documents.
    #     :type collections: Iterable
    #     :returns: None. Updates ``self.indexed_plasmids`` in place.
    #     :rtype: None
    #     :raises ValueError: If collection elements cannot be interpreted as plasmids.
    #     """
    #     self.collections = collections

    #     # TODO: Iterate thorugh the Collections and create a set of indexed plasmids, linking them to their originating definitions.
    #     # Updates indexed_plasmids

    #     return "Success"

    def index_collections(self, collections: List[str]):
        for uri in collections:
            self.sbh.pull(uri, self.sbol_doc)

        for implementation in self.sbol_doc.implementations:
            built_object = get_or_pull(self.sbol_doc, self.sbh, implementation.built)
            if (
                type(built_object) is sbol2.ModuleDefinition
                and ORGANISM_STRAIN in built_object.roles
            ):
                self._extract_plasmids_from_strain(built_object, self.sbol_doc)
            elif (
                type(built_object) is sbol2.ComponentDefinition
                and len(built_object.components) > 1
            ):
                if ENGINEERED_PLASMID in built_object.roles:
                    self.indexed_plasmids.append(
                        Plasmid(built_object, None, self.sbol_doc)
                    )
                elif PLASMID_CLONING_VECTOR in built_object.roles:
                    self.indexed_backbones.append(
                        Plasmid(built_object, None, self.sbol_doc)
                    )

        for strain in self.sbol_doc.moduleDefinitions:
            if ORGANISM_STRAIN in strain.roles:
                self._extract_plasmids_from_strain(strain, self.sbol_doc)

        for definition in self.sbol_doc.componentDefinitions:
            self._sort_plasmid_components(definition, self.sbol_doc)

    def domestication(
        self,
    ) -> list[sbol2.ComponentDefinition]:
        """Domesticate the indexed plasmids for Golden Gate assembly.

        For each indexed plasmid, this method identifies the necessary domestication
        steps (e.g., removing internal BsaI sites) and generates the corresponding
        domesticated sequences as new ComponentDefinitions in the SBOL document.

        :returns: List of domesticated ComponentDefinitions ready for assembly.
        :rtype: list[sbol2.ComponentDefinition]
        """

        # TODO: Check which parts from the abstract design are not present in the indexed plasmids with the appropiate fusion sites and need to be domesticated.
        # TODO: Create a SBOL representation of the domestication process, updating the SBOL Document.
        # TODO: Generate a protocol for the domestication process.
        protocol = "To be implemented by PUDU"
        # TODO: Updates indexed plasmids with domesticated versions.

        return protocol

    def assembly_lvl1(self, backbone: Plasmid) -> list[sbol2.ComponentDefinition]:
        """Assemble level-1 plasmids for each gene/transcriptional unit.

        Uses indexed plasmids/backbones and the current design to assemble
        lvl1 plasmids in the correct order.

        :returns: List of assembled lvl1 plasmids.
        :rtype: list[Plasmid]
        :raises LookupError: If compatible plasmids or backbones cannot be found.
        """

        # TODO: Identify parts from the abstract design needed for lvl1 assembly and find compatible indexed plasmids/backbones.
        # if backbone provided then use it.Then look for parts constraind by the backbone fusion sites.
        # else, run an algorithm to try a backbone from 4 the choices. If it fails on the 4 raise an error.

        plasmid_dict = self._get_input_plasmids(antibiotic_resistance=AMP)

        if not backbone:
            backbone, compatible_plasmids = self._get_backbone(
                plasmid_dict, antibiotic_resistance=KAN
            )
        else:
            compatible_plasmids = get_compatible_plasmids(plasmid_dict, self.backbone)

        return compatible_plasmids

        # TODO: Create a SBOL representation of the assembly process, updating the SBOL Document.
        # Using he selected parts create the representation, you need Plasmids, BsaI and T4 Ligase.
        # TODO: Updates indexed plasmids with assembled versions.
        # TODO: Generate a protocol for the assembly process.
        protocol = "To be implemented by PUDU"

        return protocol

    def assembly_lvl2(
        self,
    ) -> list[sbol2.ComponentDefinition]:
        """Assemble level-2 plasmids for the full design.

        Uses the assembled lvl1 plasmids and the current design to assemble
        lvl2 plasmids in the correct order.

        :returns: List of assembled lvl2 plasmids.
        :rtype: list[Plasmid]
        :raises LookupError: If compatible plasmids or backbones cannot be found.
        """

        # TODO: Identify parts from the abstract design needed for lvl2 assembly and find compatible indexed plasmids/backbones.
        # TODO: Create a SBOL representation of the assembly process, updating the SBOL Document.
        # TODO: Generate a protocol for the assembly process.
        protocol = "To be implemented by PUDU"
        # TODO: Updates indexed plasmids with assembled versions.

        return protocol

    def _extract_plasmids_from_strain(
        self, strain: sbol2.ModuleDefinition, doc: sbol2.Document
    ):
        for plasmid in strain.functionalComponents:
            plasmid_definition = get_or_pull(doc, self.sbh, plasmid.definition)
            if ENGINEERED_PLASMID in plasmid_definition.roles:  # TODO check
                self.indexed_plasmids.append(Plasmid(plasmid_definition, strain, doc))

    def _sort_plasmid_components(
        self, definition: sbol2.ComponentDefinition, doc: sbol2.Document
    ):
        if len(definition.components) > 1:
            if ENGINEERED_PLASMID in definition.roles:
                self.indexed_plasmids.append(Plasmid(definition, None, doc))
            elif PLASMID_CLONING_VECTOR in definition.roles:
                self.indexed_backbones.append(Plasmid(definition, None, doc))

    def _get_input_plasmids(
        self, antibiotic_resistance: str
    ) -> Dict[str, List[Plasmid]]:
        """
        with AR=ampicillin.
        """

        parts = self._extract_design_parts()
        plasmid_dictionary = self._construct_plasmid_dict(parts, antibiotic_resistance)
        return plasmid_dictionary

    def _get_backbone(
        self, plasmid_dict: Dict[str, List[Plasmid]], antibiotic_resistance: str
    ):
        """
        with AR=kanamycin.
        """
        sorted_backbones = sorted(
            self.indexed_backbones, key=lambda p: p.fusion_sites[0]
        )

        for backbone in sorted_backbones:
            if backbone.antibiotic_resistance == antibiotic_resistance:
                # check for compatibility
                # also, if we find a hit here we may not need to run get_compatible plasmids later, work is already done
                try:
                    compatible_plasmids = get_compatible_plasmids(
                        plasmid_dict, backbone
                    )
                    print(
                        f"Success with backbone: {backbone.name} and plasmids: {[plas.name for plas in compatible_plasmids]}"
                    )
                    return backbone, compatible_plasmids
                except ValueError as e:
                    print(f"{e} and backbone {backbone}")
                    compatible_plasmids = None

        return None, None

    def _extract_design_parts(self) -> List[sbol2.ComponentDefinition]:
        """
        Returns definitions of parts in a design in sequential order.

        Args:
            design: :class:`sbol2.ComponentDefinition` to extract parts from.
            doc: :class:`sbol2.Document` containing all component definitions.

        Returns:
            A list of component definitions in sequential order.
        """
        component_list = [c for c in self.abstract_design.getInSequentialOrder()]
        return [
            get_or_pull(self.sbol_doc, self.sbh, component.definition)
            for component in component_list
        ]

    def _extract_fusion_sites(
        self,
        plasmid: sbol2.ComponentDefinition,
    ) -> List[sbol2.ComponentDefinition]:
        """
        Returns all fusion site component definitions from a plasmid.

        Args:
            plasmid: :class:`sbol2.ComponentDefinition` representing the plasmid.

        Returns:
            A list of fusion site component definitions.
        """
        fusion_sites = []
        for component in plasmid.components:
            definition = get_or_pull(self.sbol_doc, self.sbh, component.definition)
            if RESTRICTION_ENZYME_ASSEMBLY_SCAR in definition.roles:
                fusion_sites.append(definition)

        return fusion_sites

    def _construct_plasmid_dict(
        self, part_list: List[sbol2.ComponentDefinition], antibiotic_resistance: str
    ) -> Dict[str, List[Plasmid]]:
        """
        For each part in the given list, this function searches for plasmids that contain the part as a component.

        Args:
            part_list:
                List of :class:`sbol2.ComponentDefinition` objects representing
                the parts to match.

        Returns:
            Dict[str, List[Plasmid]]:
                A dictionary mapping each part display ID to a list of corresponding
                `Plasmid` objects found in the collection.
        """
        plasmid_dict = {}
        for part in part_list:
            for plasmid in self.indexed_plasmids:
                if ENGINEERED_PLASMID in plasmid.plasmid_definition.roles:
                    for component in plasmid.plasmid_definition.components:
                        if (
                            component.definition == str(part)
                            and self._is_single_part(plasmid.plasmid_definition)
                            and plasmid.antibiotic_resistance == antibiotic_resistance
                        ):
                            plasmid_dict.setdefault(part.displayId, [])
                            plasmid_dict[part.displayId].append(plasmid)

        return plasmid_dict

    def _is_single_part(self, plasmid: sbol2.ComponentDefinition) -> bool:
        num_components = len(plasmid.components)

        if num_components != 4:  # TODO subject to change for more complex L0s?
            return False
        else:
            component_definitions = [
                get_or_pull(self.sbol_doc, self.sbh, comp.definition)
                for comp in plasmid.getInSequentialOrder()
            ]

            for index, comp in enumerate(component_definitions):
                if bool(set(comp.roles) & set(PART_ROLES)):  # identify part index
                    previous_component = component_definitions[
                        (index - 1) % num_components
                    ]
                    next_component = component_definitions[(index + 1) % num_components]

                    if (
                        RESTRICTION_ENZYME_ASSEMBLY_SCAR in previous_component.roles
                        and RESTRICTION_ENZYME_ASSEMBLY_SCAR in next_component.roles
                    ):
                        return True

        return False
