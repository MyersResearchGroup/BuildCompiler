import sbol2
import random
import warnings
import urllib.parse
from pathlib import Path
from typing import Any, Dict, List

from buildcompiler.plasmid import Plasmid
from buildcompiler.sbol2build import Assembly, dna_componentdefinition_with_sequence
from .abstract_translator import (
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

        sbol_outputs = []
        robot_steps = []
        logs = []

        for index, product in enumerate(normalized_products, start=1):
            plasmid = product["plasmid"]
            plasmid_impl = self._get_or_create_plasmid_implementation(
                transformation_doc, plasmid
            )
            transform_id = f"transform_{plasmid.displayId}_{index}"

            transformation_activity = sbol2.Activity(transform_id)
            transformation_activity.name = f"Transform {chassis_name} with {plasmid.displayId}"
            transformation_activity.types = "http://sbols.org/v2#build"

            chassis_usage = sbol2.Usage(
                uri=f"{transform_id}_chassis_usage",
                entity=chassis_impl.identity,
                role="http://sbols.org/v2#build",
            )
            plasmid_usage = sbol2.Usage(
                uri=f"{transform_id}_plasmid_usage",
                entity=plasmid_impl.identity,
                role="http://sbols.org/v2#build",
            )
            transformation_activity.usages = [chassis_usage, plasmid_usage]

            transformed_strain = sbol2.ModuleDefinition(
                f"{chassis_name}_with_{plasmid.displayId}"
            )
            transformed_strain.roles = [ORGANISM_STRAIN]
            transformed_strain.name = f"{chassis_name} transformed with {plasmid.displayId}"

            chassis_module_ref = sbol2.Module(
                uri=f"{transformed_strain.displayId}_chassis_module"
            )
            chassis_module_ref.definition = chassis_module.identity
            plasmid_fc = sbol2.FunctionalComponent(
                uri=f"{transformed_strain.displayId}_plasmid_fc"
            )
            plasmid_fc.definition = plasmid.identity

            transformed_strain.modules = [chassis_module_ref]
            transformed_strain.functionalComponents = [plasmid_fc]

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
        """Generate a plated 96-well output and protocol artifacts."""
        if protocol_type not in {"manual", "automated"}:
            raise ValueError("protocol_type must be one of: 'manual', 'automated'.")
        if plating_doc is None:
            plating_doc = self.sbol_doc
        advanced_params = advanced_params or {}

        normalized = normalize_plating_input(transformation_results, doc=plating_doc)
        if len(normalized) > 96:
            raise ValueError("plating supports up to 96 transformed strains.")

        wells = generate_96_well_positions(limit=len(normalized))
        results_path = Path(results_dir)
        results_path.mkdir(parents=True, exist_ok=True)

        plate_id = plate_name or "solid_96_well_plate"
        plate_impl = sbol2.Implementation(plate_id)
        plate_md = plating_doc.find("solid_96_well_plate_md") or sbol2.ModuleDefinition(
            "solid_96_well_plate_md"
        )
        plate_md.name = "Solid 96-well plate"
        self._add_if_absent(plating_doc, plate_md)
        plate_impl.built = plate_md.identity
        self._add_if_absent(plating_doc, plate_impl)

        # Optional SBOLInventory integration with fallback behavior.
        try:
            from sbol_inventory import (  # type: ignore
                make_solid_96_well_plate,
                make_plated_strain,
                place_in_plate,
            )

            inventory_enabled = True
            inventory_plate = make_solid_96_well_plate(
                uri=plate_impl.identity, plate_md_uri=plate_md.identity
            )
        except Exception:
            inventory_enabled = False
            inventory_plate = None

        activity_id = f"plating_{protocol_type}_{plate_id}"
        plating_activity = sbol2.Activity(activity_id)
        plating_activity.name = f"Plating activity for {plate_id}"
        plating_activity.types = "http://sbols.org/v2#build"
        self._add_if_absent(plating_doc, plating_activity)

        agent_id = (
            "manual_plating_agent"
            if protocol_type == "manual"
            else "opentrons_plating_agent"
        )
        agent = plating_doc.find(agent_id) or sbol2.Agent(agent_id)
        agent.name = "Manual plating agent" if protocol_type == "manual" else "Opentrons plating agent"
        self._add_if_absent(plating_doc, agent)

        plan_id = f"{plate_id}_{protocol_type}_plating_plan"
        plan = plating_doc.find(plan_id) or sbol2.Plan(plan_id)
        plan.name = f"{protocol_type.title()} plating plan for {plate_id}"
        self._add_if_absent(plating_doc, plan)

        association = sbol2.Association(
            uri=f"{activity_id}_association",
            agent=agent.identity,
            role="http://sbols.org/v2#build",
        )
        association.plan = plan.identity
        plating_activity.associations = [association]
        self._add_if_absent(plating_doc, association)

        plate_rows = []
        plate_map = {}
        bacterium_locations = {}
        plated_impls = []

        for idx, entry in enumerate(normalized):
            well = wells[idx]
            source_impl_uri = entry.get("source_impl_uri")
            source_impl = plating_doc.find(source_impl_uri) if source_impl_uri else None
            strain_module_uri = entry.get("strain_module_uri")
            if strain_module_uri is None and source_impl is not None:
                strain_module_uri = getattr(source_impl, "built", None)

            display_source = source_impl_uri or strain_module_uri or f"strain_{idx+1}"
            parsed = urllib.parse.urlparse(display_source)
            slug = parsed.path.split("/")[-1] if parsed.path else display_source
            slug = slug.replace("#", "_").replace(":", "_")

            plated_module_id = f"{slug}_plated_{well}_md"
            plated_module = plating_doc.find(plated_module_id) or sbol2.ModuleDefinition(
                plated_module_id
            )
            plated_module.roles = [ORGANISM_STRAIN]
            plated_module.name = f"Plated strain {slug} at {well}"
            if strain_module_uri:
                plated_module.wasDerivedFrom = strain_module_uri
            self._add_if_absent(plating_doc, plated_module)

            plated_impl_id = f"{slug}_plated_{well}_impl"
            plated_impl = plating_doc.find(plated_impl_id) or sbol2.Implementation(
                plated_impl_id
            )
            plated_impl.built = plated_module.identity
            plated_impl.wasGeneratedBy = plating_activity.identity
            if source_impl_uri:
                plated_impl.wasDerivedFrom = source_impl_uri
            self._add_if_absent(plating_doc, plated_impl)
            plated_impls.append(plated_impl.identity)

            usage = sbol2.Usage(
                uri=f"{activity_id}_usage_{idx+1}",
                entity=source_impl_uri or plated_module.identity,
                role=PLATING_ACTIVITY_ROLE,
            )
            self._add_if_absent(plating_doc, usage)
            current_usages = list(plating_activity.usages)
            current_usages.append(usage)
            plating_activity.usages = current_usages

            if inventory_enabled:
                try:
                    inventory_plated = make_plated_strain(
                        uri=plated_impl.identity,
                        strain_md_uri=strain_module_uri or plated_module.identity,
                        design_uri=source_impl_uri,
                    )
                    place_in_plate(inventory_plate, inventory_plated, well)
                except Exception:
                    inventory_enabled = False

            plate_map[well] = plated_impl.identity
            display_name = plated_module.displayId
            bacterium_locations[well] = display_name
            plate_rows.append(
                {
                    "well": well,
                    "source_transformed_strain_implementation": source_impl_uri,
                    "strain_module": strain_module_uri,
                    "plated_strain_implementation": plated_impl.identity,
                    "strain_display_name": display_name,
                }
            )

        plate_map_json_path = write_plate_map_json(
            results_path / "plate_map.json",
            {
                "plate_implementation": plate_impl.identity,
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
            "logs": logs,
        }

        if protocol_type == "manual":
            md_path = write_manual_plating_protocol(
                results_path / "manual_plating_protocol.md",
                plate_id=plate_impl.displayId,
                plate_rows=plate_rows,
                advanced_params=advanced_params,
            )
            protocol_artifacts["manual_protocol_markdown"] = str(md_path)
            plan.description = f"Manual protocol file: {md_path}"
        else:
            script_path = write_plating_protocol_script(
                results_path / "plating_ot2.py",
                plating_data={"bacterium_locations": bacterium_locations},
                advanced_params=advanced_params,
            )
            protocol_artifacts["ot2_script"] = str(script_path)
            plan.description = f"Automated protocol script: {script_path}"
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
                "plate_implementation": plate_impl.identity,
                "plate_map": plate_map,
            },
            "sbol_artifacts": {
                "plating_activity": plating_activity.identity,
                "agent": agent.identity,
                "plan": plan.identity,
                "plate_implementation": plate_impl.identity,
                "plated_strain_implementations": plated_impls,
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
