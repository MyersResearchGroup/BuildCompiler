import sbol2
import json
import csv
import shutil
import subprocess
import tempfile
import zipfile
from pathlib import Path
from typing import Any, Dict, List


def load_json_or_dict(value):
    """Load a JSON file path/string into a dict, or return dict-like input as-is."""
    if isinstance(value, dict):
        return value
    if isinstance(value, Path):
        return json.loads(value.read_text(encoding="utf-8"))
    if isinstance(value, str):
        path = Path(value)
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
        return json.loads(value)
    raise ValueError("Expected dict, JSON string, or JSON file path.")


def normalize_plating_input(transformation_results, doc=None):
    """Normalize transformation/plating inputs to a deterministic list of entries."""
    payload = load_json_or_dict(transformation_results)
    normalized = []

    if isinstance(payload, dict) and isinstance(payload.get("sbol_artifacts"), list):
        for idx, artifact in enumerate(payload["sbol_artifacts"], start=1):
            if not isinstance(artifact, dict):
                continue
            impl_uri = artifact.get("transformed_strain_implementation")
            module_uri = artifact.get("transformed_strain_module")
            if not impl_uri and not module_uri:
                continue
            normalized.append(
                {
                    "order": idx,
                    "well_hint": None,
                    "source_impl_uri": impl_uri,
                    "strain_module_uri": module_uri,
                }
            )
    elif isinstance(payload, dict) and isinstance(payload.get("strain_locations"), dict):
        for idx, well in enumerate(sorted(payload["strain_locations"]), start=1):
            impl_uri = payload["strain_locations"][well]
            normalized.append(
                {
                    "order": idx,
                    "well_hint": well,
                    "source_impl_uri": impl_uri,
                    "strain_module_uri": None,
                }
            )
    elif isinstance(payload, dict) and isinstance(
        payload.get("bacterium_locations"), dict
    ):
        for idx, well in enumerate(sorted(payload["bacterium_locations"]), start=1):
            impl_uri = payload["bacterium_locations"][well]
            normalized.append(
                {
                    "order": idx,
                    "well_hint": well,
                    "source_impl_uri": impl_uri,
                    "strain_module_uri": None,
                }
            )
    else:
        raise ValueError(
            "Unsupported plating input shape. Expected transformation output, "
            "strain_locations, or bacterium_locations."
        )

    if doc is not None:
        for item in normalized:
            if item["strain_module_uri"] is None and item["source_impl_uri"]:
                impl = doc.find(item["source_impl_uri"])
                if impl is not None and getattr(impl, "built", None):
                    item["strain_module_uri"] = impl.built

    if not normalized:
        raise ValueError("No transformed strains found in plating input.")

    return sorted(normalized, key=lambda x: x["order"])


def generate_96_well_positions(limit=96):
    wells = [f"{row}{column}" for row in "ABCDEFGH" for column in range(1, 13)]
    if limit < 0:
        raise ValueError("limit must be non-negative")
    return wells[:limit]


def write_plate_map_json(path, data):
    path = Path(path)
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    return path


def write_plate_map_csv(path, rows: List[Dict[str, Any]]):
    path = Path(path)
    fields = [
        "well",
        "source_transformed_strain_implementation",
        "strain_module",
        "plated_strain_implementation",
        "strain_display_name",
    ]
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow(
                {
                    "well": row.get("well"),
                    "source_transformed_strain_implementation": row.get(
                        "source_transformed_strain_implementation"
                    ),
                    "strain_module": row.get("strain_module"),
                    "plated_strain_implementation": row.get(
                        "plated_strain_implementation"
                    ),
                    "strain_display_name": row.get("strain_display_name"),
                }
            )
    return path


def write_manual_plating_protocol(path, plate_id, plate_rows, advanced_params):
    path = Path(path)
    params = advanced_params or {}
    table_lines = [
        "| Well | Source transformed strain implementation | Plated strain implementation | Strain module |",
        "|---|---|---|---|",
    ]
    for row in plate_rows:
        table_lines.append(
            f"| {row['well']} | {row.get('source_transformed_strain_implementation','')} "
            f"| {row.get('plated_strain_implementation','')} | {row.get('strain_module','')} |"
        )

    param_lines = "\n".join([f"- **{k}**: {v}" for k, v in sorted(params.items())]) or "- (none)"
    strain_lines = "\n".join(
        [
            f"- {row.get('strain_display_name', row.get('source_transformed_strain_implementation'))}"
            for row in plate_rows
        ]
    )
    content = (
        "# BuildCompiler Plating Protocol\n\n"
        f"## Plate\n- Plate ID: `{plate_id}`\n- Protocol type: `manual`\n\n"
        "## Input transformed strains\n"
        f"{strain_lines}\n\n"
        "## Parameters\n"
        f"{param_lines}\n\n"
        "## 96-well plate map\n"
        f"{chr(10).join(table_lines)}\n\n"
        "## Steps\n"
        "1. Prepare one sterile solid-media 96-well plate.\n"
        "2. Label the plate with the plate ID and date.\n"
        "3. Transfer each transformed strain to the destination well shown in the map.\n"
        "4. Incubate according to lab defaults or parameters above.\n"
    )
    path.write_text(content, encoding="utf-8")
    return path


