from __future__ import annotations

from contextlib import contextmanager
import os
import socket
from typing import Iterator


DEFAULT_PROVIDER_TIMEOUT_SECONDS = 30.0
PROVIDER_TIMEOUT_ENV = "TYPETREEFLOW_PROVIDER_TIMEOUT_SECONDS"


def provider_timeout_from_env(
    *,
    default: float = DEFAULT_PROVIDER_TIMEOUT_SECONDS,
) -> float:
    return parse_provider_timeout_seconds(
        os.environ.get(PROVIDER_TIMEOUT_ENV),
        default=default,
        source=PROVIDER_TIMEOUT_ENV,
    )


def parse_provider_timeout_seconds(
    value: object,
    *,
    default: float = DEFAULT_PROVIDER_TIMEOUT_SECONDS,
    source: str = "provider timeout",
) -> float:
    if value is None or str(value).strip() == "":
        timeout = default
    else:
        try:
            timeout = float(str(value).strip())
        except ValueError as exc:
            raise ValueError(f"{source} must be a positive number of seconds.") from exc
    if timeout <= 0:
        raise ValueError(f"{source} must be a positive number of seconds.")
    return timeout


@contextmanager
def bounded_socket_timeout(timeout_seconds: float | None) -> Iterator[None]:
    if timeout_seconds is None:
        yield
        return
    timeout = parse_provider_timeout_seconds(timeout_seconds)
    previous_timeout = socket.getdefaulttimeout()
    socket.setdefaulttimeout(timeout)
    try:
        yield
    finally:
        socket.setdefaulttimeout(previous_timeout)
