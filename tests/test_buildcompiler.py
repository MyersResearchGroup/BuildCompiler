import sbol2
import unittest
import sys
import os
import copy
from collections import Counter


sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../src")))

from buildcompiler.buildcompiler import BuildCompiler, _extract_lvl2_TUs

from buildcompiler.abstract_translator import extract_toplevel_definition, get_or_pull


class Test_Buildcompiler_Functions(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        username = os.environ.get("SBH_USERNAME")
        password = os.environ.get("SBH_PASSWORD")

        if not username or not password:
            raise RuntimeError(
                "Missing SBH_USERNAME and/or SBH_PASSWORD environment variables"
            )
        sbh = sbol2.PartShop("https://api.synbiohub.org")
        sbh.login(username, password)

        auth = sbh.key

        collections = [
            "https://synbiohub.org/user/Gon/impl_test/impl_test_collection/1",
            "https://synbiohub.org/user/Gon/Enzyme_Implementations/Enzyme_Implementations_collection/1",
        ]

        source = sbol2.Document()

        # preload combinatorial designs into buildcompiler context
        source.read("tests/test_files/complex_combinatorial_abstract.xml")
        source.append("tests/test_files/combinatorial_1.xml", True)

        cls.buildcompiler = BuildCompiler(
            collections, "https://api.synbiohub.org", auth, source, server_mode=True
        )

    def test_simple_lvl1_assembly(self):
        abstract_design_doc = sbol2.Document()
        abstract_design_doc.read("tests/test_files/moclo_parts_circuit.xml")

        design = extract_toplevel_definition(abstract_design_doc)
        product_doc = sbol2.Document()

        dict, product_doc = self.buildcompiler.assembly_lvl1([design], product_doc)

        self.assertEqual(
            len(dict),
            1,
            "There should be 1 composite resulting from the assembly",
        )

        assembly_activity = product_doc.get(
            "http://buildcompiler.org/qlSBuNBL_composite_assembly/1"
        )

        self.assertEqual(
            len(assembly_activity.usages),
            7,
            "Assembly should have 7 usages: 5 plasmids, 1 ligase, 1 Restriction Enzyme",
        )

        usage_uris = {u.identity for u in assembly_activity.usages}

        expected_usage_uris = {
            "http://buildcompiler.org/qlSBuNBL_composite_assembly/pJ23100_AB_impl/1",
            "http://buildcompiler.org/qlSBuNBL_composite_assembly/pB0034_BC_impl/1",
            "http://buildcompiler.org/qlSBuNBL_composite_assembly/pE0030_CD_impl/1",
            "http://buildcompiler.org/qlSBuNBL_composite_assembly/pB0015_DE_impl/1",
            "http://buildcompiler.org/qlSBuNBL_composite_assembly/DVK_AE_impl/1",
            "http://buildcompiler.org/qlSBuNBL_composite_assembly/BsaI_enzyme/1",
            "http://buildcompiler.org/qlSBuNBL_composite_assembly/T4_Ligase/1",
        }

        for expected_uri in expected_usage_uris:
            self.assertIn(
                expected_uri,
                usage_uris,
                f"Expected usage {expected_uri} was not found in assembly activity usages",
            )

            usage = next(
                u for u in assembly_activity.usages if str(u.identity) == expected_uri
            )

            impl = get_or_pull(product_doc, self.buildcompiler.sbh, usage.entity, True)

            self.assertIsNotNone(
                impl,
                f"Entity {usage.entity} should exist in the document or on SynBioHub",
            )

            self.assertIsInstance(
                impl,
                sbol2.Implementation,
                f"Entity {usage.entity} should be an SBOL Implementation",
            )

            self.assertIsNotNone(
                impl.built,
                f"Implementation {impl.identity} should reference a built object",
            )

        expected_product_uri = "http://buildcompiler.org/qlSBuNBL_composite_impl/1"

        product_impl = product_doc.get(expected_product_uri)
        product_def = product_doc.get(product_impl.built)

        self.assertIsNotNone(
            product_impl,
            f"Implementation {product_impl} should exist in the document",
        )

        self.assertEqual(
            product_impl.wasGeneratedBy,
            [assembly_activity.identity],
            f"Implementation {product_impl} must include wasGeneratedBy {assembly_activity.identity}",
        )

        self.assertEqual(
            product_def.identity,
            "http://buildcompiler.org/qlSBuNBL_composite/1",
            f"Implementation {product_impl} must build {product_def}",
        )

    def test_two_rbs_combinatorial_translation(self):
        comb_doc = sbol2.Document()
        comb_doc.read("tests/test_files/combinatorial_1.xml")

        design = comb_doc.combinatorialderivations[0]

        result_dict, assembly_doc = self.buildcompiler.assembly_lvl1(design)

        self.assertEqual(
            len(result_dict),
            1,
            "Expected one combinatorial derivation key in result dictionary",
        )

        derivation_uri = "https://sbolcanvas.org/abstract_combinatorial/1"

        self.assertIn(
            derivation_uri,
            result_dict,
            "Expected combinatorial derivation URI missing from results",
        )

        composites = result_dict[derivation_uri]

        self.assertEqual(
            len(composites),
            2,
            "Combinatorial assembly failed to produce 2 composites",
        )

        # ensure cobinatorial feature is satsified
        for composite in composites:
            components = composite.plasmid_definition.getInSequentialOrder()

            if len(components) > 3:
                if components[3].displayId == "B0033":
                    has_b0033 = True
                elif components[3].displayId == "B0032":
                    has_b0032 = True

        self.assertTrue(has_b0033, "No composite has B0033")
        self.assertTrue(has_b0032, "No composite has B0032")

    def test_complex_combinatorial_translation(
        self,
    ):  # testing combinatorial design with 3 variable promoters and RBSs
        complex_comb_doc = sbol2.Document()
        complex_comb_doc.read("tests/test_files/complex_combinatorial_abstract.xml")

        design = complex_comb_doc.combinatorialderivations[0]

        result_dict, assembly_doc = self.buildcompiler.assembly_lvl1(design)

        assembly_doc.write("comb_assembly.xml")

        self.assertEqual(
            len(result_dict),
            1,
            "Expected one combinatorial derivation key in result dictionary",
        )

        derivation_uri = "https://sbolcanvas.org/dEOuAjnj/1"

        self.assertIn(
            derivation_uri,
            result_dict,
            "Expected combinatorial derivation URI missing from results",
        )

        composites = result_dict[derivation_uri]

        self.assertEqual(
            len(composites),
            9,
            f"Combinatorial assembly failed to produce 9 composites, found {len(composites)}",
        )

        promoter_counts = Counter()
        rbs_counts = Counter()

        for composite in composites:
            components = composite.plasmid_definition.getInSequentialOrder()
            display_ids = [component.displayId for component in components]
            print(display_ids)

            promoter_counts[components[1].displayId] += 1  # index 1 = promoter
            rbs_counts[components[3].displayId] += 1  # index 3 = RBS

        self.assertEqual(
            promoter_counts["J23100"],
            3,
            f"Expected J23100 to appear 3 times across the composite dictionary, found {promoter_counts['J23100']}",
        )

        self.assertEqual(
            promoter_counts["J23106"],
            3,
            f"Expected J23106 to appear 3 times across the composite dictionary, found {promoter_counts['J23106']}",
        )

        self.assertEqual(
            promoter_counts["J23116"],
            3,
            f"Expected J23116 to appear 3 times across the composite dictionary, found {promoter_counts['J23116']}",
        )

        self.assertEqual(
            rbs_counts["B0034"],
            3,
            f"Expected B0034 to appear 3 times across the composite dictionary, found {rbs_counts['B0034']}",
        )

        self.assertEqual(
            rbs_counts["B0032"],
            3,
            f"Expected B0032 to appear 3 times across the composite dictionary, found {rbs_counts['B0032']}",
        )

        self.assertEqual(
            rbs_counts["B0033"],
            3,
            f"Expected B0033 to appear 3 times across the composite dictionary, found {rbs_counts['B0033']}",
        )

    def test_simple_lvl2_assembly(self):
        """
        High-level integration test for lvl2 assembly.

        Validates:
        - lvl2 plasmid generation succeeds
        - lvl1 intermediates are used as assembly inputs
        - correct enzymes are included
        - correct backbone selection occurs
        - TU ordering is preserved
        - SBOL provenance relationships are intact
        """

        abstract_design_doc = sbol2.Document()
        abstract_design_doc.read("tests/test_files/ExampleLvl2_design.xml")

        design_TUs = _extract_lvl2_TUs(abstract_design_doc)

        # ------------------------------------------------------------
        # Run lvl2 assembly
        # ------------------------------------------------------------
        lvl2_plasmids, final_doc = self.buildcompiler.assembly_lvl2(
            abstract_design_doc,
            product_name="lvl2",
        )

        self.assertEqual(
            len(lvl2_plasmids),
            1,
            "Expected exactly one lvl2 plasmid to be produced",
        )

        lvl2_plasmid = lvl2_plasmids[0]

        # ------------------------------------------------------------
        # Validate provenance / implementation relationships
        # ------------------------------------------------------------
        product_impl = lvl2_plasmid.plasmid_implementations[0]
        product_def = lvl2_plasmid.plasmid_definition

        self.assertIsNotNone(
            product_impl,
            "Lvl2 plasmid implementation should exist",
        )

        self.assertIsNotNone(
            product_def,
            "Lvl2 plasmid definition should exist",
        )

        self.assertEqual(
            product_impl.built,
            product_def.identity,
            "Implementation should reference the built lvl2 construct",
        )

        # test level 1 assembly activities
        lvl1_activities = [
            "http://buildcompiler.org/Gen_Gen1_plas_assembly/1",
            "http://buildcompiler.org/Gen1_Gen1_plas_assembly/1",
        ]

        for index, activity_id in enumerate(lvl1_activities):
            lvl1_activity = final_doc.get(activity_id)

            self.assertIsNotNone(
                lvl1_activity,
                f"Lvl1 assembly activity {activity_id} should exist",
            )

            # ------------------------------------------------------------
            # Validate lvl1 activity usages
            # ------------------------------------------------------------
            lvl1_usage_entities = [
                get_or_pull(final_doc, self.buildcompiler.sbh, u.entity, True)
                for u in lvl1_activity.usages
            ]

            lvl1_usage_display_ids = {
                entity.displayId for entity in lvl1_usage_entities if entity is not None
            }

            lvl1_usage_built_CDs = {
                final_doc.get(entity.built)
                for entity in lvl1_usage_entities
                if entity is not None
            }

            for comp in design_TUs[index].components:
                self.assertIn(
                    comp.definition,
                    [
                        subcomp.definition
                        for plas in lvl1_usage_built_CDs
                        for subcomp in plas.components
                    ],
                    f"Level 1 assembly activity {activity_id} missing {comp.definition} from design TU {design_TUs[index]}",
                )

            self.assertIn(
                "BsaI_impl",
                lvl1_usage_display_ids,
                "Lvl1 assembly should use BsaI",
            )

            self.assertIn(
                "T4_Ligase_impl",
                lvl1_usage_display_ids,
                "Lvl1 assembly should use T4 ligase",
            )

            for entity in lvl1_usage_entities:
                self.assertIsNotNone(
                    entity,
                    "All lvl1 assembly usage entities should resolve correctly",
                )

                self.assertIsInstance(
                    entity,
                    sbol2.Implementation,
                    "Lvl1 assembly usages should reference SBOL implementations",
                )

            self.assertGreaterEqual(
                len(lvl1_usage_entities),
                3,
                "Lvl1 assembly should contain enzyme and plasmid usages",
            )

        # test level2 assembly activity
        lvl2_assembly_activity = final_doc.get(
            "http://buildcompiler.org/lvl2_assembly/1"
        )

        self.assertIsNotNone(
            lvl2_assembly_activity,
            "Assembly activity should exist in final document",
        )

        self.assertEqual(
            product_impl.wasGeneratedBy,
            [lvl2_assembly_activity.identity],
            "Lvl2 implementation should reference generating assembly activity",
        )

        # ------------------------------------------------------------
        # Validate expected assembly usages
        # ------------------------------------------------------------
        usage_entities = [
            get_or_pull(final_doc, self.buildcompiler.sbh, u.entity, True)
            for u in lvl2_assembly_activity.usages
        ]

        usage_display_ids = {
            entity.displayId for entity in usage_entities if entity is not None
        }

        self.assertIn(
            "BbsI_impl",
            usage_display_ids,
            "Lvl2 assembly should use BbsI",
        )

        self.assertIn(
            "T4_Ligase_impl",
            usage_display_ids,
            "Lvl2 assembly should use T4 ligase",
        )

        # ------------------------------------------------------------
        # Ensure lvl1 plasmids were used as inputs
        # ------------------------------------------------------------
        lvl1_inputs = [
            entity
            for entity in usage_entities
            if entity is not None and "_plas" in entity.displayId.lower()
        ]

        self.assertEqual(
            len(lvl1_inputs),
            2,
            "Lvl2 assembly should consume 2 lvl1 plasmids as inputs",
        )

        # ------------------------------------------------------------
        # Validate final construct ordering
        # ------------------------------------------------------------
        components = product_def.getInSequentialOrder()
        display_ids = [component.displayId for component in components]

        expected_order = [
            "Ligation_Scar_A",
            "Gen_Gen1_plas_TU",
            "Ligation_Scar_E",
            "Gen1_Gen1_plas_TU",
            "Ligation_Scar_F",
            "dva_backbone_core",
        ]

        self.assertEqual(
            display_ids,
            expected_order,
            "Lvl2 construct does not preserve expected TU ordering",
        )

        # ------------------------------------------------------------
        # Validate all usage entities are valid implementations
        # ------------------------------------------------------------
        for entity in usage_entities:
            self.assertIsNotNone(
                entity,
                "All assembly usage entities should resolve correctly",
            )

            self.assertIsInstance(
                entity,
                sbol2.Implementation,
                "Assembly usages should reference SBOL implementations",
            )

            self.assertIsNotNone(
                entity.built,
                f"Implementation {entity.identity} should reference a built object",
            )

        # Ensure no duplicate lvl1 intermediates were generated
        lvl1_ids = [entity.displayId for entity in lvl1_inputs]

        self.assertEqual(
            len(lvl1_ids),
            len(set(lvl1_ids)),
            "Duplicate lvl1 intermediates detected",
        )

    def test_transformation(self):
        transformation_doc = sbol2.Document()

        chassis_md = sbol2.ModuleDefinition("E_coli_DH5alpha")
        chassis_impl = sbol2.Implementation("E_coli_DH5alpha_impl")
        chassis_impl.built = chassis_md.identity

        transformation_doc.add(chassis_md)
        transformation_doc.add(chassis_impl)

        result = self.buildcompiler.transformation(
            assembly_products=self.buildcompiler.indexed_plasmids[:2],
            chassis_name="E_coli_DH5alpha",
            transformation_doc=transformation_doc,
        )

        # Top-level output structure
        self.assertEqual(result["stage"], "transformation")

        plasmid_displayIds = [
            plasmid.plasmid_definition.displayId
            for plasmid in self.buildcompiler.indexed_plasmids[:2]
        ]

        self.assertEqual(
            result["inputs"],
            plasmid_displayIds,
        )

        self.assertEqual(
            result["chassis"],
            "E_coli_DH5alpha",
        )

        self.assertIn("sbol_artifacts", result)
        self.assertIn("json_intermediate", result)
        self.assertIn("protocol_artifacts", result)

        # Robot JSON intermediate
        json_intermediate = result["json_intermediate"]

        self.assertEqual(
            json_intermediate["protocol"],
            "chemical_transformation",
        )

        self.assertEqual(
            json_intermediate["version"],
            "0.1",
        )

        self.assertEqual(len(json_intermediate["steps"]), 2)

        first_step = json_intermediate["steps"][0]

        self.assertEqual(first_step["step"], 1)

        self.assertEqual(first_step["plasmid"], plasmid_displayIds[0])

        self.assertEqual(
            first_step["heat_shock"],
            {
                "temperature_c": 42,
                "duration_seconds": 45,
            },
        )

        # SBOL artifact outputs
        sbol_artifacts = result["sbol_artifacts"]

        self.assertEqual(len(sbol_artifacts), 2)

        first_artifact = sbol_artifacts[0]

        self.assertIn("transformation_activity", first_artifact)

        self.assertIn(
            "transformed_strain_module",
            first_artifact,
        )

        self.assertIn(
            "transformed_strain_implementation",
            first_artifact,
        )

        # Verify generated SBOL objects exist in document
        transform_activity = transformation_doc.get(
            f"http://buildcompiler.org/transform_{plasmid_displayIds[0]}_1/1"
        )

        self.assertIsInstance(
            transform_activity,
            sbol2.Activity,
        )

        self.assertEqual(
            len(transform_activity.usages),
            2,
        )

        self.assertEqual(
            len(transform_activity.associations),
            1,
        )

        association = transform_activity.associations[0]

        self.assertIsNotNone(association.plan)

        self.assertIsNotNone(association.agent)

        # Verify transformed strain
        transformed_strain = transformation_doc.get(
            f"http://buildcompiler.org/E_coli_DH5alpha_with_{plasmid_displayIds[0]}/1"
        )

        self.assertIsInstance(
            transformed_strain,
            sbol2.ModuleDefinition,
        )

        self.assertEqual(
            len(transformed_strain.modules),
            1,
        )

        self.assertEqual(
            len(transformed_strain.functionalComponents),
            1,
        )

        # Verify transformed implementation
        transformed_impl = transformation_doc.get(
            f"http://buildcompiler.org/E_coli_DH5alpha_with_{plasmid_displayIds[0]}_impl/1"
        )

        self.assertIsInstance(
            transformed_impl,
            sbol2.Implementation,
        )

        self.assertEqual(
            transformed_impl.built,
            transformed_strain.identity,
        )

        self.assertEqual(
            transformed_impl.wasGeneratedBy,
            [transform_activity.identity],
        )

        # Verify protocol artifacts/logging
        protocol_artifacts = result["protocol_artifacts"]

        self.assertIn(
            "ot2_script",
            protocol_artifacts,
        )

        self.assertIn(
            "human_instructions",
            protocol_artifacts,
        )

        self.assertIn(
            "logs",
            protocol_artifacts,
        )

        self.assertEqual(
            len(protocol_artifacts["logs"]),
            2,
        )

        # Error handling
        invalid_plasmid = copy.deepcopy(self.buildcompiler.indexed_plasmids[4])

        invalid_plasmid.plasmid_implementations = []

        with self.assertRaises(
            ValueError, msg="Plasmid object with no implementations should throw error"
        ):
            self.buildcompiler.transformation(
                assembly_products=[invalid_plasmid],
                transformation_doc=transformation_doc,
            )


if __name__ == "__main__":
    unittest.main()
