"""Unit tests for ``evaluation.leakage``.

These pin the post-feedback leakage detection rules so the eval
harness's primary quality signal cannot silently regress. See
``context/claudeAnalyse.md`` F8 for the production failure that
motivated this.
"""
from __future__ import annotations


def _profile(*, rejected=None, disliked_tracks=None):
    return {
        "artists": {"rejected": rejected or []},
        "feedback": {"disliked_tracks": disliked_tracks or []},
    }


def _track(artist, track):
    return {"artist": artist, "track": track}


class TestRejectedArtistRule:
    def test_flags_track_by_rejected_artist(self):
        from evaluation.leakage import compute_leakage
        report = compute_leakage(
            tracks=[_track("Bad Band", "Some Song")],
            profile=_profile(rejected=[{"name": "Bad Band", "reason": "manual"}]),
        )
        assert report.rejected_artist_count == 1
        assert report.passed is False
        assert report.hits[0].rule == "rejected_artist"
        assert "manual" in report.hits[0].detail

    def test_case_insensitive_match(self):
        from evaluation.leakage import compute_leakage
        report = compute_leakage(
            tracks=[_track("BAD BAND", "Some Song")],
            profile=_profile(rejected=[{"name": "bad band", "reason": "x"}]),
        )
        assert report.rejected_artist_count == 1

    def test_passes_when_artist_not_rejected(self):
        from evaluation.leakage import compute_leakage
        report = compute_leakage(
            tracks=[_track("Good Band", "Some Song")],
            profile=_profile(rejected=[{"name": "Bad Band", "reason": "x"}]),
        )
        assert report.passed is True
        assert report.total_leaks == 0

    def test_legacy_bare_string_rejected_entries(self):
        """Earlier profile schema stored rejected entries as bare strings.
        Make sure we still match those."""
        from evaluation.leakage import compute_leakage
        report = compute_leakage(
            tracks=[_track("Old Band", "Song")],
            profile=_profile(rejected=["Old Band"]),
        )
        assert report.rejected_artist_count == 1


class TestDislikedTrackRule:
    def test_flags_exact_track_reappearance(self):
        from evaluation.leakage import compute_leakage
        report = compute_leakage(
            tracks=[_track("Some Band", "That Song")],
            profile=_profile(disliked_tracks=[
                {"artist": "Some Band", "track": "That Song", "reason": "too slow"},
            ]),
        )
        assert report.disliked_track_count == 1
        hit = report.hits[0]
        assert hit.rule == "disliked_track"
        assert "too slow" in hit.detail

    def test_does_not_flag_different_track_by_same_artist(self):
        from evaluation.leakage import compute_leakage
        report = compute_leakage(
            tracks=[_track("Some Band", "Different Song")],
            profile=_profile(disliked_tracks=[
                {"artist": "Some Band", "track": "Original", "reason": "x"},
            ]),
        )
        assert report.disliked_track_count == 0
        assert report.passed is True


class TestDislikePatternRule:
    def test_threshold_three_distinct_tracks_flags_artist(self):
        """An artist with 3 distinct disliked tracks should trigger
        dislike_pattern even if the artist isn't in artists.rejected
        — guards against an F4 escalation that didn't reach the next
        playlist (e.g. profile not flushed, race condition)."""
        from evaluation.leakage import compute_leakage
        report = compute_leakage(
            tracks=[_track("Pattern Band", "Fourth Song")],
            profile=_profile(disliked_tracks=[
                {"artist": "Pattern Band", "track": "One"},
                {"artist": "Pattern Band", "track": "Two"},
                {"artist": "Pattern Band", "track": "Three"},
            ]),
        )
        assert report.dislike_pattern_count == 1
        assert report.passed is False

    def test_two_dislikes_below_threshold(self):
        from evaluation.leakage import compute_leakage
        report = compute_leakage(
            tracks=[_track("Two Band", "Third Song")],
            profile=_profile(disliked_tracks=[
                {"artist": "Two Band", "track": "One"},
                {"artist": "Two Band", "track": "Two"},
            ]),
        )
        assert report.dislike_pattern_count == 0
        assert report.passed is True

    def test_pattern_rule_skipped_when_artist_already_rejected(self):
        """Don't double-count: if the artist is in artists.rejected,
        rejected_artist fires; dislike_pattern stays silent on the same
        track to keep the hit list clear."""
        from evaluation.leakage import compute_leakage
        report = compute_leakage(
            tracks=[_track("Pattern Band", "Fourth Song")],
            profile=_profile(
                rejected=[{"name": "Pattern Band", "reason": "auto", "auto": True}],
                disliked_tracks=[
                    {"artist": "Pattern Band", "track": "One"},
                    {"artist": "Pattern Band", "track": "Two"},
                    {"artist": "Pattern Band", "track": "Three"},
                ],
            ),
        )
        assert report.rejected_artist_count == 1
        assert report.dislike_pattern_count == 0


class TestLeakageReportShape:
    def test_passed_true_when_no_hits(self):
        from evaluation.leakage import compute_leakage
        report = compute_leakage(
            tracks=[_track("Clean Band", "Clean Song")],
            profile=_profile(),
        )
        assert report.passed is True
        assert report.total_leaks == 0
        assert report.total_tracks == 1
        assert report.hits == []

    def test_to_json_roundtrip_preserves_counts(self):
        from evaluation.leakage import compute_leakage
        report = compute_leakage(
            tracks=[
                _track("Bad Band", "Track 1"),
                _track("Some Band", "That Song"),
            ],
            profile=_profile(
                rejected=[{"name": "Bad Band", "reason": "manual"}],
                disliked_tracks=[
                    {"artist": "Some Band", "track": "That Song", "reason": "x"},
                ],
            ),
        )
        payload = report.to_json()
        assert payload["passed"] is False
        assert payload["total_leaks"] == 2
        assert payload["rejected_artist_count"] == 1
        assert payload["disliked_track_count"] == 1
        assert payload["dislike_pattern_count"] == 0
        assert payload["total_tracks"] == 2
        assert len(payload["hits"]) == 2
        rules = {h["rule"] for h in payload["hits"]}
        assert rules == {"rejected_artist", "disliked_track"}

    def test_handles_malformed_profile(self):
        from evaluation.leakage import compute_leakage
        report = compute_leakage(tracks=[_track("X", "Y")], profile=None)
        assert report.total_tracks == 1
        assert report.passed is True

    def test_handles_malformed_track_entries(self):
        from evaluation.leakage import compute_leakage
        report = compute_leakage(
            tracks=[None, "string", _track("", ""), _track("Real", "Song")],
            profile=_profile(),
        )
        # None and 'string' are skipped silently; ("", "") has empty
        # artist so it contributes nothing.
        assert report.passed is True
        assert report.total_tracks == 4
