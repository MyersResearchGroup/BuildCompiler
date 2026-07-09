import sbol2
import json
import random
import re
import shutil
import warnings
from typing import Any, List, Dict, Tuple
import urllib.parse
import csv
from pathlib import Path

from buildcompiler.plasmid import Plasmid
from buildcompiler.sbol2build import (
    Assembly,
    Transformation as SBOL2Transformation,
    dna_componentdefinition_with_sequence,
    rebase_restriction_enzyme,
)
from .abstract_translator import (
    enumerate_design_variants,
    extract_combinatorial_design_parts,
    extract_toplevel_definition,
    get_or_pull,
    get_compatible_plasmids,
)
from .robotutils import (
    assembly_plan_RDF_to_JSON,
    generate_96_well_positions,
    normalize_plating_input,
    run_opentrons_script_to_zip,
    write_manual_plating_protocol,
    write_plate_map_csv,
    write_plate_map_json,
    write_plating_protocol_script,
)
from .constants import (
    AMP,
    ENGINEERED_REGION,
    KAN,
    FUSION_SITES,
    LIGASE,
    LVL2_FUSION_SITE_ORDER,
    PART_ROLES,
    PLASMID_VECTOR,
    RESTRICTION_ENZYME,
    RESTRICTION_ENZYME_ASSEMBLY_SCAR,
    ENGINEERED_PLASMID,
    PLASMID_CLONING_VECTOR,
    ORGANISM_STRAIN,
    PLATING_ACTIVITY_ROLE,
)


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
        collections: List[str],
        sbh_registry: str,
        auth_token: str,
        sbol_doc: sbol2.Document = None,
        server_mode: bool = False,
    ):
        self.sbh = sbol2.PartShop(sbh_registry)
        self.sbh.key = auth_token
        self.sbol_doc = sbol_doc or sbol2.Document()
        self.indexed_plasmids = []
        self.indexed_backbones = []
        self.BsaI_impl = None
        self.BbsI_impl = None
        self.T4_ligase_impl = None
        self.server_mode = server_mode

        self._index_collections(collections)

    @classmethod
    def from_local_documents(
        cls,
        collection_docs: list[sbol2.Document],
        design_doc: sbol2.Document | None = None,
    ):
        """Create a BuildCompiler instance from already-loaded local SBOL documents."""
        compiler = cls.__new__(cls)
        compiler.sbh = None
        compiler.sbol_doc = sbol2.Document()
        compiler.indexed_plasmids = []
        compiler.indexed_backbones = []
        compiler.restriction_enzyme_implementations = []
        compiler.ligase_implementations = []

        if design_doc is not None:
            compiler.index_document(design_doc)

        for collection_doc in collection_docs:
            compiler.index_document(collection_doc)

        return compiler

    def index_document(self, collection_doc: sbol2.Document):
        self._merge_document(collection_doc)
        self._index_document_objects(collection_doc)

    def _index_collections(self, collections: List[str]):
        """Index input collections into plasmids and backbones.

        Parses the provided collections (which may contain plasmids, backbones, strains, and enzymes)
        and normalizes them into internal Plasmid/enzyme records that remain linked to
        their originating strain and implementation definitions.

        :param collections: Iterable of user-provided collections/documents.
        :type collections: Iterable
        :returns: None. Updates ``self.indexed_plasmids`` in place.
        :rtype: None
        """
        for uri in collections:
            if self.server_mode:
                canonical_resource = self.sbh.resource.replace("://api.", "://")
                uri = uri.replace(canonical_resource, self.sbh.resource)
            print(f"Indexing collection: {uri}")
            self.sbh.pull(uri, self.sbol_doc)
        self._index_current_document()

    def _merge_document(self, source_doc: sbol2.Document):
        try:
            self.sbol_doc.appendString(source_doc.writeString())
        except RuntimeError as exc:
            if "SBOL_ERROR_URI_NOT_UNIQUE" in str(exc):
                for top_level in source_doc.SBOLObjects.values():
                    if top_level.identity in self.sbol_doc:
                        continue
                    self.sbol_doc.add(top_level.copy())
            else:
                raise

    def _resolve_object(self, uri: str):
        existing = self.sbol_doc.find(uri)
        if existing is not None:
            return existing
        if self.sbh is None:
            raise ValueError(
                f"Referenced SBOL object not found in local documents: {uri}. "
                "Local mode does not pull from SynBioHub."
            )
        return get_or_pull(self.sbol_doc, self.sbh, uri)

    def _index_current_document(self):
        self._index_document_objects(self.sbol_doc)

        for implementation in self.sbol_doc.implementations:
            built_object = get_or_pull(
                self.sbol_doc, self.sbh, implementation.built, self.server_mode
            )
            if (
                type(built_object) is sbol2.ModuleDefinition
                and ORGANISM_STRAIN in built_object.roles
            ):
                self._extract_plasmids_from_strain(
                    built_object, implementation, self.sbol_doc
                )
            elif (
                type(built_object) is sbol2.ComponentDefinition
                and len(built_object.components) > 1
            ):
                if ENGINEERED_PLASMID in built_object.roles:
                    existing_plasmid = self._get_indexed_plasmid(
                        self.indexed_plasmids, built_object
                    )
                    if existing_plasmid:
                        self._append_implementation_once(
                            existing_plasmid.plasmid_implementations, implementation
                        )
                    else:
                        self.indexed_plasmids.append(
                            Plasmid(
                                built_object, None, [implementation], [], self.sbol_doc
                            )
                        )
                elif PLASMID_CLONING_VECTOR in built_object.roles:
                    existing_backbone = self._get_indexed_plasmid(
                        self.indexed_backbones, built_object
                    )
                    if existing_backbone:
                        self._append_implementation_once(
                            existing_backbone.plasmid_implementations, implementation
                        )
                    else:
                        self.indexed_backbones.append(
                            Plasmid(
                                built_object, None, [implementation], [], self.sbol_doc
                            )
                        )
            elif sbol2.BIOPAX_PROTEIN in built_object.types:
                if RESTRICTION_ENZYME in built_object.roles:
                    if (
                        "http://rebase.neb.com/rebase/enz/BsaI.html"
                        in built_object.wasDerivedFrom
                    ):
                        self.BsaI_impl = implementation
                    elif (
                        "http://rebase.neb.com/rebase/enz/BbsI.html"
                        in built_object.wasDerivedFrom
                    ):
                        self.BbsI_impl = implementation
                elif LIGASE in built_object.roles:
                    self.T4_ligase_impl = implementation

        for strain in source_doc.moduleDefinitions:
            if ORGANISM_STRAIN in strain.roles:
                self._extract_plasmids_from_strain(strain, None, self.sbol_doc)

        for definition in source_doc.componentDefinitions:
            self._sort_plasmid_components(definition, self.sbol_doc)

    def domestication(
        self,
        parts: list[sbol2.ComponentDefinition],
    ) -> list[sbol2.ComponentDefinition]:
        """Domesticate a list of genetic parts for Golden Gate assembly using the MoClo standard.

        For each part, this method identifies the necessary domestication
        steps (e.g., removing internal BsaI sites) and generates the appropiate dsDNA for DNA synthesis and the corresponding
        domesticated plasmids as new ComponentDefinitions in the SBOL document.

        :returns: List of domesticated ComponentDefinitions ready for assembly.
        :rtype: list[sbol2.ComponentDefinition]
        """

        role_to_fusion_sites = {
            "http://identifiers.org/so/SO:0000167": ("GGAG", "TACT"),
            "http://identifiers.org/so/SO:0000139": ("TACT", "AATG"),
            "http://identifiers.org/so/SO:0000316": ("AATG", "AGGT"),
            "http://identifiers.org/so/SO:0000141": ("AGGT", "GCTT"),
        }
        fusion_site_name_map = {
            sequence: name for name, sequence in FUSION_SITES.items()
        }

        def _random_dna(length: int) -> str:
            return "".join(random.choices("ACGT", k=length))

        def _remove_internal_bsai_sites(sequence: str) -> tuple[str, int]:
            domesticated_sequence = sequence.upper()
            removals = 0
            for site, replacement in (("GGTCTC", "GGTCTA"), ("GAGACC", "GAGACA")):
                while site in domesticated_sequence:
                    domesticated_sequence = domesticated_sequence.replace(
                        site, replacement, 1
                    )
                    removals += 1
            return domesticated_sequence, removals

        if self.BsaI_impl is None:
            self._create_RE_implementation("BsaI")
            warnings.warn(
                "BsaI Restriction enzyme not found in provided collection(s). Domestication via purchase will be added to protocol.",
                RuntimeWarning,
            )

        if self.T4_ligase_impl is None:
            self._create_ligase_implementation()
            warnings.warn(
                "No appropriate ligase found in provided collection(s). Domestication of T4 Ligase via purchase will be added to protocol.",
                RuntimeWarning,
            )

        dsDNAs = []
        domesticated_parts = []

        for part in parts:
            part_role = next(
                (role for role in part.roles if role in role_to_fusion_sites),
                None,
            )
            if part_role is None:
                raise ValueError(
                    f"Part {part.displayId} does not have a supported role for domestication."
                )

            fusion_site_sequences = role_to_fusion_sites[part_role]
            fusion_site_names = sorted(
                fusion_site_name_map[site] for site in fusion_site_sequences
            )
            backbone = next(
                (
                    indexed_backbone
                    for indexed_backbone in self.indexed_backbones
                    if indexed_backbone.antibiotic_resistance == AMP
                    and indexed_backbone.fusion_sites == fusion_site_names
                ),
                None,
            )
            if backbone is None:
                raise ValueError(
                    f"No backbone found for {part.displayId} with fusion sites "
                    f"{fusion_site_sequences[0]} and {fusion_site_sequences[1]} and antibiotic resistance {AMP}."
                )
            if len(part.sequences) != 1:
                raise ValueError(
                    f"Part {part.displayId} must have exactly one sequence for domestication."
                )

            part_sequence = self.sbol_doc.getSequence(part.sequences[0]).elements
            domesticated_sequence, removed_sites = (
                _remove_internal_bsai_sites(  # TODO make it to return the initial sequence and the modified sequence
                    part_sequence
                )
            )
            print(
                f"BsaI domestication check for {part.displayId}: "
                f"{removed_sites} internal site(s) removed."
            )

            insert_sequence = (
                _random_dna(35)
                + "GGTCTC"
                + fusion_site_sequences[0]
                + domesticated_sequence
                + fusion_site_sequences[1]
                + "GAGACC"
                + _random_dna(35)
            )
            insert_definition = self.sbol_doc.find(
                f"{part.displayId}_domestication_insert"
            )
            if insert_definition is None:
                insert_definition, insert_seq = dna_componentdefinition_with_sequence(
                    f"{part.displayId}_domestication_insert", insert_sequence
                )
                insert_definition.name = f"{part.displayId} domestication insert"
                insert_definition.description = (
                    f"Domestication insert for {part.displayId}. "
                    f"BsaI check removed {removed_sites} internal site(s)."
                )
                insert_definition.roles = list(part.roles)
                insert_definition.wasDerivedFrom = part.identity
                self.sbol_doc.add_list([insert_definition, insert_seq])

            insert_impl = self.sbol_doc.find(
                f"{part.displayId}_domestication_insert_impl"
            )
            if insert_impl is None:
                insert_impl = sbol2.Implementation(
                    f"{insert_definition.displayId}_impl"
                )
                insert_impl.built = insert_definition.identity
                self.sbol_doc.add(insert_impl)
                dsDNAs.append(insert_impl)

            assembly = Assembly(
                [Plasmid(insert_definition, None, [insert_impl], [], self.sbol_doc)],
                backbone,
                self.BsaI_impl,
                self.T4_ligase_impl,
                self.sbol_doc,
            )
            assembly_products, assembly_doc = assembly.run()
            product_definition = assembly_products[0].plasmid_definition
            domesticated_parts.append(product_definition)

        return domesticated_parts

    def assembly_lvl1(
        self,
        abstract_designs: (
            List[sbol2.ComponentDefinition] | sbol2.CombinatorialDerivation
        ),
        final_doc: sbol2.Document = sbol2.Document(),
        product_name: str = "composite",
        backbone: Plasmid | Dict[str, Plasmid] | None = None,
    ) -> Tuple[Dict, sbol2.Document]:
        """Assemble level-1 plasmids for each gene/transcriptional unit.

        Uses indexed plasmids/backbones and the current design to assemble
        lvl1 plasmids in the correct order.

        :returns: List of assembled lvl1 plasmids.
        :rtype: list[Plasmid]
        :raises LookupError: If compatible plasmids or backbones cannot be found.
        """

        assembly_dict = {}
        if type(abstract_designs) is sbol2.CombinatorialDerivation:
            abstract_design_def = self.sbol_doc.getComponentDefinition(
                abstract_designs.masterTemplate
            )

            combinatorial_part_dict = self.extract_combinatorial_design_parts(
                abstract_design_def, abstract_designs
            )

            enumerated_part_lists = enumerate_design_variants(combinatorial_part_dict)

            for i, list in enumerate(enumerated_part_lists):
                plasmid_dict = self._construct_plasmid_dict(list, AMP)

                if isinstance(backbone, dict):
                    raise ValueError(
                        "A backbone dictionary cannot be used with a CombinatorialDerivation. "
                        "All variants share the same template, so supply a single Plasmid or None to auto-select."
                    )
                elif not backbone:
                    backbone, compatible_plasmids = self._get_backbone(
                        plasmid_dict, antibiotic_resistance=KAN
                    )
                elif type(backbone) is Plasmid:
                    compatible_plasmids = get_compatible_plasmids(
                        plasmid_dict, backbone
                    )

                if self.BsaI_impl is None:
                    self._create_RE_implementation("BsaI")
                    warnings.warn(
                        "BsaI Restriction enzyme not found in provided collection(s). Domestication via purchase will be added to protocol.",
                        RuntimeWarning,
                    )

                if self.T4_ligase_impl is None:
                    self._create_ligase_implementation()
                    warnings.warn(
                        "No appropriate ligase found in provided collection(s). Domestication of T4 Ligase via purchase will be added to protocol.",
                        RuntimeWarning,
                    )

                assembly = Assembly(
                    compatible_plasmids,
                    backbone,
                    self.BsaI_impl,
                    self.T4_ligase_impl,
                    self.sbol_doc,
                    final_doc,
                    f"{abstract_design_def.displayId}_{product_name}_comb{i}",
                )
                composite_plasmids, final_doc = (
                    assembly.run()
                )  # TODO upload product_doc?

                self.indexed_plasmids.extend(
                    composite_plasmids
                )  # see about using a wrapper function to do this, where it checks if the design already exists (like in index_collections). this way we avoid duplicate issues that might come with loading the abstract design definitions into the self.sbol_doc ahead of time

                assembly_dict.setdefault(abstract_design_def.identity, []).extend(
                    composite_plasmids
                )
        else:  # list of designs
            for abstract_design in abstract_designs:
                plasmid_dict = self._get_input_plasmids(
                    design=abstract_design, antibiotic_resistance=AMP
                )

                if not backbone:
                    resolved_backbone, compatible_plasmids = self._get_backbone(
                        plasmid_dict, antibiotic_resistance=KAN
                    )
                elif isinstance(backbone, dict):
                    resolved_backbone = backbone.get(abstract_design.displayId)
                    if resolved_backbone is None:
                        raise ValueError(
                            f"Backbone dict provided but no entry found for design '{abstract_design.displayId}'. "
                            f"Available keys: {list(backbone.keys())}"
                        )
                    compatible_plasmids = get_compatible_plasmids(
                        plasmid_dict, resolved_backbone
                    )
                else:
                    resolved_backbone, compatible_plasmids = (
                        backbone,
                        get_compatible_plasmids(plasmid_dict, backbone),
                    )

                if self.BsaI_impl is None:
                    self._create_RE_implementation("BsaI")
                    warnings.warn(
                        "BsaI Restriction enzyme not found in provided collection(s). Domestication via purchase will be added to protocol.",
                        RuntimeWarning,
                    )

                if self.T4_ligase_impl is None:
                    self._create_ligase_implementation()
                    warnings.warn(
                        "No appropriate ligase found in provided collection(s). Domestication of T4 Ligase via purchase will be added to protocol.",
                        RuntimeWarning,
                    )

                assembly = Assembly(
                    compatible_plasmids,
                    resolved_backbone,
                    self.BsaI_impl,
                    self.T4_ligase_impl,
                    self.sbol_doc,
                    final_doc,
                    f"{abstract_design.displayId}_{product_name}",
                )
                composite_plasmids, final_doc = (
                    assembly.run()
                )  # TODO upload product_doc?

                self.indexed_plasmids.extend(
                    composite_plasmids
                )  # see about using a wrapper function to do this, where it checks if the design already exists (like in index_collections). this way we avoid duplicate issues that might come with loading the abstract design definitions into the self.sbol_doc ahead of time
                assembly_dict[abstract_design.identity] = composite_plasmids

        return assembly_dict, final_doc

    def assembly_lvl2(
        self,
        abstract_design_doc: sbol2.Document,
        backbone: Plasmid = None,
        product_name: str = None,
    ) -> list[sbol2.ComponentDefinition]:
        """Assemble level-2 plasmids for the full design.

        Uses the assembled lvl1 plasmids and the current design to assemble
        lvl2 plasmids in the correct order.

        :returns: List of assembled lvl2 plasmids.
        :rtype: list[Plasmid]
        :raises LookupError: If compatible plasmids or backbones cannot be found.
        """
        # get high level genes, send to assembly_lvl1
        # send original abstract_design to get a new dictionary
        # send new dictionary to _get_backbone or get_compatible plasmids with AMP
        TUs = _extract_lvl2_TUs(abstract_design_doc)
        backbone_dict = {}
        lvl1_plasmids = []

        for i, TU in enumerate(TUs):
            print(TU.displayId)

            # l1 backbone zselection
            backbone_fusion_sites = LVL2_FUSION_SITE_ORDER[i]
            lvl1_backbone = next(
                plasmid
                for plasmid in self.indexed_backbones
                if plasmid.fusion_sites == backbone_fusion_sites
                and plasmid.antibiotic_resistance == KAN
            )

            backbone_dict[TU.displayId] = lvl1_backbone

            # TODO insert check here to see if the TU exists already (#43). should not be too expensive, as long as we search only indexed_plasmids where AR=KAN

        composite_plasmid_dict, final_doc = self.assembly_lvl1(
            TUs, backbone=backbone_dict, product_name=f"{TU.displayId}_plas"
        )

        for key, composites in composite_plasmid_dict.items():
            simplified_representation, new_defs = self._encapsulate_TU(composites[0])
            final_doc.add_list(new_defs)
            lvl1_plasmids.append(simplified_representation)
            print(simplified_representation)

        # get l2 backbone
        plasmid_dict = {}
        for p in lvl1_plasmids:
            key = p.plasmid_definition.displayId
            plasmid_dict.setdefault(key, []).append(p)

        if backbone is None:
            backbone, _ = self._get_backbone(plasmid_dict, antibiotic_resistance=AMP)

        print(backbone)

        # BbsI for l2
        if self.BbsI_impl is None:
            self._create_RE_implementation("BbsI")
            warnings.warn(
                "BbsI Restriction enzyme not found in provided collection(s). Domestication via purchase will be added to protocol.",
                RuntimeWarning,
            )

        # TODO see about making these common enzymes (BsaI, BbSI, T4) global or class variables, so they only need to be searched for once
        if self.T4_ligase_impl is None:
            self._create_ligase_implementation()
            warnings.warn(
                "No appropriate ligase found in provided collection(s). Domestication of T4 Ligase via purchase will be added to protocol.",
                RuntimeWarning,
            )

        assembly = Assembly(
            lvl1_plasmids,
            backbone,
            self.BbsI_impl,
            self.T4_ligase_impl,
            self.sbol_doc,
            final_doc,
            product_name,
        )

        lvl2_plasmids, final_doc = assembly.run()  # TODO upload product_doc?
        self.indexed_plasmids.extend(lvl2_plasmids)

        return lvl2_plasmids, final_doc

    def transformation(
        self,
        assembly_products: List[Plasmid],
        chassis_name: str = "E_coli_DH5alpha",
        transformation_doc: sbol2.Document = None,
    ) -> Dict[str, Any]:
        """Generate deterministic transformation artifacts from assembly outputs.

        :param assembly_products: Structured inputs produced by an assembly stage
        :type assembly_products: List[Plasmid]
        :param chassis_name: Display id used for the chassis module and implementation.
        :type chassis_name: str
        :param transformation_doc: Optional SBOL document to write outputs into.
        :type transformation_doc: sbol2.Document | None
        :returns: Structured transformation outputs including SBOL references,
            robot JSON intermediate, protocol placeholders, and logs.
        :rtype: dict
        :raises ValueError: If no valid plasmid inputs can be extracted.
        """
        if transformation_doc is None:
            transformation_doc = self.sbol_doc

        chassis_module, chassis_impl = self._get_or_create_chassis(
            transformation_doc, chassis_name
        )

        sbol_outputs = []
        robot_steps = []
        logs = []

        for index, plasmid_obj in enumerate(assembly_products, start=1):
            plasmid = plasmid_obj.plasmid_definition

            if not plasmid_obj.plasmid_implementations:
                raise ValueError(
                    f"No plasmid implementations found for {plasmid.displayId}"
                )

            plasmid_impl = plasmid_obj.plasmid_implementations[0]

            transform_id = f"transform_{plasmid.displayId}_{index}"

            transformation_activity = sbol2.Activity(transform_id)
            transformation_activity.name = (
                f"Transform {chassis_name} with {plasmid.displayId}"
            )
            transformation_activity.types = "http://sbols.org/v2#build"

            chassis_usage = sbol2.Usage(
                uri=f"{transform_id}_chassis",
                entity=chassis_impl.identity,
                role="http://sbols.org/v2#build",
            )
            plasmid_usage = sbol2.Usage(
                uri=f"{transform_id}_plasmid",
                entity=plasmid_impl.identity,
                role="http://sbols.org/v2#build",
            )
            transformation_activity.usages = [chassis_usage, plasmid_usage]

            transformed_strain = sbol2.ModuleDefinition(
                f"{chassis_name}_with_{plasmid.displayId}"
            )
            transformed_strain.roles = [ORGANISM_STRAIN]
            transformed_strain.name = (
                f"{chassis_name} transformed with {plasmid.displayId}"
            )

            chassis_module_ref = sbol2.Module(
                uri=f"{transformed_strain.displayId}_chassis"
            )
            chassis_module_ref.definition = chassis_module.identity
            plasmid_fc = sbol2.FunctionalComponent(
                uri=f"{transformed_strain.displayId}_plasmid"
            )
            plasmid_fc.definition = plasmid.identity

            transformed_strain.modules = [chassis_module_ref]
            transformed_strain.functionalComponents = [plasmid_fc]

            transformation_activity_association = sbol2.Association(
                f"transform_{chassis_module_ref.name}"
            )

            transformation_activity_plan = sbol2.Plan(
                f"{transformed_strain.displayId}_transformation_plan"
            )
            transformation_activity_plan.description = (
                "TODO: generate accurate description of transformation"
            )
            transformation_activity_association.plan = transformation_activity_plan

            transformation_activity_agent = sbol2.Agent("BuildCompiler")
            transformation_activity_association.agent = transformation_activity_agent

            transformation_activity.associations = [transformation_activity_association]

            transformed_impl = sbol2.Implementation(
                f"{transformed_strain.displayId}_impl"
            )

            transformed_impl.built = transformed_strain.identity
            transformed_impl.wasGeneratedBy = transformation_activity.identity

            for obj in (
                transformation_activity,
                chassis_usage,
                plasmid_usage,
                transformed_strain,
                chassis_module_ref,
                plasmid_fc,
                transformed_impl,
            ):
                self._add_if_absent(transformation_doc, obj)

            sbol_outputs.append(
                {
                    "transformation_activity": transformation_activity.identity,
                    "transformed_strain_module": transformed_strain.identity,
                    "transformed_strain_implementation": transformed_impl.identity,
                }
            )
            robot_steps.append(
                {
                    "step": index,
                    "plasmid": plasmid.displayId,
                    "chassis": chassis_name,
                    "mix_ul": {"competent_cells": 50, "assembly_product": 5},
                    "heat_shock": {"temperature_c": 42, "duration_seconds": 45},
                    "recovery": {"medium": "SOC", "volume_ul": 950, "duration_min": 60},
                }
            )
            logs.append(
                f"Prepared transformation input for plasmid {plasmid.displayId} into chassis {chassis_name}."
            )

        return {
            "stage": "transformation",
            "inputs": [
                plasmid.plasmid_definition.displayId for plasmid in assembly_products
            ],
            "chassis": chassis_name,
            "sbol_artifacts": sbol_outputs,
            "json_intermediate": {
                "protocol": "chemical_transformation",
                "version": "0.1",
                "steps": robot_steps,
            },
            "protocol_artifacts": {
                "ot2_script": "TODO: adapter to protocol generator",
                "human_instructions": [
                    "Thaw competent cells on ice.",
                    "Combine assembly product with competent cells as specified.",
                    "Run heat shock and recovery according to generated parameters.",
                ],
                "logs": logs,
            },
        }

    def transformation(
        self,
        assembly_products: List[Any],
        chassis_name: str = "E_coli_DH5alpha",
        transformation_doc: sbol2.Document = None,
    ) -> Dict[str, Any]:
        """Generate deterministic transformation artifacts from assembly outputs.

        The method accepts either:
        - ``Plasmid`` objects,
        - ``sbol2.ComponentDefinition`` plasmids, or
        - dictionaries containing at least a ``plasmid`` key with one of the above.

        :param assembly_products: Structured inputs produced by an assembly stage.
        :type assembly_products: list
        :param chassis_name: Display id used for the chassis module and implementation.
        :type chassis_name: str
        :param transformation_doc: Optional SBOL document to write outputs into.
        :type transformation_doc: sbol2.Document | None
        :returns: Structured transformation outputs including SBOL references,
            robot JSON intermediate, protocol placeholders, and logs.
        :rtype: dict
        :raises ValueError: If no valid plasmid inputs can be extracted.
        """
        if transformation_doc is None:
            transformation_doc = self.sbol_doc

        normalized_products = self._normalize_transformation_inputs(assembly_products)
        if not normalized_products:
            raise ValueError("transformation requires at least one plasmid input.")

        chassis_module, chassis_impl = self._get_or_create_chassis(
            transformation_doc, chassis_name
        )
        normalized_plasmids = []
        for product in normalized_products:
            indexed = self._get_indexed_plasmid(
                self.indexed_plasmids, product["plasmid"]
            )
            if indexed is None:
                indexed = type(
                    "TransformationPlasmid",
                    (),
                    {
                        "plasmid_definition": product["plasmid"],
                        "plasmid_implementations": [],
                        "name": product["plasmid"].displayId,
                    },
                )()
            normalized_plasmids.append(indexed)

        sbol_outputs = SBOL2Transformation(
            plasmids=normalized_plasmids,
            chassis_name=chassis_name,
            source_document=transformation_doc,
        ).chemical_transformation()

        robot_steps = []
        logs = []

        for index, product in enumerate(normalized_products, start=1):
            plasmid = product["plasmid"]
            robot_steps.append(
                {
                    "step": index,
                    "plasmid": plasmid.displayId,
                    "chassis": chassis_name,
                    "mix_ul": {"competent_cells": 50, "assembly_product": 5},
                    "heat_shock": {"temperature_c": 42, "duration_seconds": 45},
                    "recovery": {"medium": "SOC", "volume_ul": 950, "duration_min": 60},
                }
            )
            logs.append(
                f"Prepared transformation input for plasmid {plasmid.displayId} into chassis {chassis_name}."
            )

        return {
            "stage": "transformation",
            "inputs": [item["source"] for item in normalized_products],
            "chassis": chassis_name,
            "sbol_artifacts": sbol_outputs,
            "json_intermediate": {
                "protocol": "chemical_transformation",
                "version": "0.1",
                "steps": robot_steps,
            },
            "protocol_artifacts": {
                "ot2_script": "TODO: adapter to protocol generator",
                "human_instructions": [
                    "Thaw competent cells on ice.",
                    "Combine assembly product with competent cells as specified.",
                    "Run heat shock and recovery according to generated parameters.",
                ],
                "logs": logs,
            },
        }

    def plating(
        self,
        transformation_results: dict,
        results_dir: str | Path,
        protocol_type: str = "manual",
        advanced_params: dict | None = None,
        plate_name: str | None = None,
        plating_doc: sbol2.Document | None = None,
        overwrite: bool = False,
    ) -> Dict[str, Any]:
        """Generate plating layout artifacts and protocol metadata.

        This implementation is file/metadata oriented and does not create new
        SBOL objects for plating.
        """
        if protocol_type not in {"manual", "automated"}:
            raise ValueError("protocol_type must be one of: 'manual', 'automated'.")
        advanced_params = advanced_params or {}
        doc_ref = plating_doc or self.sbol_doc

        normalized = normalize_plating_input(transformation_results, doc=doc_ref)
        if len(normalized) > 96:
            raise ValueError("plating supports up to 96 transformed strains.")

        wells = generate_96_well_positions(limit=len(normalized))
        results_path = Path(results_dir)
        results_path.mkdir(parents=True, exist_ok=True)

        plate_id = plate_name or "solid_96_well_plate"
        plate_rows = []
        plate_map = {}
        bacterium_locations = {}

        for idx, entry in enumerate(normalized):
            well = wells[idx]
            source_impl_uri = entry.get("source_impl_uri")
            source_impl = doc_ref.find(source_impl_uri) if source_impl_uri else None
            strain_module_uri = entry.get("strain_module_uri")
            if strain_module_uri is None and source_impl is not None:
                strain_module_uri = getattr(source_impl, "built", None)

            display_source = source_impl_uri or strain_module_uri or f"strain_{idx+1}"
            parsed = urllib.parse.urlparse(display_source)
            slug = parsed.path.split("/")[-1] if parsed.path else display_source
            slug = slug.replace("#", "_").replace(":", "_")

            plated_impl_id = f"{slug}_plated_{well}_impl"
            plate_map[well] = plated_impl_id
            display_name = plated_impl_id
            bacterium_locations[well] = display_name
            plate_rows.append(
                {
                    "well": well,
                    "source_transformed_strain_implementation": source_impl_uri,
                    "strain_module": strain_module_uri,
                    "plated_strain_implementation": plated_impl_id,
                    "strain_display_name": display_name,
                }
            )

        plate_layout_csv = results_path / "plate_layout_dataframe.csv"
        with plate_layout_csv.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(
                handle,
                fieldnames=list(plate_rows[0].keys()) if plate_rows else ["well"],
            )
            writer.writeheader()
            for row in plate_rows:
                writer.writerow(row)

        plate_map_json_path = write_plate_map_json(
            results_path / "plate_map.json",
            {
                "plate_implementation": plate_id,
                "protocol_type": protocol_type,
                "well_map": plate_rows,
            },
        )
        plate_map_csv_path = write_plate_map_csv(
            results_path / "plate_map.csv", plate_rows
        )
        plating_input_json_path = write_plate_map_json(
            results_path / "plating_input.json",
            {"bacterium_locations": bacterium_locations},
        )

        logs = []
        protocol_artifacts: Dict[str, Any] = {
            "plate_map_json": str(plate_map_json_path),
            "plate_map_csv": str(plate_map_csv_path),
            "plate_layout_dataframe_csv": str(plate_layout_csv),
            "logs": logs,
            "pudu": {
                "runner_script": "https://github.com/MyersResearchGroup/PUDU/blob/main/scripts/run_sbol2plating_with_params.py",
                "mode": protocol_type,
                "advanced_params": advanced_params,
            },
        }

        if protocol_type == "manual":
            md_path = write_manual_plating_protocol(
                results_path / "manual_plating_protocol.md",
                plate_id=plate_id,
                plate_rows=plate_rows,
                advanced_params=advanced_params,
            )
            protocol_artifacts["manual_protocol_markdown"] = str(md_path)
        else:
            script_path = write_plating_protocol_script(
                results_path / "plating_ot2.py",
                plating_data={"bacterium_locations": bacterium_locations},
                advanced_params=advanced_params,
            )
            protocol_artifacts["ot2_script"] = str(script_path)
            try:
                sim_zip = run_opentrons_script_to_zip(
                    script_path,
                    plating_input_json_path,
                    overwrite=overwrite,
                )
                protocol_artifacts["simulation_zip"] = str(sim_zip)
            except Exception as exc:
                logs.append(f"Opentrons simulation skipped: {exc}")

        return {
            "stage": "plating",
            "protocol_type": protocol_type,
            "plate": {
                "plate_implementation": plate_id,
                "plate_map": plate_map,
            },
            "metadata": {
                "plate_rows": plate_rows,
                "layout_dataframe_columns": (
                    list(plate_rows[0].keys()) if plate_rows else []
                ),
            },
            "json_intermediate": {
                "plating_data": {"bacterium_locations": bacterium_locations},
                "advanced_params": advanced_params,
            },
            "protocol_artifacts": protocol_artifacts,
        }

    def _extract_plasmids_from_strain(
        self,
        strain: sbol2.ModuleDefinition,
        strain_implementation: sbol2.Implementation,
        doc: sbol2.Document,
    ):
        # strain_implementation = optional param
        for plasmid in strain.functionalComponents:
            plasmid_definition = get_or_pull(
                doc, self.sbh, plasmid.definition, self.server_mode
            )

            if ENGINEERED_PLASMID in plasmid_definition.roles:
                existing = self._get_indexed_plasmid(
                    self.indexed_plasmids, plasmid_definition
                )

                if existing:
                    # Add strain if not already recorded, else do nothing
                    if all(
                        s.identity != strain.identity
                        for s in existing.strain_definitions
                        if s is not None
                    ):
                        existing.strain_definitions.append(strain)

                    if strain_implementation:
                        existing.strain_implementations.append(strain_implementation)
                else:
                    # Create new Plasmid entry
                    self.indexed_plasmids.append(
                        Plasmid(
                            plasmid_definition,
                            strain,
                            [],
                            [strain_implementation] if strain_implementation else [],
                            doc,
                        )
                    )
            elif PLASMID_CLONING_VECTOR in plasmid_definition.roles:
                existing = self._get_indexed_plasmid(
                    self.indexed_backbones, plasmid_definition
                )
                if existing:
                    # Add strain if not already recorded, else do nothing
                    if all(
                        s.identity != strain.identity
                        for s in existing.strain_definitions
                        if s is not None
                    ):
                        existing.strain_definitions.append(strain)

                    if strain_implementation:
                        existing.strain_implementations.append(strain_implementation)
                else:
                    # Create new backbone entry
                    self.indexed_backbones.append(
                        Plasmid(
                            plasmid_definition,
                            strain,
                            [],
                            [strain_implementation] if strain_implementation else [],
                            doc,
                        )
                    )

    def _get_indexed_plasmid(self, plasmid_list, plasmid_definition):
        return next(
            (
                p
                for p in plasmid_list
                if p.plasmid_definition.identity == plasmid_definition.identity
            ),
            None,
        )

    def _sort_plasmid_components(
        self, definition: sbol2.ComponentDefinition, doc: sbol2.Document
    ):
        if len(definition.components) > 1:
            if (
                ENGINEERED_PLASMID in definition.roles
                and not self._get_indexed_plasmid(self.indexed_plasmids, definition)
            ):
                self.indexed_plasmids.append(Plasmid(definition, None, [], [], doc))
            elif (
                PLASMID_CLONING_VECTOR in definition.roles
                and not self._get_indexed_plasmid(self.indexed_backbones, definition)
            ):
                self.indexed_backbones.append(Plasmid(definition, None, [], [], doc))

    def _get_input_plasmids(
        self, design: sbol2.ComponentDefinition, antibiotic_resistance: str
    ) -> Dict[str, List[Plasmid]]:
        """
        with AR=ampicillin.
        """

        parts = self._extract_design_parts(design)
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

    def _extract_design_parts(
        self, design: sbol2.ComponentDefinition
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
            get_or_pull(self.sbol_doc, self.sbh, component.definition, self.server_mode)
            for component in component_list
        ]

    def extract_combinatorial_design_parts(
        self,
        design: sbol2.ComponentDefinition,
        derivation: sbol2.CombinatorialDerivation,
    ) -> Dict[str, List[sbol2.ComponentDefinition]]:
        """
        Extracts and returns a mapping of component definitions from a combinatorial design, in order.
        Variants of combinatinatorial components are entered in a list corresponding to the URI of the component in the abstract design.

        Args:
            design:
                The top-level :class:`sbol2.ComponentDefinition` representing the
                abstract design template whose components should be extracted in
                sequential order.

            derivation:
                The :class:`sbol2.CombinatorialDerivation` associated with ``design``
                that defines variable components and their allowed variants.

        Returns:
            Dict[str, List[sbol2.ComponentDefinition]]:
                A dictionary mapping component identities to lists
                of variable component definitions.

                - Sequential design components map to lists containing a single definition.
                - Combinatorial variable components map to lists of variant definitions.
        """
        component_list = [c for c in design.getInSequentialOrder()]
        component_dict = {
            component.identity: [
                get_or_pull(
                    self.sbol_doc, self.sbh, component.definition, self.server_mode
                )
            ]
            for component in component_list
        }

        for component in derivation.variableComponents:
            component_dict[component.variable] = [
                self.sbol_doc.getComponentDefinition(var) for var in component.variants
            ]

        return component_dict

    def _get_abstract_design(self) -> sbol2.ComponentDefinition:
        for definition in source_doc.componentDefinitions:
            if (
                ENGINEERED_PLASMID in definition.roles
                or PLASMID_CLONING_VECTOR in definition.roles
                or len(definition.components) <= 1
            ):
                continue

            component_definitions = [
                get_or_pull(
                    self.sbol_doc, self.sbh, component.definition, self.server_mode
                )
                for component in definition.getInSequentialOrder()
            ]
            if any(
                set(component.roles) & PART_ROLES for component in component_definitions
            ):
                return definition

        raise ValueError("No abstract design found in the SBOL document.")

    def _get_required_fusion_sites(
        self, part_list: List[sbol2.ComponentDefinition]
    ) -> List[tuple[str, str]]:
        fusion_site_names = sorted(FUSION_SITES)
        if len(part_list) + 1 > len(fusion_site_names):
            raise ValueError("Abstract design exceeds supported fusion-site positions.")

        return [
            (fusion_site_names[index], fusion_site_names[index + 1])
            for index in range(len(part_list))
        ]

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
                if (
                    ENGINEERED_PLASMID in plasmid.plasmid_definition.roles
                ):  # TODO only grab implemented plasmids
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
                get_or_pull(self.sbol_doc, self.sbh, comp.definition, self.server_mode)
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

    def _encapsulate_TU(
        self, plasmid: Plasmid
    ) -> Tuple[Plasmid, List[sbol2.Identified]]:
        """
        Collapse a detailed plasmid with a transcriptional unit (pro, rbs, cds, terminator)
        into a simplified representation:

            fusion_site_left -> TU -> fusion_site_right -> backbone

        Builds new sequences for both the TU and simplified plasmid.

        Returns
        -------
        Tuple[Plasmid, List[Identified]]
            simplified plasmid and all new SBOL objects created
        """

        new_objs = []
        plasmid_def = plasmid.plasmid_definition

        fusion_left, fusion_right = plasmid.fusion_sites
        left_seq = FUSION_SITES[fusion_left]
        right_seq = FUSION_SITES[fusion_right]

        left_def = None
        right_def = None
        backbone_def = None
        promoter = None
        terminator = None

        # scan subcomponents for pro and term to establish range + get backbone
        for comp in plasmid_def.components:
            comp_def = self.sbol_doc.get(comp.definition)

            if RESTRICTION_ENZYME_ASSEMBLY_SCAR in comp_def.roles:
                seq_obj = self.sbol_doc.get(comp_def.sequences[0])
                if seq_obj.elements == left_seq:
                    left_def = comp_def
                    continue
                if seq_obj.elements == right_seq:
                    right_def = comp_def
                    continue

            elif PLASMID_VECTOR in comp_def.roles:
                backbone_def = comp_def

            elif sbol2.SO_PROMOTER in comp_def.roles:
                promoter = comp

            elif sbol2.SO_TERMINATOR in comp_def.roles:
                terminator = comp

        if promoter is None or terminator is None:
            raise ValueError("Could not locate promoter or terminator in plasmid TU")

        comp_dict = {c.identity: c for c in plasmid_def.components}

        follows = {}
        for sc in plasmid_def.sequenceConstraints:
            if sc.restriction == sbol2.SBOL_RESTRICTION_PRECEDES:
                subject_comp = comp_dict[sc.subject]
                object_comp = comp_dict[sc.object]
                follows[subject_comp] = object_comp

        old_tu_components = []
        curr_comp = promoter

        while True:
            old_tu_components.append(curr_comp)

            if curr_comp.identity == terminator.identity:
                break

            if curr_comp not in follows:
                raise ValueError("Broken sequence constraint chain in TU")

            curr_comp = follows[curr_comp]

        def build_sequence_from_components(components):
            seq = ""
            ranges = {}
            cursor = 1

            for comp in components:
                comp_def = self.sbol_doc.get(comp.definition)

                if not comp_def.sequences:
                    raise ValueError(f"{comp_def.displayId} has no sequence")

                seq_obj = self.sbol_doc.get(comp_def.sequences[0])
                part_seq = seq_obj.elements

                start = cursor
                end = cursor + len(part_seq) - 1

                ranges[comp.identity] = (start, end)

                seq += part_seq
                cursor = end + 1

            return seq, ranges

        # Create TU definition
        tu_def = sbol2.ComponentDefinition(plasmid_def.displayId + "_TU")
        tu_def.roles = [ENGINEERED_REGION]

        self.sbol_doc.add(tu_def)
        new_objs.append(tu_def)

        # map old components to new
        comp_map = {}

        for comp in old_tu_components:
            new_comp = tu_def.components.create(comp.displayId)
            new_comp.definition = comp.definition
            comp_map[comp.identity] = new_comp.identity

        # Build TU sequence
        tu_seq_string, tu_ranges = build_sequence_from_components(old_tu_components)

        tu_seq = sbol2.Sequence(
            tu_def.displayId + "_seq",
            elements=tu_seq_string,
            encoding=sbol2.SBOL_ENCODING_IUPAC,
        )

        self.sbol_doc.addSequence(tu_seq)
        tu_def.sequences = [tu_seq.identity]

        new_objs.append(tu_seq)

        # Copy TU annotations
        for sa in plasmid_def.sequenceAnnotations:
            if sa.component not in comp_map:
                continue

            new_sa = tu_def.sequenceAnnotations.create(sa.displayId)
            new_sa.component = comp_map[sa.component]

            offset_start, _ = tu_ranges[sa.component]

            for loc in sa.locations:
                if isinstance(loc, sbol2.Range):
                    new_start = offset_start + loc.start - 1
                    new_end = offset_start + loc.end - 1

                    new_loc = new_sa.locations.createRange(loc.displayId)
                    new_loc.start = new_start
                    new_loc.end = new_end
                    new_loc.orientation = loc.orientation

        # --------------------------------------------------
        # Copy TU sequence constraints
        # --------------------------------------------------
        for sc in plasmid_def.sequenceConstraints:
            if sc.subject in comp_map and sc.object in comp_map:
                new_sc = tu_def.sequenceConstraints.create(sc.displayId)
                new_sc.subject = comp_map[sc.subject]
                new_sc.object = comp_map[sc.object]
                new_sc.restriction = sc.restriction

        # --------------------------------------------------
        # Build simplified plasmid definition
        # --------------------------------------------------
        simple_plasmid_def = sbol2.ComponentDefinition(
            plasmid_def.displayId + "_simple"
        )

        self.sbol_doc.addComponentDefinition(simple_plasmid_def)
        new_objs.append(simple_plasmid_def)

        simple_plasmid_def.types = list(plasmid_def.types)
        simple_plasmid_def.roles = list(plasmid_def.roles)

        fusion_left_comp = simple_plasmid_def.components.create("fusion_left")
        fusion_left_comp.definition = left_def.identity

        tu_comp = simple_plasmid_def.components.create("TU")
        tu_comp.definition = tu_def.identity

        fusion_right_comp = simple_plasmid_def.components.create("fusion_right")
        fusion_right_comp.definition = right_def.identity

        backbone_comp = None
        if backbone_def:
            backbone_comp = simple_plasmid_def.components.create("backbone")
            backbone_comp.definition = backbone_def.identity

        # --------------------------------------------------
        # Sequence ordering constraints
        # --------------------------------------------------
        constraint_counter = 0

        def add_precedes(subj, obj):
            nonlocal constraint_counter
            sc = simple_plasmid_def.sequenceConstraints.create(
                f"constraint_{constraint_counter}"
            )
            sc.subject = subj.identity
            sc.object = obj.identity
            sc.restriction = sbol2.SBOL_RESTRICTION_PRECEDES
            constraint_counter += 1

        add_precedes(fusion_left_comp, tu_comp)
        add_precedes(tu_comp, fusion_right_comp)

        if backbone_comp:
            add_precedes(fusion_right_comp, backbone_comp)

        # --------------------------------------------------
        # Build simplified plasmid sequence
        # --------------------------------------------------
        ordered_components = [fusion_left_comp, tu_comp, fusion_right_comp]

        if backbone_comp:
            ordered_components.append(backbone_comp)

        plas_seq_string, plas_ranges = build_sequence_from_components(
            ordered_components
        )

        plas_seq = sbol2.Sequence(
            simple_plasmid_def.displayId + "_seq",
            elements=plas_seq_string,
            encoding=sbol2.SBOL_ENCODING_IUPAC,
        )

        self.sbol_doc.addSequence(plas_seq)
        simple_plasmid_def.sequences = [plas_seq.identity]

        new_objs.append(plas_seq)

        for comp_uri, (start, end) in plas_ranges.items():
            anno = simple_plasmid_def.sequenceAnnotations.create(
                f"simple_plasmid_def_{start}_{end}_annotation"
            )
            anno.component = comp_uri

            location = anno.locations.createRange(
                f"{simple_plasmid_def.displayId}_{start}_{end}_location"
            )
            location.start = start
            location.end = end

        # --------------------------------------------------
        # Construct new plasmid object
        # --------------------------------------------------
        new_plasmid = Plasmid(
            simple_plasmid_def,
            plasmid.strain_definitions[0],
            plasmid.plasmid_implementations,
            plasmid.strain_implementations,
            self.sbol_doc,
        )

        return new_plasmid, new_objs

    def _create_RE_implementation(self, name: str):
        RE_def = rebase_restriction_enzyme(name)

        RE_sourcing = sbol2.Activity(f"{name}_restriction_enzyme_purchase")
        RE_sourcing.name = "Restriction Enzyme Purchase"

        RE_impl = sbol2.Implementation(f"{RE_def.displayId}_impl")

        RE_impl.built = RE_def.identity
        RE_impl.wasGeneratedBy = RE_sourcing.identity

        self.sbol_doc.add_list([RE_impl, RE_def])

        if name == "BsaI":
            self.BsaI_impl = RE_impl
        elif name == "BbsI":
            self.BbsI_impl = RE_impl

    def _create_ligase_implementation(self):
        ligase_def = sbol2.ComponentDefinition("T4_Ligase")
        ligase_def.name = "T4_Ligase"
        ligase_def.types = [sbol2.BIOPAX_PROTEIN]
        ligase_def.roles = ["http://identifiers.org/ncit/NCIT:C16796"]

        ligase_sourcing = sbol2.Activity("ligase_purchase")
        ligase_sourcing.name = "Ligase Purchase"

        T4_impl = sbol2.Implementation(f"{ligase_def.displayId}_impl")

        T4_impl.built = ligase_def.identity
        T4_impl.wasGeneratedBy = ligase_sourcing.identity

        self.sbol_doc.add_list([T4_impl, ligase_def])
        self.T4_ligase_impl = T4_impl

    def _add_if_absent(self, doc: sbol2.Document, obj: Any):
        if doc.find(obj.identity) is None:
            doc.add(obj)

    def _get_or_create_chassis(
        self, doc: sbol2.Document, chassis_name: str
    ) -> tuple[sbol2.ModuleDefinition, sbol2.Implementation]:
        chassis_module = doc.find(chassis_name) or sbol2.ModuleDefinition(chassis_name)
        chassis_module.roles = [ORGANISM_STRAIN]
        chassis_module.name = chassis_name
        self._add_if_absent(doc, chassis_module)

        chassis_impl_id = f"{chassis_name}_impl"
        chassis_impl = doc.find(chassis_impl_id) or sbol2.Implementation(
            chassis_impl_id
        )
        chassis_impl.built = chassis_module.identity
        self._add_if_absent(doc, chassis_impl)
        return chassis_module, chassis_impl


def _extract_lvl2_TUs(  # TODO send to misc helper file instead of buildcompiler.py?
    design_doc: sbol2.Document,
) -> List[sbol2.ComponentDefinition]:
    """
    Returns the component definitions of each level-1 component (TU)
    in the design.

    Args:
        design: :class:`sbol2.Document` containing the design.

    Returns:
        A list of TU component definitions in sequential order.
    """
    top_design = extract_toplevel_definition(design_doc)

    return [
        design_doc.get(comp.definition) for comp in top_design.getInSequentialOrder()
    ]
