from __future__ import annotations

import json
import socket
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
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

DEFAULT_BACDIVE_API_BASE_URL = "https://api.bacdive.dsmz.de"
BACDIVE_API_DOCUMENTATION_URL = "https://api.bacdive.dsmz.de/"
BACDIVE_FIELD_INFORMATION_URL = (
    "https://api.bacdive.dsmz.de/strain_fields_information"
)
BACDIVE_TERMS_URL = "https://bacdive.dsmz.de/about"
BACDIVE_CITATION_URL = "https://bacdive.dsmz.de/about#how-to-cite"
BACDIVE_LICENSE_URL = "https://creativecommons.org/licenses/by/4.0/"

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
    http_status: int | None = None
    retry_count: int = 0

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
    source_audit: Mapping[str, Any] | None = None

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


class BacDiveHTTPTransportProtocol(Protocol):
    def get_json(self, url: str, timeout: float, max_response_bytes: int) -> Any:
        """Return decoded JSON for one BacDive URL."""


class BacDiveTransportError(Exception):
    """Base transport exception for injectable BacDive HTTP transports."""


class BacDiveTimeoutError(BacDiveTransportError):
    """Raised by transports when a request times out."""


class BacDiveMalformedJSONError(BacDiveTransportError):
    """Raised by transports when a response body is not valid JSON."""


class BacDiveResponseTooLargeError(BacDiveTransportError):
    """Raised by transports when a response exceeds the configured byte guard."""


