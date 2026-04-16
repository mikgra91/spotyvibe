# Rationale chip — few-shot examples

## Example 1
Track: "Hysteria" — Muse
User profile core: theatrical rock, strong bass, high energy
User history: many Queen tracks, 3 Foo Fighters tracks

Output:
{
  "artist": "Muse",
  "title": "Hysteria",
  "rationale": [
    { "type": "profile_match", "arg": "theatrical rock" },
    { "type": "artist_match",  "arg": "Queen" }
  ]
}

## Example 2
Track: "Running Up That Hill" — Kate Bush (2022 remaster)
User profile: melodic, cinematic, haunting vocals
Filters active: energy 60-90%

Output:
{
  "artist": "Kate Bush",
  "title": "Running Up That Hill",
  "rationale": [
    { "type": "profile_match", "arg": "haunting vocals" },
    { "type": "audio_match",   "arg": "energy 60-90%" }
  ]
}

