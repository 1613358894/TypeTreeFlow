from __future__ import annotations

import json

import pytest

from typetreeflow.cli_recognizer import recognize_cli_command


@pytest.mark.parametrize(
    ("argv", "expected"),
    [
        (
            ["doctor"],
            {
                "command": "doctor",
                "subcommand": None,
                "mode": "diagnostic",
                "is_report_only": False,
                "is_manual_review": False,
                "is_strict_gating": False,
                "writes_outputs_declared": False,
                "requires_outdir": False,
                "unknown": False,
                "invalid": False,
            },
        ),
        (["verify-genus", "Fusobacterium"], {"command": "verify-genus", "mode": "workflow", "writes_outputs_declared": True, "requires_outdir": True}),
        (["status"], {"command": "status", "mode": "diagnostic", "writes_outputs_declared": False, "requires_outdir": True}),
        (["next-step"], {"command": "next-step", "mode": "diagnostic", "writes_outputs_declared": False, "requires_outdir": True}),
        (["package-results"], {"command": "package-results", "mode": "packaging", "writes_outputs_declared": True, "requires_outdir": True}),
        (["--doctor"], {"command": "doctor", "mode": "diagnostic", "writes_outputs_declared": False, "requires_outdir": False}),
        (["--status"], {"command": "status", "mode": "diagnostic", "writes_outputs_declared": False, "requires_outdir": True}),
        (["--next-step"], {"command": "next-step", "mode": "diagnostic", "writes_outputs_declared": False, "requires_outdir": True}),
        (["--package-results"], {"command": "package-results", "mode": "packaging", "writes_outputs_declared": True, "requires_outdir": True}),
        (["--verify-release-genus", "Fusobacterium"], {"command": "verify-release-genus", "mode": "workflow", "writes_outputs_declared": True, "requires_outdir": True}),
        (["manual-review", "validate", "--input", "review.tsv"], {"command": "manual-review", "subcommand": "validate", "mode": "manual_review", "is_manual_review": True, "writes_outputs_declared": False, "requires_outdir": False}),
        (["manual-review", "import", "--input", "review.tsv", "--reconciler-audit", "audit.tsv", "--write", "--outdir", "isolated"], {"command": "manual-review", "subcommand": "import", "mode": "manual_review", "is_manual_review": True, "writes_outputs_declared": True, "requires_outdir": True}),
        (["strict-gating", "evaluate", "--manual-review-dir", "review", "--reconciler-audit", "audit.tsv"], {"command": "strict-gating", "subcommand": "evaluate", "mode": "strict_gating", "is_strict_gating": True, "writes_outputs_declared": False, "requires_outdir": False}),
        (["verify-genus", "Fusobacterium", "--resume", "--report-only"], {"command": "verify-genus", "mode": "report_only", "is_report_only": True, "writes_outputs_declared": True, "requires_outdir": True}),
        (["--report-only", "--outdir", "existing-run"], {"command": "workflow", "mode": "report_only", "is_report_only": True, "writes_outputs_declared": True, "requires_outdir": True}),
    ],
)
def test_recognizes_documented_cli_surfaces(argv, expected):
    before = list(argv)

    result = recognize_cli_command(argv)

    assert argv == before
    assert result == {**result, **expected}
    json.dumps(result)


def test_strict_gating_precedes_manual_review_tokens_like_main_dispatch():
    # main() checks the first top-level token and dispatches strict-gating first;
    # later command-like values are left to that isolated parser to reject.
    result = recognize_cli_command(
        ["strict-gating", "evaluate", "--outdir", "manual-review"]
    )

    assert result["command"] == "strict-gating"
    assert result["is_strict_gating"] is True
    assert result["is_manual_review"] is False


@pytest.mark.parametrize(
    ("argv", "expected"),
    [
        (
            ["doctor", "--report-only"],
            {"command": "doctor", "mode": "diagnostic", "writes_outputs_declared": False, "requires_outdir": False},
        ),
        (
            ["status", "--report-only"],
            {"command": "status", "mode": "diagnostic", "writes_outputs_declared": False, "requires_outdir": True},
        ),
        (
            ["next-step", "--report-only"],
            {"command": "next-step", "mode": "diagnostic", "writes_outputs_declared": False, "requires_outdir": True},
        ),
        (
            ["package-results", "--report-only"],
            {"command": "package-results", "mode": "packaging", "writes_outputs_declared": True, "requires_outdir": True},
        ),
        (
            ["verify-release-genus", "Fusobacterium", "--report-only"],
            {"command": "verify-release-genus", "mode": "workflow", "writes_outputs_declared": True, "requires_outdir": True},
        ),
        (
            ["--doctor", "--report-only"],
            {"command": "doctor", "mode": "diagnostic", "writes_outputs_declared": False, "requires_outdir": False},
        ),
        (
            ["--status", "--report-only"],
            {"command": "status", "mode": "diagnostic", "writes_outputs_declared": False, "requires_outdir": True},
        ),
        (
            ["--next-step", "--report-only"],
            {"command": "next-step", "mode": "diagnostic", "writes_outputs_declared": False, "requires_outdir": True},
        ),
        (
            ["--package-results", "--report-only"],
            {"command": "package-results", "mode": "packaging", "writes_outputs_declared": True, "requires_outdir": True},
        ),
        (
            ["--verify-release-genus", "Fusobacterium", "--report-only"],
            {"command": "verify-release-genus", "mode": "workflow", "writes_outputs_declared": True, "requires_outdir": True},
        ),
    ],
)
def test_report_only_flag_does_not_override_higher_priority_dispatch(argv, expected):
    result = recognize_cli_command(argv)

    assert result["is_report_only"] is True
    assert result == {**result, **expected}


@pytest.mark.parametrize(
    ("argv", "unknown"),
    [
        (["manual-review"], False),
        (["manual-review", "publish"], True),
        (["strict-gating"], False),
        (["unrecognized-command"], True),
        (["verify-genus", "--report-only"], False),
    ],
)
def test_marks_only_structurally_obvious_invalid_or_unknown_commands(argv, unknown):
    result = recognize_cli_command(argv)

    assert result["invalid"] is True
    assert result["unknown"] is unknown
