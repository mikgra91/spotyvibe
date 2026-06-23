"""Translatable errors that surface to the UI.

Backend code raises ``TranslatableError`` with an i18n key + English fallback;
Flask handlers serialise it via :func:`as_response_payload` so the frontend
can call ``i18n(error_key, error)``.
"""

from __future__ import annotations

from typing import Any


class TranslatableError(Exception):
    """An error whose message is meant to be shown to the user.

    The ``key`` is a stable i18n lookup key (must exist in en/de/jp.json).
    ``message`` is the English fallback used when the key is missing.
    ``params`` are interpolated by the frontend (``{name}`` placeholders).
    ``status_code`` lets Flask handlers map a single error type to the
    correct HTTP status without an extra except branch.
    ``error_class`` (U2) tags the failure as ``"transient"`` (e.g. upstream
    rate-limit / timeout — the user can simply retry) or ``"permanent"``
    (a real configuration / data problem). Frontend renders the two
    differently (⏳ vs ❌).
    """

    def __init__(
        self,
        key: str,
        message: str,
        *,
        params: dict[str, Any] | None = None,
        status_code: int = 400,
        error_class: str = "permanent",
    ) -> None:
        super().__init__(message)
        self.key = key
        self.message = message
        self.params = dict(params) if params else None
        self.status_code = status_code
        self.error_class = error_class


def as_response_payload(exc: BaseException) -> dict[str, Any]:
    """Build the JSON payload returned by Flask error handlers.

    Always includes ``error`` (the English fallback). Adds ``error_key`` and
    optional ``error_params`` when *exc* is a :class:`TranslatableError` or
    carries a ``key`` attribute (so the OpenAI error subclasses tagged with
    ``key`` flow through the same path).
    """
    payload: dict[str, Any] = {"error": str(exc)}
    key = getattr(exc, "key", None)
    if isinstance(key, str) and key:
        payload["error_key"] = key
        params = getattr(exc, "params", None)
        if isinstance(params, dict) and params:
            payload["error_params"] = params
    error_class = getattr(exc, "error_class", None)
    if isinstance(error_class, str) and error_class in ("transient", "permanent"):
        payload["error_class"] = error_class
    return payload