class BacDiveHTTPError(BacDiveTransportError):
    """Raised by transports for non-success HTTP status codes."""

    def __init__(self, status_code: int, message: str = "") -> None:
        self.status_code = int(status_code)
        super().__init__(message or f"BacDive HTTP status {status_code}")


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
    """Injectable BacDive v2 HTTP client.

    The public workflow still does not construct this client automatically.
    Tests should inject a fake transport; the default transport exists only for
    explicit future live use after terms and citation provenance are confirmed.
    """

    def __init__(
        self,
        *,
        terms_confirmed: bool = False,
        citation_confirmed: bool = False,
        base_url: str = DEFAULT_BACDIVE_API_BASE_URL,
        timeout_seconds: float = 20.0,
        max_http_calls: int = 50,
        max_detail_ids: int = 100,
        max_response_bytes: int = 5_000_000,
        transport: BacDiveHTTPTransportProtocol | None = None,
    ) -> None:
        if not terms_confirmed or not citation_confirmed:
            raise ValueError(
                "BacDive live adapter requires confirmed terms and citation metadata"
            )
        if timeout_seconds <= 0:
            raise ValueError("BacDive live timeout must be positive")
        if max_http_calls <= 0:
            raise ValueError("BacDive live max_http_calls must be positive")
        if max_detail_ids <= 0:
            raise ValueError("BacDive live max_detail_ids must be positive")
        if max_response_bytes <= 0:
            raise ValueError("BacDive live max_response_bytes must be positive")
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = float(timeout_seconds)
        self.max_http_calls = int(max_http_calls)
        self.max_detail_ids = int(max_detail_ids)
        self.max_response_bytes = int(max_response_bytes)
        self.transport = transport or _StdlibBacDiveJsonTransport()
        self.http_calls_made = 0
        self._rate_limited = False

    def lookup(self, request: BacDiveLookupRequest) -> BacDiveClientResponse:
        accessed_at = _utc_now()
        endpoint = self._lookup_endpoint(request)
        if endpoint is None:
            return self._status_response(
                SCHEMA_DRIFT,
                "BacDive live client has no endpoint for this query kind or species shape",
                accessed_at=accessed_at,
                query=request.query,
                endpoint="",
            )

        lookup_url = self._url(endpoint)
        lookup_payload, lookup_error = self._get_json(
            lookup_url,
            accessed_at=accessed_at,
            query=request.query,
            endpoint=endpoint,
        )
        if lookup_error is not None:
            return lookup_error

        direct_records = _extract_detail_records(lookup_payload)
        if direct_records:
            return self._success_response(
                direct_records,
                source_url=lookup_url,
                accessed_at=accessed_at,
                query=request.query,
                endpoints=(endpoint,),
            )

        bacdive_ids = _extract_bacdive_ids(lookup_payload)
        if bacdive_ids:
            if len(bacdive_ids) > self.max_detail_ids:
                return self._status_response(
                    API_UNAVAILABLE,
                    "BacDive detail ID cap skipped this fetch request",
                    accessed_at=accessed_at,
                    query=request.query,
                    endpoint=endpoint,
                    code="bacdive_max_detail_id_cap_exceeded",
                )
            fetch_endpoint = self.fetch_endpoint(bacdive_ids)
            fetch_url = self._url(fetch_endpoint)
            detail_payload, detail_error = self._get_json(
                fetch_url,
                accessed_at=accessed_at,
                query=";".join(bacdive_ids),
                endpoint=fetch_endpoint,
            )
            if detail_error is not None:
                return detail_error

            detail_records = _extract_detail_records(detail_payload)
            if not detail_records:
                status = (
                    SCHEMA_DRIFT
                    if _candidate_record_mappings(detail_payload)
                    else NO_RESULT
                )
                return self._status_response(
                    status,
                    "BacDive detail fetch lacked minimal detail records",
                    accessed_at=accessed_at,
                    query=request.query,
                    endpoint=fetch_endpoint,
                    endpoints=(endpoint, fetch_endpoint),
                )
            return self._success_response(
                detail_records,
                source_url=fetch_url,
                accessed_at=accessed_at,
                query=request.query,
                endpoints=(endpoint, fetch_endpoint),
            )

        if _candidate_record_mappings(lookup_payload):
            return self._status_response(
                SCHEMA_DRIFT,
                "BacDive lookup records lacked minimal detail shape",
                accessed_at=accessed_at,
                query=request.query,
                endpoint=endpoint,
            )

        if not bacdive_ids:
            return self._status_response(
                NO_RESULT,
                "BacDive lookup returned no IDs or detail records",
                accessed_at=accessed_at,
                query=request.query,
                endpoint=endpoint,
            )

    def culture_collection_endpoint(self, culturecollectionno: str) -> str:
        return "/v2/culturecollectionno/" + _quote_path_segment(culturecollectionno)

    def taxon_endpoint(self, species_name: str) -> str | None:
        parts = _normalize_space(species_name).split()
        if len(parts) < 2:
            return None
        genus, species_epithet = parts[0], parts[1]
        return (
            "/v2/taxon/"
            + _quote_path_segment(genus)
            + "/"
            + _quote_path_segment(species_epithet)
        )

    def fetch_endpoint(self, bacdive_ids: Sequence[str]) -> str:
        encoded = ";".join(_quote_path_segment(str(item)) for item in bacdive_ids)
        return "/v2/fetch/" + encoded

    def _lookup_endpoint(self, request: BacDiveLookupRequest) -> str | None:
        if request.query_kind == "culture_collection":
            return self.culture_collection_endpoint(request.query)
        if request.query_kind == "species_name":
            return self.taxon_endpoint(request.query)
        return None

    def _url(self, endpoint: str) -> str:
        return f"{self.base_url}{endpoint}"

    def _get_json(
        self,
        url: str,
        *,
        accessed_at: str,
        query: str,
        endpoint: str,
    ) -> tuple[Any | None, BacDiveClientResponse | None]:
        if self._rate_limited:
            return None, self._status_response(
                RATE_LIMITED,
                "BacDive rate limit already reached; no further call attempted",
                accessed_at=accessed_at,
                query=query,
                endpoint=endpoint,
                http_status=429,
            )
        if self.http_calls_made >= self.max_http_calls:
            return None, self._status_response(
                API_UNAVAILABLE,
                "BacDive max HTTP call cap skipped this request",
                accessed_at=accessed_at,
                query=query,
                endpoint=endpoint,
                code="bacdive_max_query_cap_exceeded",
            )
        self.http_calls_made += 1
        try:
            return (
                self.transport.get_json(
                    url,
                    self.timeout_seconds,
                    self.max_response_bytes,
                ),
                None,
            )
        except (BacDiveTimeoutError, TimeoutError, socket.timeout):
            return None, self._status_response(
                TIMEOUT,
                "BacDive lookup timed out",
                accessed_at=accessed_at,
                query=query,
                endpoint=endpoint,
            )
        except BacDiveHTTPError as error:
            if error.status_code == 429:
                self._rate_limited = True
                return None, self._status_response(
                    RATE_LIMITED,
                    "BacDive lookup was rate limited",
                    accessed_at=accessed_at,
                    query=query,
                    endpoint=endpoint,
                    http_status=429,
                )
            if 500 <= error.status_code <= 599:
                return None, self._status_response(
                    API_UNAVAILABLE,
                    "BacDive API returned a server error",
                    accessed_at=accessed_at,
                    query=query,
                    endpoint=endpoint,
                    http_status=error.status_code,
                )
            if error.status_code == 404:
                return None, self._status_response(
                    NO_RESULT,
                    "BacDive lookup returned HTTP 404",
                    accessed_at=accessed_at,
                    query=query,
                    endpoint=endpoint,
                    http_status=404,
                )
            return None, self._status_response(
                API_UNAVAILABLE,
                "BacDive API returned an unsupported HTTP error",
                accessed_at=accessed_at,
                query=query,
                endpoint=endpoint,
                http_status=error.status_code,
            )
        except (BacDiveMalformedJSONError, json.JSONDecodeError):
            return None, self._status_response(
                SCHEMA_DRIFT,
                "BacDive response was not valid JSON",
                accessed_at=accessed_at,
                query=query,
                endpoint=endpoint,
                code="bacdive_malformed_json",
            )
        except BacDiveResponseTooLargeError:
            return None, self._status_response(
                API_UNAVAILABLE,
                "BacDive response exceeded max_response_bytes before JSON parsing",
                accessed_at=accessed_at,
                query=query,
                endpoint=endpoint,
                code="bacdive_response_too_large",
            )
        except BacDiveTransportError:
            return None, self._status_response(
                API_UNAVAILABLE,
                "BacDive transport failed",
                accessed_at=accessed_at,
                query=query,
                endpoint=endpoint,
            )

    def _success_response(
        self,
        raw_records: Sequence[Mapping[str, Any]],
        *,
        source_url: str,
        accessed_at: str,
        query: str,
        endpoints: Sequence[str],
    ) -> BacDiveClientResponse:
        records = tuple(
            _with_source_metadata(record, source_url=source_url, accessed_at=accessed_at)
            for record in raw_records
        )
        return BacDiveClientResponse(
            status=SUCCESS,
            raw_records=records,
            source_url=source_url,
            accessed_at=accessed_at,
            source_audit=self._source_audit(
                query=query,
                endpoints=endpoints,
                accessed_at=accessed_at,
            ),
        )

    def _status_response(
        self,
        status: BacDiveLookupStatus,
        message: str,
        *,
        accessed_at: str,
        query: str,
        endpoint: str,
        endpoints: Sequence[str] | None = None,
        code: str | None = None,
        http_status: int | None = None,
    ) -> BacDiveClientResponse:
        diagnostic = BacDiveDiagnostic(
            status=status,
            code=code or _NON_SUCCESS_DIAGNOSTIC_CODES[status],
            message=message,
            http_status=http_status,
        )
        all_endpoints = tuple(endpoints or ((endpoint,) if endpoint else ()))
        return BacDiveClientResponse(
            status=status,
            diagnostics=(diagnostic,),
            source_url=self._url(endpoint) if endpoint else "",
            accessed_at=accessed_at,
            source_audit=self._source_audit(
                query=query,
                endpoints=all_endpoints,
                accessed_at=accessed_at,
                http_status=http_status,
            ),
        )

    def _source_audit(
        self,
        *,
        query: str,
        endpoints: Sequence[str],
        accessed_at: str,
        http_status: int | None = None,
    ) -> dict[str, object]:
        return {
            "endpoint": endpoints[-1] if endpoints else "",
            "endpoints": list(endpoints),
            "query": query,
            "accessed_at": accessed_at,
            "api_documentation_url": BACDIVE_API_DOCUMENTATION_URL,
            "field_information_url": BACDIVE_FIELD_INFORMATION_URL,
            "terms_url": BACDIVE_TERMS_URL,
            "citation_url": BACDIVE_CITATION_URL,
            "license_url": BACDIVE_LICENSE_URL,
            "live_api_called": self.http_calls_made > 0,
            "http_call_count": self.http_calls_made,
            "http_status": http_status or "",
            "timeout_seconds": self.timeout_seconds,
            "max_detail_ids": self.max_detail_ids,
            "max_response_bytes": self.max_response_bytes,
            "raw_payload_policy": "not_written",
            "candidate_only": True,
            "strict_confirmed": False,
        }


