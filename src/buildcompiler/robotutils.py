import sbol2
import json
import os
import shutil
import subprocess
import tempfile
import zipfile
from pathlib import Path

def assembly_plan_RDF_to_JSON(file):
    if type(file)==sbol2.Document:
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

    with open('output.json', 'w') as json_file:
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
        log = subprocess.run(["opentrons_simulate", opentrons_script_path, json_file_path], capture_output=True).stdout
        
        # Save log to a file in the temporary directory
        with open(os.path.join(tmpdir, "build_log.txt"), "wb") as log_file: 
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