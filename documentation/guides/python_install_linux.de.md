---
title: Python installieren und SpotyVibe unter Linux starten
subtitle: Die meisten Distributionen haben Python bereits; hier wird es bestätigt und SpotyVibe installiert.
---

## Step 1 — Python prüfen
Öffne ein Terminal. Auf Ubuntu/Debian/Fedora/Arch ist Python 3 normalerweise vorinstalliert. Bestätige:

```copy
python3 --version
```

Du benötigst Python **3.10 oder neuer**. Falls deine Version älter ist oder Python fehlt, fahre mit Schritt 2 fort.

![Terminal zeigt Python-Version](/docs/guides/python-linux/step1_check.png)

## Step 2 — Python installieren (falls nötig)
Verwende den Paketmanager deiner Distribution. Wähle den Befehl für deine Distro:

```copy
# Ubuntu / Debian
sudo apt update && sudo apt install -y python3 python3-pip python3-venv

# Fedora
sudo dnf install -y python3 python3-pip

# Arch
sudo pacman -S python python-pip
```

## Step 3 — Virtuelle Umgebung erstellen (empfohlen)
Systemweites `pip install` ist auf vielen modernen Distros blockiert. Verwende eine virtuelle Umgebung:

```copy
python3 -m venv ~/.spotyvibe-venv
source ~/.spotyvibe-venv/bin/activate
```

Dein Prompt beginnt jetzt mit `(.spotyvibe-venv)`. Alle folgenden `pip`- und `spotyvibe`-Befehle laufen in dieser venv.

## Step 4 — SpotyVibe installieren
Ersetze `spotyvibe-*.whl` durch den tatsächlichen Dateinamen des heruntergeladenen Wheels:

```copy
pip install spotyvibe-*.whl
```

![pip install erfolgreich](/docs/guides/python-linux/step2_install.png)

## Step 5 — SpotyVibe starten
Mit der noch aktiven venv:

```copy
spotyvibe
```

Ein Browser-Tab öffnet sich unter `http://127.0.0.1:5000`. Lass das Terminal-Fenster geöffnet, während du die App nutzt.

Beim nächsten Start die venv vorher wieder aktivieren:

```copy
source ~/.spotyvibe-venv/bin/activate
spotyvibe
```

![SpotyVibe läuft](/docs/guides/python-linux/step3_launch.png)

