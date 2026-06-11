from __future__ import annotations

import os
import sys


def _env_value(name: str) -> str | None:
    value = os.environ.get(name)
    if value is None:
        return None
    stripped = value.strip()
    return stripped or None


def _normalize_command_argv(
    argv: list[str] | None,
) -> tuple[list[str] | None, bool, bool]:
    raw_argv = list(sys.argv[1:] if argv is None else argv)
    if raw_argv and raw_argv[0] == "doctor":
        normalized = ["--doctor"]
        for item in raw_argv[1:]:
            if item == "--strict":
                normalized.append("--doctor-strict")
            else:
                normalized.append(item)
        return normalized, False, False
    if raw_argv and raw_argv[0] == "status":
        return ["--status", *raw_argv[1:]], False, False
    if raw_argv and raw_argv[0] == "next-step":
        return ["--next-step", *raw_argv[1:]], False, False
    if raw_argv and raw_argv[0] == "package-results":
        return ["--package-results", *raw_argv[1:]], False, True
    if raw_argv and raw_argv[0] == "verify-release-genus":
        if len(raw_argv) >= 2 and raw_argv[1] in {"-h", "--help"}:
            return ["--help"], False, False
        if len(raw_argv) < 2 or raw_argv[1].startswith("-"):
            raise ValueError("verify-release-genus requires a GENUS argument.")
        return ["--verify-release-genus", raw_argv[1], *raw_argv[2:]], False, False
    if not raw_argv or raw_argv[0] != "verify-genus":
        return argv, False, False
    if len(raw_argv) >= 2 and raw_argv[1] in {"-h", "--help"}:
        return ["--help"], False, False
    if len(raw_argv) < 2 or raw_argv[1].startswith("-"):
        raise ValueError("verify-genus requires a GENUS argument.")

    genus = raw_argv[1]
    normalized = ["--acquire-genus", genus, "--dry-run"]
    remaining = raw_argv[2:]
    index = 0
    while index < len(remaining):
        item = remaining[index]
        if item == "--policy":
            normalized.append("--selection-policy")
            if index + 1 >= len(remaining):
                raise ValueError(
                    "--policy requires one of: strict, balanced, review-only, "
                    "representative."
                )
            normalized.append(remaining[index + 1])
            index += 2
            continue
        if item.startswith("--policy="):
            normalized.append("--selection-policy=" + item.split("=", 1)[1])
            index += 1
            continue
        if item == "--enable-biosample-entrez":
            normalized.extend(["--enrich-biosample", item])
            index += 1
            continue
        normalized.append(item)
        index += 1
    return normalized, True, False
