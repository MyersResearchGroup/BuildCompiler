import sbol2
import unittest
import sys
import os
from collections import Counter

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../src")))

from buildcompiler.buildcompiler import BuildCompiler

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
            "https://api.synbiohub.org/user/Gon/impl_test/impl_test_collection/1",
            "https://api.synbiohub.org/user/Gon/Enzyme_Implementations/Enzyme_Implementations_collection/1",
        ]

        source = sbol2.Document()

        # preload combinatorial designs into buildcompiler context
        source.read("tests/test_files/complex_combinatorial_abstract.xml")
        source.append("tests/test_files/combinatorial_1.xml", True)

        cls.buildcompiler = BuildCompiler(
            collections, "https://api.synbiohub.org", auth, source
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

            impl = get_or_pull(product_doc, self.buildcompiler.sbh, usage.entity)

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

        expected_product_uri = "http://buildcompiler.org/qlSBuNBL_composite_1_impl/1"

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
            "http://buildcompiler.org/qlSBuNBL_composite_1/1",
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


if __name__ == "__main__":
    unittest.main()
