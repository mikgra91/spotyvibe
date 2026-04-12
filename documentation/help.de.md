# SpotyVibe Benutzerhandbuch

Willkommen bei **SpotyVibe** — deinem KI-gestützten Musikentdeckungs-Assistenten.
Diese Anleitung erklärt, wie du die **SpotyVibe-Oberfläche** nutzt, um deine Vorlieben einzurichten, Spotify zu verbinden, Playlists zu generieren und Empfehlungen zu verfeinern.

---

## Inhaltsverzeichnis

- [Datenschutz — Was dein Gerät verlässt](#datenschutz--was-dein-gerät-verlässt)
- [Erste Schritte](#erste-schritte)
- [Kontoeinrichtung](#kontoeinrichtung)
- [Benutzereinstellungen](#benutzereinstellungen)
- [Musikprofil](#musikprofil)
- [Playlist generieren](#playlist-generieren)
- [Playlist verfeinern](#playlist-verfeinern)
- [Band-/Song-Analyse](#band-song-analyse)
- [Verlauf](#verlauf)
- [Fehlerbehebung](#fehlerbehebung)

---

## Datenschutz — Was dein Gerät verlässt

| Ziel | Was gesendet wird | Warum |
|------|-------------------|-------|
| **OpenAI API** | Dein Geschmacksprofil (JSON), Vorschlags-Verlauf, Feedback-Zusammenfassung | Vorschläge generieren, Profil trainieren, Analyse |
| **Spotify API** | OAuth-Token, Track-Suchen, Playlist-Änderungen | Tracks verifizieren, Playlists verwalten |
| **Nirgendwo sonst** | Keine Telemetrie, keine Tracking-Pixel, kein externes Analytics | — |

Deine API-Schlüssel werden im OS-Schlüsselbund gespeichert (Windows Credential Manager / macOS Keychain). Keine Daten werden an SpotyVibe-Server oder Dritte gesendet.

---

## Erste Schritte

### Übersicht

SpotyVibe ist in zwei Hauptbereiche unterteilt:

- **OpenAI** — Geschmacksprofil-Training und KI-gestützte Band-/Song-Analyse
- **Spotify** — Musik entdecken (Playlist-Generierung), Playlist verfeinern, Verlauf

### Voraussetzungen

1. **OpenAI API-Schlüssel** — von [platform.openai.com/api-keys](https://platform.openai.com/api-keys)
2. **Spotify-Zugangsdaten** — Client ID und Secret von [developer.spotify.com/dashboard](https://developer.spotify.com/dashboard)
3. **Redirect URI** — `http://127.0.0.1:5000/callback` muss in deinem Spotify-Dashboard eingetragen sein

---

## Kontoeinrichtung

### Menü öffnen

Klicke auf das **☰ Menü** (Zahnrad-Symbol) oben rechts, um auf Zugangsdaten, Einstellungen, Hilfe und Schnellstart zuzugreifen.

### Zugangsdaten eingeben

1. Öffne ☰ → **🔑 Zugangsdaten**
2. Gib deinen **OpenAI API-Schlüssel** ein
3. Gib deine **Spotify Client ID** und **Client Secret** ein
4. Klicke **Speichern**

### Spotify verbinden

1. Nachdem die Zugangsdaten gespeichert sind, erscheint ein „Mit Spotify verbinden"-Banner
2. Klicke darauf, um dich bei Spotify anzumelden und SpotyVibe Zugriff zu gewähren
3. Der Status wechselt auf „Verbunden ✓"

---

## Benutzereinstellungen

### Einstellungen

Öffne ☰ → **⚙️ Einstellungen** um zu konfigurieren:

- **Anbieter** — Wähle deinen KI-Anbieter (OpenAI, Ollama, LM Studio, Groq, OpenRouter oder Custom)
- **Verwendetes Modell** — Welches KI-Modell deine Vorschläge generiert
- **Kostenschätzung** — Ungefähre Kosten pro Generierung
- **Playlist-Größe** — Wie viele Tracks generiert werden (10–30)
- **Neue Künstler %** — Mindestanteil neuer Künstler in jeder Generation
- **GPT-Sprache** — In welcher Sprache die KI antwortet
- **Debug-Modus** — Protokollierung für Fehlerbehebung (nur Desktop)

### Sprache

Die Oberfläche ist in Englisch und Deutsch verfügbar. Wechsle über das Sprachmenü unten auf der Seite.

### Design

Wähle zwischen verschiedenen Hintergrund-Designs über die Design-Umschalter unter dem Seitentitel.

---

## Musikprofil

### Profil erstellen

1. Wähle ein bestehendes Profil oder erstelle ein neues über das Dropdown
2. Gib deinen Musikgeschmack in die strukturierten Felder ein:
   - **Beschreibe deinen Vibe** — Freie Beschreibung, was du suchst
   - **Kernbeschreibung** — Grundlage deines Sounds
   - **Muss enthalten** — Nicht verhandelbare Anforderungen
   - **Weiche Präferenzen** — Wünschenswert, aber nicht zwingend
   - **Vermeiden** — Absolute Ausschlusskriterien

### Profil speichern

- **Direkt speichern** — Deine Eingaben werden direkt gespeichert
- **KI-Profil-Update** — Die KI analysiert und strukturiert deine Eingaben

### Profil aus Playlist erstellen

Du kannst ein Profil aus einer bestehenden Spotify-Playlist erstellen:
1. Öffne das ⋯-Menü → **Aus Playlist erzeugen**
2. Wähle eine Playlist aus dem Picker
3. SpotyVibe analysiert die Playlist und erstellt einen Profil-Entwurf
4. Überprüfe und speichere den Entwurf

### Profil importieren/exportieren

- **⬆ Hochladen** — Profil aus einer JSON-Datei importieren
- **⬇ Exportieren** — Profil als JSON-Datei herunterladen
- **↩ Zurücksetzen** — Letzte Änderung rückgängig machen

---

## Playlist generieren

### Generierungsmodi

- **Erstellen** — Immer eine neue Playlist anlegen
- **Anhängen** — Tracks zu einer bestehenden Playlist hinzufügen
- **Ersetzen** — Bestehende Playlist leeren und neu befüllen

### Audio-Filter

Optionale Filter für: Energie, Valence, Tempo, Tanzbarkeit, Akustik.
Lass sie leer, damit die KI frei wählen kann.

### Generierung starten

1. Konfiguriere Modus, Filter und optionalen Playlist-Namen
2. Klicke **▶ Generieren**
3. Verfolge den Fortschritt im SSE-Stream
4. Verwende **▶ X Tracks verwenden** um früh abzubrechen mit aktuellen Ergebnissen

### Erklärbare Empfehlungen

Jeder vorgeschlagene Track zeigt 1–2 Begründungs-Chips:
- **passt zu „Genre"** — Stimmt mit deinem Profil überein
- **ähnlich zu Künstler** — Verwandt mit einem bekannten Künstler
- **Entdeckung** — Bewusster Vielfalt-Pick

---

## Playlist verfeinern

Lade eine bestehende Spotify-Playlist und bewerte Tracks ohne zu generieren:
- 👍 **Gefällt mir** — Zur Geschmacksdatenbank hinzufügen
- 👎 **Gefällt mir nicht** — Aus der Playlist entfernen und Feedback speichern
- ✕ **Entfernen** — Entfernen ohne Feedback

---

## Band-/Song-Analyse

Gib einen Künstler und optional einen Track ein. Die KI liefert:
- Genre-Klassifizierung
- Stil-Tags
- Musikalische Merkmale
- Geschätzte Audio-Features
- Profilvorschläge

---

## Geschmacks-Dashboard

Unter dem Profil-Editor zeigt ein einklappbares Dashboard drei Diagramme:
- **Top-Genres** — Donut-Diagramm deiner häufigsten Genres
- **Energie × Valence** — Streudiagramm der Stimmung deiner Tracks
- **Jahrzehnte** — Balkendiagramm der Veröffentlichungsjahrzehnte

Benötigt mindestens 10 einzigartige Tracks aus deinem Verlauf.

---

## Verlauf

Zeigt vergangene Generierungs-Läufe mit Playlist-Link, Zeitstempel und Track-Liste. Die letzten 5 Läufe werden gespeichert.

---

## Spracherkennung

Im „Beschreibe deinen Vibe"-Textfeld erscheint ein 🎤 **Sprechen**-Button (nur Desktop-Browser). Klicke zum Starten, erneut zum Stoppen. Die Transkription wird an der Cursor-Position eingefügt.

---

## Fehlerbehebung

| Problem | Lösung |
|---------|--------|
| „Spotify-Zugangsdaten fehlen" | Öffne ☰ → Zugangsdaten und gib Client ID und Secret ein |
| „Bitte trainiere zuerst dein Geschmacksprofil" | Beschreibe deinen Musikgeschmack im OpenAI-Bereich |
| Spotify-Anmeldung schlägt fehl | Überprüfe Client ID/Secret und Redirect URI |
| „403 Forbidden" bei Generierung | Spotify-Sitzung abgelaufen — erneut verbinden |
| „OpenAI API-Schlüssel nicht konfiguriert" | Öffne ☰ → Zugangsdaten und gib den API-Schlüssel ein |
| Die meisten Tracks „auf Spotify nicht gefunden" | Erneut generieren — jeder Durchlauf ergibt andere Ergebnisse |
| App startet nicht | `pip install -r requirements.txt` ausführen, Python 3.10+ verwenden |