class _StdlibBacDiveJsonTransport:
    """Small stdlib JSON transport with no credential or cookie headers."""

    def __init__(self) -> None:
        self._opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))

    def get_json(self, url: str, timeout: float, max_response_bytes: int) -> Any:
        request = urllib.request.Request(
            url,
            headers={
                "Accept": "application/json",
                "User-Agent": "TypeTreeFlow BacDive candidate-evidence client",
            },
            method="GET",
        )
        try:
            with self._opener.open(request, timeout=timeout) as response:
                content_length = response.headers.get("Content-Length")
                if (
                    content_length
                    and content_length.isdigit()
                    and int(content_length) > max_response_bytes
                ):
                    raise BacDiveResponseTooLargeError(
                        f"response Content-Length {content_length} exceeds guard"
                    )
                body_bytes = response.read(max_response_bytes + 1)
                if len(body_bytes) > max_response_bytes:
                    raise BacDiveResponseTooLargeError(
                        f"response exceeded {max_response_bytes} bytes"
                    )
                body = body_bytes.decode("utf-8")
        except urllib.error.HTTPError as error:
            raise BacDiveHTTPError(error.code) from error
        except TimeoutError as error:
            raise BacDiveTimeoutError(str(error)) from error
        except urllib.error.URLError as error:
            if isinstance(error.reason, TimeoutError):
                raise BacDiveTimeoutError(str(error.reason)) from error
            raise BacDiveTransportError(str(error)) from error
        try:
            return json.loads(body)
        except json.JSONDecodeError as error:
            raise BacDiveMalformedJSONError(str(error)) from error


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


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _quote_path_segment(value: str) -> str:
    return urllib.parse.quote(_normalize_space(value), safe="")


