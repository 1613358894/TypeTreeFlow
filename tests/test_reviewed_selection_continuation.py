from pathlib import Path
from types import SimpleNamespace

import pytest

from typetreeflow.cli import (
    ReviewedSelectionResumeRequired,
    _format_verify_genus_envelope,
    parse_args,
)
from typetreeflow.workflow.reviewed_selection_continuation import (
    build_reviewed_selection_retry_argv,
    decide_reviewed_selection_continuation,
    is_reviewed_selection_surface,
    is_task_bound_reviewed_selection,
)
from typetreeflow.workflow.state import WorkflowState


def _paths(tmp_path: Path) -> SimpleNamespace:
    root = tmp_path / "run"
    return SimpleNamespace(
        manifest=root / "manifest.tsv",
        run_state_path=root / "run_state.json",
        user_selection_path=root / "selection" / "user_selection.tsv",
    )


@pytest.mark.parametrize(
    ("argv", "expected"),
    [
        (["verify-genus", "Fusobacterium"], True),
        (["--genus", "Fusobacterium", "--selection-policy", "review-only"], True),
        (["--genus", "Fusobacterium"], False),
    ],
)
def test_reviewed_selection_surface_characterization(argv, expected):
    assert is_reviewed_selection_surface(parse_args(argv)) is expected


def test_task_binding_requires_canonical_selection_outdir_and_same_genus(
    tmp_path, monkeypatch
):
    paths = _paths(tmp_path)
    canonical = paths.user_selection_path.resolve()
    config = parse_args(
        [
            "verify-genus",
            "Fusobacterium",
            "--outdir",
            str(paths.manifest.parent),
            "--selection-tsv",
            str(canonical),
        ]
    )
    state = WorkflowState(status="planned", outdir=str(paths.manifest.parent.resolve()))
    monkeypatch.setattr(
        "typetreeflow.workflow.reviewed_selection_continuation.read_run_state",
        lambda _path: state,
    )
    monkeypatch.setattr(
        "typetreeflow.workflow.reviewed_selection_continuation.selection_projection_task_genus",
        lambda _root, _paths: "fusobacterium",
    )

    assert is_task_bound_reviewed_selection(paths, config) is True
    assert is_task_bound_reviewed_selection(
        paths, parse_args(["verify-genus", "Clostridium", "--selection-tsv", str(canonical)])
    ) is False
    assert is_task_bound_reviewed_selection(
        paths,
        parse_args(
            [
                "verify-genus",
                "Fusobacterium",
                "--selection-tsv",
                str(tmp_path / "external.tsv"),
            ]
        ),
    ) is False


@pytest.mark.parametrize(
    "extra",
    [[], ["--dry-run"], ["--force"], ["--auto-accept-selection"]],
)
def test_missing_resume_decision_characterization(tmp_path, monkeypatch, extra):
    paths = _paths(tmp_path)
    argv = ["verify-genus", "Fusobacterium", "--selection-tsv", str(paths.user_selection_path), *extra]
    config = parse_args(argv)
    monkeypatch.setattr(
        "typetreeflow.workflow.reviewed_selection_continuation.is_task_bound_reviewed_selection",
        lambda _paths, _config: True,
    )

    decision = decide_reviewed_selection_continuation(paths, config, argv)
    assert decision.task_bound is True
    assert decision.resume_required is (not extra)


def test_trusted_legacy_resume_normalization_characterization(tmp_path, monkeypatch):
    paths = _paths(tmp_path)
    config = parse_args(
        [
            "--genus",
            "Fusobacterium",
            "--selection-policy",
            "review-only",
            "--selection-tsv",
            str(paths.user_selection_path),
            "--resume",
        ]
    )
    monkeypatch.setattr(
        "typetreeflow.workflow.reviewed_selection_continuation.is_task_bound_reviewed_selection",
        lambda _paths, _config: True,
    )

    decision = decide_reviewed_selection_continuation(paths, config, ["--resume"])
    normalized = decision.normalized_config

    assert normalized.verify_genus is True
    assert normalized.acquire_genus == "Fusobacterium"
    assert normalized.genus == "Fusobacterium"


@pytest.mark.parametrize("legacy", [False, True])
def test_reviewed_selection_retry_argv_exact_tuple(tmp_path, legacy):
    paths = _paths(tmp_path)
    base = ["--outdir", str(paths.manifest.parent)]
    config = (
        parse_args(["--genus", "Fusobacterium", "--selection-policy", "review-only", *base])
        if legacy
        else parse_args(["verify-genus", "Fusobacterium", *base])
    )
    expected = (
        (
            "typetreeflow",
            "--genus",
            "Fusobacterium",
            "--outdir",
            str(paths.manifest.parent.resolve()),
            "--resume",
            "--selection-tsv",
            str(paths.user_selection_path.resolve()),
            "--selection-policy",
            "review-only",
        )
        if legacy
        else (
            "typetreeflow",
            "verify-genus",
            "Fusobacterium",
            "--outdir",
            str(paths.manifest.parent.resolve()),
            "--resume",
            "--selection-tsv",
            str(paths.user_selection_path.resolve()),
        )
    )

    assert build_reviewed_selection_retry_argv(paths, config) == expected


@pytest.mark.parametrize(
    "argv",
    [
        ["verify-genus", "Fusobacterium"],
        ["--selection-tsv", "standalone.tsv"],
        ["--genus", "Fusobacterium", "--selection-policy", "review-only"],
    ],
)
def test_non_task_bound_decision_does_not_build_retry_argv(
    tmp_path, monkeypatch, argv
):
    paths = _paths(tmp_path)
    monkeypatch.setattr(
        "typetreeflow.workflow.reviewed_selection_continuation.is_task_bound_reviewed_selection",
        lambda _paths, _config: False,
    )
    monkeypatch.setattr(
        "typetreeflow.workflow.reviewed_selection_continuation.build_reviewed_selection_retry_argv",
        lambda _paths, _config: (_ for _ in ()).throw(AssertionError("unexpected")),
    )

    decision = decide_reviewed_selection_continuation(paths, parse_args(argv), argv)

    assert decision.task_bound is False
    assert decision.resume_required is False


@pytest.mark.parametrize("legacy", [False, True])
def test_resume_required_envelope_uses_retry_builder(tmp_path, legacy):
    paths = _paths(tmp_path)
    base = ["--outdir", str(paths.manifest.parent)]
    config = (
        parse_args(["--genus", "Fusobacterium", "--selection-policy", "review-only", *base])
        if legacy
        else parse_args(["verify-genus", "Fusobacterium", *base])
    )
    payload = __import__("json").loads(
        _format_verify_genus_envelope(
            config,
            paths,
            exit_code=2,
            error=ReviewedSelectionResumeRequired("resume required"),
        )
    )

    argv = payload["next_actions"][0]["argv"]
    assert argv[:2] == (["typetreeflow", "--genus"] if legacy else ["typetreeflow", "verify-genus"])
    assert "--resume" in argv
    assert "--enable-downloads" not in argv
    assert ("--selection-policy" in argv) is legacy
