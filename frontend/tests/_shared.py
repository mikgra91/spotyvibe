"""Canonical mock-profile fixtures shared across frontend test modules.

Both `helpers.py` (page-load tests) and `helpers_integration.py`
(workflow-integration tests) re-export these so existing imports
(`from helpers import EMPTY_PROFILE`, `from helpers_integration import
TRAINED_PROFILE`) keep working unchanged. Defining the fixtures once here
prevents subtle drift between the two helper files.
"""

EMPTY_PROFILE = {
    "meta": {},
    "preferences": {
        "core_description": "",
        "must_have": [],
        "soft_preferences": [],
        "avoid": [],
    },
    "artists": {"confirmed": [], "moderate": [], "rejected": []},
    "taste_rules": {},
    "feedback": {"liked_tracks": [], "disliked_tracks": [], "disliked_artists": []},
    "suggested_artists": [],
    "suggested_tracks": [],
}

TRAINED_PROFILE = {
    **EMPTY_PROFILE,
    "preferences": {
        "core_description": "Upbeat theatrical rock with strong melodies",
        "must_have": ["high energy", "strong melodies"],
        "soft_preferences": ["slight prog influence"],
        "avoid": ["electronic production"],
    },
    "last_updated": "2025-01-01T00:00:00",
}
