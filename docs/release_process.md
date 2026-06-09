# Release Process

## Scope

This process covers TypeTreeFlow release commits, annotated tags, GitHub
Releases, release PRs, and post-release repository cleanup.

## Pre-Release Checks

- Worktree clean.
- Version metadata consistent across `pyproject.toml`,
  `typetreeflow/__init__.py`, `CITATION.cff`, and `CHANGELOG.md`.
- Changelog entry present.
- Targeted tests pass.
- Full or release-appropriate CI passes.

Use `docs/release_checklist.md` as the detailed execution checklist when
preparing release artifacts or validating a release candidate.

For maintenance releases, treat the checklist as the release gate for
version-consistency checks, repo-local pytest temp usage, wheel smoke testing,
temporary-directory cleanup, and "no real downloads unless explicitly scoped"
confirmation.

Release validation outputs should live outside the repository by default. Use
`<workspace>/runs/release/<run-name>` for real or large run outputs and
`<workspace>/deliveries/<delivery-name>` for package handoffs; a local
maintainer workspace may be `D:\Draft\TypeTreeFlow_workspace`. If `--outdir` is
omitted, TypeTreeFlow writes to `TYPETREEFLOW_WORKSPACE/runs/default` when that
environment variable is set, otherwise to the user-level platform workspace
(`%LOCALAPPDATA%/TypeTreeFlow/workspace/runs/default` on Windows, or
`$XDG_DATA_HOME/typetreeflow/workspace/runs/default` with
`~/.local/share/typetreeflow/workspace/runs/default` as the POSIX fallback).
Explicit `--outdir` paths are always used exactly as supplied.

## Release Commit

- Create a release readiness commit.
- Confirm the release commit hash.
- Do not include caches, local environment files, generated run output, real
  download data, or large artifacts.
- Do not include `typetreeflow_out/`; it is the old default/historical example
  path and is not the current default output location.
- Keep repository `results/` limited to curated, small, trackable verification
  evidence. Do not commit real runs, large downloads, or scratch output there.
- Do not mix unrelated feature work into the release readiness commit.

## Annotated Tag

- Create an annotated tag:

  ```bash
  git tag -a vX.Y.Z -m "Release vX.Y.Z"
  ```

- Push the release commit and tag.
- Confirm the tag dereferences to the intended release commit:

  ```bash
  git rev-parse vX.Y.Z^{}
  ```

- Do not rewrite public tags unless the maintainer explicitly approves the
  exception and records the reason.

## GitHub Release

- Create a draft GitHub Release from the pushed tag.
- Use the changelog entry as release notes.
- Confirm the draft release is bound to the intended tag.
- Publish only after the release PR is merged into `main`.
- Confirm stable releases are not left as draft or prerelease releases.

Draft release URLs may temporarily look like `untagged-*`; verify the release
record's `tagName` before publishing.

## Release PR

- Open a PR from the release branch to `main`.
- Use a merge commit only.
- Do not squash or rebase release PRs, because the tag commit must remain
  reachable from `main`.
- Confirm required CI checks pass.

## Branch Protection Notes

- PR authors cannot approve their own PRs.
- For single-maintainer repositories, keep the required approving review count
  at `0` unless another reviewer is available.
- Required CI checks should remain enabled.

## Post-Release Cleanup

- Confirm the latest GitHub Release points to the intended stable release.
- Confirm the tag commit is reachable from `main`.
- Confirm the release PR was merged, required CI passed, and the published
  GitHub Release is attached to the intended tag.
- Delete the merged release branch.
- Sync local `main`.
- Verify the worktree is clean.

Useful checks:

```bash
git fetch --tags origin
git merge-base --is-ancestor vX.Y.Z^{} main
git status -sb
```

## Troubleshooting

- Draft release URLs may temporarily look like `untagged-*`; verify `tagName`.
- If Git proxy points to `127.0.0.1:7890` and fails, either start the proxy or
  run one-off commands with:

  ```bash
  git -c http.proxy= -c https.proxy= ...
  ```
