import json
import tempfile
import unittest
import zipfile
import os
import sys
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../src")))

from buildcompiler.buildcompiler import BuildCompiler
from buildcompiler.robotutils import (
    normalize_plating_data,
    run_opentrons_script_to_zip,
)


class TestPlatingNormalization(unittest.TestCase):
    def test_accepts_bacterium_locations_shape(self):
        data = {"bacterium_locations": {"A1": "strain_1"}}
        normalized = normalize_plating_data(data)
        self.assertEqual(normalized, data)

    def test_accepts_strain_locations_shape(self):
        normalized = normalize_plating_data({"strain_locations": {"A1": "strain_1"}})
        self.assertEqual(normalized, {"bacterium_locations": {"A1": "strain_1"}})

    def test_accepts_thermocycler_wells_shape(self):
        normalized = normalize_plating_data({"thermocycler_wells": {"B2": "strain_2"}})
        self.assertEqual(normalized, {"bacterium_locations": {"B2": "strain_2"}})

    def test_accepts_raw_well_map_shape(self):
        normalized = normalize_plating_data({"C3": "strain_3"})
        self.assertEqual(normalized, {"bacterium_locations": {"C3": "strain_3"}})

    def test_invalid_shape_raises_value_error(self):
        with self.assertRaises(ValueError):
            normalize_plating_data({"unexpected": {"A1": "strain_1"}})


class TestBuildCompilerPlating(unittest.TestCase):
    def test_plating_writes_json_and_script(self):
        compiler = BuildCompiler.__new__(BuildCompiler)

        with tempfile.TemporaryDirectory() as tmpdir:
            results_dir = Path(tmpdir) / "plating_results"

            with patch(
                "buildcompiler.buildcompiler.run_opentrons_script_to_zip",
                return_value=results_dir / "plating.zip",
            ):
                output = compiler.plating(
                    transformation_results={"A1": "strain_1"},
                    results_dir=results_dir,
                    advanced_params={"target_colonies": 12},
                )

            self.assertTrue(Path(output["plating_json"]).exists())
            self.assertTrue(Path(output["protocol_script"]).exists())
            self.assertTrue(output["simulation_zip"].endswith("plating.zip"))

            script_text = Path(output["protocol_script"]).read_text(encoding="utf-8")
            self.assertIn("from pudu.plating import Plating", script_text)
            self.assertIn("json_params=ADVANCED_PARAMS", script_text)
            self.assertNotIn("advanced_params=ADVANCED_PARAMS", script_text)

            payload = json.loads(Path(output["plating_json"]).read_text(encoding="utf-8"))
            self.assertIn("plating_data", payload)
            self.assertIn("advanced_params", payload)
            self.assertEqual(
                payload["plating_data"], {"bacterium_locations": {"A1": "strain_1"}}
            )


class TestPlatingSimulationZip(unittest.TestCase):
    def test_run_opentrons_script_to_zip_with_monkeypatched_subprocess(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)
            script_path = tmpdir_path / "run_plating.py"
            script_path.write_text("print('hello')\n", encoding="utf-8")

            json_path = tmpdir_path / "plating_input.json"
            json_path.write_text(json.dumps({"plating_data": {}}), encoding="utf-8")

            class ProcResult:
                stdout = b"simulated stdout"
                stderr = b"simulated stderr"
                returncode = 0

            with patch("buildcompiler.robotutils.subprocess.run", return_value=ProcResult()):
                zip_path = run_opentrons_script_to_zip(script_path, json_path, zip_name="sim.zip")

            self.assertTrue(zip_path.exists())

            with zipfile.ZipFile(zip_path, "r") as zf:
                names = set(zf.namelist())
                self.assertIn("run_plating.py", names)
                self.assertIn("plating_input.json", names)
                self.assertIn("simulate_stdout.txt", names)
                self.assertIn("simulate_stderr.txt", names)
                self.assertIn("simulate_returncode.txt", names)


if __name__ == "__main__":
    unittest.main()
