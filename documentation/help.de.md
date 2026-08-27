# SpotyVibe Benutzerhandbuch

Willkommen bei **SpotyVibe** — deinem KI-gestützten Musikentdeckungs-Assistenten.
Diese Anleitung erklärt, wie du die **SpotyVibe-Oberfläche** nutzt, um deine Vorlieben einzurichten, Spotify zu verbinden, Playlists zu generieren und Empfehlungen im Laufe der Zeit zu verfeinern.

---

## Wähle ein Thema

<div class="help-tiles">
  <a class="help-tile" href="#account-setup">
    <span class="help-tile-title">1. Zugangsdaten einrichten</span>
    <span class="help-tile-desc">OpenAI- und Spotify-Schlüssel speichern und Spotify verbinden.</span>
  </a>
  <a class="help-tile" href="#music-profile">
    <span class="help-tile-title">2. Musikprofil erstellen</span>
    <span class="help-tile-desc">Beschreibe deinen Geschmack, damit die KI passende Tracks vorschlägt.</span>
  </a>
  <a class="help-tile" href="#playlist-generation">
    <span class="help-tile-title">3. Playlists generieren</span>
    <span class="help-tile-desc">Modus wählen, Filter feinjustieren und eine neue Playlist erstellen.</span>
  </a>
  <a class="help-tile" href="#refine-playlist">
    <span class="help-tile-title">4. Verfeinern und bewerten</span>
    <span class="help-tile-desc">Tracks liken, disliken oder verwerfen, um dein Profil zu schärfen.</span>
  </a>
  <a class="help-tile" href="#troubleshooting--tips">
    <span class="help-tile-title">5. Fehlerbehebung</span>
    <span class="help-tile-desc">Häufige Probleme und abschließende Tipps.</span>
  </a>
</div>

**Nachschlagen**

<ul class="help-reference-list">
  <li><a href="#privacy--what-leaves-your-device">Datenschutz</a></li>
  <li><a href="#getting-started">Erste Schritte</a></li>
  <li><a href="#user-preferences">Benutzereinstellungen</a></li>
  <li><a href="#discovery--analysis">Band-/Song-Analyse</a></li>
  <li><a href="#discover-artists">Künstler entdecken</a></li>
  <li><a href="#track-review--feedback">Track-Bewertung &amp; Feedback</a></li>
  <li><a href="#taste-dashboard">Geschmacks-Dashboard</a></li>
  <li><a href="#song-list--run-history">Songliste &amp; Lauf-Verlauf</a></li>
  <li><a href="#mobile-usage">Mobile Nutzung</a></li>
</ul>

---

<a id="privacy--what-leaves-your-device"></a>
## Datenschutz — Was dein Gerät verlässt

SpotyVibe speichert deine Schlüssel und dein Geschmacksprofil auf deinem Gerät. Wenn du eine Playlist generierst, wird dein Geschmacksprofil an OpenAI gesendet (um Vorschläge zu erhalten) und die Songtitel werden an Spotify gesendet (um sie zu verifizieren und zu speichern). Mehr wird nicht übertragen.

| Daten | Auf dem Gerät | An OpenAI | An Spotify |
|-------|---------------|-----------|------------|
| API-Schlüssel | ✓ | — | — |
| Geschmacksprofil (Text) | ✓ | ✓ (pro Generierung) | — |
| Song-Bewertungen | ✓ | ✓ (pro Generierung) | — |
| Vorgeschlagene Songtitel | ✓ | — | ✓ (Suche / Hinzufügen) |
| Hörverlauf | — | — | ✓ (einmal gelesen) |

Gilt für die Standard-Einrichtung von SpotyVibe. Eigene LLM-Endpunkte können Daten anders verarbeiten.

---

<a id="getting-started"></a>
## Erste Schritte

<a id="overview"></a>
### Übersicht

SpotyVibe hilft dir, Musik basierend auf deinem persönlichen Geschmack zu entdecken.
Du beschreibst, was dir gefällt, verbindest dein Spotify-Konto und lässt die App auf dich zugeschnittene Playlist-Vorschläge generieren.

Je mehr Feedback du gibst, desto besser werden die Empfehlungen.

SpotyVibe läuft auf **Windows**, **macOS** und **Linux**. Unter Windows läuft es als native Desktop-App (PyInstaller-Executable). Auf macOS und Linux installierst du das Python-Paket (`pip install spotyvibe-*.whl`) und führst `spotyvibe` aus — der Server startet und öffnet automatisch deinen Browser.

![Hauptbildschirm](/docs/screenshots/01_main_home_screen.png)

---

<a id="before-you-start"></a>
### Voraussetzungen

Um SpotyVibe zu nutzen, benötigst du:

- Ein **Spotify Premium**-Konto
- Deinen **OpenAI API-Schlüssel**
- Deine **Spotify Client ID**
- Dein **Spotify Client Secret**

Du gibst diese Daten während der Einrichtung in der App ein.

![Zugangsdaten-Bildschirm](/docs/screenshots/24_onboarding_credentials.png)

---

<a id="understanding-the-main-screen"></a>
### Die Hauptansicht verstehen

Wenn du SpotyVibe öffnest, siehst du die Hauptoberfläche mit zwei Anbieterbereichen:

- **OpenAI** — Geschmacksprofil-Editor, KI-Profil-Updates und KI-Band-/Song-Analyse.
- **Spotify** — Playlist-Generierung, Playlist-Verfeinerung und Lauf-Verlauf.

Status-Anzeigen oben in jedem Bereich zeigen, ob deine Zugangsdaten konfiguriert und verbunden sind. Im Kopfbereich befindet sich zusätzlich ein kleines **Spotify-Status-Pill** — ein farbiger Punkt (grün = verbunden, rot = nicht verbunden, grau = unbekannt) neben dem Wort „Spotify". Klick darauf verbindet bzw. trennt; der Status aktualisiert sich, sobald der Tab wieder fokussiert wird.

Jede Hauptkomponente ist **auf-/zuklappbar**. Du kannst auf die Bereichsüberschrift (irgendwo im Titelbereich) oder den Ein-/Ausblenden-Button klicken, um sie auf- oder zuzuklappen. Eine kurze Beschreibung unter jedem Titel erklärt, was die Komponente tut.

Jede Bereichsüberschrift hat auch ein kleines **?**-Hilfe-Symbol. Klicke darauf, um diese Anleitung direkt zum relevanten Abschnitt geöffnet zu bekommen.

Die Hauptansicht ist in aufklappbare Komponenten unterteilt, gruppiert unter zwei Anbieterbereichen:

**OpenAI-Bereich:**
- **🎯 Musikprofil** — Definiere deinen Musikgeschmack — Genres, Stimmungen, Muss-Kriterien und Ausschlüsse.
- **🔍 Band-/Song-Analyse** — Erhalte eine KI-gestützte Analyse eines beliebigen Künstlers oder Tracks mit kopierfertigen Profilvorschlägen.

**Spotify-Bereich:**
- **🎧 Tracks entdecken** — Erstelle KI-gestützte Playlists und speichere sie direkt in deinem Spotify-Konto. Enthält ein optionales **Audio-Filter**-Panel, um Vorschläge nach Stimmung einzugrenzen. *(Standardmäßig zugeklappt.)*
- **🔄 Playlist verfeinern** — Lade eine bestehende Playlist und gib Track-für-Track-Feedback, um dein Geschmacksprofil zu verfeinern. *(Standardmäßig zugeklappt.)*
- **🕓 Verlauf** — Vergangene Generierungs-Läufe anzeigen.

