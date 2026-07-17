from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal, Mapping, Protocol, Sequence

from typetreeflow.evidence.bacdive import (
    BACDIVE_CONFLICT,
    BACDIVE_INSUFFICIENT_LINKAGE,
    BacDiveEvidenceRecord,
    compare_bacdive_lpsn_tokens,
    normalize_culture_collection_identifiers,
    parse_bacdive_evidence_record,
    reconcile_bacdive_record,
)


BacDiveQueryKind = Literal[
    "culture_collection",
    "strain_designation",
    "species_name",
]
BacDiveLookupStatus = Literal[
    "success",
    "no_result",
    "api_unavailable",
    "timeout",
    "rate_limited",
    "schema_drift",
    "conflict",
    "terms_not_confirmed",
]

SUCCESS: BacDiveLookupStatus = "success"
NO_RESULT: BacDiveLookupStatus = "no_result"
API_UNAVAILABLE: BacDiveLookupStatus = "api_unavailable"
TIMEOUT: BacDiveLookupStatus = "timeout"
RATE_LIMITED: BacDiveLookupStatus = "rate_limited"
SCHEMA_DRIFT: BacDiveLookupStatus = "schema_drift"
CONFLICT: BacDiveLookupStatus = "conflict"
TERMS_NOT_CONFIRMED: BacDiveLookupStatus = "terms_not_confirmed"

_VALID_QUERY_KINDS = {
    "culture_collection",
    "strain_designation",
    "species_name",
}
_VALID_LOOKUP_STATUSES = {
    "success",
    "no_result",
    "api_unavailable",
    "timeout",
    "rate_limited",
    "schema_drift",
    "conflict",
    "terms_not_confirmed",
}
_NON_SUCCESS_DIAGNOSTIC_CODES = {
    NO_RESULT: "bacdive_no_result",
    API_UNAVAILABLE: "bacdive_api_unavailable",
    TIMEOUT: "bacdive_timeout",
    RATE_LIMITED: "bacdive_rate_limited",
    SCHEMA_DRIFT: "bacdive_schema_drift",
    CONFLICT: "bacdive_conflict",
    TERMS_NOT_CONFIRMED: "bacdive_terms_not_confirmed",
}


@dataclass(frozen=True)
class BacDiveLookupRequest:
    """Bounded BacDive enrichment lookup request for adapter tests."""

    query_kind: BacDiveQueryKind
    query: str
    species_name: str = ""
    source_context: str = ""

    def __post_init__(self) -> None:
        if self.query_kind not in _VALID_QUERY_KINDS:
            raise ValueError(f"Unsupported BacDive query kind: {self.query_kind!r}")
        if not self.query.strip():
            raise ValueError("BacDive lookup query must not be empty")


@dataclass(frozen=True)
class BacDiveDiagnostic:
    status: BacDiveLookupStatus
    code: str
    message: str
    evidence_effect: str = "none"
    notes: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.status not in _VALID_LOOKUP_STATUSES:
            raise ValueError(f"Unsupported BacDive diagnostic status: {self.status!r}")


@dataclass(frozen=True)
class BacDiveClientResponse:
    """Raw client response before BacDiveEvidenceRecord normalization."""

    status: BacDiveLookupStatus = SUCCESS
    raw_records: tuple[Mapping[str, Any], ...] = ()
    diagnostics: tuple[BacDiveDiagnostic, ...] = ()
    source_url: str = ""
    accessed_at: str = ""

    def __post_init__(self) -> None:
        if self.status not in _VALID_LOOKUP_STATUSES:
            raise ValueError(f"Unsupported BacDive client status: {self.status!r}")


@dataclass(frozen=True)
class BacDiveLookupResult:
    request: BacDiveLookupRequest
    records: tuple[BacDiveEvidenceRecord, ...]
    status: BacDiveLookupStatus
    diagnostics: tuple[BacDiveDiagnostic, ...] = ()
    source_url: str = ""
    accessed_at: str = ""

    def __post_init__(self) -> None:
        if self.status not in _VALID_LOOKUP_STATUSES:
            raise ValueError(f"Unsupported BacDive lookup status: {self.status!r}")


class BacDiveClientProtocol(Protocol):
    def lookup(self, request: BacDiveLookupRequest) -> BacDiveClientResponse:
        """Return raw BacDive-like records for a bounded lookup request."""


