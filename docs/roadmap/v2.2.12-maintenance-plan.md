# TypeTreeFlow v2.2.12 Maintenance Plan

v2.2.12 is a maintenance-only release. Its purpose is to freeze a narrow
release/docs cleanup scope without changing runtime behavior, selection
decisions, evidence interpretation, provider automation, or download strategy.

## Release Goal

v2.2.12 is a maintenance-only release for release consistency, checklist
hardening, and handoff/reporting documentation clarity.

## Allowed Changes

- Release/docs consistency cleanup.
- Release checklist hardening.
- Handoff/reporting docs clarification.
- Small tests for documentation/metadata consistency.

## Forbidden Changes

- No download behavior changes.
- No selection safety changes.
- No evidence threshold changes.
- No provider/ATCC automation.
- No real Clostridium/Microbacterium download runs.
- No large results artifacts.

## Validation Commands

```powershell
python -m pytest -p no:cacheprovider --basetemp .tmp_pytest_v2_2_12_docs tests/test_docs_consistency.py
```

## Stop Conditions

- Any runtime behavior change appears necessary.
- Any release scope item would require real downloads.
- Tests require broad unrelated rewrites.

## Stage 3 Current Version Reference Audit

Stage 3 records the current v2.2.11/version-reference surface before any
v2.2.12 cleanup. Do not delete, rewrite, bump, tag, push, or run live
downloads in this stage.

### Required release metadata/version checks

These references must remain explicit because they are release metadata,
package metadata, changelog anchors, or tests that verify the active release
state:

- `pyproject.toml:7` keeps the package version as `2.2.11`.
- `typetreeflow/__init__.py:3` keeps `__version__` as `2.2.11`.
- `CITATION.cff:4` keeps citation metadata version `2.2.11`.
- `CHANGELOG.md:3` and `CHANGELOG.md:5` define the active v2.2.11 changelog
  section and maintenance/refactor-only release note.
- `tests/test_docs_consistency.py:84` asserts the current version is
  `2.2.11`.

### Current user-facing release docs

These references are expected to remain visible to operators for the current
release until the actual version bump/release-doc update stage:

- `README.md:16` describes the current 2.2.11 release as maintenance/refactor
  only.
- `README.md:98` points users at release-verification behavior, v2.2.11
  maintenance notes, and reliability reporting.
- `README.md:222` starts the current `Recommended v2.2.11 workflow` section.
- `docs/release_verification.md:6`, `docs/release_verification.md:8`, and
  `docs/release_verification.md:14` document v2.2.11 maintenance notes and
  expected metadata checks.
- `docs/release_notes_v2_2_x.md:3`, `docs/release_notes_v2_2_x.md:69`, and
  `docs/release_notes_v2_2_x.md:81` summarize the v2.2.2 through v2.2.11
  release-notes context and v2.2.11 maintenance scope.

### Candidates for deduplication in later stage

These are user-facing repeats of the same "current recommended workflow/route"
message. They should be considered for later deduplication or cross-linking,
but should not be rewritten in Stage 3:

- `docs/index.md:147` repeats `Recommended v2.2.11 Route`.
- `docs/index.md:149` redirects to README's `Recommended v2.2.11 workflow`.
- `docs/index.md:153` repeats the v2.2.11 maintenance release focus.
- `docs/cookbook.md:133` repeats v2.2.11 reliability-check guidance.
- `docs/cookbook.md:138` points again to `release_verification.md` and
  `release_notes_v2_2_x.md` for v2.2.11 handoff/reporting expectations.
- Repeated "Recommended v2.2.11 workflow/route" wording currently appears in
  both `README.md` and `docs/index.md`; later cleanup can keep README as the
  canonical workflow and make secondary docs shorter links.

### Historical references to leave unchanged

Older release history should remain unchanged unless a later release-specific
cleanup explicitly targets it:

- Older changelog sections should preserve their original version references.
- Older release notes should preserve their original version references.
- v2.2.9 and v2.2.10 history should remain intact because those entries
  describe prior behavior and release progression.

## Stage 4 Current Version Deduplication

