---
title: Spotify-Entwickler-App erstellen
subtitle: Ein kostenloses Spotify-Entwicklerkonto mit eigenen App-Zugangsdaten.
---

## Step 1 — Spotify Developer Dashboard öffnen
Gehe zu [developer.spotify.com/dashboard](https://developer.spotify.com/dashboard) und melde dich mit deinem Spotify-Konto an (oder erstelle eines, falls du noch keins hast).
![Spotify Developer Dashboard](/docs/guides/spotify/step1_dashboard.png)

## Step 2 — Neue App erstellen
Klicke auf **Create app**. Gib einen beliebigen Namen (z.B. `SpotyVibe`) und eine Beschreibung ein. Wähle **Web API** als zu verwendende API.
![App erstellen](/docs/guides/spotify/step2_create.png)

## Step 3 — Redirect URI eintragen
Füge diese exakte URL in das Feld **Redirect URIs** ein und klicke **Add**:

```copy
http://127.0.0.1:5000/callback
```

Dies teilt Spotify mit, wohin die Authentifizierungsantwort zurück an SpotyVibe gesendet werden soll.
![Redirect URI](/docs/guides/spotify/step3_redirect.png)

## Step 4 — Client ID und Secret kopieren
Nach dem Erstellen der App siehst du die **Client ID** auf der Übersichtsseite der App. Klicke auf **Show client secret**, um das Secret anzuzeigen. Kopiere beide Werte und füge sie in SpotyVibe ein.
![Client ID und Secret](/docs/guides/spotify/step4_secret.png)

