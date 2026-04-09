import os
import sys
import unittest

import sbol2

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../src")))

from buildcompiler.buildcompiler import BuildCompiler
from buildcompiler.constants import ENGINEERED_PLASMID
from buildcompiler.plasmid import Plasmid


class TestBuildCompilerTransformation(unittest.TestCase):
    def setUp(self):
        self.doc = sbol2.Document()
        self.compiler = BuildCompiler(
            collections=[],
            sbh_registry="https://synbiohub.org",
            auth_token="",
            sbol_doc=self.doc,
        )

    def _build_plasmid(self, display_id: str) -> Plasmid:
        plasmid_definition = sbol2.ComponentDefinition(display_id)
        plasmid_definition.roles = [ENGINEERED_PLASMID]
        self.doc.add(plasmid_definition)

        plasmid_impl = sbol2.Implementation(f"{display_id}_impl")
        plasmid_impl.built = plasmid_definition.identity
        self.doc.add(plasmid_impl)

        return Plasmid(plasmid_definition, None, [plasmid_impl], [], self.doc)

    def test_transformation_with_assembly_products(self):
        plasmid = self._build_plasmid("assembled_gene")

        result = self.compiler.transformation(assembly_products=[plasmid])

        self.assertEqual(result["stage"], "transformation")
        self.assertEqual(len(result["json"]["reactions"]), 1)
        self.assertEqual(result["json"]["reactions"][0]["plasmid"], "assembled_gene")
        self.assertEqual(len(result["sbol"]["transformed_strains"]), 1)

    def test_transformation_with_plasmid_inputs(self):
        plasmid_definition = sbol2.ComponentDefinition("input_plasmid")
        plasmid_definition.roles = [ENGINEERED_PLASMID]
        self.doc.add(plasmid_definition)

        result = self.compiler.transformation(plasmid_inputs=[plasmid_definition])

        self.assertEqual(result["stage"], "transformation")
        self.assertEqual(result["inputs"], [plasmid_definition.identity])
        self.assertEqual(result["json"]["reactions"][0]["destination_strain"], "E_coli_DH5alpha_with_input_plasmid_1")

    def test_transformation_requires_single_input_channel(self):
        with self.assertRaises(ValueError):
            self.compiler.transformation()

        plasmid = self._build_plasmid("dual_mode")
        with self.assertRaises(ValueError):
            self.compiler.transformation(
                assembly_products=[plasmid],
                plasmid_inputs=[plasmid.plasmid_definition],
            )


if __name__ == "__main__":
    unittest.main()
