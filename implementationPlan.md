SpotyVibe UI Restructure + Spotify Metadata Integration Plan
1. Objective
Replace the current Step 1 / Step 2 UI model with two clear top-level provider sections:

OpenAI
Spotify
This improves usability by grouping features by service/provider responsibility instead of workflow sequence.

Also add a new Spotify Metadata Analysis feature to the Spotify section, allowing users to analyze artists/tracks using Spotify metadata APIs.

2. Target UX Structure
New top-level layout
OpenAI Summary Container
Purpose: everything powered primarily by GPT / taste understanding

Contains:

OpenAI credential/config status
selected model
GPT language
profile readiness / last trained
Taste Profile editor
AI Profile Update
existing Band/Song AI Analysis (/api/analyze)
Spotify Summary Container
Purpose: everything powered primarily by Spotify

Contains:

Spotify credentials/auth status
connect/disconnect action
new Spotify Metadata Analysis
playlist generation controls
playlist mode selector
audio filters
run history / undo
3. Information Architecture Changes
Current
Step 1 — Taste Profile
Step 2 — Generate Playlist
New
Section: OpenAI

Summary header
Profile tools
AI analysis tools
Section: Spotify

Summary header
Spotify metadata analysis
Playlist generation
History / undo
Important UX rule
Generate Playlist remains under Spotify, but should show dependency cues:

OpenAI ready: yes/no
Spotify connected: yes/no
This keeps the logic understandable:

OpenAI = learns and analyzes
Spotify = inspects, verifies, and saves music
4. UI Component Plan
4.1 OpenAI Summary Container
Header summary content
status chip: OpenAI key configured / missing
status chip: profile trained / not trained
status chip: model name
status chip: GPT language
helper text:
“Use OpenAI to define your music taste and analyze reference songs.”
Body sections
Taste Profile
existing edit profile UI
save / AI profile update
import/export/reset
AI Band/Song Analysis
existing /api/analyze
keep copy-to-clipboard suggestions
4.2 Spotify Summary Container
Header summary content
status chip: Spotify credentials configured / missing
status chip: Spotify connected / not authenticated / authenticated
status chip: playlist ready yes/no
helper text:
“Use Spotify to inspect music metadata and create playlists.”
Body sections
Spotify Metadata Analysis
Generate Playlist
Audio Filters
Run History
5. New Spotify Metadata Feature
5.1 User-facing purpose
Allow user to input:

artist only
track only
artist + track
Return:

artist metadata
track metadata
audio features if available
warnings if unavailable
This is a factual Spotify-based complement to the existing GPT-based analysis.

5.2 UX placement
Add a new collapsible card under the Spotify container:

Spotify Metadata Analysis
Fields:

Artist input
Track input
Market select/input, default US
Analyze button
Result blocks:

Match summary
Track metadata
Artist metadata
Audio features
Warnings / low-confidence notice
6. Backend Architecture Changes
6.1 New module
Create:

core/spotify_metadata.py
Purpose:

client credentials auth for Spotify metadata endpoints
search and scoring
track/artist lookup
best-effort audio-features fetch
normalized response formatting
6.2 Separation from playlist OAuth
Do not reuse playlist user OAuth flow.

Keep metadata lookup separate from core/playlist.py because:

playlist functions use user OAuth
metadata lookup should work with Spotify app credentials only
no Spotify user login should be required for metadata lookup
7. Spotify Metadata API Plan for Flask
7.1 New endpoint
Add:

POST /api/spotify/metadata/analyze
Request:

{
  "artist": "The Weeknd",
  "track": "Blinding Lights",
  "market": "US"
}
Reason for POST:

aligns with current Flask API style
avoids confusion with existing POST /api/analyze
7.2 Response schema
{
  "query": {
    "artist": "The Weeknd",
    "track": "Blinding Lights",
    "market": "US"
  },
  "match": {
    "provider": "spotify",
    "type": "track",
    "confidence": 0.98,
    "processed_at": "2026-03-31T18:50:00Z",
    "spotify_track_id": "0VjIjW4GlUZAMYd2vXMi3b",
    "spotify_artist_id": "1Xyo4u8uXC1ZmMpatF05PJ"
  },
  "track": {},
  "artist": {},
  "audio_features": {},
  "warnings": []
}
7.3 Search strategy
Use fielded search:

both → track:{track} artist:{artist}
track only → track:{track}
artist only → artist:{artist}
Rules:

if track exists, search type=track
if only artist, search type=artist
request limit=5
default market=US
7.4 String normalization
Before scoring:

