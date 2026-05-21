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

    with pytest.raises(RuntimeError, match="Required executable not found on PATH: datasets"):
        tools.require_executable("datasets")
