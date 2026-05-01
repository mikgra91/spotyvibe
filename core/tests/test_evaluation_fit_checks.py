"""Unit tests for ``evaluation.fit_checks``.

Pin the deterministic per-track fit-check rules so the eval harness
quality signal cannot silently regress. F8.3 (2026-05-01).
"""
from __future__ import annotations


def _profile(avoid):
    """Build a profile shell with the given avoid prose (str or list)."""
    return {"preferences": {"avoid": avoid}}


def _track(artist, title, *, release_year=None, release_date=None):
    t = {"artist": artist, "track": title}
    if release_year is not None:
        t["release_year"] = release_year
    if release_date is not None:
        t["release_date"] = release_date
    return t


class TestDecadeAvoidCheck:
    def test_no_decade_in_avoid_means_check_not_applied(self):
        from evaluation.fit_checks import compute_fit
        report = compute_fit(
            tracks=[_track("Some Band", "Some Song", release_year=1985)],
            profile=_profile("avoid generic radio pop and EDM"),
        )
        # No decade keyword in avoid prose → check is a no-op.
        assert report.checks_applied == []
        assert report.passed is True
        assert report.total_fails == 0

    def test_short_form_80s_avoid_flags_1980s_track(self):
        from evaluation.fit_checks import compute_fit
        report = compute_fit(
            tracks=[_track("Synth Band", "Eighties Hit", release_year=1985)],
            profile=_profile("avoid 80s production style"),
        )
        assert "decade_avoid" in report.checks_applied
        assert report.decade_avoid_count == 1
        assert report.passed is False
        hit = report.hits[0]
        assert hit.rule == "decade_avoid"
        assert "1985" in hit.detail
        assert "1980s" in hit.detail

    def test_long_form_1980s_avoid_flags_1980s_track(self):
        from evaluation.fit_checks import compute_fit
        report = compute_fit(
            tracks=[_track("Vintage Band", "Old Song", release_year=1988)],
            profile=_profile("avoid 1980s arena rock"),
        )
        assert report.decade_avoid_count == 1
        assert report.passed is False

    def test_track_outside_avoided_decade_passes(self):
        from evaluation.fit_checks import compute_fit
        report = compute_fit(
            tracks=[
                _track("Modern Band", "New Song", release_year=2024),
                _track("Other Band", "Newer", release_year=2010),
            ],
            profile=_profile("avoid 80s production style"),
        )
        assert report.decade_avoid_count == 0
        assert report.passed is True

    def test_release_date_string_fallback(self):
        """release_year may be missing if Spotify hasn't enriched yet —
        fall back to parsing release_date prefix."""
        from evaluation.fit_checks import compute_fit
        report = compute_fit(
            tracks=[_track("X", "Y", release_date="1987-04-12")],
            profile=_profile("avoid 80s feel"),
        )
        assert report.decade_avoid_count == 1

    def test_unknown_year_gets_benefit_of_the_doubt(self):
        from evaluation.fit_checks import compute_fit
        report = compute_fit(
            tracks=[_track("X", "Y")],  # no year info at all
            profile=_profile("avoid 80s feel"),
        )
        # Check applied (avoid mentions a decade), but track without
        # year info passes — same convention as the production
        # emerging-only filter.
        assert report.checks_applied == ["decade_avoid"]
        assert report.decade_avoid_count == 0
        assert report.passed is True

    def test_avoid_as_list_form(self):
        """preferences.avoid can be a list of strings (some scenarios
        store it that way) — the check must handle both shapes."""
        from evaluation.fit_checks import compute_fit
        report = compute_fit(
            tracks=[_track("X", "Y", release_year=1995)],
            profile=_profile([
                "Electronic music",
                "80s production style",
                "American artists",
            ]),
        )
        # 90s avoid not in prose → 1995 track passes despite check applied.
        assert report.checks_applied == ["decade_avoid"]
        assert report.decade_avoid_count == 0

    def test_short_form_not_substring_of_long_form(self):
        """`80s` appears as substring in `1980s` — our regex must NOT
        double-count or false-fire on the embedded 80s. Without the
        word-boundary guard we'd extract `80s` from `1980s` text and
        report two decades."""
        from evaluation.fit_checks import compute_fit
        report = compute_fit(
            tracks=[_track("X", "Y", release_year=1985)],
            profile=_profile("avoid 1980s sound"),
        )
        # Both 80s and 1980s map to the same (1980, 1989) decade, so
        # one hit, not two.
        assert report.decade_avoid_count == 1

    def test_multiple_decades_in_avoid_flag_correctly(self):
        from evaluation.fit_checks import compute_fit
        report = compute_fit(
            tracks=[
                _track("A", "1", release_year=1975),  # 70s — flag
                _track("B", "2", release_year=1985),  # 80s — flag
                _track("C", "3", release_year=2005),  # clean
            ],
            profile=_profile("avoid 70s and 80s arena rock"),
        )
        assert report.decade_avoid_count == 2

    def test_to_json_shape(self):
        from evaluation.fit_checks import compute_fit
        report = compute_fit(
            tracks=[_track("X", "Y", release_year=1985)],
            profile=_profile("avoid 80s sound"),
        )
        payload = report.to_json()
        assert payload["passed"] is False
        assert payload["total_fails"] == 1
        assert payload["decade_avoid_count"] == 1
        assert payload["total_tracks"] == 1
        assert payload["checks_applied"] == ["decade_avoid"]
        assert len(payload["hits"]) == 1
        assert payload["hits"][0]["rule"] == "decade_avoid"

    def test_handles_malformed_input(self):
        from evaluation.fit_checks import compute_fit
        report = compute_fit(
            tracks=[None, "string", _track("", "", release_year=1985)],
            profile=_profile("avoid 80s"),
        )
        # All malformed entries are skipped silently.
        assert report.passed is True
        assert report.total_tracks == 3
