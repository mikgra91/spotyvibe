"""Controlled vocabulary for AI corpus tag-enrichment.

The single most important design decision in tag enrichment: the model
must pick from a FIXED taxonomy, not free-form. Free-form produces
"quirky" for one artist and "zany"/"eccentric" for its twin — no tag
overlap, so similarity stays broken. A closed vocabulary forces the
same word for the same concept across every artist, which is what makes
tag-overlap similarity work.

v2 (2026-05-30): expanded from the rock-centric v1 (~180 terms) to cover
all major genre families. The 500-artist long-tail validation showed v1
hitting 18-37% out-of-vocabulary on the general corpus (the model
correctly wanted death metal / lo-fi hip hop / k-pop / latin / techno
tags that v1 omitted, then dropped the genre or returned empty). v2
targets < 5% OOV across the whole corpus while preserving the fine
scene granularity that the seed-band neighbourhood needs.

Terms are grouped only for readability; the model receives the flat
union. Bump VOCABULARY_VERSION whenever the term set changes so the
overlay's source-hash gating re-enriches against the new vocabulary.
"""

VOCABULARY_VERSION = "3"

# ── Rock & its scenes ───────────────────────────────────────────────
ROCK = [
    "rock", "classic rock", "hard rock", "soft rock", "alternative rock",
    "indie rock", "art rock", "progressive rock", "psychedelic rock",
    "garage rock", "surf rock", "blues rock", "folk rock", "country rock",
    "southern rock", "glam rock", "arena rock", "stoner rock", "math rock",
    "noise rock", "post-rock", "krautrock", "space rock", "jam band",
    "roots rock", "heartland rock", "adventure rock", "theatrical rock",
    "experimental rock", "gothic rock", "new wave", "post-punk",
    "power pop", "pop rock", "pop punk", "emo", "midwest emo", "emo pop",
    "easycore", "post-hardcore", "swancore", "screamo", "hardcore punk",
    "punk", "punk rock", "ska", "ska punk", "grunge", "post-grunge",
    "britpop", "shoegaze", "slacker rock", "jangle pop", "visual kei",
    "j-rock", "k-rock", "indie surf",
    # v3 additions (genuine discriminative gaps seen in 2000-run OOV)
    "experimental", "noise", "psychedelic", "neo-psychedelia",
    "psychedelic pop", "hardcore", "avant-garde", "indietronica",
]

# ── Metal ───────────────────────────────────────────────────────────
METAL = [
    "metal", "heavy metal", "thrash metal", "death metal",
    "melodic death metal", "black metal", "doom metal", "death-doom metal",
    "sludge metal", "stoner metal", "power metal", "progressive metal",
    "symphonic metal", "folk metal", "gothic metal", "nu metal",
    "alternative metal", "metalcore", "deathcore", "grindcore",
    "industrial metal", "groove metal", "speed metal", "djent", "mathcore",
    # v3 additions
    "brutal death metal", "technical death metal", "melodic black metal",
    "atmospheric black metal", "post-metal", "blackened death metal",
]

# ── Hip hop / rap ───────────────────────────────────────────────────
HIPHOP = [
    "hip hop", "rap", "boom bap", "trap", "drill", "gangsta rap",
    "conscious hip hop", "alternative hip hop", "lo-fi hip hop",
    "instrumental hip hop", "cloud rap", "emo rap", "pop rap", "jazz rap",
    "g-funk", "crunk", "grime", "uk drill", "old school hip hop",
    "west coast hip hop", "east coast hip hop", "southern hip hop",
    "experimental hip hop", "phonk",
]

# ── Electronic ──────────────────────────────────────────────────────
ELECTRONIC = [
    "electronic", "edm", "house", "deep house", "tech house",
    "progressive house", "techno", "trance", "dubstep",
    "drum and bass", "breakbeat", "ambient", "downtempo", "trip hop",
    "idm", "synthwave", "vaporwave", "chillwave", "electropop",
    "synthpop", "future bass", "electro", "uk garage", "jungle",
    "hardstyle", "glitch", "lo-fi", "chiptune", "industrial", "ebm",
    "darkwave", "electronic rock", "electronica",
    # v3 additions
    "synth-pop", "electro house", "psy-trance", "future garage",
]

# ── Pop ─────────────────────────────────────────────────────────────
POP = [
    "pop", "dance-pop", "art pop", "dream pop", "hyperpop", "bedroom pop",
    "baroque pop", "chamber pop", "teen pop", "bubblegum pop",
    "sophisti-pop", "city pop", "indie pop", "latin pop", "country pop",
    "adult contemporary", "alt-pop", "alternative pop",
]

