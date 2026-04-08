# TODO — SpotyVibe

## Features

### Suggest New Artists from Spotify
- [ ] Add a feature that suggests new/similar artists based on the user's taste profile using Spotify's recommendation or related-artists API.
- [ ] Could complement the existing GPT-based suggestion pipeline with pure Spotify data.

### Tab Groups Instead of Scrollbar
- [ ] Replace the current vertical scroll-based section navigation with a tabbed UI (tab groups).
- [ ] Each major section (Profile, Generate, Review, Analysis, History) becomes a tab.
- [ ] Eliminates the need for the scroll-based jump bubble and long-page scrolling.

## UX / UI Improvements

### Default Theme — Without Movement
- [ ] Provide a static/calm default theme that has no background animations or particle movement.
- [ ] Users who want motion can opt into an animated theme explicitly.

### Move Theme Picker to the Bottom
- [ ] Relocate the theme picker/switcher to the bottom of the page (or into a less prominent position).
- [ ] Currently it feels like a primary UI component; it should be secondary/cosmetic.

### Pagination in Quickstart — Remove on Top
- [ ] Remove the top pagination in the quickstart guide; keep only the bottom pagination.
- [ ] Simplifies the quickstart layout.

### Move Feedback/Retry to a Different Help Container After Profile Creation
- [ ] Once the user has created a music profile, relocate the feedback/retry controls into a separate help or utility container.
- [ ] Avoids cluttering the main workflow area post-profile-creation.

## i18n / Wording

### "Musik entdecken", "Playlist verfeinern" — German UI Shows English Text
- [ ] The German translation (`de.json`) incorrectly uses the English word "Show" instead of the German "Anzeigen" for these labels.
- [ ] Find and fix affected keys in `de.json` so the German UI reads "Anzeigen" (or another proper German verb).
- [ ] Verify `en.json` counterparts are correct.

## Data / History

### Reset History = Reset Last Change
- [ ] The "Reset History" action should undo only the last change (single-step undo) rather than wiping the entire history.
- [ ] Rename or clarify the button label to match the new behavior (e.g., "Undo Last Change").
