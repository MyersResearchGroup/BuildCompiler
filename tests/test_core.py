import sbol2
import os
import sys
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../src")))

from buildcompiler.constants import (
    CIRCULAR,
    ENGINEERED_INSERT,
    ENGINEERED_PLASMID,
    FIVE_PRIME_OVERHANG,
    LINEAR,
    PLASMID_VECTOR,
    THREE_PRIME_OVERHANG,
)
from buildcompiler.sbol2build import (
    Assembly,
    backbone_digestion,
    part_digestion,
    ligation,
)

from buildcompiler.plasmid import Plasmid


class Test_Assembly_Functions(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.sbh = sbol2.PartShop("https://api.synbiohub.org")

        username = os.environ.get("SBH_USERNAME")
        password = os.environ.get("SBH_PASSWORD")

        if not username or not password:
            raise RuntimeError(
                "Missing SBH_USERNAME and/or SBH_PASSWORD environment variables"
            )

        cls.sbh.login(username, password)

        cls.source_doc = sbol2.Document()
        final_doc = sbol2.Document()

        cls.sbh.pull(
            "https://api.synbiohub.org/user/Gon/CIDARMoCloParts/CIDARMoCloParts_collection/1",
            cls.source_doc,
        )
        cls.sbh.pull(
            "https://api.synbiohub.org/user/Gon/CIDARMoCloPlasmidsKit/CIDARMoCloPlasmidsKit_collection/1",
            cls.source_doc,
        )
        cls.sbh.pull(
            "https://api.synbiohub.org/user/Gon/Enzyme_Implementations/Enzyme_Implementations_collection/1",
            cls.source_doc,
        )
        cls.sbh.pull(
            "https://api.synbiohub.org/user/Gon/impl_test/impl_test_collection/1",
            cls.source_doc,
        )

        cls.re_impl = cls.source_doc.get(
            "https://synbiohub.org/user/Gon/Enzyme_Implementations/BsaI_impl/1"
        )
        cls.ligase_impl = cls.source_doc.get(
            "https://synbiohub.org/user/Gon/Enzyme_Implementations/T4_Ligase_impl/1"
        )

        cls.assembly = Assembly(
            None, None, cls.re_impl, cls.ligase_impl, cls.source_doc, final_doc
        )

    def test_part_digestion(self):  # TODO test activity relationships
        impl = self.source_doc.get(
            "https://synbiohub.org/user/Gon/impl_test/pJ23100_AB_impl/1"
        )
        definition = self.source_doc.get(impl.built)
        plasmid = Plasmid(definition, None, [impl], None, self.source_doc)
        assembly_activity = self.assembly.initialize_assembly_activity()

        parts_list, assembly_activity = part_digestion(
            plasmid, [self.re_impl], assembly_activity, self.source_doc
        )

        product_doc = sbol2.Document()
        for extract, _ in parts_list:
            product_doc.add(extract)
        product_doc.add(assembly_activity)

        usages = list(assembly_activity.usages)

        # Expect: 1 reactant + at least 1 enzyme
        self.assertTrue(
            len(usages) >= 2,
            "assembly activity should include reactant and enzyme usages",
        )

        entities = [u.entity for u in usages]

        # reactant implementation should be present
        self.assertIn(
            plasmid.plasmid_implementations[0].identity,
            entities,
            "Reactant implementation missing from activity usages",
        )

        # restriction enzyme should be present
        self.assertIn(
            self.re_impl.identity,
            entities,
            "Restriction enzyme missing from activity usages",
        )

        extract = parts_list[0][0]
        self.assertTrue(
            ENGINEERED_INSERT in extract.roles,
            "Part digestion extracted part missing engineered insert role",
        )  # engineered insert role
        self.assertTrue(
            LINEAR in extract.types,
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
                    comp_def.identity in self.source_doc.componentDefinitions,
                    "Digested part missing reference to part from original document",
                )  # check that old part has been transcribed to new doc, in extracted part

        sbol_validation_result = product_doc.validate()
        self.assertEqual(
            sbol_validation_result, "Valid.", "Part Digestion SBOL validation failed"
        )

    def test_backbone_digestion(self):
        impl = self.source_doc.get(
            "https://synbiohub.org/user/Gon/impl_test/DVK_AE_impl/1"
        )
        definition = self.source_doc.get(impl.built)
        plasmid = Plasmid(definition, None, [impl], None, self.source_doc)
        assembly_activity = self.assembly.initialize_assembly_activity()

        parts_list, assembly_activity = backbone_digestion(
            plasmid, [self.re_impl], assembly_activity, self.source_doc
        )

        product_doc = sbol2.Document()
        for extract, _ in parts_list:
            product_doc.add(extract)
        product_doc.add(assembly_activity)

        usages = list(assembly_activity.usages)

        # Expect: 1 reactant + at least 1 enzyme
        self.assertTrue(
            len(usages) >= 2,
            "Digestion activity should include reactant and enzyme usages",
        )

        entities = [u.entity for u in usages]

        # reactant implementation should be present
        self.assertIn(
            plasmid.plasmid_implementations[0].identity,
            entities,
            "Reactant implementation missing from activity usages",
        )

        # restriction enzyme should be present
        self.assertIn(
            self.re_impl.identity,
            entities,
            "Restriction enzyme missing from activity usages",
        )

        extract = parts_list[0][0]
        self.assertEqual(
            extract.roles,
            [PLASMID_VECTOR],
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
                    [THREE_PRIME_OVERHANG],
                    "Part digestion missing 3 prime role",
                )
            elif "five_prime_oh" in comp_obj.displayId:
                self.assertEqual(
                    comp_def.roles,
                    [FIVE_PRIME_OVERHANG],
                    "Part digestion missing 5 prime role",
                )
            else:
                self.assertTrue(
                    comp_def.identity in self.source_doc.componentDefinitions,
                    "Digested part missing reference to part from original document",
                )  # check that old part has been transcribed to new doc, in extracted part

        sbol_validation_result = product_doc.validate()
        self.assertEqual(
            sbol_validation_result,
            "Valid.",
            "Backbone Digestion SBOL validation failed",
        )

    def test_ligation(self):
        ligation_doc = sbol2.Document()
        reactants_list = []
        assembly_activity = self.assembly.initialize_assembly_activity()
        parts = [
            self.source_doc.get(
                "https://synbiohub.org/user/Gon/impl_test/pJ23100_AB_impl/1"
            ),
            self.source_doc.get(
                "https://synbiohub.org/user/Gon/impl_test/pB0034_BC_impl/1"
            ),
            self.source_doc.get(
                "https://synbiohub.org/user/Gon/impl_test/pE0030_CD_impl/1"
            ),
            self.source_doc.get(
                "https://synbiohub.org/user/Gon/impl_test/pB0015_DE_impl/1"
            ),
        ]

        for i, impl in enumerate(parts):
            definition = self.source_doc.get(impl.built)
            plasmid = Plasmid(definition, None, [impl], None, self.source_doc)

            extracts_tuple_list, assembly_activity = part_digestion(
                plasmid, [self.re_impl], assembly_activity, self.source_doc
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

        backbone_impl = self.source_doc.get(
            "https://synbiohub.org/user/Gon/impl_test/DVK_AE_impl/1"
        )

        # run digestion, extract component + sequence, add to ligation_doc, reactants_list
        definition = self.source_doc.get(backbone_impl.built)

        self.sbh.pull(
            "https://api.synbiohub.org/user/Gon/CIDARMoCloPlasmidsKit/DVK_AE/1",
            self.source_doc,
        )

        plasmid = Plasmid(definition, None, [backbone_impl], None, self.source_doc)

        extracts_tuple_list, assembly_activity = backbone_digestion(
            plasmid, [self.re_impl], assembly_activity, self.source_doc
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

        ligation_doc.add(assembly_activity)
        reactants_list.append(extracts_tuple_list[0][0])

        ligation_doc.add_list([self.re_impl, self.ligase_impl])

        pull_uri = self.ligase_impl.built.replace(
            "https://synbiohub.org", "https://api.synbiohub.org"
        )
        self.sbh.pull(pull_uri, ligation_doc)

        final_doc = sbol2.Document()

        composite_impls = ligation(
            reactants_list,
            assembly_activity,
            "test",
            ligation_doc,
            final_doc,
            self.ligase_impl,
        )

        usages = list(assembly_activity.usages)
        entities = [u.entity for u in usages]

        self.assertIn(
            self.ligase_impl.identity,
            entities,
            "Ligase missing from assembly activity usages",
        )

        for part_impl in parts:
            self.assertIn(
                part_impl.identity,
                entities,
                f"{part_impl.displayId} missing from assembly activity usages",
            )

        for i in composite_impls:
            obj = final_doc.get(i.built)

            self.assertEqual(
                i.wasGeneratedBy,
                [assembly_activity.identity],
                "Composite implementation not linked to assembly activity",
            )

            if type(obj) is sbol2.ComponentDefinition:
                self.assertTrue(
                    CIRCULAR in obj.types,
                    "Ligation product missing circular DNA type",
                )
                self.assertTrue(
                    "http://www.biopax.org/release/biopax-level3.owl#Dna" in obj.types,
                    "Ligation product missing DNA Molecule type",
                )
                self.assertTrue(
                    ENGINEERED_PLASMID in obj.roles,
                    "Ligation product missing engineered plasmid role",
                )

                locations = []

                for anno in obj.sequenceAnnotations:
                    for location in anno.locations:
                        locations.append((anno.identity, location.start, location.end))

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

        sbol_validation_result = final_doc.validate()
        self.assertEqual(
            sbol_validation_result, "Valid.", "Ligation SBOL validation failed"
        )


if __name__ == "__main__":
    unittest.main()
