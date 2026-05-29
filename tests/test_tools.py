import pytest

from typetreeflow.external import tools


def test_check_executable_true_when_found(monkeypatch):
    monkeypatch.setattr(tools.shutil, "which", lambda name: f"/bin/{name}")

    assert tools.check_executable("datasets") is True


def test_check_executable_false_when_missing(monkeypatch):
    monkeypatch.setattr(tools.shutil, "which", lambda name: None)

    assert tools.check_executable("datasets") is False


def test_require_executable_allows_found_tool(monkeypatch):
    monkeypatch.setattr(tools.shutil, "which", lambda name: f"/bin/{name}")

    tools.require_executable("datasets")


def test_require_executable_errors_for_missing_tool(monkeypatch):
    monkeypatch.setattr(tools.shutil, "which", lambda name: None)

    with pytest.raises(RuntimeError) as excinfo:
        tools.require_executable("datasets")

    message = str(excinfo.value)
    assert "Required executable not found on PATH: datasets" in message
    assert "NCBI Datasets CLI" in message
    assert "conda install -c conda-forge ncbi-datasets-cli" in message
    assert 'This is not the Python package named "datasets".' in message
