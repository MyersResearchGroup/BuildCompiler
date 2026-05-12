# test 1: test same abstract design with each possible circuit selection, ensure the promoter and terminator shift accordingly

# test 2: inaccessible part in abstract design -> should throw informative error message

# test 3: (FUTURE) abstract design with multiple TUs

import sbol2
import unittest
import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../src")))

from buildcompiler.buildcompiler import BuildCompiler

from buildcompiler.abstract_translator import extract_toplevel_definition


class Test_Abstract_Translation_Functions(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        username = os.environ.get("SBH_USERNAME")
        password = os.environ.get("SBH_PASSWORD")

        if not username or not password:
            raise RuntimeError(
                "Missing SBH_USERNAME and/or SBH_PASSWORD environment variables"
            )
        sbh = sbol2.PartShop("https://synbiohub.org")
        sbh.login(username, password)

        auth = sbh.key

        collections = [
            "https://synbiohub.org/user/Gon/impl_test/impl_test_collection/1",
            "https://synbiohub.org/user/Gon/Enzyme_Implementations/Enzyme_Implementations_collection/1",
        ]

        cls.buildcompiler = BuildCompiler(
            collections, "https://synbiohub.org", auth, sbol2.Document()
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
            "https://SBOL2Build.org/qlSBuNBL_composite_assembly/1"
        )

        self.assertEqual(
            len(assembly_activity.usages),
            7,
            "Assembly should have 7 usages: 5 plasmids, 1 ligase, 1 Restriction Enzyme",
        )

        usage_uris = {u.identity for u in assembly_activity.usages}

        expected_usage_uris = {
            "https://SBOL2Build.org/qlSBuNBL_composite_assembly/pJ23100_AB_impl/1",
            "https://SBOL2Build.org/qlSBuNBL_composite_assembly/pB0034_BC_impl/1",
            "https://SBOL2Build.org/qlSBuNBL_composite_assembly/pE0030_CD_impl/1",
            "https://SBOL2Build.org/qlSBuNBL_composite_assembly/pB0015_DE_impl/1",
            "https://SBOL2Build.org/qlSBuNBL_composite_assembly/DVK_AE_impl/1",
            "https://SBOL2Build.org/qlSBuNBL_composite_assembly/BsaI_enzyme/1",
            "https://SBOL2Build.org/qlSBuNBL_composite_assembly/T4_Ligase/1",
        }

        for expected_uri in expected_usage_uris:
            usage = product_doc.get(expected_uri)
            impl = product_doc.get(usage.entity)

            self.assertIn(
                expected_uri,
                usage_uris,
                f"Expected usage {expected_uri} was not found in assembly activity usages",
            )

            self.assertIsNotNone(
                impl,
                f"Entity {impl} should exist in the activity",
            )

        expected_product_uri = "https://SBOL2Build.org/qlSBuNBL_composite_1_impl/1"

        product_impl = product_doc.get(expected_product_uri)
        product_def = product_doc.get(product_impl.built)

        self.assertIsNotNone(
            product_impl,
            f"Implementation {product_impl} should exist in the document",
        )

        self.assertEqual(
            product_impl.wasGeneratedBy,
            assembly_activity.identity,
            f"Implementation {product_impl} must include wasGeneratedBy {assembly_activity.identity}",
        )

        self.assertEqual(
            product_def,
            "https://SBOL2Build.org/qlSBuNBL_composite_1/1",
            f"Implementation {product_impl} must build {product_def}",
        )

        product_doc.write("test_simple_lvl1_assembly.xml")

    # def test_two_rbs_combinatorial_translation(self):
    #     comb_doc = sbol2.Document()
    #     comb_doc.read("tests/test_files/combinatorial_1.xml")

    #     design = extract_toplevel_definition(comb_doc)

    #     self.assertEqual(
    #         len(comb_plasmid_list),
    #         5,
    #         "There should be 5 plasmids in the abstract translation",
    #     )

    #     # Run through sbol2build to test composite count
    #     part_documents = []

    #     for mocloPlasmid in comb_plasmid_list:
    #         temp_doc = sbol2.Document()
    #         mocloPlasmid.definition.copy(temp_doc)
    #         copy_sequences(mocloPlasmid.definition, temp_doc, self.plasmid_collection)
    #         part_documents.append(temp_doc)

    #     assembly_doc = sbol2.Document()
    #     assembly_obj = golden_gate_assembly_plan(
    #         "combinatorial_rbs_assembly_plan",
    #         part_documents,
    #         self.DVK_AE_doc,
    #         "BsaI",
    #         assembly_doc,
    #     )

    #     composite_list = assembly_obj.run()
    #     assembly_doc.write("comb_assembly.xml")

    #     self.assertEqual(
    #         len(composite_list),
    #         2,
    #         "Combinatorial assembly failed to produce 2 composites",
    #     )

    # def test_complex_combinatorial_translation(
    #     self,
    # ):  # testing combinatorial design with 3 variable promoters and RBSs
    #     complex_comb_doc = sbol2.Document()
    #     complex_comb_doc.read("tests/test_files/complex_combinatorial_abstract.xml")

    #     comb_plasmid_list = translate_abstract_to_plasmids(
    #         complex_comb_doc, self.plasmid_collection, self.DVK_AE_doc
    #     )

    #     self.assertEqual(
    #         len(comb_plasmid_list),
    #         8,
    #         f"There should be 8 plasmids in the abstract translation, found {len(comb_plasmid_list)}",
    #     )

    #     # Run through sbol2build to test composite count
    #     part_documents = []

    #     for mocloPlasmid in comb_plasmid_list:
    #         temp_doc = sbol2.Document()
    #         mocloPlasmid.definition.copy(temp_doc)
    #         copy_sequences(mocloPlasmid.definition, temp_doc, self.plasmid_collection)
    #         part_documents.append(temp_doc)

    #     assembly_doc = sbol2.Document()
    #     assembly_obj = golden_gate_assembly_plan(
    #         "complex_combinatorial_assembly_plan",
    #         part_documents,
    #         self.DVK_AE_doc,
    #         "BsaI",
    #         assembly_doc,
    #     )

    #     composite_list = assembly_obj.run()
    #     assembly_doc.write("complex_comb_assembly.xml")

    #     self.assertEqual(
    #         len(composite_list),
    #         9,
    #         f"Combinatorial assembly failed to produce 9 composites, found {len(composite_list)}",
    #     )


if __name__ == "__main__":
    unittest.main()
