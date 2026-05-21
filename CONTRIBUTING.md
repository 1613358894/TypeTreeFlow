# Contributing

Thank you for helping improve TypeTreeFlow. This project is a guarded
command-line workflow for microbial type-strain genome and 16S analysis.
Changes should preserve reproducible outputs, explicit opt-in for real external
tools, and clear resume behavior.

## Development setup

Use Python 3.10 or newer.

```bash
python -m pip install -e ".[dev]"
```

The full test suite uses fake runners and does not require real external
bioinformatics tools or network access:

```bash
pytest -p no:cacheprovider --basetemp .pytest_tmp
```

## Pull request expectations

- Keep changes focused on one behavior or documentation area.
- Add or update tests for behavior changes.
- Update `README.md`, `docs/`, or `CHANGELOG.md` when user-visible behavior
  changes.
- Do not commit generated run outputs, downloaded GTDB metadata, NCBI ZIPs,
  build artifacts, caches, or local environment directories.
- Keep real external execution behind explicit opt-in flags and preserve dry-run
  safety.

Before opening a pull request, run:

```bash
pytest -p no:cacheprovider --basetemp .pytest_tmp
python typetreeflow.py --help
python -m pip wheel . --no-deps -w .dist_test
```

See `docs/release_checklist.md` for the fuller release validation workflow.
