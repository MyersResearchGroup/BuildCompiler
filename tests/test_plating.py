import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import sbol2

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../src")))

from buildcompiler.buildcompiler import BuildCompiler
from buildcompiler.constants import ENGINEERED_PLASMID, ORGANISM_STRAIN
from buildcompiler.robotutils import generate_96_well_positions, normalize_plating_input


class _ProcResult:
    def __init__(self, returncode=0, stdout="", stderr=""):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


class TestPlating(unittest.TestCase):
    def setUp(self):
        self.doc = sbol2.Document()
        self.compiler = BuildCompiler(
            collections=[],
            sbh_registry="https://synbiohub.org",
            auth_token="",
            sbol_doc=self.doc,
        )
        self._id_seed = 0

    def _make_transform_result(self, count=1):
        artifacts = []
        self._id_seed += 1
        prefix = f"t{self._id_seed}_"
        for i in range(1, count + 1):
            plasmid = sbol2.ComponentDefinition(f"{prefix}p{i}")
            plasmid.roles = [ENGINEERED_PLASMID]
            self.doc.add(plasmid)
            transform_module = sbol2.ModuleDefinition(f"{prefix}strain_{i}")
            transform_module.roles = [ORGANISM_STRAIN]
            self.doc.add(transform_module)
            impl = sbol2.Implementation(f"{prefix}strain_{i}_impl")
            impl.built = transform_module.identity
            self.doc.add(impl)
            artifacts.append(
                {
                    "transformed_strain_module": transform_module.identity,
                    "transformed_strain_implementation": impl.identity,
                }
            )
        return {"stage": "transformation", "sbol_artifacts": artifacts}

    def test_normalization_shapes(self):
        result = self._make_transform_result(2)
        normalized = normalize_plating_input(result, doc=self.doc)
        self.assertEqual(len(normalized), 2)

        sloc = normalize_plating_input({"strain_locations": {"A1": "x", "A2": "y"}})
        self.assertEqual(len(sloc), 2)

        bloc = normalize_plating_input({"bacterium_locations": {"A1": "x"}})
        self.assertEqual(len(bloc), 1)

        with self.assertRaises(ValueError):
            normalize_plating_input({"invalid": True})

    def test_plate_well_mapping_limits(self):
        self.assertEqual(generate_96_well_positions(1), ["A1"])
        self.assertEqual(generate_96_well_positions(13)[-1], "B1")
        self.assertEqual(len(generate_96_well_positions(96)), 96)

        with tempfile.TemporaryDirectory() as tmpdir:
            ok = self.compiler.plating(
                self._make_transform_result(96), Path(tmpdir), protocol_type="manual"
            )
            self.assertEqual(len(ok["plate"]["plate_map"]), 96)

            with self.assertRaises(ValueError):
                self.compiler.plating(
                    self._make_transform_result(97), Path(tmpdir), protocol_type="manual"
                )

    def test_plating_manual_outputs_and_provenance(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            result = self.compiler.plating(
                transformation_results=self._make_transform_result(2),
                results_dir=tmpdir,
                protocol_type="manual",
                advanced_params={"incubation_temperature_c": 37},
            )
            self.assertEqual(result["stage"], "plating")
            self.assertEqual(result["protocol_type"], "manual")
            self.assertEqual(len(result["plate"]["plate_map"]), 2)
            self.assertTrue(
                Path(result["protocol_artifacts"]["manual_protocol_markdown"]).exists()
            )
            self.assertTrue(Path(result["protocol_artifacts"]["plate_map_json"]).exists())
            self.assertTrue(Path(result["protocol_artifacts"]["plate_map_csv"]).exists())

            activity = self.doc.find(result["sbol_artifacts"]["plating_activity"])
            self.assertIsNotNone(activity)
            self.assertEqual(len(activity.usages), 2)
            self.assertTrue(len(activity.associations) >= 1)

    @patch("buildcompiler.robotutils.subprocess.run")
    def test_plating_automated_script_and_sim_zip(self, mock_run):
        mock_run.return_value = _ProcResult(returncode=0, stdout="ok", stderr="")
        with tempfile.TemporaryDirectory() as tmpdir:
            result = self.compiler.plating(
                transformation_results=self._make_transform_result(1),
                results_dir=tmpdir,
                protocol_type="automated",
                advanced_params={"replicates": 1},
                overwrite=True,
            )
            script_path = Path(result["protocol_artifacts"]["ot2_script"])
            script = script_path.read_text(encoding="utf-8")
            self.assertIn("def run(protocol: protocol_api.ProtocolContext):", script)
            self.assertIn("from opentrons import protocol_api", script)
            self.assertIn("json_params=ADVANCED_PARAMS", script)
            self.assertNotIn("advanced_params=ADVANCED_PARAMS", script)
            self.assertTrue(Path(result["protocol_artifacts"]["simulation_zip"]).exists())


if __name__ == "__main__":
    unittest.main()