lowercase
trim whitespace
collapse repeated spaces
strip suffixes like:
- remastered
(live)
[2024 mix]
(deluxe edition) for comparison only
Do not alter displayed Spotify values.

7.5 Scoring heuristic
For top 5 candidates:

exact normalized track match: +0.6
exact normalized artist match: +0.3
popularity tie-breaker: + popularity / 1000
If only artist search:

exact normalized artist match is primary
popularity is secondary
If score is below threshold:

return best result
include warning: "low_confidence_match"
7.6 Fetch strategy
After choosing best match:

Track flow
Fetch:

/v1/tracks/{id}
/v1/artists/{primaryArtistId}
/v1/audio-features/{id} best effort
Artist-only flow
Fetch:

/v1/artists/{id}
Optional future enhancement:

/v1/artists/{id}/top-tracks?market=US
7.7 Authentication
Use Spotify Client Credentials Flow in core/spotify_metadata.py

Requirements:

reuse stored SPOTIFY_CLIENT_ID
reuse stored SPOTIFY_CLIENT_SECRET
Implementation:

cache token in memory
refresh before expiry
protect refresh with lock
7.8 Error handling
missing both artist and track → 400
no match → 404
audio-features 403/404 → audio_features: null + warning
low confidence → 200 + warning
rate limit 429 → respect Retry-After + retry with backoff
8. Flask File-Level Change Plan
Backend
app.py
add POST /api/spotify/metadata/analyze
validate request payload
call core.spotify_metadata.analyze_metadata()
return normalized JSON
core/spotify_metadata.py
Implement:

get_client_credentials_token()
spotify_api_request()
normalize_compare_text()
strip_version_suffixes()
search_track_candidates()
search_artist_candidates()
score_track_candidate()
score_artist_candidate()
get_track_metadata()
get_artist_metadata()
get_audio_features_safe()
analyze_metadata()
tests/
Add:

tests/test_spotify_metadata.py
Test:

query normalization
suffix stripping
candidate scoring
artist-only request
track request
low confidence behavior
audio-features failure fallback
Frontend Templates
Likely impacted:

frontend/templates/base.html
relevant partial templates for profile/generate/analysis areas
Refactor layout:

remove “Step 1” / “Step 2” labels
introduce:
.provider-section.provider-openai
.provider-section.provider-spotify
each gets:
summary header
status pills
description
body blocks
Frontend JS
Likely impacted:

frontend/static/js/main.js
existing modules for auth / profile / pipeline / analysis
add new module:
frontend/static/js/modules/spotify-metadata.js
Responsibilities:

submit metadata analysis form
render result cards
handle loading/error states
show warnings
preserve current generate flow unchanged
Optional helper:

provider-summary.js for refreshing OpenAI/Spotify summary chips from existing status endpoints
CSS
Update static/css/styles.css

Add styles for:

provider summary containers
status pills
subsection cards
metadata result grid
warning badges
confidence indicator
Keep current dark glass design language.

i18n
Update:

static/i18n/en.json
static/i18n/de.json
Add keys for:

OpenAI summary labels
Spotify summary labels
metadata analysis form
metadata result labels
warnings:
low confidence
audio features unavailable
no result
credentials missing
9. Documentation Changes
Technical Manual
Update:

UI layout description from step-based to provider-based
add core/spotify_metadata.py
add POST /api/spotify/metadata/analyze
User Manual
Update:

replace “Step 1 / Step 2” framing
add:
OpenAI section
Spotify section
add subsection:
Spotify Metadata Analysis
explain audio-features access caveat
10. UX Copy Recommendation
OpenAI
Subtitle:
Define your taste profile and analyze reference music with AI.

Spotify
Subtitle:
Inspect track metadata, control playlists, and save generated music to Spotify.

Spotify Metadata Analysis
Helper text:
Look up artist, track, popularity, genres, and audio features from Spotify metadata.

11. Important Product Rules
Do not remove the existing GPT-based /api/analyze feature.
Do not merge GPT analysis and Spotify metadata into one endpoint.
Present them as complementary:
OpenAI analysis = interpretive / descriptive
Spotify metadata = factual / platform metadata
Keep playlist generation behavior unchanged.
Keep Spotify metadata lookup available even if user is not Spotify-user-authenticated, as long as Spotify app credentials exist.
12. Structured Checklist for Claude Sonnet 4.6
Instructions for Claude
Use checkbox markers in-place:

[ ] = not implemented
[x] = implemented
When completing work, update each task by replacing [ ] with [x].

