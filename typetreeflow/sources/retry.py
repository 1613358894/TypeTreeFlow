from __future__ import annotations

from collections.abc import Callable
from http.client import IncompleteRead
import logging
import socket
import time
from typing import TypeVar
from urllib.error import HTTPError, URLError


T = TypeVar("T")

TRANSIENT_HTTP_STATUS_CODES = {429, 500, 502, 503, 504}


class RetryError(RuntimeError):
    """Raised when a transient network operation exhausts retry attempts."""


def retry_transient_network_errors(
    operation: str,
    func: Callable[[], T],
    *,
    stage: str = "",
    provider: str = "",
    action: str = "",
    timeout_seconds: float | None = None,
    attempts: int = 3,
    base_delay_seconds: float = 1.0,
    sleep: Callable[[float], None] = time.sleep,
    logger: logging.Logger | None = None,
) -> T:
    """Run a network operation with limited retry/backoff for transient errors."""

    if attempts < 1:
        raise ValueError("Retry attempts must be at least 1.")

    log = logger or logging.getLogger(__name__)
    last_error: BaseException | None = None
    for attempt in range(1, attempts + 1):
        try:
            result = func()
        except Exception as error:
            if not is_transient_network_error(error):
                raise
            last_error = error
            category = transient_error_category(error)
            diagnostic = _provider_diagnostic(
                stage=stage,
                provider=provider,
                action=action or operation,
                attempt=attempt,
                timeout_seconds=timeout_seconds,
                exception_category=category,
            )
            if attempt >= attempts:
                message = (
                    f"{operation} failed after {attempts} attempt(s); "
                    f"{diagnostic}; final error: {error}"
                )
                log.error(message)
                raise RetryError(message) from error
            delay = base_delay_seconds * attempt
            log.warning(
                "%s transient network error on attempt %d/%d: %s; %s; "
                "retrying in %.2fs",
                operation,
                attempt,
                attempts,
                error,
                diagnostic,
                delay,
            )
            sleep(delay)
            continue
        if attempt > 1:
            log.info("%s succeeded on retry attempt %d/%d", operation, attempt, attempts)
        return result

    raise RetryError(
        f"{operation} failed after {attempts} attempt(s); final error: {last_error}"
    )


def is_transient_network_error(error: BaseException) -> bool:
    if isinstance(error, HTTPError):
        return error.code in TRANSIENT_HTTP_STATUS_CODES
    if isinstance(error, (IncompleteRead, TimeoutError, ConnectionError, URLError)):
        return True
    return False


def transient_error_category(error: BaseException) -> str:
    if _is_timeout_error(error):
        return "provider_timeout"
    if isinstance(error, HTTPError):
        return f"http_{error.code}"
    if isinstance(error, URLError):
        return "url_error"
    if isinstance(error, IncompleteRead):
        return "incomplete_read"
    if isinstance(error, ConnectionError):
        return "connection_error"
    return type(error).__name__


def _is_timeout_error(error: BaseException) -> bool:
    if isinstance(error, (TimeoutError, socket.timeout)):
        return True
    if isinstance(error, URLError):
        reason = getattr(error, "reason", None)
        if isinstance(reason, (TimeoutError, socket.timeout)):
            return True
        reason_text = str(reason or error).lower()
        return "timed out" in reason_text or "timeout" in reason_text
    return False


def _provider_diagnostic(
    *,
    stage: str,
    provider: str,
    action: str,
    attempt: int,
    timeout_seconds: float | None,
    exception_category: str,
) -> str:
    fields = {
        "stage": stage,
        "provider": provider,
        "action": action,
        "attempt": str(attempt),
        "timeout_seconds": _format_timeout_seconds(timeout_seconds),
        "exception_category": exception_category,
    }
    return "provider_diagnostic " + " ".join(
        f"{key}={value}" for key, value in fields.items() if value
    )


def _format_timeout_seconds(timeout_seconds: float | None) -> str:
    if timeout_seconds is None:
        return ""
    return f"{float(timeout_seconds):g}"
