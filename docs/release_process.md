# Release Process

This document records TypeTreeFlow release policy, process, and release-record
standards. Use `docs/release_checklist.md` as the execution checklist before
tagging, publishing, or auditing a release.

## Version Source of Truth

For every release, the version must be consistent across:

- `pyproject.toml`
- `typetreeflow/__init__.py`
- `CITATION.cff`
- `CHANGELOG.md`

Do not treat the Git tag or GitHub Release title as the only source of truth.
They must match the version recorded in the repository files above.

## Release Tag Policy

Release tags use this format:

```text
vMAJOR.MINOR.PATCH
```

Release tags should be annotated tags. The tag message format is:

```text
TypeTreeFlow vX.Y.Z
```

Public tags are not rewritten by default. If rewriting a public tag is
explicitly approved, create a backup first and record the reason.

Historical note: `v0.2.1` was originally published as a lightweight tag. To
standardize release tag records, it has since been replaced with an annotated
tag while preserving the peeled commit:
`cc4534a704623009038f31c23cb04e2b13274750`. After the full commit history was
normalized, the old backup tag was no longer retained as a Git ref. The
pre-rewrite history is preserved locally in the bundle:
`D:\Draft\TypeTreeFlow-pre-history-rewrite-c8c77e2-20260526.bundle`.

## GitHub Release Policy

GitHub Releases must follow these rules:

- Release title: `TypeTreeFlow vX.Y.Z`
- The newest stable release is marked as Latest.
- Stable releases are not draft releases.
- Stable releases are not prereleases.
- Each release must upload the corresponding wheel asset.
- Wheel asset filename format: `typetreeflow-X.Y.Z-py3-none-any.whl`

The GitHub Release version, tag, title, Latest marker, and wheel asset must all
refer to the same release version.

## Validation Policy

Every release must pass the local validation, packaging, and clean-clone checks
listed in `docs/release_checklist.md`. Clean-clone verification happens before
publishing the GitHub Release and must use the exact release tag in a
disposable directory.

Required validation is intentionally offline unless a release explicitly plans
guarded real validation. The default tests and scaffolding checks must not
require network access or external bioinformatics tools.

## Safety Rules

- Release preparation must not add unrelated features.
- Clean clone verification must not modify the source repository.
- Scaffolding tests must not require network access.
- Scaffolding tests must not require external bioinformatics tools.
- Do not call `datasets`, `barrnap`, `FastANI`, `MAFFT`, `trimAl`, or
  `IQ-TREE` during release preparation unless running an explicitly planned,
  guarded real validation.
- Guarded real validation must document the exact command, input data, output
  directory, and reason for running it.

## Clean Clone Verification Standard

Before publishing a GitHub Release:

1. Clone the repository into a disposable directory.
2. Check out the exact release tag.
3. Confirm the version files match the tag.
4. Run the required tests and CLI help check.
5. Build the wheel and confirm its filename matches the release version.
6. Confirm the clean clone remains unmodified after verification.

## Release Record Audit

Before closing a release, audit the local repository, remote repository, tags,
and GitHub Release record:

- Check that `main` and `origin/main` are aligned at the intended release
  commit.
- Check that local release tags and origin release tags agree.
- Check that the release tag is annotated.
- Check that the GitHub Release exists for the release tag.
- Check that the GitHub Release has the required wheel asset.
- Check that the wheel asset filename is
  `typetreeflow-X.Y.Z-py3-none-any.whl`.
- Check that the newest stable release is marked as Latest.
- Check that stable releases are not draft or prerelease releases.

Record any exception in the release notes or project maintenance notes before
considering the release complete.