# ── R&B / soul / funk / disco ───────────────────────────────────────
SOUL_FUNK = [
    "r&b", "contemporary r&b", "neo soul", "soul", "motown", "funk",
    "p-funk", "disco", "boogie", "quiet storm", "new jack swing",
    "gospel", "doo-wop", "afrobeat", "alternative r&b",
]

# ── Jazz / blues ────────────────────────────────────────────────────
JAZZ_BLUES = [
    "jazz", "smooth jazz", "jazz fusion", "bebop", "swing", "big band",
    "free jazz", "cool jazz", "hard bop", "nu jazz", "acid jazz",
    "blues", "delta blues", "chicago blues", "electric blues",
    # v3 additions
    "contemporary jazz", "post-bop", "jazz funk",
]

# ── Folk / country / americana ──────────────────────────────────────
FOLK_COUNTRY = [
    "folk", "indie folk", "contemporary folk", "freak folk", "country",
    "alt-country", "americana", "bluegrass", "outlaw country", "roots",
    "celtic", "singer-songwriter",
]

# ── Classical / instrumental / score ────────────────────────────────
CLASSICAL_SCORE = [
    "classical", "contemporary classical", "neoclassical", "baroque",
    "orchestral", "chamber music", "opera", "instrumental", "soundtrack",
    "film score", "video game music", "new age", "minimalism", "piano",
]

# ── World / regional ────────────────────────────────────────────────
WORLD = [
    "latin", "reggaeton", "salsa", "bossa nova", "samba", "cumbia",
    "bachata", "reggae", "dancehall", "dub", "afrobeats", "amapiano",
    "highlife", "k-pop", "j-pop", "c-pop", "mandopop", "cantopop",
    "enka", "bollywood", "bhangra", "flamenco", "fado", "chanson",
    "schlager", "arabesque", "world", "anison",
]

# ── Mood / character ────────────────────────────────────────────────
MOOD_CHARACTER = [
    "upbeat", "melancholic", "energetic", "aggressive", "playful",
    "quirky", "theatrical", "dramatic", "anthemic", "introspective",
    "dark", "bright", "whimsical", "humorous", "intense", "laid-back",
    "uplifting", "bittersweet", "nostalgic", "romantic", "angsty",
    "cathartic", "epic", "eclectic", "genre-bending", "chaotic",
    "polished", "raw", "complex", "catchy", "hook-driven", "feel-good",
    "atmospheric", "groovy", "hypnotic", "sentimental",
]

# ── Vocal style ─────────────────────────────────────────────────────
VOCAL_STYLE = [
    "vocal harmonies", "gang vocals", "clean vocals", "screamed vocals",
    "harsh vocals", "rapped vocals", "spoken word", "falsetto",
    "melodic vocals", "layered vocals", "call-and-response",
    "shouted vocals", "soft vocals", "powerful vocals", "dual vocals",
    "autotuned vocals", "growled vocals", "operatic vocals",
    "female vocals", "male vocals", "instrumental (no vocals)",
]

# ── Instrumentation / production ────────────────────────────────────
INSTRUMENTATION_PRODUCTION = [
    "guitar-driven", "riff-heavy", "synth-heavy", "piano-led",
    "brass section", "orchestral arrangement", "string arrangements",
    "twinkly guitars", "distorted guitars", "technical guitar",
    "driving bass", "prominent bass", "electronic production",
    "lo-fi production", "dense production", "layered production",
    "acoustic", "horn-driven", "ambient textures", "sample-based",
    "808 bass", "drum machine",
]

# ── Rhythm / structure / tempo ──────────────────────────────────────
RHYTHM_STRUCTURE = [
    "high-energy", "danceable", "driving rhythm", "fast tempo",
    "mid-tempo", "slow tempo", "odd time signatures",
    "frequent tempo shifts", "complex song structures",
    "build-and-release dynamics", "breakdowns", "syncopated", "ballad",
    "four-on-the-floor",
]

# ── Era ─────────────────────────────────────────────────────────────
ERA = [
    "60s", "70s", "80s", "90s", "2000s", "2010s", "2020s",
    "modern production", "retro production",
]

VOCABULARY = (
    ROCK + METAL + HIPHOP + ELECTRONIC + POP + SOUL_FUNK + JAZZ_BLUES
    + FOLK_COUNTRY + CLASSICAL_SCORE + WORLD + MOOD_CHARACTER
    + VOCAL_STYLE + INSTRUMENTATION_PRODUCTION + RHYTHM_STRUCTURE + ERA
)

# Sanity: no duplicates (a dup would silently shrink coverage).
_dupes = [t for t in set(VOCABULARY) if VOCABULARY.count(t) > 1]
assert not _dupes, f"duplicate vocab terms: {_dupes}"

if __name__ == "__main__":
    print(f"Vocabulary v{VOCABULARY_VERSION}: {len(VOCABULARY)} terms")