Der allgemeine Ablauf ist:

1. Menü öffnen und Einrichtung abschließen
2. Musikprofil erstellen oder verfeinern
3. Playlist generieren
4. Songs bewerten und Feedback geben
5. Wiederholen, um künftige Empfehlungen zu verbessern

Am oberen Seitenrand kannst du außerdem zugreifen auf:

- Das **Menü**
- Die **Sprachauswahl**
- Die **Design-Auswahl**

![Header mit Menü-, Sprach- und Design-Steuerung](/docs/screenshots/02_header_controls.png)

---

<a id="quick-start-guide"></a>
### Schnellstart-Anleitung

Wenn du SpotyVibe zum ersten Mal öffnest, erscheint automatisch eine **Schnellstart-Anleitung** für den aktiven Anbieterbereich. Die Anleitung ist in zwei anbieterspezifische Varianten aufgeteilt:

- **🤖 OpenAI-Schnellstart** — Einrichtung, Profil erstellen, Wiederholen & Verbessern.
- **🎵 Spotify-Schnellstart** — Einrichtung, Playlist generieren, Bewerten & Feedback, Bestehende Playlists verfeinern, Wiederholen & Verbessern.

Jede Variante zeigt nur die für ihren Anbieter relevanten Schritte und hat ihre eigene „Nicht mehr anzeigen"-Einstellung.

**Die Anleitung verwenden:**

- Die **Inhaltsseite** listet nur die Schritte für den aktiven Anbieter. Klicke auf einen Eintrag, um direkt zu diesem Schritt zu springen.
- Jeder Schritt hat eine Textbeschreibung, eine **Wichtige Aktionen**-Checkliste und eine **interaktive Demo**, die genau zeigt, was in der App zu klicken ist.
- Die Demos spielen automatisch ab — nutze **▶/⏸** zum Pausieren oder **‹ / ›** zum manuellen Durchblättern.
- Verwende die **nummerierten Punkte** oder **Zurück / Weiter**-Buttons am unteren Rand, um zwischen Schritten zu navigieren.
- Beim letzten Schritt wird **Weiter** zu **Los geht's** und schließt die Anleitung.

**Ausblenden und erneut öffnen:**

- Aktiviere **„Nicht mehr anzeigen"** auf einer beliebigen Seite, damit die Anleitung dieses Anbieters bei zukünftigen Besuchen nicht mehr erscheint.
- Wenn du zum ersten Mal in einer Sitzung zum anderen Anbieter wechselst, wird dessen Anleitung automatisch angezeigt (sofern nicht ausgeblendet).
- Um sie jederzeit erneut zu öffnen, klicke auf **☰ → 🚀 Schnellstart** (öffnet die Anleitung für den aktuell aktiven Anbieter).

![Schnellstart-Anleitung Inhaltsseite](/docs/screenshots/26_quickstart_toc.png)

---

<a id="account-setup"></a>
## Kontoeinrichtung

<a id="open-the-menu"></a>
### Menü öffnen

Klicke auf das **☰ Menü-Symbol** (Hamburger-Menü) oben rechts, um das Menü zu öffnen.

Von hier aus erreichst du:

- **Zugangsdaten**
- **Einstellungen**
- **Spotify trennen** (wenn bereits verbunden)

![Menü geöffnet](/docs/screenshots/03_burger_menu_open.png)

---

<a id="enter-your-credentials"></a>
### Zugangsdaten eingeben

Öffne **Zugangsdaten** und gib ein:

- **OpenAI API-Schlüssel**
- **Spotify Client ID**
- **Spotify Client Secret**

Klicke auf **Speichern**, wenn du fertig bist. Deine API-Schlüssel werden sicher im Schlüsselbund deines Betriebssystems gespeichert (z. B. Windows Credential Manager) — sie werden niemals als Klartext gespeichert. App-Einstellungen (Modell, Playlist-Größe usw.) werden in einer separaten Einstellungsdatei gespeichert.

Wenn die Angaben korrekt sind, kannst du mit der Spotify-Verbindung fortfahren.

![Zugangsdaten-Formular](/docs/screenshots/04_credentials_modal.png)

---

<a id="connect-your-spotify-account"></a>
### Spotify-Konto verbinden

Nachdem du deine Zugangsdaten gespeichert hast, fordert SpotyVibe dich auf, Spotify zu verbinden.

Klicke auf **Mit Spotify verbinden** und schließe den Anmeldeprozess ab.

Nach der Verbindung:

- Das Verbindungs-Banner verschwindet
- Du kannst Playlists generieren
- SpotyVibe kann Playlists für dich erstellen und verwalten

Falls deine Sitzung später abläuft, verbinde dich einfach erneut.

![Mit Spotify verbinden Banner](/docs/screenshots/27_connect_spotify_banner.png)

---

<a id="user-preferences"></a>
## Benutzereinstellungen

<a id="settings"></a>
### Einstellungen

Öffne **Einstellungen** über das Menü, um SpotyVibe nach deinen Wünschen anzupassen.

Verfügbare Einstellungen:

- **Modell-Strategie für Vorschläge**
  Wähle, wie SpotyVibe das Modell bestimmt: **Schnell** (immer das günstige Mini), **Beste** (immer Premium), **Automatisch** (günstig bis du Feedback gegeben hast, danach Premium) oder **Benutzerdefiniert** (verwendet das unten ausgewählte Modell — nötig für lokale LLMs).

- **Verwendetes Modell**
  Wähle, welches KI-Modell SpotyVibe verwendet. Ausgegraut, sofern die Strategie oben nicht auf **Benutzerdefiniert** steht.

- **Playlist-Größe**
  Lege fest, wie viele Tracks SpotyVibe generieren soll.

- **Neue Künstler %**
  Bestimme, wie stark SpotyVibe Künstler bevorzugt, die du noch nicht gehört hast.

- **ChatGPT-Sprache**
  Wähle die Sprache für KI-generierte Erklärungen und Profil-Updates.

