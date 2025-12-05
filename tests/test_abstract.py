# test 1: test same abstract design with each possible circuit selection, ensure the promoter and terminator shift accordingly

# test 2: inaccessible part in abstract design -> should throw informative error message

# test 3: (FUTURE) abstract design with multiple TUs

import sbol2
import unittest
import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../src")))

from sbol2build.abstract_translator import (
    translate_abstract_to_plasmids,
    copy_sequences,
)

from sbol2build import (
    golden_gate_assembly_plan,
)


class Test_Abstract_Translation_Functions(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.sbh = sbol2.PartShop("https://synbiohub.org")

        cls.plasmid_collection = sbol2.Document()
        cls.sbh.pull(
            "https://synbiohub.org/user/Gon/CIDARMoCloPlasmidsKit/CIDARMoCloPlasmidsKit_collection/1/b7fdc21c6601a61d3166073a9e50f2c3843e1df5/share",
            cls.plasmid_collection,
        )

        cls.DVK_AE_doc = sbol2.Document()
        cls.sbh.pull(
            "https://synbiohub.org/user/Gon/CIDARMoCloPlasmidsKit/DVK_AE/1/647c5b2458567dcce6b0a37178d352b8ffa9a7fe/share",
            cls.DVK_AE_doc,
        )

    def test_simple_abstract_translation(self):
        abstract_design_doc = sbol2.Document()
        abstract_design_doc.read("tests/test_files/moclo_parts_circuit.xml")

        mocloplasmid_list = translate_abstract_to_plasmids(
            abstract_design_doc, self.plasmid_collection, self.DVK_AE_doc
        )

        self.assertEqual(
            len(mocloplasmid_list),
            4,
            "There should be 4 plasmids in the abstract translation",
        )

        prev_site = "A"
        for plas in mocloplasmid_list:
            self.assertEqual(prev_site, plas.fusion_sites[0], mocloplasmid_list)
            prev_site = plas.fusion_sites[1]

    def test_two_rbs_combinatorial_translation(self):
        comb_doc = sbol2.Document()
        comb_doc.read("tests/test_files/combinatorial_1.xml")

        comb_plasmid_list = translate_abstract_to_plasmids(
            comb_doc, self.plasmid_collection, self.DVK_AE_doc
        )

        self.assertEqual(
            len(comb_plasmid_list),
            5,
            "There should be 5 plasmids in the abstract translation",
        )

        # Run through sbol2build to test composite count
        part_documents = []

        for mocloPlasmid in comb_plasmid_list:
            temp_doc = sbol2.Document()
            mocloPlasmid.definition.copy(temp_doc)
            copy_sequences(mocloPlasmid.definition, temp_doc, self.plasmid_collection)
            part_documents.append(temp_doc)

        assembly_doc = sbol2.Document()
        assembly_obj = golden_gate_assembly_plan(
            "combinatorial_rbs_assembly_plan",
            part_documents,
            self.DVK_AE_doc,
            "BsaI",
            assembly_doc,
        )

        composite_list = assembly_obj.run()
        assembly_doc.write("comb_assembly.xml")

        self.assertEqual(
            len(composite_list),
            2,
            "Combinatorial assembly failed to produce 2 composites",
        )

    def test_complex_combinatorial_translation(
        self,
    ):  # testing combinatorial design with 3 variable promoters and RBSs
        complex_comb_doc = sbol2.Document()
        complex_comb_doc.read("tests/test_files/complex_combinatorial_abstract.xml")

        comb_plasmid_list = translate_abstract_to_plasmids(
            complex_comb_doc, self.plasmid_collection, self.DVK_AE_doc
        )

        self.assertEqual(
            len(comb_plasmid_list),
            8,
            f"There should be 8 plasmids in the abstract translation, found {len(comb_plasmid_list)}",
        )

        # Run through sbol2build to test composite count
        part_documents = []

        for mocloPlasmid in comb_plasmid_list:
            temp_doc = sbol2.Document()
            mocloPlasmid.definition.copy(temp_doc)
            copy_sequences(mocloPlasmid.definition, temp_doc, self.plasmid_collection)
            part_documents.append(temp_doc)

        assembly_doc = sbol2.Document()
        assembly_obj = golden_gate_assembly_plan(
            "complex_combinatorial_assembly_plan",
            part_documents,
            self.DVK_AE_doc,
            "BsaI",
            assembly_doc,
        )

        composite_list = assembly_obj.run()
        assembly_doc.write("complex_comb_assembly.xml")

        self.assertEqual(
            len(composite_list),
            9,
            f"Combinatorial assembly failed to produce 9 composites, found {len(composite_list)}",
        )


if __name__ == "__main__":
    unittest.main()
