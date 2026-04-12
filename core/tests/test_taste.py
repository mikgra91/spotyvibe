"""Unit tests for taste aggregation (Wave 3)."""

from core.src.taste import aggregate_taste


def test_aggregate_empty_runs():
    result = aggregate_taste([])
    assert result["tracks_considered"] == 0
    assert result["runs_considered"] == 0
    assert result["top_genres"] == []
    assert result["energy_valence"] == []
    assert result["decades"] == []


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
    genres = {g["genre"]: g["count"] for g in result["top_genres"]}
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
    decade_map = {d["decade"]: d["count"] for d in result["decades"]}
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
    assert len(result["energy_valence"]) == 1
    assert result["energy_valence"][0]["energy"] == 0.8


def test_aggregate_caps_energy_valence_at_100():
    runs = [
        {"tracks": [
            {"artist": f"A{i}", "track": f"T{i}", "energy": 0.5, "valence": 0.5}
            for i in range(150)
        ]},
    ]
    result = aggregate_taste(runs)
    assert len(result["energy_valence"]) == 100


def test_aggregate_genres_capped_to_8():
    runs = [
        {"tracks": [
            {"artist": f"A{i}", "track": f"T{i}", "genres": [f"genre{i}"]}
            for i in range(20)
        ]},
    ]
    result = aggregate_taste(runs)
    assert len(result["top_genres"]) <= 8

