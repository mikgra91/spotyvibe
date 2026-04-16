---
title: Install Python and launch SpotyVibe on Linux
subtitle: Most distros already have Python; this confirms it and installs SpotyVibe.
---

## Step 1 — Check Python
Open a terminal. On Ubuntu/Debian/Fedora/Arch, Python 3 is usually pre-installed. Confirm:

```copy
python3 --version
```

You need Python **3.10 or newer**. If your version is older, or Python is missing, continue with Step 2.

![Terminal showing python version](/docs/guides/python-linux/step1_check.png)

## Step 2 — Install Python (if needed)
Use your distro's package manager. Pick the command for your distro:

```copy
# Ubuntu / Debian
sudo apt update && sudo apt install -y python3 python3-pip python3-venv

# Fedora
sudo dnf install -y python3 python3-pip

# Arch
sudo pacman -S python python-pip
```

## Step 3 — Create a virtual environment (recommended)
System-wide `pip install` is blocked on many modern distros. Use a virtual environment:

```copy
python3 -m venv ~/.spotyvibe-venv
source ~/.spotyvibe-venv/bin/activate
```

Your prompt now starts with `(.spotyvibe-venv)`. All `pip` and `spotyvibe` commands below run inside this venv.

## Step 4 — Install SpotyVibe
Replace `spotyvibe-*.whl` with the file name of the wheel you downloaded:

```copy
pip install spotyvibe-*.whl
```

![pip install succeeding](/docs/guides/python-linux/step2_install.png)

## Step 5 — Launch SpotyVibe
With the venv still active:

```copy
spotyvibe
```

A browser tab opens at `http://127.0.0.1:5000`. Leave the terminal window open while using the app.

Next time you start the app, remember to activate the venv again first:

```copy
source ~/.spotyvibe-venv/bin/activate
spotyvibe
```

![SpotyVibe running](/docs/guides/python-linux/step3_launch.png)

