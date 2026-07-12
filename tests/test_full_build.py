import json
import os
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import sbol2

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../src")))

from buildcompiler.buildcompiler import BuildCompiler
from buildcompiler.plasmid import Plasmid
from buildcompiler.constants import ENGINEERED_PLASMID


class TestFullBuild(unittest.TestCase):
    def setUp(self):
        self.doc = sbol2.Document()
        self.compiler = BuildCompiler(
            collections=[],
            sbh_registry="https://synbiohub.org",
            auth_token="",
            sbol_doc=self.doc,
        )

    def _make_part(self, display_id: str) -> sbol2.ComponentDefinition:
        part = sbol2.ComponentDefinition(display_id)
        self.doc.add(part)
        return part

    def _get_by_display_id(self, display_id: str):
        for obj in self.doc.componentDefinitions:
            if obj.displayId == display_id:
                return obj
        return None

    def _make_design(self, display_id: str, part_ids: list[str]) -> sbol2.ComponentDefinition:
        design = sbol2.ComponentDefinition(display_id)
        self.doc.add(design)
        created_components = []
        for index, part_id in enumerate(part_ids, start=1):
            part = self._get_by_display_id(part_id) or self._make_part(part_id)
            comp = design.components.create(f"{display_id}_c{index}")
            comp.definition = part.identity
            created_components.append(comp)
        for index in range(len(created_components) - 1):
            sc = design.sequenceConstraints.create(f"{display_id}_sc{index+1}")
            sc.subject = created_components[index].identity
            sc.object = created_components[index + 1].identity
            sc.restriction = sbol2.SBOL_RESTRICTION_PRECEDES
        return design

    def _make_plasmid(self, display_id: str) -> sbol2.ComponentDefinition:
        plasmid = sbol2.ComponentDefinition(display_id)
        plasmid.roles = [ENGINEERED_PLASMID]
        self.doc.add(plasmid)
        return plasmid

    def _make_lvl2_document(self) -> tuple[sbol2.Document, sbol2.ComponentDefinition]:
        doc = sbol2.Document()
        tu = sbol2.ComponentDefinition("example_tu")
        lvl2 = sbol2.ComponentDefinition("example_lvl2_design")
        doc.add(tu)
        doc.add(lvl2)
        comp = lvl2.components.create("tu_component")
        comp.definition = tu.identity
        return doc, tu

    def test_normalize_full_build_designs_input_shapes(self):
        d1 = self._make_design("design_a", ["part_a"])
        d2 = self._make_design("design_b", ["part_b"])

        self.assertEqual(self.compiler._normalize_full_build_designs(d1), [d1])
        self.assertEqual(self.compiler._normalize_full_build_designs([d1, d2]), [d1, d2])

        derivation = sbol2.CombinatorialDerivation("combo")
        self.doc.add(derivation)
        with patch.object(self.compiler, "_expand_combinatorial_derivation", return_value=[d1]) as mock_expand:
            normalized = self.compiler._normalize_full_build_designs(derivation)
            self.assertEqual(normalized, [d1])
            mock_expand.assert_called_once_with(derivation)

    def test_expand_combinatorial_derivation_creates_deterministic_variants(self):
        p1 = self._make_part("p1")
        p2 = self._make_part("p2")
        p3 = self._make_part("p3")

        template = self._make_design("master", ["p1", "p2"])
        derivation = sbol2.CombinatorialDerivation("combo_2")
        derivation.masterTemplate = template.identity

        with patch("buildcompiler.buildcompiler.get_or_pull", return_value=template), patch(
            "buildcompiler.buildcompiler.extract_combinatorial_design_parts", return_value={"a": [p1, p2], "b": [p3]}
        ), patch(
            "buildcompiler.buildcompiler.enumerate_design_variants",
            return_value=[[p1, p3], [p2, p3]],
        ):
            variants = self.compiler._expand_combinatorial_derivation(derivation, product_name_prefix="combo")

        self.assertEqual([v.displayId for v in variants], ["combo_variant_001", "combo_variant_002"])
        self.assertIsNotNone(self._get_by_display_id("combo_variant_001"))
        self.assertIsNotNone(self._get_by_display_id("combo_variant_002"))

    def test_find_missing_parts_reports_missing_and_present(self):
        design = self._make_design("design_missing", ["part_x", "part_y"])
        part_x = self._get_by_display_id("part_x")
        part_y = self._get_by_display_id("part_y")

        with patch.object(self.compiler, "_extract_design_parts", return_value=[part_x, part_y]), patch.object(
            self.compiler,
            "_construct_plasmid_dict",
            return_value={"part_x": [object()], "part_y": []},
        ), patch.object(self.compiler, "_get_backbone", return_value=(object(), [object()])):
            missing = self.compiler._find_missing_parts_for_lvl1(design)

        self.assertEqual(len(missing), 1)
        self.assertEqual(missing[0]["part"].displayId, "part_y")
        self.assertEqual(missing[0]["reason"], "no implemented plasmid")

    def test_run_domestication_indexes_products_before_retry(self):
        missing_part = self._make_part("missing_for_retry")
        domesticated = self._make_plasmid("domesticated_for_retry")

        with tempfile.TemporaryDirectory() as tmpdir, patch.object(
            self.compiler, "domestication", return_value=[domesticated]
        ), patch.object(
            self.compiler, "_sort_plasmid_components"
        ) as mock_sort, patch.object(
            self.compiler, "_run_transformation_and_plating"
        ):
            self.compiler._run_domestication(
                [missing_part],
                result={
                    "domestication": {"successful": [], "failed": []},
                    "transformation": {"successful": [], "failed": []},
                    "plating": {"successful": [], "failed": []},
                },
                assembly_payloads={},
                results_path=Path(tmpdir),
                chassis_name="E_coli_DH5alpha",
                plating_protocol_type="manual",
                plating_advanced_params=None,
                overwrite=True,
            )

        mock_sort.assert_called_once_with(domesticated, self.compiler.sbol_doc)

    def test_index_domestication_products_adds_plasmid_routes_once(self):
        domesticated = self._make_plasmid("domesticated_route_for_retry")
        route = object.__new__(Plasmid)
        route.plasmid_definition = domesticated

        self.compiler._index_domestication_products([route])
        self.compiler._index_domestication_products([route])

        self.assertEqual(self.compiler.indexed_plasmids, [route])

    def test_full_build_orchestration_and_stage_skip(self):
        design_a = self._make_design("dA", ["pa"])
        design_b = self._make_design("dB", ["pb"])
        missing_part = self._make_part("missing_part")
        domesticated = self._make_plasmid("domesticated_missing_part")
        assembled = self._make_plasmid("assembled_dA")

        with tempfile.TemporaryDirectory() as tmpdir, patch.object(
            self.compiler, "_normalize_full_build_designs", return_value=[design_a, design_b]
        ), patch.object(
            self.compiler,
            "_find_missing_parts_for_lvl1",
            side_effect=[
                [{"part": missing_part, "reason": "no implemented plasmid"}],
                [{"part": missing_part, "reason": "no implemented plasmid"}],
            ],
        ), patch.object(self.compiler, "domestication", return_value=[domesticated]) as mock_dom, patch.object(
            self.compiler, "transformation", return_value={"stage": "transformation", "sbol_artifacts": []}
        ) as mock_tx, patch.object(
            self.compiler, "plating", return_value={"stage": "plating"}
        ) as mock_plating, patch.object(
            self.compiler,
            "assembly_lvl1",
            side_effect=[[assembled], RuntimeError("assembly fail")],
        ) as mock_asm:
            result = self.compiler.full_build(designs=[design_a, design_b], results_dir=tmpdir, overwrite=True)

        mock_dom.assert_called_once()
        self.assertEqual(mock_asm.call_count, 2)
        self.assertGreaterEqual(mock_tx.call_count, 2)
        self.assertGreaterEqual(mock_plating.call_count, 2)
        self.assertEqual(result["skipped"][0]["stage"], "assembly_lvl2")
        self.assertEqual(len(result["assembly_lvl1"]["successful"]), 1)
        self.assertEqual(len(result["assembly_lvl1"]["failed"]), 1)

    def test_full_build_writes_manifest_and_zip_and_return_shape(self):
        design = self._make_design("d_main", ["p_main"])
        assembled = self._make_plasmid("assembled_main")

        with tempfile.TemporaryDirectory() as tmpdir, patch.object(
            self.compiler, "_find_missing_parts_for_lvl1", return_value=[]
        ), patch.object(
            self.compiler, "assembly_lvl1", return_value=[assembled]
        ), patch.object(
            self.compiler, "transformation", return_value={"stage": "transformation", "sbol_artifacts": []}
        ), patch.object(
            self.compiler, "plating", return_value={"stage": "plating"}
        ):
            result = self.compiler.full_build(designs=[design], results_dir=Path(tmpdir) / "run", overwrite=True)

            manifest_path = Path(result["manifest_path"])
            zip_path = Path(result["zip_path"])

            self.assertTrue(manifest_path.exists())
            self.assertTrue(zip_path.exists())
            self.assertIn("domestication", result)
            self.assertIn("assembly_lvl1", result)
            self.assertIn("transformation", result)
            self.assertIn("plating", result)
            self.assertIn("skipped", result)

            with zipfile.ZipFile(zip_path, "r") as archive:
                names = archive.namelist()
                self.assertIn("full_build_manifest.json", names)

    def test_full_build_pudu_transformation_pairs_each_strain_with_own_product(self):
        result = {
            "transformation": {
                "successful": [
                    {
                        "stage_label": "assembly_lvl1",
                        "products": ["plasmid_a", "plasmid_b"],
                        "result": {
                            "chassis": "E_coli_DH5alpha",
                            "sbol_artifacts": [
                                {"transformed_strain_module": "strain_a"},
                                {"transformed_strain_module": "strain_b"},
                            ],
                        },
                    }
                ]
            },
            "plating": {"successful": []},
        }

        with tempfile.TemporaryDirectory() as tmpdir:
            self.compiler._write_full_build_artifacts(
                result=result,
                assembly_payloads={},
                results_path=Path(tmpdir),
            )
            payload = json.loads(
                (Path(tmpdir) / "transformation_pudu_input.json").read_text(
                    encoding="utf-8"
                )
            )

        self.assertEqual(
            payload,
            [
                {
                    "Strain": "strain_a",
                    "Chassis": "E_coli_DH5alpha",
                    "Plasmids": ["plasmid_a"],
                },
                {
                    "Strain": "strain_b",
                    "Chassis": "E_coli_DH5alpha",
                    "Plasmids": ["plasmid_b"],
                },
            ],
        )

    def test_full_build_lvl2_example_packages_pudu_protocols_for_recovery_stack(self):
        lvl2_doc, _ = self._make_lvl2_document()
        missing_part = self._make_part("missing_promoter")
        domesticated = self._make_plasmid("domesticated_missing_promoter")
        lvl1_product = self._make_plasmid("assembled_example_tu")
        lvl2_product = self._make_plasmid("assembled_example_lvl2")
        calls = []

        def fake_assembly_lvl2(*args, **kwargs):
            calls.append("assembly_lvl2")
            if calls.count("assembly_lvl2") == 1:
                raise RuntimeError("level-2 input is missing level-1 regions")
            self.compiler.last_assembly_pudu_json_by_stage = {
                "assembly_lvl2": [
                    {
                        "Product": lvl2_product.identity,
                        "Backbone": "lvl2_backbone",
                        "PartsList": [lvl1_product.identity],
                        "Restriction Enzyme": "BbsI",
                    }
                ]
            }
            return [lvl2_product], self.doc

        def fake_assembly_lvl1(*args, **kwargs):
            calls.append("assembly_lvl1")
            if calls.count("assembly_lvl1") == 1:
                raise RuntimeError("level-1 input is missing domesticated part")
            self.compiler.last_assembly_pudu_json_by_stage = {
                "assembly_lvl1": [
                    {
                        "Product": lvl1_product.identity,
                        "Backbone": "lvl1_backbone",
                        "PartsList": [domesticated.identity],
                        "Restriction Enzyme": "BsaI",
                    }
                ]
            }
            return [lvl1_product], self.doc

        def fake_domestication(parts):
            calls.append("domestication")
            self.compiler.last_assembly_pudu_json_by_stage = {
                "domestication": [
                    {
                        "Product": domesticated.identity,
                        "Backbone": "domestication_backbone",
                        "PartsList": [missing_part.identity],
                        "Restriction Enzyme": "BsaI",
                    }
                ]
            }
            return [domesticated]

        def fake_transformation(
            products, chassis_name="E_coli_DH5alpha", transformation_doc=None
        ):
            calls.append("transformation")
            product_id = products[0].identity
            return {
                "stage": "transformation",
                "chassis": chassis_name,
                "sbol_artifacts": [
                    {
                        "transformed_strain_module": f"{product_id}_strain",
                        "transformed_strain_implementation": f"{product_id}_strain_impl",
                    }
                ],
            }

        def fake_plating(*args, **kwargs):
            calls.append("plating")
            return {
                "stage": "plating",
                "json_intermediate": {
                    "plating_data": {
                        "bacterium_locations": {"A1": "example_transformed_strain"}
                    }
                },
            }

        with tempfile.TemporaryDirectory() as tmpdir, patch.object(
            self.compiler, "assembly_lvl2", side_effect=fake_assembly_lvl2
        ), patch.object(
            self.compiler, "assembly_lvl1", side_effect=fake_assembly_lvl1
        ), patch.object(
            self.compiler,
            "_find_missing_parts_for_lvl1",
            return_value=[{"part": missing_part}],
        ), patch.object(
            self.compiler, "domestication", side_effect=fake_domestication
        ), patch.object(
            self.compiler, "transformation", side_effect=fake_transformation
        ), patch.object(
            self.compiler, "plating", side_effect=fake_plating
        ):
            result = self.compiler.full_build(
                designs=lvl2_doc,
                results_dir=Path(tmpdir) / "lvl2_full_build",
                overwrite=True,
            )
            zip_path = Path(result["zip_path"])
            self.assertTrue(zip_path.exists())
            with zipfile.ZipFile(zip_path, "r") as archive:
                names = set(archive.namelist())

        self.assertEqual(
            calls[:3], ["assembly_lvl2", "assembly_lvl1", "domestication"]
        )
        self.assertEqual(result["artifact_zip"], result["zip_path"])

        expected_artifacts = {
            "assembly_lvl1_pudu_assembly_input.json",
            "assembly_lvl2_pudu_assembly_input.json",
            "domestication_pudu_assembly_input.json",
            "assembly_lvl1_pudu_assembly_protocol.py",
            "assembly_lvl2_pudu_assembly_protocol.py",
            "domestication_pudu_assembly_protocol.py",
            "transformation_pudu_input.json",
            "transformation_plasmid_locations.json",
            "pudu_transformation_protocol.py",
            "plating_pudu_input.json",
            "pudu_plating_protocol.py",
            "full_build_manifest.json",
        }
        self.assertTrue(expected_artifacts.issubset(names))


if __name__ == "__main__":
    unittest.main()
