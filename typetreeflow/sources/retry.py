from __future__ import annotations

from collections.abc import Callable
from http.client import IncompleteRead
import logging
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
            if attempt >= attempts:
                message = (
                    f"{operation} failed after {attempts} attempt(s); "
                    f"final error: {error}"
                )
                log.error(message)
                raise RetryError(message) from error
            delay = base_delay_seconds * attempt
            log.warning(
                "%s transient network error on attempt %d/%d: %s; retrying in %.2fs",
                operation,
                attempt,
                attempts,
                error,
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