Phase 1 — UI Restructure
[x] Replace “Step 1 / Step 2” labels with provider-based sections: OpenAI and Spotify
[x] Add summary headers for both sections with helper text
[x] Add status pills to OpenAI section
[x] Add status pill for OpenAI key configured
[x] Add status pill for profile trained
[ ] Add status pill for selected model
[ ] Add status pill for GPT language
[x] Add status pills to Spotify section
[x] Add status pill for Spotify credentials configured
[x] Add status pill for Spotify auth state
[x] Add status pill for playlist readiness/dependency state
[x] Move existing Taste Profile UI under OpenAI section
[x] Move existing GPT Band/Song Analysis UI under OpenAI section
[x] Move existing Generate Playlist UI under Spotify section
[x] Move existing Audio Filters UI under Spotify section
[x] Move existing Run History UI under Spotify section
[x] Preserve current functionality and existing event wiring after layout move

Phase 2 — Spotify Metadata Backend
[x] Create core/spotify_metadata.py
[x] Implement Spotify Client Credentials token flow
[x] Add in-memory token cache with expiry handling
[x] Add lock protection for token refresh
[x] Implement sanitized fielded search
[x] Implement artist-only flow
[x] Implement track flow
[x] Implement normalization helper for comparison
[x] Implement suffix stripping for scoring only
[x] Implement top-5 candidate scoring
[x] Implement low-confidence warning behavior
[x] Implement best-effort audio-features fetch
[x] Handle 403/404 audio-features without failing request
[x] Handle 429 retry with Retry-After
[x] Normalize output to canonical schema

Phase 3 — Flask API Integration
[x] Add POST /api/spotify/metadata/analyze to app.py
[x] Validate JSON input: at least one of artist or track
[x] Default market to US
[x] Return proper status codes for 400 / 404 / 500
[x] Return warnings for low-confidence and restricted audio-features

Phase 4 — Frontend Spotify Metadata UI
[x] Add Spotify Metadata Analysis card to Spotify section
[x] Add artist input
[x] Add track input
[x] Add market input/select
[x] Add analyze button
[x] Add loading state
[x] Add error state
[x] Render match summary
[x] Render track metadata block
[x] Render artist metadata block
[x] Render audio features block
[x] Render warnings block
[x] Keep UI responsive for tablet and phone layouts

Phase 5 — Styling
[x] Add provider section styles
[x] Add summary chip styles
[x] Add subsection card styles
[x] Add metadata result grid styles
[x] Add confidence badge styles
[x] Add warning badge styles
[x] Ensure visual consistency with existing dark glass design
[x] Verify reduced-motion compatibility

Phase 6 — Translation / Copy
[x] Add new i18n keys in en.json
[x] Add new i18n keys in de.json
[x] Update old step-based copy to provider-based copy
[x] Add labels for Spotify Metadata Analysis
[x] Add warning/error translations

Phase 7 — Documentation
[x] Update Technical Manual UI section from steps to provider containers
[x] Add core/spotify_metadata.py documentation
[x] Add POST /api/spotify/metadata/analyze to endpoint list
[x] Update User Manual to explain new OpenAI / Spotify grouping
[x] Add user guide section for Spotify Metadata Analysis

Phase 8 — Testing
[x] Add unit tests for string normalization
[x] Add unit tests for suffix stripping
[x] Add unit tests for candidate scoring
[x] Add unit tests for artist-only metadata lookup
[x] Add unit tests for track lookup
[x] Add unit tests for low-confidence warning
[x] Add unit tests for audio-features 403/404 fallback
[x] Smoke test UI interactions after layout refactor
[x] Verify existing playlist generation still works
[x] Verify existing GPT analysis still works

13. Acceptance Criteria
[x] UI no longer presents the app as Step 1 / Step 2
[x] UI clearly presents two top-level provider sections: OpenAI and Spotify
[x] Existing profile training still works
[x] Existing GPT analysis still works
[x] Existing playlist generation still works
[x] New Spotify Metadata Analysis works with artist only
[x] New Spotify Metadata Analysis works with track only
[x] New Spotify Metadata Analysis works with artist + track
[x] Metadata lookup does not require Spotify user login
[x] Audio-features failure does not break metadata response
[x] User can clearly distinguish AI analysis vs Spotify metadata analysis
[x] Manuals and translations are updated

14. Recommended Naming
Use these exact labels:

OpenAI
Spotify
Taste Profile
AI Band/Song Analysis
Spotify Metadata Analysis
Generate Playlist
Audio Filters
Run History