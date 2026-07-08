# Release Process

## Scope

This process covers TypeTreeFlow release commits, annotated tags, GitHub
Releases, release PRs, and post-release repository cleanup.

Use [release_checklist.md](release_checklist.md) as the detailed execution
checklist when preparing release artifacts or validating a release candidate.

Release validation outputs should live outside the repository by default. See
[workspace_policy.md](workspace_policy.md) for workspace placement,
[results_policy.md](results_policy.md) for repository `results/` exclusion, and
[output_layout.md](output_layout.md) for run-directory file contracts.

## Phase 1: Prepare Release Commit

Prepare one reviewable release readiness commit before tagging or publishing.

- Create a release readiness commit.
- Confirm the release commit hash.
- Worktree clean.
- Version metadata consistent across `pyproject.toml`,
  `typetreeflow/__init__.py`, `CITATION.cff`, and `CHANGELOG.md`.
- Changelog entry present.
- Do not include caches, local environment files, generated run output, real
  download data, or large artifacts.
- Do not include `typetreeflow_out/`; it is the old default/historical example
  path and is not the current default output location.
- Do not include repository `results/`; keep release evidence in an external
  workspace per [results_policy.md](results_policy.md).
- Do not mix unrelated feature work into the release readiness commit.

## Phase 2: Local Release Gate

Run the local gate from the release commit before creating or publishing any
release artifact.

Future `scripts/release_gate.py` is the local release gate orchestration
script. It is not a publishing script. It must only run and summarize local
readiness checks, and it must orchestrate the existing check scripts rather
than replacing their logic.

- Documentation hygiene passes with `python scripts/check_docs_hygiene.py`.
- Release consistency and workspace hygiene checks pass.
- Targeted tests pass.
- Full or release-appropriate CI passes.
- CLI entry-point checks pass.
- Wheel build and temporary-venv wheel smoke tests pass.
- Temporary validation directories are removed or confirmed untracked.

`scripts/release_gate.py` must not create tags, push commits or tags, create
GitHub Releases, upload release assets, or run real downloads. Tagging,
pushing, release asset upload, and GitHub Release publication stay in Phase 3
and require explicit maintainer action.

For maintenance-only releases, this gate defaults to no real downloads. Run
real staged validation only when the explicit release scope changes or validates
live acquisition, download, selection, evidence, or report behavior. Otherwise,
offline tests, CLI checks, wheel smoke testing, and hygiene checks are the
maintenance release gate.

## Phase 3: Publish

Publish only after the prepared release commit has passed the local release
gate and the maintainer is ready to tag, push, open the release PR, and publish
the GitHub Release.

### Annotated Tag

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

### GitHub Release

- Create a draft GitHub Release from the pushed tag.
- Use the changelog entry as release notes.
- Confirm the draft release is bound to the intended tag.
- Publish only after the release PR is merged into `main`.
- Confirm stable releases are not left as draft or prerelease releases.

Draft release URLs may temporarily look like `untagged-*`; verify the release
record's `tagName` before publishing.

### Release PR

- Open a PR from the release branch to `main`.
- Use a merge commit only.
- Do not squash or rebase release PRs, because the tag commit must remain
  reachable from `main`.
- Confirm required CI checks pass.

### Branch Protection Notes

- PR authors cannot approve their own PRs.
- For single-maintainer repositories, keep the required approving review count
  at `0` unless another reviewer is available.
- Required CI checks should remain enabled.

### Post-Release Cleanup

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