def write_plating_protocol_script(path, plating_data, advanced_params):
    path = Path(path)
    script = (
        "from pudu.plating import Plating\n"
        "from opentrons import protocol_api\n\n"
        "metadata = {\n"
        '    "protocolName": "BuildCompiler Plating",\n'
        '    "author": "BuildCompiler",\n'
        '    "description": "Automated plating protocol generated from BuildCompiler transformation results",\n'
        '    "apiLevel": "2.21",\n'
        "}\n\n"
        f"PLATING_DATA = {json.dumps(plating_data, indent=4)}\n"
        f"ADVANCED_PARAMS = {json.dumps(advanced_params or {}, indent=4)}\n\n"
        "def run(protocol: protocol_api.ProtocolContext):\n"
        "    plating = Plating(\n"
        "        plating_data=PLATING_DATA,\n"
        "        json_params=ADVANCED_PARAMS,\n"
        "    )\n"
        "    plating.run(protocol)\n"
    )
    path.write_text(script, encoding="utf-8")
    return path


def run_opentrons_script_to_zip(
    opentrons_script_path,
    plating_json_path,
    zip_name=None,
    overwrite=False,
):
    script_path = Path(opentrons_script_path).resolve()
    json_path = Path(plating_json_path).resolve()
    if not script_path.exists():
        raise FileNotFoundError(f"Opentrons script not found: {script_path}")
    if not json_path.exists():
        raise FileNotFoundError(f"JSON file not found: {json_path}")

    out_zip = script_path.parent / (zip_name or f"{script_path.stem}_simulation.zip")
    if out_zip.exists() and not overwrite:
        stem = out_zip.stem
        suffix = out_zip.suffix
        i = 1
        while True:
            candidate = out_zip.parent / f"{stem}_{i}{suffix}"
            if not candidate.exists():
                out_zip = candidate
                break
            i += 1

    with tempfile.TemporaryDirectory() as tmpdirname:
        tmpdir = Path(tmpdirname)
        tmp_script = tmpdir / script_path.name
        tmp_json = tmpdir / json_path.name
        shutil.copy2(script_path, tmp_script)
        shutil.copy2(json_path, tmp_json)

        proc = subprocess.run(
            ["opentrons_simulate", str(tmp_script)],
            capture_output=True,
            text=True,
            cwd=tmpdir,
        )
        (tmpdir / "simulate_stdout.txt").write_text(
            proc.stdout or "", encoding="utf-8", errors="replace"
        )
        (tmpdir / "simulate_stderr.txt").write_text(
            proc.stderr or "", encoding="utf-8", errors="replace"
        )
        (tmpdir / "simulate_returncode.txt").write_text(
            str(proc.returncode), encoding="utf-8"
        )

        with zipfile.ZipFile(out_zip, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            for file_path in tmpdir.rglob("*"):
                if file_path.is_file():
                    zf.write(file_path, arcname=file_path.relative_to(tmpdir))

    return out_zip

def assembly_plan_RDF_to_JSON(file, output_path: str | Path | None = None):
    if isinstance(file, sbol2.Document):
        doc = file
    else:
        sbol2.Config.setOption('sbol_typed_uris', False)
        doc = sbol2.Document()
        doc.read(file)

    # Known SO roles
    PRODUCT_ROLE = 'http://identifiers.org/so/SO:0000804'
    BackBone_ROLE = 'http://identifiers.org/so/SO:0000755'
    ENZYME_ROLE = 'http://identifiers.org/obi/OBI:0000732'

    PARTS_ROLE_LIST = [
        'http://identifiers.org/so/SO:0000031', 'http://identifiers.org/so/SO:0000316',
        'http://identifiers.org/so/SO:0001977', 'http://identifiers.org/so/SO:0001956',
        'http://identifiers.org/so/SO:0000188', 'http://identifiers.org/so/SO:0000839',
        'http://identifiers.org/so/SO:0000167', 'http://identifiers.org/so/SO:0000139',
        'http://identifiers.org/so/SO:0001979', 'http://identifiers.org/so/SO:0001955',
        'http://identifiers.org/so/SO:0001546', 'http://identifiers.org/so/SO:0001263',
        'http://identifiers.org/SO:0000141', 'http://identifiers.org/so/SO:0000141'
    ]

    product_dicts = []
    globalEnzyme = None

    for cd in doc.componentDefinitions:
        print(f"\n🔍 Checking Component: {cd.displayId}")
        print(f"  Types: {cd.types}")
        print(f"  Roles: {cd.roles}")

        if ENZYME_ROLE in cd.roles:
            globalEnzyme = cd.identity
            print(f"✅ Found enzyme definition: {globalEnzyme}")

        if PRODUCT_ROLE in cd.roles:
            result = {
                'Product': cd.identity,
                'Backbone': None,
                'PartsList': [],
                'Restriction Enzyme': None
            }

            for comp in cd.components:
                sub_cd = doc.componentDefinitions.get(comp.definition)
                if sub_cd is None:
                    print(f"⚠️ Component definition for {comp.displayId} not found.")
                    continue

                print(f"  → Subcomponent: {sub_cd.displayId}")
                print(f"    Roles: {sub_cd.roles}")

                if BackBone_ROLE in sub_cd.roles:
                    result['Backbone'] = sub_cd.identity
                    print(f"    🧬 Assigned Backbone: {sub_cd.identity}")

                if any(role in PARTS_ROLE_LIST for role in sub_cd.roles):
                    result['PartsList'].append(sub_cd.identity)
                    print(f"    🧩 Added Part: {sub_cd.identity}")

            if not result['Backbone']:
                print(f"⚠️ No backbone found for product {cd.displayId}")
            if not result['PartsList']:
                print(f"⚠️ No parts found for product {cd.displayId}")

            product_dicts.append(result)

    for entry in product_dicts:
        entry['Restriction Enzyme'] = globalEnzyme

    json_output_path = Path(output_path) if output_path is not None else Path("output.json")
    with json_output_path.open('w', encoding='utf-8') as json_file:
        json.dump(product_dicts, json_file, indent=4)

    return product_dicts


def run_opentrons_script_with_json_to_zip(
    opentrons_script_path: str,
    json_file_path: str,
    zip_name: str | None = None,
    overwrite: bool = False,
) -> Path:
    """
    Runs `opentrons_simulate` on an Opentrons script + JSON, captures stdout/stderr,
    and writes a ZIP file *next to the original opentrons script*.

    Returns: Path to the created zip file.
    """
    script_path = Path(opentrons_script_path).resolve()
    json_path = Path(json_file_path).resolve()

    if not script_path.exists():
        raise FileNotFoundError(f"Opentrons script not found: {script_path}")
    if not json_path.exists():
        raise FileNotFoundError(f"JSON file not found: {json_path}")

    out_dir = script_path.parent
    base_name = zip_name or f"{script_path.stem}_opentrons_simulation.zip"
    out_zip = out_dir / base_name

    if out_zip.exists() and not overwrite:
        # avoid clobbering: foo.zip -> foo_1.zip -> foo_2.zip ...
        stem = out_zip.stem
        suffix = out_zip.suffix
        i = 1
        while True:
            candidate = out_dir / f"{stem}_{i}{suffix}"
            if not candidate.exists():
                out_zip = candidate
                break
            i += 1

    with tempfile.TemporaryDirectory() as tmpdirname:
        tmpdir = Path(tmpdirname)

        # Copy inputs into temp dir
        tmp_script = tmpdir / script_path.name
        tmp_json = tmpdir / json_path.name
        shutil.copy2(script_path, tmp_script)
        shutil.copy2(json_path, tmp_json)

        # Run inside temp dir so relative-path outputs land in tmpdir (and get zipped)

        # Run script (which has opentrons script hardcoded) using JSON file
        log = subprocess.run(
            ["opentrons_simulate", str(tmp_script), str(tmp_json)],
            capture_output=True,
            cwd=tmpdir,
        ).stdout
        
        # Save log to a file in the temporary directory
        with open(tmpdir / "build_log.txt", "wb") as log_file: 
            log_file.write(log)

        # Always include logs in the zip
        #(tmpdir / "simulate_stdout.txt").write_text(proc.stdout or "", encoding="utf-8", errors="replace")
        #(tmpdir / "simulate_stderr.txt").write_text(proc.stderr or "", encoding="utf-8", errors="replace")
        #(tmpdir / "simulate_returncode.txt").write_text(str(proc.returncode), encoding="utf-8")

        # Create the ZIP on disk next to the original script
        with zipfile.ZipFile(out_zip, "w", compression=zipfile.ZIP_DEFLATED) as z:
            for p in tmpdir.rglob("*"):
                if p.is_file():
                    z.write(p, arcname=p.relative_to(tmpdir))

    return out_zip