class FakeBacDiveClient:
    """In-memory BacDive client for unit tests; performs no network or env IO."""

    def __init__(
        self,
        responses: Mapping[
            tuple[BacDiveQueryKind, str],
            BacDiveClientResponse | Mapping[str, Any] | Sequence[Mapping[str, Any]],
        ],
    ) -> None:
        self._responses = dict(responses)
        self.requests: list[BacDiveLookupRequest] = []

    def lookup(self, request: BacDiveLookupRequest) -> BacDiveClientResponse:
        self.requests.append(request)
        response = self._responses.get((request.query_kind, request.query))
        if response is None:
            return BacDiveClientResponse(
                status=NO_RESULT,
                diagnostics=(
                    _diagnostic(
                        NO_RESULT,
                        f"No BacDive fake-client result for {request.query_kind} query",
                    ),
                ),
            )
        return _coerce_client_response(response)


class BacDiveLiveClient:
    """Non-wired live-client skeleton.

    P3b-a intentionally does not implement HTTP access. Future live use must
    confirm terms and citation metadata before any client can be constructed.
    """

    def __init__(
        self,
        *,
        terms_confirmed: bool = False,
        citation_confirmed: bool = False,
    ) -> None:
        if not terms_confirmed or not citation_confirmed:
            raise ValueError(
                "BacDive live adapter requires confirmed terms and citation metadata"
            )

    def lookup(self, request: BacDiveLookupRequest) -> BacDiveClientResponse:
        raise NotImplementedError("BacDive live HTTP lookup is not implemented in P3b-a")


def build_bacdive_lookup_request(
    *,
    species_name: str,
    culture_collection_numbers: object = (),
    strain_designation: str = "",
    source_context: str = "",
) -> BacDiveLookupRequest:
    """Build one bounded lookup, preferring culture-collection tokens."""
    collection_tokens = normalize_culture_collection_identifiers(
        culture_collection_numbers
    )
    if collection_tokens:
        return BacDiveLookupRequest(
            query_kind="culture_collection",
            query=collection_tokens[0],
            species_name=_normalize_space(species_name),
            source_context=source_context,
        )
    if strain_designation.strip():
        return BacDiveLookupRequest(
            query_kind="strain_designation",
            query=_normalize_space(strain_designation),
            species_name=_normalize_space(species_name),
            source_context=source_context,
        )
    return BacDiveLookupRequest(
        query_kind="species_name",
        query=_normalize_space(species_name),
        species_name=_normalize_space(species_name),
        source_context=source_context,
    )


def lookup_bacdive_evidence(
    request: BacDiveLookupRequest,
    client: BacDiveClientProtocol,
    *,
    lpsn_type_strain_tokens: object = (),
    terms_confirmed: bool = True,
) -> BacDiveLookupResult:
    """Normalize one fake/client response into candidate-only BacDive evidence."""
    if not terms_confirmed:
        return BacDiveLookupResult(
            request=request,
            records=(),
            status=TERMS_NOT_CONFIRMED,
            diagnostics=(
                _diagnostic(
                    TERMS_NOT_CONFIRMED,
                    "BacDive terms and citation metadata were not confirmed",
                ),
            ),
        )

    response = client.lookup(request)
    diagnostics = list(response.diagnostics)
    if response.status != SUCCESS:
        if not diagnostics:
            diagnostics.append(_diagnostic(response.status, _default_message(response.status)))
        return BacDiveLookupResult(
            request=request,
            records=(),
            status=response.status,
            diagnostics=tuple(diagnostics),
            source_url=response.source_url,
            accessed_at=response.accessed_at,
        )
    if not response.raw_records:
        diagnostics.append(
            _diagnostic(NO_RESULT, "BacDive lookup returned no records")
        )
        return BacDiveLookupResult(
            request=request,
            records=(),
            status=NO_RESULT,
            diagnostics=tuple(diagnostics),
            source_url=response.source_url,
            accessed_at=response.accessed_at,
        )

    records: list[BacDiveEvidenceRecord] = []
    status: BacDiveLookupStatus = SUCCESS
    schema_drift_count = 0
    for raw_record in response.raw_records:
        if not _has_minimal_detail_shape(raw_record):
            schema_drift_count += 1
            diagnostics.append(
                _diagnostic(
                    SCHEMA_DRIFT,
                    "BacDive response lacks minimal species detail shape",
                )
            )
            continue

        record = parse_bacdive_evidence_record(raw_record)
        records.append(record)
        diagnostics.extend(
            _record_diagnostics(
                record,
                expected_species_name=request.species_name,
                lpsn_type_strain_tokens=lpsn_type_strain_tokens,
            )
        )
        if _has_species_conflict(record, request.species_name):
            status = CONFLICT

    if records:
        source_url = response.source_url or records[0].source_url
        accessed_at = response.accessed_at or records[0].source_release_or_accessed
        return BacDiveLookupResult(
            request=request,
            records=tuple(records),
            status=status,
            diagnostics=tuple(diagnostics),
            source_url=source_url,
            accessed_at=accessed_at,
        )

    final_status = SCHEMA_DRIFT if schema_drift_count else NO_RESULT
    return BacDiveLookupResult(
        request=request,
        records=(),
        status=final_status,
        diagnostics=tuple(diagnostics),
        source_url=response.source_url,
        accessed_at=response.accessed_at,
    )


