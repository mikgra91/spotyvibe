"""Synthetic model-behaviour probes (Track B).

Cheap, deterministic, Spotify-free micro-probes that fingerprint how a
model reads instructions BEFORE a full eval is spent. See next-steps.md
§"Research Track B" for the motivation and §B.1 for the probe catalogue.

Public entry point: ``python -m evaluation.probes ...`` (see cli.py).
Programmatic entry point: ``evaluation.probes.runner.run_battery``.
"""
