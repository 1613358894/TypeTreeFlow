# Results Policy

This page is the canonical policy for repository-root `results/` paths.

## Rule

`results/` is not a run output directory and is not retained in the source
repository.

Do not commit repository-root `results/` content. Historical release
verification matrices and run evidence belong in an external workspace or, when
only durable rules remain useful, in the current release documentation. The
source tree should not keep old result files as evidence snapshots.

## Where Outputs Should Go

Large runs, real analyses, release-validation runs, local downloaded data,
delivery packages, verification matrices, and operator scratch work should live
outside the repository under a workspace. See
[workspace_policy.md](workspace_policy.md) for workspace layout.

## Hygiene Checker Relationship

`scripts/check_workspace_hygiene.py` enforces the current repository-root
hygiene boundary. For `results/`, any repository-root path is reported as
forbidden.

The script is a reporting check: it does not delete, move, or modify files.
If a future release needs durable verification evidence, keep the run output in
an external workspace and extract only current rules or gate instructions into
the release docs.

Do not work around the checker by writing new run trees under `results/`.
