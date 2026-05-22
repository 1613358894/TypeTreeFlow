# Release Process

This document records the TypeTreeFlow release process and release-record
standards. Use it together with `docs/release_checklist.md` before tagging,
publishing, or auditing a release.

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
`cc4534a704623009038f31c23cb04e2b13274750`. The original lightweight tag is
backed up as `backup/v0.2.1-lightweight`.

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

## Validation Checklist

Run the local test suite without pytest cache output:

```bash
pytest -p no:cacheprovider --basetemp .pytest_tmp
```

Check the CLI entry point:

```bash
python typetreeflow.py --help
```

Build the release wheel:

```bash
python -m pip wheel . --no-deps -w .dist_test
```

Run the selection smoke workflow:

```bash
mkdir -p <tmp>/candidates
cp examples/assembly_candidates_minimal.tsv <tmp>/candidates/assembly_candidates.tsv
python typetreeflow.py --outdir <tmp> --prepare-selection --strains-per-species 1
test -f <tmp>/selection/user_selection.tsv
```

Perform clean clone verification before publishing the GitHub Release:

1. Clone the repository into a disposable directory.
2. Check out the exact release tag.
3. Confirm the version files match the tag.
4. Run the required tests and CLI help check.
5. Build the wheel and confirm its filename matches the release version.
6. Confirm the clean clone remains unmodified after verification.

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
