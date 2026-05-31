"""Unit tests for taste aggregation (Wave 3)."""

from core.src.taste import aggregate_taste


def test_aggregate_empty_runs():
    result = aggregate_taste([])
    assert result["tracks_considered"] == 0
    assert result["runs_considered"] == 0
    assert result["neutral"]["top_genres"] == []
    assert result["neutral"]["energy_valence"] == []
    assert result["neutral"]["decades"] == []


def test_aggregate_deduplicates_tracks():
    runs = [
        {"tracks": [
            {"artist": "Muse", "track": "Hysteria", "genres": ["rock"]},
            {"artist": "muse", "track": "hysteria", "genres": ["rock"]},  # duplicate
        ]},
    ]
    result = aggregate_taste(runs)
    assert result["tracks_considered"] == 1


def test_aggregate_top_genres():
    runs = [
        {"tracks": [
            {"artist": f"A{i}", "track": f"T{i}", "genres": ["rock", "indie"]}
            for i in range(5)
        ]},
    ]
    result = aggregate_taste(runs)
    genres = {g["genre"]: g["count"] for g in result["neutral"]["top_genres"]}
    assert genres["rock"] == 5
    assert genres["indie"] == 5


def test_aggregate_decades():
    runs = [
        {"tracks": [
            {"artist": "A1", "track": "T1", "release_year": 1995},
            {"artist": "A2", "track": "T2", "release_year": 2001},
            {"artist": "A3", "track": "T3", "release_year": 2005},
        ]},
    ]
    result = aggregate_taste(runs)
    decade_map = {d["decade"]: d["count"] for d in result["neutral"]["decades"]}
    assert decade_map["1990s"] == 1
    assert decade_map["2000s"] == 2


def test_aggregate_energy_valence():
    runs = [
        {"tracks": [
            {"artist": "A1", "track": "T1", "energy": 0.8, "valence": 0.6},
            {"artist": "A2", "track": "T2"},  # missing features — skipped
        ]},
    ]
    result = aggregate_taste(runs)
    assert len(result["neutral"]["energy_valence"]) == 1
    assert result["neutral"]["energy_valence"][0]["energy"] == 0.8


def test_aggregate_caps_energy_valence_at_100():
    runs = [
        {"tracks": [
            {"artist": f"A{i}", "track": f"T{i}", "energy": 0.5, "valence": 0.5}
            for i in range(150)
        ]},
    ]
    result = aggregate_taste(runs)
    assert len(result["neutral"]["energy_valence"]) == 100


def test_aggregate_genres_capped_to_8():
    runs = [
        {"tracks": [
            {"artist": f"A{i}", "track": f"T{i}", "genres": [f"genre{i}"]}
            for i in range(20)
        ]},
    ]
    result = aggregate_taste(runs)
    assert len(result["neutral"]["top_genres"]) <= 8


def test_aggregate_sentiment_slicing():
    """Tracks are bucketed into neutral/liked/disliked slices."""
    runs = [
        {"tracks": [
            {"artist": "A1", "track": "T1", "genres": ["rock"], "sentiment": "neutral"},
            {"artist": "A2", "track": "T2", "genres": ["pop"], "sentiment": "liked"},
            {"artist": "A3", "track": "T3", "genres": ["metal"], "sentiment": "disliked"},
            {"artist": "A4", "track": "T4", "genres": ["jazz"]},  # missing → neutral
        ]},
    ]
    result = aggregate_taste(runs)
    assert result["tracks_considered"] == 4
    assert result["neutral"]["tracks_considered"] == 2
    assert result["liked"]["tracks_considered"] == 1
    assert result["disliked"]["tracks_considered"] == 1
    assert result["liked"]["top_genres"][0]["genre"] == "pop"
    assert result["disliked"]["top_genres"][0]["genre"] == "metal"


# ── Feedback-store merge (the dashboard bug fix, 2026-05-31) ──────────

def test_feedback_appears_without_any_runs():
    """Likes/dislikes given on suggestions/previews show up even when no
    playlist run was ever saved (the reported '0 tracks from 0 runs' bug)."""
    profile = {"feedback": {
        "liked_tracks": [{"artist": "Muse", "track": "Hysteria"}],
        "disliked_tracks": [{"artist": "Nickelback", "track": "Photograph"}],
    }}
    result = aggregate_taste([], profile=profile)
    assert result["runs_considered"] == 0
    assert result["tracks_considered"] == 2
    assert result["liked"]["top_artists"][0]["artist"] == "Muse"
    assert result["disliked"]["top_artists"][0]["artist"] == "Nickelback"


def test_feedback_sentiment_overrides_run_and_borrows_metadata():
    """A track that is 'neutral' in a run but liked in feedback moves to the
    liked slice, keeping the run's rich metadata (genres)."""
    runs = [{"tracks": [
        {"artist": "Muse", "track": "Hysteria", "genres": ["alternative rock"],
         "sentiment": "neutral", "release_year": 2003},
    ]}]
    profile = {"feedback": {"liked_tracks": [{"artist": "muse", "track": "hysteria"}],
                            "disliked_tracks": []}}
    result = aggregate_taste(runs, profile=profile)
    assert result["liked"]["tracks_considered"] == 1
    assert result["neutral"]["tracks_considered"] == 0
    # Run metadata is preserved, so the genre + decade charts populate.
    assert result["liked"]["top_genres"][0]["genre"] == "alternative rock"
    assert result["liked"]["decades"][0]["decade"] == "2000s"


def test_no_profile_preference_genre_fallback():
    """must_have / soft_preferences vibe phrases must NOT appear as genres."""
    profile = {
        "preferences": {
            "must_have": ["rich vocal harmonies", "momentous song progression"],
            "soft_preferences": ["upbeat energy"],
        },
        "feedback": {"liked_tracks": [{"artist": "A1", "track": "T1"}],
                     "disliked_tracks": []},
    }
    result = aggregate_taste([], profile=profile)
    # The liked track has no genre data → genre chart is empty, NOT the
    # profile's vibe phrases.
    assert result["liked"]["top_genres"] == []
    assert result["neutral"]["top_genres"] == []

