---
title: Spotify-Entwickler-App erstellen
subtitle: Ein kostenloses Spotify-Entwicklerkonto mit eigenen App-Zugangsdaten.
---

## Step 1 — Bei Spotify for Developers anmelden
Gehe zu [developer.spotify.com](https://developer.spotify.com) und klicke oben rechts auf **Log in**.
![Log-in-Button auf der Spotify-for-Developers-Seite](/docs/guides/spotify/step1_login.png)

Melde dich mit deinem normalen Spotify-Konto an — oder klicke unten auf **Sign up**, falls du noch keins hast.
![Spotify-Anmeldeformular](/docs/guides/spotify/step2_login_form.png)

## Step 2 — Dashboard öffnen
Klicke oben rechts auf deinen Profilnamen und wähle **Dashboard** aus dem Menü.
![Profilmenü mit dem Eintrag Dashboard](/docs/guides/spotify/step3_dashboard_menu.png)

## Step 3 — Neue App erstellen
Klicke im Dashboard auf **Create app**.
![Create-app-Button im Dashboard](/docs/guides/spotify/step4_create_app.png)

## Step 4 — App-Details und Redirect URI eintragen
Gib der App einen beliebigen Namen (z.B. `SpotyVibe`) und eine Beschreibung. Füge dann diese exakte URL in das Feld **Redirect URIs** ein und klicke **Add**:

```copy
http://127.0.0.1:5000/callback
```

Dies teilt Spotify mit, wohin die Authentifizierungsantwort zurück an SpotyVibe gesendet werden soll. Wähle unter **Which API/SDKs are you planning to use?** die Option **Web API**, akzeptiere die Entwicklerbedingungen und speichere die App.
![App-Formular mit Redirect URI und ausgewählter Web API](/docs/guides/spotify/step5_app_form.png)

## Step 5 — Client ID und Secret kopieren
Auf der Einstellungsseite der App siehst du die **Client ID**. Klicke auf **Show client secret**, um das Secret anzuzeigen. Kopiere beide Werte und füge sie in SpotyVibe ein.
![Felder Client ID und Client secret auf der App-Einstellungsseite](/docs/guides/spotify/step6_credentials.png)
