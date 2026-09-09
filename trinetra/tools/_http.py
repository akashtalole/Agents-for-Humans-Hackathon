"""Tiny shared retry wrapper for Trinetra's live HTTP calls.

Deliberately a per-project copy of glacierwatch/tools/_http.py rather than
an import across projects - every project in this repo is independently
deployable, and trinetra/ ships in its own container (see
Dockerfile.trinetra.webapp, which copies only trinetra/).

Real network calls have real transient failures (a timed-out TLS handshake,
a dropped connection) that have nothing to do with data quality - retrying
the same real request is not fabrication, it's ordinary resilience. This
does not retry on a non-2xx HTTP response (that's a real answer from the
server, not a transient failure) - only on connection-level errors.
"""
from __future__ import annotations

import time
from typing import Callable

import httpx


def get_with_retries(
    request_fn: Callable[[], httpx.Response], attempts: int = 3, backoff_seconds: float = 1.5
) -> httpx.Response:
    last_error: httpx.HTTPError | None = None
    for attempt in range(attempts):
        try:
            return request_fn()
        except httpx.TransportError as exc:
            last_error = exc
            if attempt < attempts - 1:
                time.sleep(backoff_seconds * (attempt + 1))
    raise last_error  # type: ignore[misc]
