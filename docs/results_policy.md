# Results Policy

This page is the canonical policy for the repository `results/` directory.

## Rule

`results/` is not a run output directory.

The repository `results/` directory is reserved for small, selected,
trackable verification evidence that is intentionally kept with the source
tree. It must not be used for ordinary runs, real analyses, guarded downloads,
delivery packages, scratch output, local caches, or large generated artifacts.

Current allowed repository evidence:

```text
results/v2_2_0_release_verification/verification_matrix.tsv
```

That TSV is retained as compact release-verification evidence. The historical
run directories that originally surrounded it are not part of the current
allowlist.

## Where Outputs Should Go

Large runs, real analyses, release-validation runs, local downloaded data,
delivery packages, and operator scratch work should live outside the
repository under a workspace. See [workspace_policy.md](workspace_policy.md).

Recommended locations:

- Runs: `<workspace>/runs/<run-name>`
- Release verification runs: `<workspace>/runs/release/<run-name>`
- Delivery packages: `<workspace>/deliveries/<delivery-name>`
- Local data and caches: `<workspace>/data/<name>`
- Reviewed manifest snapshots: `<workspace>/manifests/<name>`

## Hygiene Checker Relationship

`scripts/check_workspace_hygiene.py` enforces the current repository-root
hygiene boundary. For `results/`, it currently allows only:

```text
results/v2_2_0_release_verification/verification_matrix.tsv
```

The script is a reporting check: it does not delete, move, or modify files.
If a future release needs to keep another small repository evidence file, the
policy here and the script allowlist must be updated together in the same
reviewed change.

Do not work around the checker by writing new run trees under `results/`.
