---
title: Python installieren und SpotyVibe unter macOS starten
subtitle: Die App läuft in deinem Browser; du brauchst Python nur einmal zu installieren.
---

## Step 1 — Prüfen, ob Python bereits installiert ist
Öffne die Terminal-App (Finder → Programme → Dienstprogramme → Terminal, oder drücke ⌘Leertaste und tippe „Terminal"). Gib Folgendes ein und drücke Enter:

```copy
python3 --version
```

Wenn du eine Versionsnummer wie `Python 3.11.4` siehst, springe zu Schritt 3. Wenn „command not found" erscheint, fahre mit Schritt 2 fort.

![Terminal zeigt Python-Versionscheck](/docs/guides/python-macos/step1_check.png)

## Step 2 — Python mit dem offiziellen Installer installieren
Lade den neuesten macOS-Python-Installer von [python.org/downloads/macos](https://www.python.org/downloads/macos/) herunter. Öffne die heruntergeladene `.pkg`-Datei und folge dem Installer. Führe danach den Check aus Schritt 1 erneut durch.

![Python-Installer auf macOS](/docs/guides/python-macos/step2_installer.png)

## Step 3 — SpotyVibe installieren
Zurück im Terminal: Gib Folgendes ein, um das SpotyVibe-Wheel zu installieren. Ersetze `spotyvibe-*.whl` durch den tatsächlichen Dateinamen:

```copy
pip3 install spotyvibe-*.whl
```

Falls `pip3 install` mit einem Berechtigungsfehler fehlschlägt, versuche `pip3 install --user spotyvibe-*.whl`.

![pip install erfolgreich](/docs/guides/python-macos/step3_install.png)

## Step 4 — SpotyVibe starten
Tippe `spotyvibe` und drücke Enter. Ein Browser-Tab öffnet sich unter `http://127.0.0.1:5000`. Lass das Terminal-Fenster geöffnet, während du die App nutzt — beim Schließen wird SpotyVibe beendet.

```copy
spotyvibe
```

![SpotyVibe läuft in Terminal und Browser](/docs/guides/python-macos/step4_launch.png)