Stage 4 reduces current-version wording that was duplicated outside the
canonical release surfaces. It keeps release metadata, README's current release
and recommended workflow, and `docs/release_verification.md` as the explicit
current-release anchors.

### Deduplicated surfaces

- `docs/index.md` now uses the version-neutral `Recommended Route` heading and
  points to README's recommended workflow instead of repeating the active
  version in the route title and body.
- `docs/cookbook.md` now uses
  `results/v2_2_x_release_verification` for the release-verification example
  outdir and describes the command as current v2.2.x reliability checks.
- The cookbook still points to `release_verification.md` and
  `release_notes_v2_2_x.md` for current maintenance scope, keeping release
  wording centralized.

### Explicit references retained

- `README.md` remains the canonical operator-facing current release and
  recommended workflow surface.
- `docs/release_verification.md` remains the current release-verification
  notes surface.
- `CHANGELOG.md`, `CITATION.cff`, `pyproject.toml`,
  `typetreeflow/__init__.py`, and `tests/test_docs_consistency.py` retain
  explicit version checks and release metadata references.
- Historical v2.2.9, v2.2.10, and v2.2.11 facts remain unchanged where they
  describe prior release history rather than the current recommended path.

## Stage 5 Release Consistency Checker

Stage 5 adds `scripts/check_release_consistency.py` as a pre-release
consistency checker. The checker reads release metadata and documentation,
runs local version commands, and exits non-zero when the repository's current
release references disagree.

### Checker scope

- Read `pyproject.toml` for `project.version`.
- Compare `typetreeflow.__version__` with the pyproject version.
- Check `CITATION.cff`, `CHANGELOG.md`, `README.md`,
  `docs/release_verification.md`, and `docs/release_notes_v2_2_x.md` for the
  expected current-version anchors.
- Check `python typetreeflow.py --version` output.

### Checker boundaries

- The checker does not modify files.
- The checker does not bump versions, create tags, commit, push, or run
  downloads.
- The checker does not require the installed `typetreeflow` console script,
  because that depends on the active environment's installation state.

## Stage 6 Handoff Index Documentation

Stage 6 documents generated `handoff_index.md` files as package navigation and
operator handoff artifacts for `package-results`.

### Documented contract

- Successful delivery packages and `package-results --failed-handoff` review
  packages can both write `handoff_index.md`.
- `handoff_index.md` is not a new scientific decision source and does not
  replace `manifest.tsv`, `report/summary.md`, or `report/run_review.md`.
- Scientific, audit, and completion interpretation remains with the manifest,
  report, source-audit, and completion artifacts.
- `Recommended Next Step` is operator guidance for review or recovery, not an
  automatically executed plan.

### Boundaries retained

- No runtime code changed.
- No `package-results` behavior changed.
- No version bump, tag, commit, push, or live download run is part of this
  stage.

## Stage 7 Release Checklist Hardening

Stage 7 strengthens the release checklist so later maintenance releases have
explicit local validation, packaging smoke, cleanup, and post-release closure
gates.

### Checklist gates

- Run `python scripts/check_release_consistency.py` before release artifact
  publication.
- Use a repo-local pytest base temp directory such as
  `.tmp_pytest_vX_Y_Z`.
- Run the full suite with
  `python -m pytest -p no:cacheprovider --basetemp .tmp_pytest_vX_Y_Z`.
- Build the wheel with `python -m pip wheel . --no-deps -w dist`.
- Install the built wheel in a temporary repo-local virtual environment and
  smoke `typetreeflow --version`, `typetreeflow doctor`, and
  `typetreeflow --help`.
- Clean the repo-local pytest temp directory and smoke virtual environment.
- Keep or remove `dist/*.whl` intentionally as release artifact evidence; do
  not commit wheel artifacts for documentation-only maintenance work.
- Confirm no real downloads were run unless the explicit release scope
  requires live guarded validation.
- Confirm large `results/` trees and other generated run output are not
  committed.
- Confirm tag, release PR, required CI, merge commit, GitHub Release,
  release-branch cleanup, local `main` sync, tag reachability from `main`, and
  post-release `git status` checks.

### Boundaries retained

- No runtime code changed.
- No version bump, tag, commit, push, or live download run is part of this
  stage.
