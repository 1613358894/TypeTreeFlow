# Workspace Policy

This page is the canonical policy for TypeTreeFlow workspace roots and
generated output locations.

## Default Workspace Resolution

An explicit `--outdir PATH` always wins. TypeTreeFlow uses that path exactly as
the run directory.

When `--outdir` is omitted, TypeTreeFlow writes to a default workspace run
directory:

- If `TYPETREEFLOW_WORKSPACE` is set: `<workspace>/runs/default`
- On Windows:
  `%LOCALAPPDATA%/TypeTreeFlow/workspace/runs/default`
- On POSIX:
  `$XDG_DATA_HOME/typetreeflow/workspace/runs/default`, or
  `~/.local/share/typetreeflow/workspace/runs/default` when `XDG_DATA_HOME`
  is unset

`TYPETREEFLOW_WORKSPACE` is optional. Set it when an operator wants a stable
local root for runs, deliveries, local data, and reviewed manifests.

## Workspace Layout

Recommended workspace layout:

```text
<workspace>/
  runs/
    default/
    <run-name>/
    release/
      <release-run-name>/
  deliveries/
    <delivery-name>/
  data/
    <local-cache-or-input-name>/
  manifests/
    <reviewed-manifest-name>/
  scratch
  history
  rewrite
  archive
```

`<workspace>/runs/` is for generated run outputs. Real acquisition, guarded
download, release verification, report refresh, and analysis outputs should
normally live here. Use descriptive run names, and use
`<workspace>/runs/release/<run-name>` for release validation runs.
This is distinct from maintained repository documentation, which is not a
generated run-output location.

`<workspace>/deliveries/` is for reviewed package handoffs produced by
`package-results --delivery-dir`. Delivery packages are handoff artifacts, not
run caches or permanent source data.

`<workspace>/data/` is for local operator-owned inputs and caches that are not
intended to be committed to this repository, such as local LPSN exports,
discovery caches, BioSample caches, local FASTA inputs, or real-world release
validation inputs.

`<workspace>/manifests/` is for reviewed manifest snapshots or curated
manifest handoffs that an operator wants to keep outside any single run
directory.

`scratch`, `history`, `rewrite`, and `archive` are local workspace support
areas. Use them for disposable experiments, old local outputs, rewrite drafts,
and operator-maintained local archives. They are not TypeTreeFlow's canonical
run or delivery outputs, and they should not be treated as repository
documentation. Durable rules from local material belong in the nearest current
contract, policy, architecture, or release document.

## Local Maintainer Example

`D:\Draft\TypeTreeFlow_workspace` is only this project's local maintainer
example. It is not the universal default, and documentation should not imply
that users on other machines should have that path.

Use `<workspace>/...` in general documentation. Mention
`D:\Draft\TypeTreeFlow_workspace` only when describing a local maintenance
example for this checkout.
