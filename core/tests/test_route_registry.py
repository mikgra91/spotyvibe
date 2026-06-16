"""WS8 — no duplicate (rule, method) registrations.

A route decorator applied twice (the F9 finding) is silently collapsed by
Flask but is a maintenance hazard. This enumerates the URL map and fails
if any (rule, method) pair is registered more than once.
"""
from __future__ import annotations

from collections import Counter

from app import app


def test_no_duplicate_route_method_pairs():
    pairs = []
    for rule in app.url_map.iter_rules():
        for method in (rule.methods or set()):
            if method in {"HEAD", "OPTIONS"}:
                continue  # auto-added by Flask
            pairs.append((str(rule), method))
    dupes = [p for p, n in Counter(pairs).items() if n > 1]
    assert not dupes, f"Duplicate route/method registrations: {dupes}"
