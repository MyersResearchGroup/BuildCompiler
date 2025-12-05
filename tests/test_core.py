import sbol2
import os
import sys
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../src")))

from sbol2build import (
    golden_gate_assembly_plan,
    rebase_restriction_enzyme,
    backbone_digestion,
    part_digestion,
    ligation,
)


class Test_Core_Functions(unittest.TestCase):
    def test_part_digestion(self):
        doc = sbol2.Document()
        doc.read("tests/test_files/pro_in_bb.xml")

        md = doc.getModuleDefinition("https://sbolcanvas.org/module1")
        assembly_plan = sbol2.ModuleDefinition("assembly_plan")

        parts_list, assembly_plan = part_digestion(
            md, [rebase_restriction_enzyme("BsaI")], assembly_plan, doc
        )

        product_doc = sbol2.Document()
        for extract, sequence in parts_list:
            product_doc.add(extract)
            product_doc.add(sequence)
        product_doc.add(assembly_plan)

        extract = parts_list[0][0]
        self.assertEqual(
            extract.roles,
            ["https://identifiers.org/so/SO:0000915"],
            "Part digestion extracted part missing engineered insert role",
        )  # engineered insert role
        self.assertTrue(
            "http://identifiers.org/so/SO:0000987" in extract.types,
            "Part digestion extracted part missing linear DNA type",
        )

        # ensure extracted part has 5prime, part from sbolcanvas, and 3prime
        for anno in parts_list[0][0].sequenceAnnotations:
            comp_uri = anno.component
            comp_obj = product_doc.find(comp_uri)
            comp_def = product_doc.find(comp_obj.definition)

            if "three_prime_oh" in comp_obj.displayId:
                self.assertEqual(
                    comp_def.roles,
                    ["http://identifiers.org/so/SO:0001933"],
                    "Part digestion missing 3 prime role",
                )
            elif "five_prime_oh" in comp_obj.displayId:
                self.assertEqual(
                    comp_def.roles,
                    ["http://identifiers.org/so/SO:0001932"],
                    "Part digestion missing 5 prime role",
                )
            else:
                self.assertTrue(
                    comp_def.identity in doc.componentDefinitions,
                    "Digested part missing reference to part from original document",
                )  # check that old part has been transcribed to new doc, in extracted part

        # check that wasderivedfroms match, assembly plan records all interactions,
        contains_restriction, contains_reactant, contains_product = False, False, False
        for participation in assembly_plan.interactions[0].participations:
            if participation.displayId == "restriction":
                self.assertTrue(
                    "http://identifiers.org/biomodels.sbo/SBO:0000019"
                    in participation.roles,
                    "Restriction participation missing 'modifier' role",
                )
                contains_restriction = True
            elif "reactant" in participation.displayId:
                self.assertTrue(
                    "http://identifiers.org/biomodels.sbo/SBO:0000010"
                    in participation.roles,
                    "Restriction reactant participation missing 'reactant' role",
                )
                contains_reactant = True
            elif "product" in participation.displayId:
                self.assertTrue(
                    "http://identifiers.org/biomodels.sbo/SBO:0000011"
                    in participation.roles,
                    "Restriction product participation missing 'product' role",
                )
                contains_product = True

        self.assertTrue(
            contains_product, "Digestion Assembly plan missing product participation"
        )
        self.assertTrue(
            contains_reactant, "Digestion Assembly plan missing reactant participation"
        )
        self.assertTrue(
            contains_restriction,
            "Digestion Assembly plan missing restriction participation",
        )

        sbol_validation_result = product_doc.validate()
        self.assertEqual(
            sbol_validation_result, "Valid.", "Part Digestion SBOL validation failed"
        )

    def test_backbone_digestion(self):
        doc = sbol2.Document()
        doc.read("tests/test_files/backbone.xml")

        md = doc.getModuleDefinition("https://sbolcanvas.org/module1")
        assembly_plan = sbol2.ModuleDefinition("assembly_plan")

        parts_list, assembly_plan = backbone_digestion(
            md, [rebase_restriction_enzyme("BsaI")], assembly_plan, doc
        )

        product_doc = sbol2.Document()
        for extract, sequence in parts_list:
            product_doc.add(extract)
            product_doc.add(sequence)
        product_doc.add(assembly_plan)

        extract = parts_list[0][0]
        self.assertEqual(
            extract.roles,
            ["https://identifiers.org/so/SO:0000755"],
            "Backbone digestion extracted part missing plasmid vector role",
        )  # plasmid vector

        # ensure extracted part has 5prime, part from sbolcanvas, and 3prime
        for anno in parts_list[0][0].sequenceAnnotations:
            comp_uri = anno.component
            comp_obj = product_doc.find(comp_uri)
            comp_def = product_doc.find(comp_obj.definition)

            if "three_prime_oh" in comp_obj.displayId:
                self.assertEqual(
                    comp_def.roles,
                    ["http://identifiers.org/so/SO:0001933"],
                    "Part digestion missing 3 prime role",
                )
            elif "five_prime_oh" in comp_obj.displayId:
                self.assertEqual(
                    comp_def.roles,
                    ["http://identifiers.org/so/SO:0001932"],
                    "Part digestion missing 5 prime role",
                )
            else:
                self.assertTrue(
                    comp_def.identity in doc.componentDefinitions,
                    "Digested part missing reference to part from original document",
                )  # check that old part has been transcribed to new doc, in extracted part

        # check that wasderivedfroms match, assembly plan records all interactions,
        contains_restriction, contains_reactant, contains_product = False, False, False
        for participation in assembly_plan.interactions[0].participations:
            if participation.displayId == "restriction":
                self.assertTrue(
                    "http://identifiers.org/biomodels.sbo/SBO:0000019"
                    in participation.roles,
                    "Restriction participation missing 'modifier' role",
                )
                contains_restriction = True
            elif "reactant" in participation.displayId:
                self.assertTrue(
                    "http://identifiers.org/biomodels.sbo/SBO:0000010"
                    in participation.roles,
                    "Restriction reactant participation missing 'reactant' role",
                )
                contains_reactant = True
            elif "product" in participation.displayId:
                self.assertTrue(
                    "http://identifiers.org/biomodels.sbo/SBO:0000011"
                    in participation.roles,
                    "Restriction product participation missing 'product' role",
                )
                contains_product = True

        self.assertTrue(
            contains_product, "Digestion Assembly plan missing product participation"
        )
        self.assertTrue(
            contains_reactant, "Digestion Assembly plan missing reactant participation"
        )
        self.assertTrue(
            contains_restriction,
            "Digestion Assembly plan missing restriction participation",
        )

        sbol_validation_result = product_doc.validate()
        self.assertEqual(
            sbol_validation_result,
            "Valid.",
            "Backbone Digestion SBOL validation failed",
        )

    def test_ligation(self):
        ligation_doc = sbol2.Document()
        temp_doc = sbol2.Document()
        reactants_list = []
        assembly_plan = sbol2.ModuleDefinition("assembly_plan")
        parts = [
            "tests/test_files/pro_in_bb.xml",
            "tests/test_files/rbs_in_bb.xml",
            "tests/test_files/cds_in_bb.xml",
            "tests/test_files/terminator_in_bb.xml",
        ]

        for i, part in enumerate(parts):
            temp_doc.read(part)
            md = temp_doc.getModuleDefinition("https://sbolcanvas.org/module1")
            extracts_tuple_list, assembly_plan = part_digestion(
                md, [rebase_restriction_enzyme("BsaI")], assembly_plan, temp_doc
            )

            for extract, sequence in extracts_tuple_list:
                try:
                    ligation_doc.add(extract)
                    ligation_doc.add(sequence)
                except Exception as e:
                    if "<SBOLErrorCode.SBOL_ERROR_URI_NOT_UNIQUE: 17>" in str(e):
                        pass
                    else:
                        print(e)

            reactants_list.append(extracts_tuple_list[0][0])

        temp_doc.read("tests/test_files/backbone.xml")
        # run digestion, extract component + sequence, add to ligation_doc, reactants_list
        md = temp_doc.getModuleDefinition("https://sbolcanvas.org/module1")
        extracts_tuple_list, assembly_plan = backbone_digestion(
            md, [rebase_restriction_enzyme("BsaI")], assembly_plan, temp_doc
        )
        for extract, seq in extracts_tuple_list:
            try:
                ligation_doc.add(
                    extract
                )  # add only extracted definitions and and sequences from digestion
                ligation_doc.add(seq)
            except Exception as e:
                if "<SBOLErrorCode.SBOL_ERROR_URI_NOT_UNIQUE: 17>" in str(e):
                    pass
                else:
                    print(e)

        ligation_doc.add(assembly_plan)
        reactants_list.append(extracts_tuple_list[0][0])

        ligation_doc.add(rebase_restriction_enzyme("BsaI"))

        pl = ligation(reactants_list, assembly_plan, ligation_doc)

        for p in pl:
            for obj in p:
                ligation_doc.add(obj)

                if type(obj) is sbol2.ComponentDefinition:
                    self.assertTrue(
                        "http://identifiers.org/so/SO:0000988" in obj.types,
                        "Ligation product missing circular DNA type",
                    )
                    self.assertTrue(
                        "http://www.biopax.org/release/biopax-level3.owl#Dna"
                        in obj.types,
                        "Ligation product missing DNA Molecule type",
                    )
                    self.assertTrue(
                        "http://identifiers.org/so/SO:0000804" in obj.roles,
                        "Ligation product missing engineered region role",
                    )

                    locations = []

                    for anno in obj.sequenceAnnotations:
                        for location in anno.locations:
                            locations.append(
                                (anno.identity, location.start, location.end)
                            )

                    locations.sort(key=lambda x: x[1])

                    for i in range(len(locations) - 1):
                        current_end = locations[i][2]
                        next_start = locations[i + 1][1]

                        self.assertEqual(
                            current_end + 1,
                            next_start,
                            f"Mismatch in continuity: {locations[i][0]} ends at {current_end}, "
                            f"but {locations[i + 1][0]} starts at {next_start}",
                        )

        sbol_validation_result = ligation_doc.validate()
        self.assertEqual(
            sbol_validation_result, "Valid.", "Ligation SBOL validation failed"
        )

    def test_golden_gate(self):
        pro_doc = sbol2.Document()
        pro_doc.read("tests/test_files/pro_in_bb.xml")

        rbs_doc = sbol2.Document()
        rbs_doc.read("tests/test_files/rbs_in_bb.xml")

        cds_doc = sbol2.Document()
        cds_doc.read("tests/test_files/cds_in_bb.xml")

        ter_doc = sbol2.Document()
        ter_doc.read("tests/test_files/terminator_in_bb.xml")

        bb_doc = sbol2.Document()
        bb_doc.read("tests/test_files/backbone.xml")

        part_docs = [pro_doc, rbs_doc, cds_doc, ter_doc]

        assembly_doc = sbol2.Document()
        assembly_obj = golden_gate_assembly_plan(
            "testassem", part_docs, bb_doc, "BsaI", assembly_doc
        )

        composites = assembly_obj.run(plasmids_in_module_definitions=True)

        self.assertEqual(len(composites), 1)

        assembly_doc.write("validation_assembly.xml")

        sbol_validation_result = assembly_doc.validate()
        self.assertEqual(
            sbol_validation_result, "Valid.", "Assembly SBOL validation failed"
        )


if __name__ == "__main__":
    unittest.main()
