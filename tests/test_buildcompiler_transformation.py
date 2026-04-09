import os
import sys
import unittest

import sbol2

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../src")))

from buildcompiler.buildcompiler import BuildCompiler
from buildcompiler.constants import ENGINEERED_PLASMID


class TestBuildCompilerTransformation(unittest.TestCase):
    def setUp(self):
        self.doc = sbol2.Document()
        self.compiler = BuildCompiler(
            collections=[],
            sbh_registry="https://synbiohub.org",
            auth_token="",
            sbol_doc=self.doc,
        )

    def _make_plasmid(self, display_id: str) -> sbol2.ComponentDefinition:
        plasmid = sbol2.ComponentDefinition(display_id)
        plasmid.roles = [ENGINEERED_PLASMID]
        self.doc.add(plasmid)
        return plasmid

    def test_transformation_accepts_component_definitions(self):
        p1 = self._make_plasmid("geneA_plasmid")
        p2 = self._make_plasmid("geneB_plasmid")

        result = self.compiler.transformation([p1, p2], chassis_name="DH5alpha")

        self.assertEqual(result["stage"], "transformation")
        self.assertEqual(result["chassis"], "DH5alpha")
        self.assertEqual(len(result["sbol_artifacts"]), 2)
        self.assertEqual(len(result["json_intermediate"]["steps"]), 2)
        self.assertEqual(
            result["json_intermediate"]["steps"][0]["plasmid"], "geneA_plasmid"
        )
        self.assertIn("logs", result["protocol_artifacts"])

    def test_transformation_accepts_dict_payloads(self):
        plasmid = self._make_plasmid("geneC_plasmid")
        result = self.compiler.transformation(
            [{"name": "lvl1_geneC_output", "plasmid": plasmid}]
        )

        self.assertEqual(result["inputs"], ["lvl1_geneC_output"])
        self.assertEqual(
            result["sbol_artifacts"][0]["transformed_strain_module"].endswith(
                "E_coli_DH5alpha_with_geneC_plasmid/1"
            ),
            True,
        )

    def test_transformation_requires_inputs(self):
        with self.assertRaises(ValueError):
            self.compiler.transformation([])


if __name__ == "__main__":
    unittest.main()
