import sys
import sbol2
import json
import shutil
import subprocess
import tempfile
import zipfile
import re
from pathlib import Path

def assembly_plan_RDF_to_JSON(file, output_path: str | Path | None = None):
    if isinstance(file, sbol2.Document):
        doc = file
    else:
        sbol2.Config.setOption('sbol_typed_uris', False)
        doc = sbol2.Document()
        doc.read(file)

    restriction_enzyme_name = "BsaI"    

    # Known SBOL types
    PRODUCT_TYPE = 'http://identifiers.org/so/SO:0000988'
    # Known SO roles
    PRODUCT_ROLE = 'http://identifiers.org/so/SO:0000804'
    BackBone_ROLE = 'http://identifiers.org/so/SO:0000755'
    ENZYME_ROLE = 'http://identifiers.org/obi/OBI_0000732'

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

        if ENZYME_ROLE in cd.roles and restriction_enzyme_name in cd.displayId:
            globalEnzyme = cd.identity
            print(f"✅ Found enzyme definition: {globalEnzyme}")

        if PRODUCT_ROLE in cd.roles and PRODUCT_TYPE in cd.types:
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



# TODO: this is not returning the markdown generated by runing generate_manual_assembly_protocol.py, it should run a subprocess to run the script and capture the markdown in the zip file.

def run_manual_script_with_json_to_zip(
    manual_script_path: str,
    json_file_path: str,
    zip_name: str | None = None,
    overwrite: bool = False,
) -> Path:
    """
    Runs `opentrons_simulate` on an Opentrons script + JSON, captures stdout/stderr,
    and writes a ZIP file *next to the original opentrons script*.

    Returns: Path to the created zip file.
    """
    script_path = Path(manual_script_path).resolve()
    json_path = Path(json_file_path).resolve()

    if not script_path.exists():
        raise FileNotFoundError(f"Manual script not found: {script_path}")
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
        manual_protocol_script = Path(__file__).resolve().parents[2] / "notebooks" / "generate_manual_assembly_protocol.py"


        # Copy inputs into temp dir
        tmp_script = tmpdir / script_path.name
        tmp_json = tmpdir / json_path.name
        shutil.copy2(script_path, tmp_script)
        shutil.copy2(json_path, tmp_json)

        # Run inside temp dir so relative-path outputs land in tmpdir (and get zipped)

        # Run script (which has opentrons script hardcoded) using JSON file
        log = subprocess.run(
            ["python", str(tmp_script), str(tmp_json)],
            capture_output=True,
            cwd=tmpdir,
        ).stdout
        
        # Save log to a file in the temporary directory
        with open(tmpdir / "build_log.md", "wb") as log_file: 
            log_file.write(log)
            
        manual_protocol_path = tmpdir / "manual_assembly_protocol.md"
        subprocess.run(
            [
                sys.executable,
                str(manual_protocol_script),
                "--input",
                str(tmp_json),
                "--output",
                str(manual_protocol_path),
            ],
            capture_output=True,
            cwd=tmpdir,
            check=True,
        )


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


def load_json_or_dict(value):
    """Load JSON input from a dictionary, JSON string, or JSON file path."""
    if isinstance(value, dict):
        return value

    if isinstance(value, Path):
        candidate = value
    elif isinstance(value, str):
        candidate = Path(value)
    else:
        raise ValueError("Expected a dict, JSON string, or path to a JSON file.")

    if candidate.exists():
        with candidate.open("r", encoding="utf-8") as infile:
            return json.load(infile)

    try:
        return json.loads(str(value))
    except json.JSONDecodeError as exc:
        raise ValueError(
            "Could not parse input as JSON string or JSON file path."
        ) from exc


def normalize_plating_data(transformation_results):
    """Normalize transformation results to {'bacterium_locations': {...}}."""
    data = load_json_or_dict(transformation_results)
    if not isinstance(data, dict):
        raise ValueError("Transformation results must be a JSON object.")

    key_aliases = (
        "bacterium_locations",
        "strain_locations",
        "thermocycler_wells",
    )
    for key in key_aliases:
        if key in data:
            well_mapping = data[key]
            if not isinstance(well_mapping, dict) or not well_mapping:
                raise ValueError(f"'{key}' must be a non-empty object.")
            return {"bacterium_locations": well_mapping}

    well_pattern = re.compile(r"^[A-H](?:[1-9]|1[0-2])$")
    if data and all(well_pattern.match(str(k)) for k in data.keys()):
        return {"bacterium_locations": data}

    raise ValueError(
        "Unsupported transformation results format. Expected one of: "
        "{'bacterium_locations': {...}}, {'strain_locations': {...}}, "
        "{'thermocycler_wells': {...}}, or a raw well mapping like {'A1': 'strain_1'}."
    )


def write_plating_protocol_script(output_path, plating_data, advanced_params):
    """Write a self-contained PUDU plating runner script."""
    script_path = Path(output_path)
    script_text = (
        "from pudu.plating import Plating\n\n"
        f"PLATING_DATA = {json.dumps(plating_data, indent=4)}\n\n"
        f"ADVANCED_PARAMS = {json.dumps(advanced_params, indent=4)}\n\n"
        "if __name__ == '__main__':\n"
        "    protocol = Plating(plating_data=PLATING_DATA, json_params=ADVANCED_PARAMS)\n"
        "    protocol.run()\n"
    )
    script_path.write_text(script_text, encoding="utf-8")
    return script_path


def run_opentrons_script_to_zip(
    opentrons_script_path: str | Path,
    plating_json_path: str | Path,
    zip_name: str | None = None,
    overwrite: bool = False,
) -> Path:
    """Run opentrons_simulate and zip protocol artifacts and logs."""
    script_path = Path(opentrons_script_path).resolve()
    json_path = Path(plating_json_path).resolve()

    if not script_path.exists():
        raise FileNotFoundError(f"Opentrons script not found: {script_path}")
    if not json_path.exists():
        raise FileNotFoundError(f"JSON file not found: {json_path}")

    out_dir = script_path.parent
    base_name = zip_name or f"{script_path.stem}_opentrons_simulation.zip"
    out_zip = out_dir / base_name

    if out_zip.exists() and not overwrite:
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
        tmp_script = tmpdir / script_path.name
        tmp_json = tmpdir / json_path.name
        shutil.copy2(script_path, tmp_script)
        shutil.copy2(json_path, tmp_json)

        proc = subprocess.run(
            ["opentrons_simulate", str(tmp_script)],
            capture_output=True,
            cwd=tmpdir,
        )

        (tmpdir / "simulate_stdout.txt").write_text(
            (proc.stdout or b"").decode("utf-8", errors="replace"), encoding="utf-8"
        )
        (tmpdir / "simulate_stderr.txt").write_text(
            (proc.stderr or b"").decode("utf-8", errors="replace"), encoding="utf-8"
        )
        (tmpdir / "simulate_returncode.txt").write_text(
            str(proc.returncode), encoding="utf-8"
        )

        with zipfile.ZipFile(out_zip, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            for p in tmpdir.rglob("*"):
                if p.is_file():
                    zf.write(p, arcname=p.relative_to(tmpdir))

    return out_zip
