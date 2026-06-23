"""Generic AI-tag exclusion set for retrieval indexing.

The AI enrichment overlay (``ai_tags_overlay.json``) tags each artist with
8-15 controlled-vocabulary terms spanning genre, scene, vocal style, mood,
rhythm, instrumentation, and era. Only the **discriminative** subset
(genre / scene / vocal) belongs in the retrieval tag space — those are the
terms that separate one artist's neighbourhood from another's.

The **generic** terms below (mood / rhythm / era / instrumentation) are
shared by huge swaths of the corpus, so indexing them would bloat posting
lists and dilute precision — exactly what the enrichment scaling study
found (``evaluation/enrichment_probe/FINDINGS.md`` §1: similarity runs on
``base ∪ AI-discriminative``; the generic facets are kept as metadata but
excluded from the similarity space).

⚠ Keep this in sync with the generic categories in
``evaluation/enrichment_probe/vocabulary.py`` (MOOD_CHARACTER,
RHYTHM_STRUCTURE, ERA, INSTRUMENTATION_PRODUCTION). VOCAL_STYLE is
deliberately *not* here — vocal style is discriminative.
"""

from __future__ import annotations

# Mood / character
_MOOD = {
    "upbeat", "melancholic", "energetic", "aggressive", "playful", "quirky",
    "theatrical", "dramatic", "anthemic", "introspective", "dark", "bright",
    "whimsical", "humorous", "intense", "laid-back", "uplifting", "bittersweet",
    "nostalgic", "romantic", "angsty", "cathartic", "epic", "eclectic",
    "genre-bending", "chaotic", "polished", "raw", "complex", "catchy",
    "hook-driven", "feel-good", "atmospheric", "groovy", "hypnotic",
    "sentimental",
}

# Rhythm / structure / tempo
_RHYTHM = {
    "high-energy", "danceable", "driving rhythm", "fast tempo", "mid-tempo",
    "slow tempo", "odd time signatures", "frequent tempo shifts",
    "complex song structures", "build-and-release dynamics", "breakdowns",
    "syncopated", "ballad", "four-on-the-floor",
}

# Era
_ERA = {
    "60s", "70s", "80s", "90s", "2000s", "2010s", "2020s",
    "modern production", "retro production",
}

# Instrumentation / production
_INSTRUMENTATION = {
    "guitar-driven", "riff-heavy", "synth-heavy", "piano-led", "brass section",
    "orchestral arrangement", "string arrangements", "twinkly guitars",
    "distorted guitars", "technical guitar", "driving bass", "prominent bass",
    "electronic production", "lo-fi production", "dense production",
    "layered production", "acoustic", "horn-driven", "ambient textures",
    "sample-based", "808 bass", "drum machine",
}

# Normalised forms compared against ``normalise_tag(ai_tag)`` at index time.
# The vocabulary terms are already lowercase/clean so this is ~identity, but
# the set is the single source of truth for "do NOT index this AI tag".
GENERIC_AI_TAGS: frozenset[str] = frozenset(_MOOD | _RHYTHM | _ERA | _INSTRUMENTATION)
