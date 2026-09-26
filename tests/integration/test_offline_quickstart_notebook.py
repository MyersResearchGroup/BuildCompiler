from pathlib import Path

import pytest

nbformat = pytest.importorskip("nbformat")
nbclient = pytest.importorskip("nbclient")


@pytest.mark.notebook
def test_offline_quickstart_executes_with_explicit_outputs(monkeypatch, tmp_path):
    repo_root = Path(__file__).resolve().parents[2]
    notebook_path = repo_root / "notebooks" / "buildcompiler_offline_quickstart.ipynb"
    results_dir = tmp_path / "results"
    monkeypatch.setenv("BUILDCOMPILER_RESULTS_DIR", str(results_dir))
    monkeypatch.setenv("pydna_config_dir", str(tmp_path / "pydna-config"))
    monkeypatch.setenv("pydna_log_dir", str(tmp_path / "pydna-logs"))

    notebook = nbformat.read(notebook_path, as_version=4)
    nbclient.NotebookClient(
        notebook,
        timeout=600,
        kernel_name="python3",
        resources={"metadata": {"path": str(repo_root)}},
    ).execute()

    assert (results_dir / "offline_lvl1_products.xml").exists()
    assert (results_dir / "offline_lvl1_pudu_input.json").exists()
    assert (results_dir / "protocol_bundle" / "protocol_manifest.json").exists()
