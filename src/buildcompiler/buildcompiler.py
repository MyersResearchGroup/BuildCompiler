import sbol2
import json
import random
import re
import shutil
import warnings
import urllib.parse
import csv
from pathlib import Path
from typing import Any, Dict, List

from buildcompiler.plasmid import Plasmid
from buildcompiler.sbol2build import (
    Assembly,
    Transformation as SBOL2Transformation,
    dna_componentdefinition_with_sequence,
)
from .abstract_translator import (
    enumerate_design_variants,
    extract_combinatorial_design_parts,
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
    KAN,
    FUSION_SITES,
    LIGASE,
    PART_ROLES,
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
        sbol_doc: sbol2.Document,
    ):
        self.sbh = sbol2.PartShop(sbh_registry)
        self.sbh.key = auth_token
        self.sbol_doc = sbol_doc or sbol2.Document()
        self.indexed_plasmids = []
        self.indexed_backbones = []
        self.restriction_enzyme_implementations = []
        self.ligase_implementations = []

        self._index_collections(collections)

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
            print(f"Indexing collection: {uri}")
            self.sbh.pull(uri, self.sbol_doc)

        for implementation in self.sbol_doc.implementations:
            built_object = get_or_pull(self.sbol_doc, self.sbh, implementation.built)
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
                        existing_plasmid.plasmid_implementations.append(implementation)
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
                        existing_backbone.plasmid_implementations.append(implementation)
                    else:
                        self.indexed_backbones.append(
                            Plasmid(
                                built_object, None, [implementation], [], self.sbol_doc
                            )
                        )
            elif sbol2.BIOPAX_PROTEIN in built_object.types:
                if RESTRICTION_ENZYME in built_object.roles:
                    self.restriction_enzyme_implementations.append(implementation)
                elif LIGASE in built_object.roles:
                    self.ligase_implementations.append(implementation)

        for strain in self.sbol_doc.moduleDefinitions:
            if ORGANISM_STRAIN in strain.roles:
                self._extract_plasmids_from_strain(strain, None, self.sbol_doc)

        for definition in self.sbol_doc.componentDefinitions:
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

        bsaI_impl = next(
            (
                impl
                for impl in self.restriction_enzyme_implementations
                if self.sbol_doc.find(impl.built).displayId == "BsaI"
            ),
            None,
        )
        if bsaI_impl is None:
            self._create_RE_implementation("BsaI")
            warnings.warn(
                "BsaI Restriction enzyme not found in provided collection(s). Domestication via purchase will be added to protocol.",
                RuntimeWarning,
            )

        ligase_impl = (
            self.ligase_implementations[0] if self.ligase_implementations else None
        )
        if ligase_impl is None:
            self._create_ligase_implementation()
            warnings.warn(
                "No appropriate ligase found in provided collection(s). Domestication of T4 Ligase via purchase will be added to protocol."
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
                bsaI_impl,
                ligase_impl,
                self.sbol_doc,
            )
            assembly_products, assembly_doc = assembly.run()
            product_definition = assembly_products[0].plasmid_definition
            domesticated_parts.append(product_definition)

        return domesticated_parts

    def assembly_lvl1(
        self,
        abstract_design: sbol2.ComponentDefinition,
        final_doc: sbol2.Document = sbol2.Document(),
        product_name: str = None,
        backbone: Plasmid = None,
    ) -> list[sbol2.ComponentDefinition]:
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

        plasmid_dict = self._get_input_plasmids(
            design=abstract_design, antibiotic_resistance=AMP
        )

        if not backbone:
            backbone, compatible_plasmids = self._get_backbone(
                plasmid_dict, antibiotic_resistance=KAN
            )
        else:
            compatible_plasmids = get_compatible_plasmids(plasmid_dict, backbone)

        bsaI_impl = next(
            impl
            for impl in self.restriction_enzyme_implementations
            if self.sbol_doc.find(impl.built).displayId == "BsaI"
        )
        if bsaI_impl is None:
            raise ValueError(
                "BsaI Restriction enzyme not found in provided collections. Terminating assembly."
            )

        ligase_impl = self.ligase_implementations[0]
        if bsaI_impl is None:
            raise ValueError(
                "No appropriate ligase found in provided collections. Terminating assembly."
            )

        assembly = Assembly(
            compatible_plasmids,
            backbone,
            bsaI_impl,
            ligase_impl,
            self.sbol_doc,
            final_doc,
            product_name,
        )
        composite_plasmids, product_doc = assembly.run()  # TODO upload product_doc?

        self.indexed_plasmids.extend(composite_plasmids)
        assembly_plan_RDF_to_JSON(product_doc)
        
        return composite_plasmids

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
            indexed = self._get_indexed_plasmid(self.indexed_plasmids, product["plasmid"])
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

        normalized = normalize_plating_input(
            transformation_results, doc=doc_ref
        )
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
            writer = csv.DictWriter(handle, fieldnames=list(plate_rows[0].keys()) if plate_rows else ["well"])
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
        plate_map_csv_path = write_plate_map_csv(results_path / "plate_map.csv", plate_rows)
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
                "layout_dataframe_columns": list(plate_rows[0].keys()) if plate_rows else [],
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
            plasmid_definition = get_or_pull(doc, self.sbh, plasmid.definition)

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
            if ENGINEERED_PLASMID in definition.roles and not self._get_indexed_plasmid(
                self.indexed_plasmids, definition
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
            get_or_pull(self.sbol_doc, self.sbh, component.definition)
            for component in component_list
        ]

    def _get_abstract_design(self) -> sbol2.ComponentDefinition:
        for definition in self.sbol_doc.componentDefinitions:
            if (
                ENGINEERED_PLASMID in definition.roles
                or PLASMID_CLONING_VECTOR in definition.roles
                or len(definition.components) <= 1
            ):
                continue

            component_definitions = [
                get_or_pull(self.sbol_doc, self.sbh, component.definition)
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

    def _create_RE_implementation(name: str):
        pass

    def _create_ligase_implementation():
        pass

    def _normalize_transformation_inputs(
        self, assembly_products: List[Any]
    ) -> List[Dict[str, Any]]:
        normalized = []
        for item in assembly_products or []:
            if isinstance(item, Plasmid):
                normalized.append(
                    {"plasmid": item.plasmid_definition, "source": item.name}
                )
                continue

            if isinstance(item, sbol2.ComponentDefinition):
                normalized.append({"plasmid": item, "source": item.displayId})
                continue

            if isinstance(item, dict) and "plasmid" in item:
                plasmid_candidate = item["plasmid"]
                if isinstance(plasmid_candidate, Plasmid):
                    normalized.append(
                        {
                            "plasmid": plasmid_candidate.plasmid_definition,
                            "source": item.get("name", plasmid_candidate.name),
                        }
                    )
                elif isinstance(plasmid_candidate, sbol2.ComponentDefinition):
                    normalized.append(
                        {
                            "plasmid": plasmid_candidate,
                            "source": item.get("name", plasmid_candidate.displayId),
                        }
                    )
        return normalized

    def _safe_display_id(self, value: str) -> str:
        safe_value = re.sub(r"[^A-Za-z0-9_]+", "_", value or "")
        return safe_value.strip("_") or "unnamed_design"

    def _serialize_sbol_identity(self, obj_or_uri) -> str:
        return getattr(obj_or_uri, "identity", str(obj_or_uri))

    def _write_json(self, path: Path, payload: dict) -> Path:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2, sort_keys=True)
        return path

    def _status_from_manifest(self, manifest: dict) -> str:
        if manifest.get("errors"):
            return "completed_with_errors"
        if manifest["assembly_lvl1"].get("successful"):
            return "completed"
        if (
            manifest["assembly_lvl1"].get("failed")
            or manifest["domestication"].get("errors")
        ):
            return "completed_with_errors"
        return "failed"

    def _find_missing_parts_for_lvl1(
        self,
        design: sbol2.ComponentDefinition,
        backbone: Plasmid = None,
    ) -> list[dict]:
        parts = self._extract_design_parts(design)
        plasmid_dict = self._construct_plasmid_dict(parts, antibiotic_resistance=AMP)

        missing_parts = []
        for part in parts:
            candidates = plasmid_dict.get(part.displayId, [])
            if not candidates:
                missing_parts.append(
                    {
                        "part": part,
                        "reason": "no implemented plasmid",
                    }
                )
                continue

            try:
                if backbone is None:
                    selected_backbone, _ = self._get_backbone(
                        plasmid_dict, antibiotic_resistance=KAN
                    )
                    if selected_backbone is None:
                        missing_parts.append(
                            {
                                "part": part,
                                "reason": "no compatible backbone",
                            }
                        )
                else:
                    compatible = get_compatible_plasmids(plasmid_dict, backbone)
                    if not compatible:
                        missing_parts.append(
                            {
                                "part": part,
                                "reason": "no compatible plasmid",
                            }
                        )
            except Exception:
                missing_parts.append(
                    {
                        "part": part,
                        "reason": "no compatible plasmid",
                    }
                )

        return missing_parts

    def _index_domestication_products(
        self,
        products: list[sbol2.ComponentDefinition],
    ) -> None:
        for product_definition in products:
            if self._get_indexed_plasmid(self.indexed_plasmids, product_definition):
                continue
            try:
                indexed = Plasmid(product_definition, None, [], [], self.sbol_doc)
            except Exception:
                indexed = type(
                    "IndexedDomesticationPlasmid",
                    (),
                    {
                        "plasmid_definition": product_definition,
                        "name": product_definition.displayId,
                        "fusion_sites": [],
                        "antibiotic_resistance": None,
                    },
                )()
            self.indexed_plasmids.append(indexed)

    def _zip_full_build_results(
        self,
        source_dir: Path,
        zip_path: Path,
        overwrite: bool = False,
    ) -> Path:
        if zip_path.exists():
            if not overwrite:
                raise FileExistsError(
                    f"Zip path already exists and overwrite=False: {zip_path}"
                )
            zip_path.unlink()
        zip_path.parent.mkdir(parents=True, exist_ok=True)
        zip_base = zip_path.with_suffix("")
        archive = shutil.make_archive(
            str(zip_base), "zip", root_dir=str(source_dir), base_dir="."
        )
        return Path(archive)

    def _expand_combinatorial_derivation(
        self,
        derivation: sbol2.CombinatorialDerivation,
        product_name_prefix: str = None,
    ) -> list[sbol2.ComponentDefinition]:
        master_template = get_or_pull(self.sbol_doc, self.sbh, derivation.masterTemplate)
        component_variants = extract_combinatorial_design_parts(
            master_template, self.sbol_doc, self.sbol_doc
        )
        variant_definitions = enumerate_design_variants(component_variants)

        prefix = product_name_prefix or master_template.displayId
        created_variants = []

        ordered_components = list(master_template.getInSequentialOrder())
        for index, variant_parts in enumerate(variant_definitions, start=1):
            variant_display_id = f"{self._safe_display_id(prefix)}_variant_{index:03d}"
            variant_design = self.sbol_doc.find(variant_display_id) or sbol2.ComponentDefinition(
                variant_display_id
            )
            variant_design.types = list(master_template.types)
            variant_design.roles = list(master_template.roles)
            variant_design.wasDerivedFrom = derivation.identity
            self._add_if_absent(self.sbol_doc, variant_design)

            if len(variant_design.components) == 0:
                for comp_index, component in enumerate(ordered_components):
                    part_def = variant_parts[comp_index]
                    variant_component = variant_design.components.create(
                        f"{variant_display_id}_component_{comp_index+1:03d}"
                    )
                    variant_component.definition = part_def.identity
                    try:
                        variant_component.access = component.access
                    except Exception:
                        pass
                    try:
                        variant_component.direction = component.direction
                    except Exception:
                        pass
            created_variants.append(variant_design)

        return created_variants

    def _normalize_full_build_designs(self, designs) -> list[sbol2.ComponentDefinition]:
        if isinstance(designs, sbol2.ComponentDefinition):
            return [designs]
        if isinstance(designs, sbol2.CombinatorialDerivation):
            return self._expand_combinatorial_derivation(designs)
        if isinstance(designs, list):
            if all(isinstance(design, sbol2.ComponentDefinition) for design in designs):
                return designs
            raise TypeError("designs list must contain only ComponentDefinition objects.")
        raise TypeError(
            "designs must be a ComponentDefinition, list[ComponentDefinition], or CombinatorialDerivation."
        )

    def full_build(
        self,
        designs,
        results_dir,
        chassis_name: str = "E_coli_DH5alpha",
        protocol_type: str = "manual",
        transformation_params: dict | None = None,
        plating_params: dict | None = None,
        product_name_prefix: str | None = None,
        overwrite: bool = False,
    ) -> dict:
        transformation_params = transformation_params or {}
        plating_params = plating_params or {}
        results_path = Path(results_dir)
        results_path.mkdir(parents=True, exist_ok=True)

        input_type = type(designs).__name__
        normalized_designs = self._normalize_full_build_designs(designs)
        manifest = {
            "stage": "full_build",
            "inputs": {
                "input_type": input_type,
                "design_count": len(normalized_designs),
                "chassis_name": chassis_name,
                "protocol_type": protocol_type,
                "product_name_prefix": product_name_prefix,
            },
            "domestication": {
                "missing_parts": [],
                "products": [],
                "transformation": {},
                "plating": {},
                "errors": [],
            },
            "assembly_lvl1": {"successful": [], "failed": []},
            "transformation": {"assembly_products": {}},
            "plating": {"assembly_products": {}},
            "skipped": [
                {
                    "stage": "assembly_lvl2",
                    "status": "skipped",
                    "reason": "assembly_lvl2 is not implemented yet",
                }
            ],
            "errors": [],
        }

        per_design_missing = {}
        unique_missing = {}
        for design in normalized_designs:
            missing_items = self._find_missing_parts_for_lvl1(design)
            serialized_missing = []
            for item in missing_items:
                part = item["part"]
                entry = {
                    "part_identity": self._serialize_sbol_identity(part),
                    "part_display_id": part.displayId,
                    "reason": item["reason"],
                }
                serialized_missing.append(entry)
                unique_missing.setdefault(part.identity, {"part": part, "reason": item["reason"]})
            per_design_missing[design.identity] = serialized_missing

        manifest["domestication"]["missing_parts"] = list(unique_missing.values())
        if unique_missing:
            manifest["domestication"]["missing_parts"] = [
                {
                    "part_identity": self._serialize_sbol_identity(item["part"]),
                    "part_display_id": item["part"].displayId,
                    "reason": item["reason"],
                }
                for item in unique_missing.values()
            ]
            unique_missing_parts = [item["part"] for item in unique_missing.values()]
            try:
                domesticated_products = self.domestication(unique_missing_parts)
                self._index_domestication_products(domesticated_products)
                manifest["domestication"]["products"] = [
                    self._serialize_sbol_identity(product)
                    for product in domesticated_products
                ]
                try:
                    domestication_transformation = self.transformation(
                        domesticated_products,
                        chassis_name=chassis_name,
                        transformation_doc=self.sbol_doc,
                        **transformation_params,
                    )
                    manifest["domestication"]["transformation"] = domestication_transformation
                except Exception as exc:
                    manifest["domestication"]["errors"].append(
                        f"Domestication transformation failed: {exc}"
                    )
                    domestication_transformation = None

                if domestication_transformation:
                    try:
                        domestication_plating = self.plating(
                            transformation_results=domestication_transformation,
                            results_dir=results_path / "domestication" / "plating",
                            protocol_type=protocol_type,
                            advanced_params=plating_params,
                            plating_doc=self.sbol_doc,
                            overwrite=overwrite,
                        )
                        manifest["domestication"]["plating"] = domestication_plating
                    except Exception as exc:
                        manifest["domestication"]["errors"].append(
                            f"Domestication plating failed: {exc}"
                        )
            except Exception as exc:
                manifest["domestication"]["errors"].append(f"Domestication failed: {exc}")
                manifest["errors"].append(f"Domestication failed: {exc}")

        for index, design in enumerate(normalized_designs, start=1):
            design_slug = self._safe_display_id(design.displayId or f"design_{index:03d}")
            stable_product_name = (
                f"{self._safe_display_id(product_name_prefix)}_{design_slug}_{index:03d}"
                if product_name_prefix
                else f"{design_slug}_{index:03d}"
            )
            try:
                assembly_products = self.assembly_lvl1(
                    abstract_design=design,
                    product_name=stable_product_name,
                )
                product_ids = [
                    self._serialize_sbol_identity(
                        product.plasmid_definition if isinstance(product, Plasmid) else product
                    )
                    for product in assembly_products
                ]

                assembly_transformation = self.transformation(
                    assembly_products,
                    chassis_name=chassis_name,
                    transformation_doc=self.sbol_doc,
                    **transformation_params,
                )
                assembly_plating = self.plating(
                    transformation_results=assembly_transformation,
                    results_dir=results_path / "assembly_lvl1" / design_slug / "plating",
                    protocol_type=protocol_type,
                    advanced_params=plating_params,
                    plating_doc=self.sbol_doc,
                    overwrite=overwrite,
                )

                manifest["assembly_lvl1"]["successful"].append(
                    {
                        "design_identity": design.identity,
                        "design_display_id": design.displayId,
                        "assembly_product_identities": product_ids,
                    }
                )
                manifest["transformation"]["assembly_products"][design_slug] = assembly_transformation
                manifest["plating"]["assembly_products"][design_slug] = assembly_plating
            except Exception as exc:
                failure_entry = {
                    "design_identity": design.identity,
                    "design_display_id": design.displayId,
                    "error": str(exc),
                    "missing_parts": per_design_missing.get(design.identity, []),
                }
                manifest["assembly_lvl1"]["failed"].append(failure_entry)
                manifest["errors"].append(
                    f"Assembly failed for {design.displayId}: {exc}"
                )

        sbol_path = results_path / "sbol" / "full_build.xml"
        try:
            sbol_path.parent.mkdir(parents=True, exist_ok=True)
            self.sbol_doc.write(str(sbol_path))
        except Exception as exc:
            manifest["errors"].append(f"SBOL write failed: {exc}")

        manifest_path = self._write_json(results_path / "full_build_manifest.json", manifest)
        zip_path = results_path / "full_build_results.zip"
        try:
            zip_result = self._zip_full_build_results(
                source_dir=results_path,
                zip_path=zip_path,
                overwrite=overwrite,
            )
        except Exception as exc:
            manifest["errors"].append(f"Result packaging failed: {exc}")
            self._write_json(manifest_path, manifest)
            zip_result = zip_path

        status = self._status_from_manifest(manifest)
        result = {
            "stage": "full_build",
            "status": status,
            "results_dir": str(results_path),
            "zip_path": str(zip_result),
            "manifest_path": str(manifest_path),
            "sbol_path": str(sbol_path),
            "inputs": manifest["inputs"],
            "domestication": manifest["domestication"],
            "assembly_lvl1": manifest["assembly_lvl1"],
            "transformation": manifest["transformation"],
            "plating": manifest["plating"],
            "skipped": manifest["skipped"],
            "errors": manifest["errors"],
        }
        self._write_json(manifest_path, manifest)
        return result

    def _get_or_create_chassis(
        self, doc: sbol2.Document, chassis_name: str
    ) -> tuple[sbol2.ModuleDefinition, sbol2.Implementation]:
        chassis_module = doc.find(chassis_name) or sbol2.ModuleDefinition(chassis_name)
        chassis_module.roles = [ORGANISM_STRAIN]
        chassis_module.name = chassis_name
        self._add_if_absent(doc, chassis_module)

        chassis_impl_id = f"{chassis_name}_impl"
        chassis_impl = doc.find(chassis_impl_id) or sbol2.Implementation(chassis_impl_id)
        chassis_impl.built = chassis_module.identity
        self._add_if_absent(doc, chassis_impl)
        return chassis_module, chassis_impl

    def _get_or_create_plasmid_implementation(
        self, doc: sbol2.Document, plasmid: sbol2.ComponentDefinition
    ) -> sbol2.Implementation:
        plasmid_impl_id = f"{plasmid.displayId}_impl"
        plasmid_impl = doc.find(plasmid_impl_id) or sbol2.Implementation(plasmid_impl_id)
        plasmid_impl.built = plasmid.identity
        self._add_if_absent(doc, plasmid_impl)
        return plasmid_impl

    def _add_if_absent(self, doc: sbol2.Document, obj: Any):
        if doc.find(obj.identity) is None:
            doc.add(obj)