def _coerce_client_response(
    response: BacDiveClientResponse | Mapping[str, Any] | Sequence[Mapping[str, Any]],
) -> BacDiveClientResponse:
    if isinstance(response, BacDiveClientResponse):
        return response
    if isinstance(response, Mapping):
        return BacDiveClientResponse(status=SUCCESS, raw_records=(response,))
    return BacDiveClientResponse(status=SUCCESS, raw_records=tuple(response))


def _record_diagnostics(
    record: BacDiveEvidenceRecord,
    *,
    expected_species_name: str,
    lpsn_type_strain_tokens: object,
) -> tuple[BacDiveDiagnostic, ...]:
    diagnostics: list[BacDiveDiagnostic] = []
    if len(record.culture_collection_numbers) > 1:
        diagnostics.append(
            BacDiveDiagnostic(
                status=SUCCESS,
                code="bacdive_multiple_accessions",
                message="BacDive record contains multiple culture collection accessions",
                evidence_effect="candidate_review",
            )
        )

    reconciliation = reconcile_bacdive_record(
        record,
        expected_species_name=expected_species_name,
        lpsn_type_strain_tokens=lpsn_type_strain_tokens,
    )
    if reconciliation.status == BACDIVE_CONFLICT:
        diagnostics.append(
            BacDiveDiagnostic(
                status=CONFLICT,
                code="bacdive_conflict",
                message="BacDive species conflicts with expected species",
                evidence_effect="manual_review",
                notes=reconciliation.notes,
            )
        )
    elif (
        reconciliation.status == BACDIVE_INSUFFICIENT_LINKAGE
        and record.is_type_strain
        and lpsn_type_strain_tokens
        and not compare_bacdive_lpsn_tokens(record, lpsn_type_strain_tokens)
    ):
        diagnostics.append(
            BacDiveDiagnostic(
                status=SUCCESS,
                code="bacdive_no_lpsn_token_overlap",
                message="BacDive type-strain signal lacks LPSN token overlap",
                evidence_effect="candidate_review",
                notes=reconciliation.notes,
            )
        )
    return tuple(diagnostics)


def _has_minimal_detail_shape(raw_record: Mapping[str, Any]) -> bool:
    return bool(parse_bacdive_evidence_record(raw_record).species_name)


def _has_species_conflict(
    record: BacDiveEvidenceRecord,
    expected_species_name: str,
) -> bool:
    if not expected_species_name.strip() or not record.species_name.strip():
        return False
    return _normalize_space(record.species_name).lower() != (
        _normalize_space(expected_species_name).lower()
    )


def _diagnostic(
    status: BacDiveLookupStatus,
    message: str,
) -> BacDiveDiagnostic:
    return BacDiveDiagnostic(
        status=status,
        code=_NON_SUCCESS_DIAGNOSTIC_CODES[status],
        message=message,
    )


def _default_message(status: BacDiveLookupStatus) -> str:
    return {
        NO_RESULT: "BacDive lookup returned no result",
        API_UNAVAILABLE: "BacDive API was unavailable",
        TIMEOUT: "BacDive lookup timed out",
        RATE_LIMITED: "BacDive lookup was rate limited",
        SCHEMA_DRIFT: "BacDive response schema drift was detected",
        CONFLICT: "BacDive lookup returned conflicting evidence",
        TERMS_NOT_CONFIRMED: "BacDive terms and citation metadata were not confirmed",
        SUCCESS: "BacDive lookup succeeded",
    }[status]


def _normalize_space(value: str) -> str:
    return " ".join(str(value or "").split())
