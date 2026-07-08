# Security Policy

## Supported versions

Security fixes are considered for the latest released version of TypeTreeFlow.

## Reporting a vulnerability

Please report suspected vulnerabilities privately by opening a GitHub security
advisory for the repository, or by contacting the repository owner directly if
private advisories are not available.

Do not include exploit details in public issues before maintainers have had a
reasonable chance to investigate and prepare a fix.

## Scope

TypeTreeFlow is a local command-line workflow. Some stages can call external
tools or network services, but real execution is guarded by explicit opt-in
flags. Reports are especially useful when they involve unsafe command
construction, path traversal, archive extraction behavior, accidental network
access during dry runs, or leakage of user-provided credentials such as Entrez
API keys.
