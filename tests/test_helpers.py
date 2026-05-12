import sbol2
import os
import sys
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../src")))

from buildcompiler.sbol2build import (
    rebase_restriction_enzyme,
    dna_componentdefinition_with_sequence,
    number_to_suffix,
    is_circular,
    append_extracts_to_doc,
)


class Test_HelperFunctions(unittest.TestCase):
    def test_restriction_enzyme(self):
        bsai = rebase_restriction_enzyme(name="BsaI")
        constructor_error = "Constructor Error: ed_restriction_enzyme"

        test_cases = [
            (
                "http://rebase.neb.com/rebase/enz/BsaI.html",
                bsai.wasDerivedFrom,
                constructor_error,
            ),
            (
                "http://www.biopax.org/release/biopax-level3.owl#Protein",
                bsai.types,
                constructor_error,
            ),
            ("BsaI", bsai.name, constructor_error),
            (
                "Restriction enzyme BsaI from REBASE.",
                bsai.description,
                constructor_error,
            ),
        ]

        for expected, attribute, error_msg in test_cases:
            with self.subTest(expected=expected, attribute=attribute):
                self.assertIn(expected, attribute, error_msg)

    def test_dna_component_and_sequence(self):
        # create a test dna component
        dna_identity = "Test_dna_identity"
        dna_sequence = "Test_dna_sequence"
        test_dna_component, test_sequence = dna_componentdefinition_with_sequence(
            dna_identity, dna_sequence
        )

        test_cases = [
            (
                "<class 'sbol2.componentdefinition.ComponentDefinition'>",
                repr(type(test_dna_component)),
                "Constructor Error: dna_componentdefinition_with_sequence, Not a ComponentDefinition",
            ),
            (
                "<class 'sbol2.sequence.Sequence'>",
                repr(type(test_sequence)),
                "Constructor Error: dna_componentdefinition_with_sequence, Not a Sequence",
            ),
            (
                f"http://buildcompiler.org/{dna_identity}_seq/1",
                test_sequence.identity,
                "Constructor Error: dna_componentdefinition_with_sequence, Incorrect Identity",
            ),
            (
                [test_sequence.identity],
                test_dna_component.sequences,
                "Constructor Error: dna_componentdefinition_with_sequence, Sequence not in ComponentDefinition Sequences List",
            ),
            (
                ["http://www.biopax.org/release/biopax-level3.owl#DnaRegion"],
                test_dna_component.types,
                "Constructor Error: dna_componentdefinition_with_sequence, Missing DNA type",
            ),
        ]

        for expected, attribute, error_msg in test_cases:
            with self.subTest(expected=expected, attribute=attribute):
                self.assertEqual(expected, attribute, error_msg)

    def test_is_circular(self):
        comp_def_circ = sbol2.ComponentDefinition("test")
        comp_def_circ.types = ["http://identifiers.org/so/SO:0000988"]

        comp_def_not_circ = sbol2.ComponentDefinition("test_not_circ")

        self.assertTrue(is_circular(comp_def_circ))
        self.assertFalse(is_circular(comp_def_not_circ))

    def test_number_to_suffix(self):
        # 1 letter
        self.assertEqual(number_to_suffix(1), "A")
        self.assertEqual(number_to_suffix(2), "B")
        self.assertEqual(number_to_suffix(26), "Z")
        # 2 letters
        self.assertEqual(number_to_suffix(27), "AA")
        self.assertEqual(number_to_suffix(28), "AB")
        self.assertEqual(number_to_suffix(52), "AZ")
        self.assertEqual(number_to_suffix(53), "BA")
        # 3 letters
        self.assertEqual(number_to_suffix(702), "ZZ")  # 26*27 - 1
        self.assertEqual(number_to_suffix(703), "AAA")  # 26*27
        self.assertEqual(number_to_suffix(704), "AAB")  # 26*27 + 1
        self.assertEqual(number_to_suffix(0), "")

    def test_append_extracts_to_doc(self):
        doc = sbol2.Document()
        tup1 = dna_componentdefinition_with_sequence("def1", "atgcaatg")
        tup2 = dna_componentdefinition_with_sequence("def2", "ggacttaac")

        append_extracts_to_doc([tup1, tup2, tup1], doc)

        # ensure duplicate of tup1 is not being counted
        self.assertEqual(len(doc.sequences), 2)
        self.assertEqual(len(doc.componentDefinitions), 2)

        self.assertEqual(doc.sequences[0].elements, "atgcaatg")
        self.assertEqual(doc.componentDefinitions[0].displayId, "def1")
        self.assertEqual(doc.sequences[1].elements, "ggacttaac")
        self.assertEqual(doc.componentDefinitions[1].displayId, "def2")

    # TODO test for part in backbone?


if __name__ == "__main__":
    unittest.main()