def _extract_bacdive_ids(payload: Any) -> tuple[str, ...]:
    ids: list[str] = []
    seen: set[str] = set()

    def add(value: Any) -> None:
        text = str(value).strip()
        if text and text not in seen:
            seen.add(text)
            ids.append(text)

    def collect(value: Any) -> None:
        if isinstance(value, Mapping):
            candidate = _first_mapping_text(
                value,
                (
                    "bacdive_id",
                    "BacDive-ID",
                    "BacDive_id",
                    "bacdiveId",
                    "id",
                ),
            )
            if candidate:
                add(candidate)
            for key in ("results", "result", "records", "data", "ids"):
                nested = value.get(key)
                if nested is not None:
                    collect(nested)
        elif isinstance(value, list):
            for item in value:
                if isinstance(item, (str, int)):
                    add(item)
                elif isinstance(item, Mapping):
                    collect(item)

    collect(payload)
    return tuple(ids)


def _extract_detail_records(payload: Any) -> tuple[Mapping[str, Any], ...]:
    records: list[Mapping[str, Any]] = []
    for candidate in _candidate_record_mappings(payload):
        if _has_minimal_detail_shape(candidate):
            records.append(candidate)
    return tuple(records)


def _candidate_record_mappings(payload: Any) -> list[Mapping[str, Any]]:
    if isinstance(payload, Mapping):
        if _looks_like_detail_record(payload):
            return [payload]
        records: list[Mapping[str, Any]] = []
        for key in ("records", "results", "result", "data", "strains"):
            value = payload.get(key)
            if isinstance(value, Mapping):
                records.extend(_candidate_record_mappings(value))
            elif isinstance(value, list):
                records.extend(item for item in value if isinstance(item, Mapping))
        records.extend(_keyed_detail_records(payload))
        return records
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, Mapping)]
    return []


def _looks_like_detail_record(record: Mapping[str, Any]) -> bool:
    return bool(
        _first_mapping_text(
            record,
            (
                "species_name",
                "species",
                "full_scientific_name",
                "BacDive-ID",
                "bacdive_id",
                "taxonomy",
                "taxonomy_name",
                "Name and taxonomic classification",
            ),
        )
    )


def _keyed_detail_records(payload: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    records: list[Mapping[str, Any]] = []
    for key, value in payload.items():
        if not _looks_like_bacdive_id_key(key) or not isinstance(value, Mapping):
            continue
        record = dict(value)
        record.setdefault("bacdive_id", str(key).strip())
        records.append(record)
    return records


def _looks_like_bacdive_id_key(value: Any) -> bool:
    return str(value).strip().isdigit()


def _first_mapping_text(record: Mapping[str, Any], keys: Sequence[str]) -> str:
    lowered = {str(key).lower(): key for key in record}
    for key in keys:
        actual_key = key if key in record else lowered.get(key.lower())
        if actual_key is None:
            continue
        value = record[actual_key]
        if isinstance(value, (str, int)):
            return str(value).strip()
        if isinstance(value, Mapping):
            return "mapping"
    return ""


def _with_source_metadata(
    record: Mapping[str, Any],
    *,
    source_url: str,
    accessed_at: str,
) -> Mapping[str, Any]:
    enriched = dict(record)
    enriched.setdefault("source_url", source_url)
    enriched.setdefault("source_release_or_accessed", accessed_at)
    enriched.setdefault("source_platform", "BacDive/DSMZ")
    return enriched