- **KI-generierte Musik filtern** *(optional)*  
  Wenn aktiviert, entfernt SpotyVibe jeden vorgeschlagenen Titel, dessen Künstler auf einer von der Community gepflegten Sperrliste KI-generierter Acts steht (Abgleich über die Spotify-Künstler-ID). Standardmäßig deaktiviert. Die Sperrliste muss zuerst heruntergeladen werden — nutze die Schaltfläche **Jetzt herunterladen** unter dieser Option. Nach der Installation zeigt die Zeile die installierte Version, und die Schaltfläche wird zu **Nach Update suchen**; die Sperrliste wird unabhängig vom Kandidaten-Korpus aktualisiert, du musst also nie auf einen Korpus-Neubau warten. Die Daten stammen aus dem Open-Source-Projekt [spotify-ai-blocker](https://github.com/CennoxX/spotify-ai-blocker) (MIT).

Klicke nach Änderungen auf **Speichern**.

![Einstellungen-Panel](/docs/screenshots/05_settings_modal.png)

---

<a id="language"></a>
### Sprache

Verwende die **Sprachauswahl** oben auf der Seite, um die Oberflächensprache zu wechseln.

Dies ändert Texte wie:

- Buttons
- Beschriftungen
- Meldungen
- Menüs

![Sprachauswahl](/docs/screenshots/06_language_selector.png)

---

<a id="theme"></a>
### Design

SpotyVibe enthält mehrere visuelle Designs.

Verwende den **Design-Umschalter** oben auf der Seite, um dein bevorzugtes Aussehen auszuwählen.

Designs ändern den visuellen Stil der Oberfläche, beeinflussen aber nicht die Playlist-Ergebnisse.

![Design-Umschalter](/docs/screenshots/07_theme_switcher.png)

---

<a id="music-profile"></a>
## Musikprofil

<a id="create-your-music-profile"></a>
### Musikprofil erstellen

Bevor SpotyVibe gute Empfehlungen generieren kann, musst du ihm deinen Geschmack beibringen.

Klicke im **OpenAI**-Bereich auf **Profil bearbeiten** oder irgendwo auf die **Musikprofil**-Überschrift, um den Profil-Editor aufzuklappen.

Der Editor ist in **aufklappbare Akkordeon-Panels** organisiert. Klicke auf eine Panel-Überschrift, um es auf- oder zuzuklappen. Das erste Panel — **Profile** — dient der Verwaltung deiner Profile.

![Musikprofil-Editor mit Akkordeon-Panels](/docs/screenshots/08_profile_editor_open.png)

---

<a id="select-or-create-a-profile"></a>
#### Profil auswählen oder erstellen

Das **👤 Profile**-Akkordeon ist das erste Panel im Editor. Es enthält ein Dropdown und einen Erstellen-Button.

1. Klicke auf **+ Neues Profil erstellen** unter dem Dropdown.
2. Gib einen Namen ein — z. B. „Workout", „Chill" oder „Entdeckung" — und drücke **Enter** oder klicke **✓**. Namen können bis zu 40 Zeichen lang sein.
3. Das neue Profil wird automatisch ausgewählt und ist bereit zur Bearbeitung.

Du kannst beliebig viele Profile erstellen. Jedes Profil ist vollständig unabhängig — ideal für verschiedene Stimmungen, Aktivitäten oder Familienmitglieder.

Um Profile zu wechseln, wähle ein anderes aus dem Dropdown. Die Formularfelder aktualisieren sich automatisch beim Wechsel.

![Profile-Akkordeon mit Dropdown und Erstelleingabe](/docs/screenshots/09_profiles_accordion.png)

---

<a id="profile-status"></a>
#### Profilstatus

Unter der Bereichsüberschrift siehst du eine Statuszeile:

- **✓ Zuletzt trainiert: [Datum/Uhrzeit]** — Das Profil wurde mindestens einmal gespeichert oder KI-aktualisiert. Dies zeigt, wann die letzte Speicherung stattfand, nicht wie gut das Profil ist.
- **⚠ Noch nicht trainiert** — Das Profil wurde noch nie gespeichert. Beschreibe deinen Geschmack und speichere, um loszulegen.

![Profilstatus-Anzeigen](/docs/screenshots/10_profile_status.png)

---

<a id="describe-your-vibe"></a>
#### Beschreibe deinen Vibe

Das **💬 Beschreibe deinen Vibe**-Akkordeon ist der schnellste Weg, SpotyVibe mitzuteilen, was du suchst.

Schreibe in Alltagssprache — wie in einem Gespräch mit einem Freund — welche Art von Musik du möchtest. Zum Beispiel:

- „Ich liebe energetischen Rock mit theatralischem Gesang wie Queen. Überrasche mich mit etwas Neuem, aber halte es energiegeladen und melodisch!"
- „Mehr Jazz-Einfluss, weniger Elektronik. Denke Snarky Puppy trifft Radiohead."
- „Mach mein Profil dunkler und härter, aber behalte die Melodien."

**Intelligente Klassifizierung:** Wenn du **KI-Profil-Update** verwendest, speichert SpotyVibe deinen Text nicht einfach — es **klassifiziert automatisch** jeden Teil deiner Nachricht und leitet ihn an den korrekten Profilbereich weiter. Die KI erkennt natürliche Auslösephrasen:

| Was du schreibst | Wohin es kommt |
|---|---|
| „muss starken Bass haben", „braucht kräftigen Gesang" | → **Muss vorhanden sein** |
| „kein Autotune", „keine langsamen Songs", „ohne Synths" | → **Vermeiden** |
| „wäre schön, Jazz-Einfluss zu haben", „idealerweise etwas Prog-Elemente" | → **Weiche Präferenzen** |
| Allgemeine Geschmacksbeschreibungen, Genre/Stimmung/Energie | → **Kernbeschreibung** |

Das bedeutet, du kannst alles an einem Ort schreiben und die KI sortieren lassen. Nach Abschluss des Updates wird das Feld **automatisch geleert** — deine Eingabe wurde in die strukturierten Profilbereiche übernommen, sodass die einmalige Anweisung nicht mehr benötigt wird.

Wenn du dieses Feld ausfüllst, wird die **Kernbeschreibung** darunter optional — die KI generiert eine für dich.

![Beschreibe deinen Vibe Feld mit Beispieltext](/docs/screenshots/11_vibe_description.png)

---

<a id="core-description"></a>
#### Kernbeschreibung

Das **🎵 Kernbeschreibung**-Akkordeon ist die Grundlage deines Profils.

Beschreibe die Musik, die du möchtest, in eigenen Worten, z. B.:

- Genre
- Stimmung
- Energie
- Atmosphäre
- Referenzkünstler
- Instrumente
- Gesang

Dieses Feld sollte deinen allgemeinen Geschmack klar beschreiben.

![Kernbeschreibung-Feld](/docs/screenshots/12_core_description.png)

---

<a id="must-have"></a>
#### Muss vorhanden sein

Das **✅ Muss vorhanden sein**-Akkordeon ist für nicht verhandelbare Eigenschaften, die jede Empfehlung **haben muss**. Ein Track, dem eine davon fehlt, wird abgelehnt.

Beispiele:

- starke Melodien
- emotionaler Gesang
- energetisches Schlagzeug
- atmosphärische Gitarrenarbeit

Ein Eintrag pro Zeile.

![Muss vorhanden sein Bereich](/docs/screenshots/13_must_have.png)

---

<a id="soft-preferences"></a>
#### Weiche Präferenzen

Das **💡 Weiche Präferenzen**-Akkordeon ist für Eigenschaften, die willkommen, aber nicht erforderlich sind — Wünschenswertes, das einen Vorschlag verbessert.

Beispiele:

- leichte Progressive-Elemente
- warme Produktion
- gelegentliche Synth-Texturen

Ein Eintrag pro Zeile.

![Weiche Präferenzen Bereich](/docs/screenshots/14_soft_preferences.png)

---

<a id="avoid"></a>
#### Vermeiden

Das **🚫 Vermeiden**-Akkordeon ist für absolute Ausschlusskriterien — Klänge oder Eigenschaften, die du **nicht** möchtest.

Beispiele:

- übermäßig elektronische Produktion
- langsame Balladen
- harter Gesang
- repetitive Refrains

Ein Eintrag pro Zeile.

![Vermeiden Bereich](/docs/screenshots/15_avoid.png)

---

<a id="save-or-ai-profile-update"></a>
#### Speichern oder KI-Profil-Update

Nach der Bearbeitung deines Profils erscheinen zwei Aktionsbuttons am unteren Rand des Editors:

- **Speichern** (rechte Seite)
  Speichert dein Profil genau so, wie es geschrieben ist. Keine KI-Verarbeitung, kein API-Aufruf, sofort. Funktioniert auch bei leeren Feldern. Benötigt **keinen** OpenAI API-Schlüssel.

- **KI-Profil-Update** (linke Seite)
  Sendet deine Eingabe an GPT, das dein Profil verfeinert, organisiert und strukturiert. Die KI klassifiziert automatisch deine Vibe-Beschreibung (siehe oben), extrahiert Referenzkünstler, generiert interne Geschmacksregeln und verbessert die Formulierung jedes Bereichs. Erfordert einen OpenAI API-Schlüssel und verbraucht eine geringe Anzahl an Tokens. Eine gelbe Warnung erscheint, wenn sowohl Kernbeschreibung als auch Vibe-Beschreibung leer sind.

**Wann was verwenden:**

| | Speichern | KI-Profil-Update |
|---|---|---|
| Geschwindigkeit | Sofort | Einige Sekunden |
| API-Schlüssel erforderlich | Nein | Ja (OpenAI) |
| Token-Kosten | Keine | Gering |
| Formulierung verbessern | Nein — speichert wie eingegeben | Ja — verbessert Struktur |
| Vibe-Text klassifizieren | Nein | Ja — leitet in korrekte Bereiche |
| Ideal für | Schnelle Anpassungen, kleine Änderungen | Ersteinrichtung, größere Änderungen |

Während des KI-Profil-Updates erscheint ein Ladespinner mit rotierenden Statusmeldungen.

![Speichern und KI-Profil-Update Buttons](/docs/screenshots/16_save_buttons.png)

---

<a id="what-the-ai-does-behind-the-scenes"></a>
#### Was die KI im Hintergrund tut

Wenn du **KI-Profil-Update** ausführst, tut GPT mehr, als nur deinen Text zu speichern. Es füllt auch mehrere interne Felder, die du nie direkt bearbeitest, die aber die Playlist-Generierung erheblich verbessern:

- **Ziel & primäre Referenz** — Eine Einzeilen-Zusammenfassung und dominante Stil-Referenz, abgeleitet aus deiner Kernbeschreibung.
- **Bestätigte / mittlere / abgelehnte Künstler** — Künstlernamen aus deinen Beschreibungen, kategorisiert danach, wie gut sie zu deinem Geschmack passen.
- **Geschmacksregeln** — Eine Prioritätsreihenfolge zur Bewertung von Tracks (z. B. „Melodie > Energie > Stil") und eine geordnete Liste absoluter Ausschlusskriterien aus deinem Vermeiden-Bereich.

Diese Felder sind in der Oberfläche unsichtbar, werden aber in jeden Generierungsprompt einbezogen und helfen GPT, genauere Vorschläge zu machen. Du musst sie nicht verwalten — sie aktualisieren sich automatisch bei jedem KI-Profil-Update.

---

<a id="import-export-reset-and-delete-your-profile"></a>
### Profil importieren, exportieren, zurücksetzen und löschen

Die **Profile**-Akkordeon-Überschrift enthält einen **⋯**-Button (Drei-Punkte-Menü) neben dem Zuklapp-Pfeil. Klicke darauf, um ein Dropdown mit folgenden Aktionen zu öffnen:

- **Profil hochladen**
  Importiere eine gespeicherte Profil-JSON-Datei in das aktuelle Profil. Ein Bestätigungsdialog erscheint zuerst. Dein vorheriges Profil wird automatisch in einer Verlaufsdatei gesichert, bevor der Import es überschreibt. Unbekannte Felder in der importierten Datei werden stillschweigend entfernt; fehlende Felder werden aus der Standard-Vorlage aufgefüllt.

- **Profil exportieren**
  Lade dein aktuelles Profil als `spotyvibe_profile.json`-Datei herunter (vollständiges JSON einschließlich aller KI-generierten internen Felder).

- **Profil zurücksetzen**
  Stelle die vorherige Version deines Profils wieder her (Ein-Schritt-Rückgängig). Dies lädt die automatische Sicherung, die vor dem letzten Speichern, KI-Update oder Import erstellt wurde.

- **Profil löschen**
  Entferne das aktuelle Profil und seinen Verlauf dauerhaft. Ein Bestätigungsdialog erscheint zuerst. Dies kann nicht rückgängig gemacht werden. Wenn andere Profile existieren, wird automatisch das erste ausgewählt.

**Deaktivierte Einträge:** Wenn kein Profil ausgewählt ist, sind **Exportieren**, **Zurücksetzen** und **Löschen** ausgegraut, da sie ein aktives Profil erfordern. **Hochladen** ist immer verfügbar — es erstellt oder ersetzt das aktive Profil.

Dies ist nützlich, wenn du dein Profil sichern, auf ein anderes Gerät übertragen, ungenutzte Profile aufräumen oder eine kürzliche Änderung rückgängig machen möchtest.

![Import / Export / Zurücksetzen / Löschen Steuerung](/docs/screenshots/17_profile_io_controls.png)

---

<a id="updating-your-taste-over-time"></a>
### Geschmack im Laufe der Zeit aktualisieren

Dein Geschmack kann sich ändern, und SpotyVibe ist darauf ausgelegt, sich mit dir zu entwickeln.

Um deine Vorlieben zu aktualisieren:

1. Gehe zurück zum **OpenAI**-Bereich
2. Klicke auf **Profil bearbeiten**
3. Aktualisiere deine Beschreibung oder Präferenzlisten — oder schreibe einfach, was sich geändert hat, in das **Beschreibe deinen Vibe**-Feld
4. Speichere oder führe **KI-Profil-Update** aus
5. Generiere erneut

Je genauer dein Profil deinen aktuellen Geschmack widerspiegelt, desto besser werden deine zukünftigen Playlists. Für kleine Anpassungen nutze das Vibe-Feld — z. B. „mehr akustisch, weniger elektronisch" — und lass die KI es in dein bestehendes Profil einarbeiten.

![Bestehendes Profil bearbeiten](/docs/screenshots/28_editing_existing_profile.png)

---

<a id="discovery--analysis"></a>
## Entdeckung & Analyse

<a id="bandsong-analysis"></a>
### Band-/Song-Analyse

Klicke im **OpenAI**-Bereich auf **Analyse öffnen** oder irgendwo auf die **Band-/Song-Analyse**-Überschrift, um sie aufzuklappen.

Diese Funktion hilft dir, einen Künstler oder Song zu analysieren und das in Profilsprache umzuwandeln.

Anleitung:

1. Gib einen **Künstlernamen** ein
2. Optional einen **Tracknamen** eingeben
3. Klicke auf **Analysieren**
4. Prüfe die Ergebnisse
5. Kopiere nützliche Vorschläge in dein Musikprofil

Das ist besonders hilfreich, wenn du weißt, was dir gefällt, aber nicht sicher bist, wie du es beschreiben sollst.

![Band-/Song-Analyse Panel](/docs/screenshots/18_analysis_panel.png)

---

<a id="playlist-generation"></a>
## Playlist-Generierung

Sobald dein Profil fertig und Spotify verbunden ist, gehe zum **Spotify**-Bereich und klicke auf **Einblenden** bei der **Tracks entdecken**-Überschrift (oder klicke irgendwo auf die Überschrift), um sie aufzuklappen.

Hier erstellt SpotyVibe Playlist-Vorschläge basierend auf deinem Geschmack. Der Bereich ist standardmäßig zugeklappt, um die Seite kompakt zu halten.

![Tracks entdecken Bereich aufgeklappt](/docs/screenshots/19_discover_section.png)

---

<a id="choose-a-playlist-mode"></a>
### Playlist-Modus wählen

Wähle vor der Generierung, wie SpotyVibe mit der Playlist umgehen soll.

Verfügbare Optionen:

- **Standard**
  Verwendet die Standard-SpotyVibe-Playlist

- **Neue Playlist erstellen**
  Erstellt eine brandneue Playlist

- **Anhängen**
  Fügt Tracks zu einer bestehenden Playlist hinzu

- **Ersetzen**
  Leert eine bestehende Playlist und füllt sie mit neuen Tracks

Bei einer neuen Playlist kannst du in der Regel einen eigenen Playlist-Namen eingeben.

![Playlist-Modus-Auswahl](/docs/screenshots/20_playlist_mode_selector.png)

---

<a id="quick-vs-advanced-mode"></a>
### Schnell- vs. Erweitert-Modus

Das Generieren-Panel hat zwei Modi, erreichbar über den Pill-Umschalter oben:

- **Schnell** — Zeigt nur Playlist-Größe, den Erkundungs-Regler und den Generieren-Button. Ideal für den täglichen Gebrauch.
- **Erweitert** — Zeigt alle Steuerelemente: Voreinstellungs-Auswahl, Playlist-Modus, aufstrebende Künstler, Audio-Filter, Neue-Künstler-% und den Erkundungs-Regler.

Deine Modus-Auswahl wird gespeichert und beim Neuladen wiederhergestellt.

---

<a id="exploration-slider"></a>
### Erkundungs-Regler

Der **Erkundung vs. Treue**-Regler ist ein 5-Stufen-Steuerelement, das bestimmt, wie abenteuerlustig deine Vorschläge sein werden:

1. **Vertraut** — Fokus auf Künstler, die du bereits kennst (10 % neu, Temperatur 0,5).
2. **Meist bekannt** — Ein paar neue Künstler dabei (25 % neu, Temperatur 0,7).
3. **Ausgewogen** — Etwa zur Hälfte neue Künstler, moderate Vielfalt (50 % neu, Temperatur 0,8).
4. **Meist neu** — Entdeckungsmodus mit vertrauten Ankern (70 % neu, Temperatur 0,9).
5. **Abenteuerlustig** — Nur aufstrebende Künstler, hohe Vielfalt (90 % neu, Temperatur 1,0).

Im Erweitert-Modus, wenn du „Neue Künstler %" oder die Checkbox für aufstrebende Künstler manuell auf Werte setzt, die keiner Stufe entsprechen, wechselt der Regler in einen **Eigene Einstellung**-Zustand. Das Zurückbewegen zu einer Stufe übernimmt wieder die Voreinstellungswerte.

---

<a id="generation-presets"></a>
### Generierungs-Voreinstellungen

Im Erweitert-Modus ermöglicht ein **Voreinstellung**-Dropdown oben das Speichern und Abrufen kompletter Generierungskonfigurationen:

- **Mitgelieferte Voreinstellungen:** Sichere Wahl, Ausgewogen, Tiefe Entdeckung. Können nicht bearbeitet, aber dupliziert werden.
- **Eigene Voreinstellungen:** Erscheinen über den mitgelieferten. Speichere über „💾 Aktuelle Einstellungen speichern…".
- **Voreinstellungen verwalten:** Öffne über ☰ Menü → 🎛 Voreinstellungen verwalten. Umbenennen, Löschen, Umsortieren, Importieren oder Exportieren.
- Voreinstellungen werden lokal auf deinem Gerät im localStorage des Browsers gespeichert.
- **BENUTZERDEFINIERT-Badge:** Wenn du das Feld **Neue Künstler %** auf einen Wert änderst, der nicht zum Wert der aktiven Voreinstellung passt, erscheint ein kleines **BENUTZERDEFINIERT**-Badge neben dem Eingabefeld. Speichere die Abweichung als neue Voreinstellung (oder aktualisiere die bestehende), um die Änderung dauerhaft zu machen.

> **Hinweis zur Künstlerabdeckung:** Der Offline-Künstler-Korpus von SpotyVibe (der optionale **Candidate pool (RAG)** in den Einstellungen) enthält nur Acts, die ab den **1960er Jahren** aktiv wurden. Musik vor den 1960ern ist bewusst ausgeschlossen — der Anteil im typischen Hörverhalten ist gering und das Auslassen hält den Index schlank. Derselbe Hinweis erscheint als Tooltip (ⓘ) neben dem Schalter in den Einstellungen.

> **Hinweis zu lokalen LLMs:** Mit aktiviertem RAG wächst der Prompt typischerweise auf ~4–6 k Tokens (60-Slot-Pool + Profil + Verlauf + JSON-Ausgabe). Verwendest du ein lokales Modell mit kleinem Kontext (4 k oder 8 k Tokens) und die Qualität fällt ab, deaktiviere RAG in den Einstellungen, verringere `RAG_POOL_SIZE` oder wechsle auf ein Modell mit ≥ 16 k Kontext. RAG wurde für gehostete GPT-4-Klasse-Modelle entworfen.

---

<a id="use-audio-filters"></a>
### Audio-Filter verwenden

Klicke im **Tracks entdecken**-Bereich auf die **🎚 Audio-Filter (optional)**-Leiste, um das Filter-Panel aufzuklappen. Diese optionalen Filter leiten GPT an, Tracks passend zu deiner gewünschten Stimmung und Atmosphäre vorzuschlagen.

Verfügbare Filter:

- **Energie** — Wie intensiv/energetisch der Track wirkt (0–1)
- **Valenz** — Wie fröhlich/positiv der Track klingt (0–1)
- **Tempo** — Schläge pro Minute (BPM)
- **Tanzbarkeit** — Wie gut sich der Track zum Tanzen eignet (0–1)
- **Akustik** — Wie akustisch (vs. elektronisch) der Track ist (0–1)

Jeder Filter hat ein **Min**- und **Max**-Eingabefeld. Beim Tippen erscheint rechts ein verständlicher Hinweis (z. B. „↳ Energetisch bis Intensiv"), damit du auf einen Blick siehst, was die Zahlen bedeuten.

**Alle löschen:** Klicke auf **✕ Alle löschen** oben rechts im Filter-Panel, um alle Filter auf einmal zurückzusetzen.

#### Band-/Song-Analyse zum Setzen von Filtern nutzen

Der einfachste Weg, Audio-Filter auszufüllen, ist über die **Band-/Song-Analyse**:

1. Öffne die **Band-/Song-Analyse** und analysiere einen Referenztrack.
2. In den Ergebnissen hat jede Audio-Feature-Zeile (Energie, Valenz usw.) einen **⇒ Filter**-Button.
3. Klicke auf **⇒ Filter** bei einem beliebigen Feature — es setzt automatisch einen sinnvollen Min/Max-Bereich (±10 %, oder ±15 BPM für Tempo) im Musik-entdecken-Filter-Panel.
4. Oder klicke auf **⇒ Alle als Filter verwenden**, um alle Features auf einmal anzuwenden.
5. Der Entdecken-Bereich und das Filter-Panel öffnen sich automatisch, wenn du einen Filter anwendest.

Dies überbrückt die Lücke zwischen Analyse und Generierung — kein Merken von Zahlen mehr nötig.

![Audio-Filter Sub-Panel in Tracks entdecken](/docs/screenshots/21_audio_filters.png)

![Band-/Song-Analyse mit Filter-Buttons](/docs/screenshots/18_analysis_panel.png)

---

<a id="emerging-artists-only"></a>
### Nur aufstrebende Künstler

Zwischen den Playlist-Name/Modus-Steuerungen und dem Audio-Filter-Panel befindet sich eine **„Nur neue / aufstrebende Künstler"**-Checkbox.

Wenn aktiviert:

- Die KI wird angewiesen, **nur Tracks von Künstlern vorzuschlagen, die in den letzten 6 Monaten debütiert haben**.
- Nach der Spotify-Verifizierung werden Tracks anhand ihres Album-**Veröffentlichungsdatums** gefiltert — alles, was älter als 6 Monate ist, wird entfernt.
- Um die stärkere Filterung auszugleichen, fordert die KI mehr Kandidaten pro Batch an.
- Die finale Playlist kann **weniger Tracks** als deine konfigurierte Größe haben. Eine Statusmeldung erklärt das Ergebnis (z. B. „Zeige 14 von 30 geprüften Tracks — nur Tracks von kürzlich aufgetauchten Künstlern sind enthalten.").

Lass die Checkbox deaktiviert für normales Generierungsverhalten.

---

<a id="start-generation"></a>
### Generierung starten

Klicke auf **Playlist erstellen**, um zu beginnen.

Ein Ladespinner erscheint unterhalb des Buttons im Musik-entdecken-Bereich. Fortschrittsmeldungen werden unter dem Spinner angezeigt, während SpotyVibe arbeitet:

1. Song-Vorschläge generieren
2. Auf Spotify prüfen
3. Playlist erstellen
4. Ergebnisse im Bereich anzeigen (unterhalb einer Trennlinie)
5. Link zum Öffnen der Playlist in Spotify bereitstellen

![Generierung läuft mit Inline-Spinner](/docs/screenshots/29_generation_spinner.png)

---

<a id="stop-early-or-use-current-tracks"></a>
### Vorzeitig stoppen oder aktuelle Tracks verwenden

Während der Generierung können zwei hilfreiche Optionen erscheinen:

- **Abbrechen**
  Stoppt die aktuelle Generierung ohne Änderungen anzuwenden

- **X Tracks jetzt verwenden**
  Stoppt die Generierung und erstellt die Playlist mit den bereits gefundenen Tracks

Das ist nützlich, wenn dir die bisherigen Ergebnisse bereits gefallen und du nicht länger warten möchtest.

![Abbrechen und X Tracks verwenden Buttons](/docs/screenshots/30_cancel_use_tracks.png)

---

<a id="discover-artists"></a>
## Künstler entdecken

**Künstler entdecken** liegt zwischen „Tracks entdecken“ und „Playlist verfeinern“. Statt einer Track-Playlist bringt es **neue Künstler** zum Vorschein, die einen Blick wert sind — jeweils mit ein paar echten Tracks zum Einstieg.

Klappe den Bereich mit **Einblenden** auf und stelle zwei Regler ein:

- **Anzahl Künstler** — wie viele neue Künstler entdeckt werden (1–10).
- **Erkundung vs. Genauigkeit** — *Vertraut* bevorzugt Künstler nahe deinem Geschmack; *Abenteuerlich* bringt unbekannte Geheimtipps.

Jeder vorgeschlagene Künstler ist **neu** — Künstler, die bereits in deinem Profil sind (bestätigt oder zuvor vorgeschlagen), werden ausgeschlossen.

Klicke auf **Künstler entdecken**. SpotyVibe ruft einen großen Kandidaten-Pool ab, und ein einzelner KI-Durchlauf wählt die endgültige Liste. Jeder Künstler wird mit einer kurzen Begründung, Genre-Tags und einigen repräsentativen Tracks angezeigt. Auf Spotify gefundene Tracks sind verlinkt; nicht gefundene sind als *nicht auf Spotify* markiert.

Mit **Auf Playlist anwenden** fügst du die auf Spotify verifizierten Tracks einer Playlist hinzu — erstellen, anhängen oder ersetzen, dieselben Optionen wie bei „Tracks entdecken“ — oder **Leeren**, um die Liste zu verwerfen.

---

<a id="track-review--feedback"></a>
## Track-Bewertung & Feedback

Nach der Generierung zeigt SpotyVibe die vorgeschlagenen Tracks **innerhalb des Musik-entdecken-Bereichs** an, unterhalb des Generieren-Buttons, getrennt durch eine Trennlinie. Ein Abschluss-Banner und Playlist-Link erscheinen zuerst, gefolgt von den Track-Karten. Track-Karten leuchten beim Hover grün.

Jede Karte kann zeigen:

- Trackname
- Künstler
- Albumcover
- Begründung der Empfehlung
- Aktionsbuttons

Du kannst jeden Song bewerten und entscheiden, was als Nächstes zu tun ist.

![Track-Karten nach der Generierung](/docs/screenshots/31_track_cards.png)

---

<a id="preview-a-track"></a>
### Track vorhören

Klicke auf das Albumcover einer Song-Karte, um das Vorschau-Overlay am unteren Bildschirmrand zu öffnen.

Die Vorschau verwendet ein Drei-Zonen-Layout:

1. **Player** — Der Track-Player (zentriert, breit). Mit Spotify Premium auf unterstützten Plattformen verwendet SpotyVibe das Spotify Web Playback SDK für die Wiedergabe in voller Länge und zeigt 👍 / 👎 Schnellbewertungs-Buttons direkt neben den Wiedergabesteuerungen. Andernfalls liefert der eingebettete Spotify-iframe ~30-Sekunden-Vorschauen.
2. **Aktions-Buttons** — Ein **Feedback**-Button (öffnet das Begründungs-Panel) und ein **Löschen**-Button (entfernt den Track aus der Spotify-Playlist, ohne Feedback zu erfassen), rechts vom Player.
3. **Feedback-Panel** — Gleitet ein, wenn du **Feedback** klickst. Das Panel zeigt die Track-Details plus ein optionales Begründungsfeld und unten zwei Submit-Buttons: **👍 Gefällt mir** (grün) und **👎 Gefällt mir nicht** (rot). Wähle deine Bewertung beim Absenden, nicht beim Öffnen des Panels.

Die schnellen 👍 / 👎 im Player senden sofort ohne Begründung ab — praktisch während der Song läuft. „Gefällt mir nicht" entfernt den Track zusätzlich aus der Spotify-Playlist und springt zur nächsten Vorschau.

Verwende die ‹ und › Pfeile, um zwischen Tracks zu navigieren, ohne das Overlay zu schließen.

> **Erste Track-Vorschau?** Die 👍 / 👎 im Player pulsieren kurz und ein Hinweis erklärt die schnelle Bewertung. Der Hinweis erscheint nur beim ersten Öffnen pro Gerät.

![Vorschau-Player geöffnet](/docs/screenshots/32_preview_player.png)

---

<a id="open-spotify-links"></a>
### Spotify-Links öffnen

Jede Song-Karte enthält Schnelllinks zum Öffnen von Inhalten in Spotify, wie z. B.:

- den Track
- den Künstler
- das Album

Nutze diese Links, um Musik genauer zu erkunden.

![Spotify-Schnelllinks auf einer Song-Karte](/docs/screenshots/33_spotify_quick_links.png)

---

<a id="like-a-track"></a>
### Track liken

Klicke auf **Gefällt mir**, wenn ein Track deinem Geschmack entspricht.

Du kannst optional einen kurzen Grund hinzufügen, bevor du absendest.

Tracks zu liken hilft SpotyVibe zu lernen, was gut für dich funktioniert.

Beispiele für Gründe:

- perfekte Stimmung
- toller Gesang
- starke Melodie
- genau der Sound, den ich will

![Like-Feedback-Formular](/docs/screenshots/34_like_feedback_form.png)

---

<a id="dislike-a-track"></a>
### Track disliken

Klicke auf **Gefällt mir nicht**, wenn ein Track nicht passt.

Du kannst optional einen Grund angeben, warum.

Beispiele:

- zu langsam
- falsche Atmosphäre
- zu elektronisch
- schwacher Refrain

Das hilft SpotyVibe, ähnliche Tracks in zukünftigen Durchläufen zu vermeiden.

![Dislike-Feedback-Formular](/docs/screenshots/35_dislike_feedback_form.png)

#### Eine ganze Band ablehnen

Wenn du beim Dislike das **Track**-Feld leer lässt, fragt SpotyVibe nach: *„Alle Songs von '<Künstler>' aus dieser Playlist entfernen und nie wieder vorschlagen?"*. Mit OK werden alle Tracks dieses Künstlers aus der aktiven Playlist entfernt (nicht nur der sichtbare) und der Künstler dauerhaft auf die Vermeiden-Liste gesetzt. Abbrechen tut nichts.

---

<a id="remove-a-track"></a>
### Track entfernen

Klicke auf **Entfernen**, um einen Song aus der Liste zu nehmen, ohne ihn als Like oder Dislike zu erfassen.

Nutze dies für Tracks, bei denen du neutral bist.

![Entfernen-Button auf Song-Karte](/docs/screenshots/36_remove_button.png)

---

<a id="refine-playlist"></a>
## Playlist verfeinern

Der **Playlist verfeinern**-Bereich ermöglicht es dir, eine bestehende Spotify-Playlist zu laden und ihre Tracks einzeln zu bewerten. Du kannst jeden Track liken, disliken oder verwerfen, um dein Geschmacksprofil zu verfeinern und die Playlist gleichzeitig aufzuräumen.

Das ist nützlich, wenn du:

- Eine früher erstellte Playlist durchgehen und nachträgliches Feedback geben möchtest
- Eine Playlist aufräumen möchtest, indem du Tracks entfernst, die nicht mehr passen
- SpotyVibe mehr über deinen Geschmack beibringen möchtest, basierend auf echten Hörerfahrungen

Zum Öffnen klicke auf **Einblenden** bei der **🔄 Playlist verfeinern**-Überschrift (oder klicke irgendwo auf die Überschrift) im Spotify-Bereich.

![Playlist verfeinern Bereich aufgeklappt](/docs/screenshots/22_refine_playlist_section.png)

---

<a id="select-and-load-a-playlist"></a>
### Playlist auswählen und laden

1. Klappe den **Playlist verfeinern**-Bereich auf — deine Spotify-Playlists werden automatisch in das Dropdown geladen
2. Wähle eine Playlist aus dem **Dropdown**
3. Klicke auf **🔄 Playlist laden**

Ein Ladespinner erscheint unter dem Button, während SpotyVibe die Tracks abruft. Nach dem Laden erscheinen die Tracks im Bereich, unterhalb des Buttons, getrennt durch eine Trennlinie. Track-Karten sehen ähnlich aus wie die Vorschlagsliste beim Entdecken.

![Playlist-Dropdown mit geladenen Playlists](/docs/screenshots/37_playlist_dropdown.png)

---

<a id="review-tracks"></a>
### Tracks durchgehen

Jede Track-Karte zeigt:

- Albumcover (zum Vorhören klicken)
- Künstler und Trackname
- Spotify-Links (Track, Künstler, Album)
- Aktionsbuttons: **💬 Feedback** (öffnet das Begründungs-Panel) und **🗑 Löschen** (entfernt den Track aus der Spotify-Playlist, ohne Feedback zu erfassen)

Du kannst auch auf das Albumcover klicken, um den Spotify-Vorschau-Player zu öffnen. Beim Vorhören aus der Verfeinern-Liste navigiert die Vor/Zurück-Steuerung innerhalb der Bewertungs-Trackliste.

![Bewertungs-Track-Karten](/docs/screenshots/38_review_track_cards.png)

---

<a id="like-a-track-refine"></a>
### Track liken (Verfeinern)

Klicke auf **💬 Feedback** auf der Track-Karte und dann unten im Panel auf **👍 Gefällt mir**. Du kannst optional Künstler, Trackname bearbeiten und einen Grund hinzufügen, bevor du absendest.

Nach dem Absenden animiert die Karte aus der Bewertungsliste heraus. Der Track **bleibt in der Spotify-Playlist** — nur dein Geschmacksprofil wird aktualisiert.

![Like-Feedback-Formular im Verfeinern-Bereich](/docs/screenshots/39_review_like_form.png)

---

<a id="dislike-a-track-refine"></a>
### Track disliken (Verfeinern)

Klicke auf **💬 Feedback** auf der Track-Karte und dann unten im Panel auf **👎 Gefällt mir nicht**. Du kannst optional Künstler, Trackname bearbeiten und einen Grund hinzufügen, bevor du absendest.

Nach dem Absenden wird der Track:

1. **Als Dislike erfasst** in deinem Geschmacksprofil
2. **Aus der Spotify-Playlist entfernt**

Die Karte animiert aus der Bewertungsliste heraus.

![Dislike-Feedback-Formular im Verfeinern-Bereich](/docs/screenshots/40_review_dislike_form.png)

---

<a id="dismiss-a-track"></a>
### Track löschen

Klicke auf **🗑 Löschen**, um einen Track aus der Spotify-Playlist zu entfernen, **ohne** Geschmacksprofil-Feedback zu erfassen.

Nutze dies für Tracks, bei denen du neutral bist, die du aber aus der Playlist entfernen möchtest.

Die Karte animiert aus der Bewertungsliste heraus.

![Verwerfen-Button auf Bewertungs-Track-Karte](/docs/screenshots/41_review_dismiss_button.png)

---

<a id="taste-dashboard"></a>
## Geschmacks-Dashboard

Unter dem Musikprofil-Editor zeigt der Bereich **„Dein Geschmack auf einen Blick"** interaktive Diagramme, die deine Hörgewohnheiten visualisieren. Die Daten werden automatisch aus deinem Playlist-Generierungsverlauf aggregiert.

<a id="opening-the-dashboard"></a>
### Dashboard öffnen

Klicke auf **Einblenden** (oder auf die Bereichsüberschrift), um das Dashboard-Panel aufzuklappen. Wenn du noch nicht genug Playlists generiert hast, siehst du stattdessen einen **„Noch nicht genug Daten"**-Platzhalter. Diagramme erscheinen, sobald du mindestens **10 einzigartige Tracks** über deine Generierungsläufe hast.

<a id="charts"></a>
### Diagramme

Das Dashboard zeigt drei Diagrammtypen:

- **Top-Genres** — Ein Donut-Diagramm deiner häufigsten Genres, abgeleitet aus Spotify-Künstler-Metadaten. Fahre mit der Maus über ein Segment, um Genre und Track-Anzahl zu sehen.
- **Energie × Valence** — Ein Streudiagramm, das die Stimmung deiner Tracks abbildet. Die horizontale Achse zeigt Valence (traurig → fröhlich) und die vertikale Achse zeigt Energie (ruhig → intensiv). Fahre mit der Maus über einen Punkt, um Künstler und Tracktitel zu sehen. Ein Hinweis erinnert daran, dass Energie- und Valence-Werte KI-Schätzungen sind, keine exakten Messwerte.
- **Jahrzehnte** — Ein Balkendiagramm der Veröffentlichungsjahrzehnte deiner Tracks, abgeleitet aus Spotify-Albumdaten.

<a id="sentiment-sections"></a>
### Stimmungsabschnitte

Wenn du Feedback zu Tracks gegeben hast (Likes/Dislikes), wird das Dashboard in bis zu drei Unterabschnitte aufgeteilt:

- **Alle Tracks** — Die Hauptansicht, die jeden Track aus deinen Läufen zusammenfasst.
- **Gelikte Tracks** — Diagramme nur für Tracks, die du geliked (👍) hast.
- **Dislikte Tracks** — Diagramme nur für Tracks, die du disliked (👎) hast.

Die Like- und Dislike-Abschnitte erscheinen nur, wenn genug Daten vorhanden sind.

<a id="profile-isolation"></a>
### Profil-Isolation

Jedes Profil hat seine eigenen, unabhängigen Dashboard-Daten. Wenn du **Profile wechselst** oder ein **neues Profil erstellst**, wird das Dashboard vollständig zurückgesetzt:

- Alle Diagramme werden sofort geleert.
- Der „Noch nicht genug Daten"-Platzhalter wird angezeigt.
- Wenn das Dashboard-Panel gerade aufgeklappt ist, werden automatisch frische Daten für das neu aktive Profil geladen.

Du siehst also niemals veraltete Diagramme eines vorherigen Profils. Ein neues Profil beginnt immer mit „Noch nicht genug Daten", bis du unter diesem Profil Playlists generierst.

---

<a id="song-list--run-history"></a>
## Songliste & Lauf-Verlauf

<a id="run-history"></a>
### Lauf-Verlauf

SpotyVibe speichert die **letzten 5** Playlist-Generierungsläufe im **Verlauf**-Bereich, der sich im Spotify-Panel unterhalb von Playlist verfeinern befindet. Klicke auf **Verlauf anzeigen** oder irgendwo auf die Bereichsüberschrift, um ihn aufzuklappen.

Für jeden Lauf siehst du:

- Wann der Lauf stattfand
- Wie viele Tracks hinzugefügt wurden
- Einen Link zur Playlist (falls sie noch auf Spotify existiert)

**Klicke auf einen Verlaufseintrag**, um ihn aufzuklappen und die vollständige Liste der Tracks (Künstler — Track) anzuzeigen, die während dieses Laufs hinzugefügt wurden. Klicke erneut, um zuzuklappen.

Ältere Läufe über die letzten 5 hinaus werden automatisch entfernt, um die Liste übersichtlich zu halten.

![Lauf-Verlauf Bereich mit aufgeklapptem Eintrag](/docs/screenshots/23_run_history.png)

---

<a id="persistent-song-list"></a>
### Beständige Songliste

Deine generierte Songliste wird im Musik-entdecken-Bereich gespeichert und beim Neuladen der Seite wiederhergestellt — du verlierst deine Track-Karten nie zwischen Sitzungen.

Das bedeutet:

- Du kannst vorherige Vorschläge erneut durchgehen
- Du verlierst die Liste nicht beim Zurückkehren zur App
- Du kannst Songs über einen längeren Zeitraum bewerten

Wenn die Liste zu voll wird, entferne einige Tracks, bevor du neue generierst.

![Songliste mit gespeicherten Tracks](/docs/screenshots/42_history_song_list.png)

---

<a id="mobile-usage"></a>
## Mobile Nutzung

SpotyVibe funktioniert auch gut auf Smartphones und Tablets.

Auf mobilen Geräten:

- Panels stapeln sich vertikal
- Buttons sind leicht tippbar
- Dialoge und Formulare passen sich an kleinere Bildschirme an

Du kannst denselben Hauptablauf nutzen:

1. Einrichtung abschließen
2. Spotify verbinden
3. Profil erstellen
4. Playlists generieren
5. Songs bewerten und Feedback geben

![Mobile Ansicht des Hauptbildschirms](/docs/screenshots/43_mobile_view.png)

---

<a id="troubleshooting--tips"></a>
## Fehlerbehebung & Tipps

<a id="troubleshooting"></a>
### Fehlerbehebung

**Ich kann keine Playlist generieren**
Stelle sicher, dass du:

- alle erforderlichen Zugangsdaten eingegeben hast
- dein Spotify-Konto verbunden hast
- dein Musikprofil ausgefüllt hast

**Spotify-Verbindung funktioniert nicht**
Versuche, Spotify über das Menü zu trennen und erneut zu verbinden.

**Die Empfehlungen passen nicht zu meinem Geschmack**
Aktualisiere dein Musikprofil mit klareren Beschreibungen und spezifischeren Likes/Dislikes.

**Die App schlägt immer ähnliche Songs vor**
Nutze detailliertere Profil-Bearbeitungen, erhöhe den Anteil neuer Künstler und gib direktes Feedback zu Tracks, die dir gefallen oder nicht gefallen.

**Zu wenige Tracks werden hinzugefügt**
Erweitere deine Audio-Filter oder versuche es erneut mit weniger Einschränkungen.

![Beispiel-Warn- oder Fehlermeldung](/docs/screenshots/44_warning_message.png)

---

<a id="final-tips"></a>
### Abschließende Tipps

Um die besten Ergebnisse mit SpotyVibe zu erzielen:

- Sei spezifisch in deinem Musikprofil
- Gib häufig Feedback
- Aktualisiere dein Profil, wenn sich dein Geschmack ändert
- Nutze Audio-Filter nur, wenn du engere Kontrolle möchtest
- Nutze den Lauf-Verlauf, um vergangene Generierungen zu überprüfen

Die App verbessert sich mit jeder Interaktion, daher führt regelmäßiges Feedback zu besseren Entdeckungen.

---

Viel Spaß beim Entdecken deiner nächsten Lieblingsmusik mit **SpotyVibe**.
