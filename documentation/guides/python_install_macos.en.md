---
title: Install Python and launch SpotyVibe on macOS
subtitle: The app runs in your browser; you just need Python once.
---

## Step 1 — Check if Python is already installed
Open the Terminal app (Finder → Applications → Utilities → Terminal, or press ⌘Space and type "Terminal"). Type this and press Enter:

```copy
python3 --version
```

If you see a version number like `Python 3.11.4`, skip to Step 3. If you see "command not found", continue with Step 2.

![Terminal showing Python version check](/docs/guides/python-macos/step1_check.png)

## Step 2 — Install Python with the official installer
Download the latest macOS Python installer from [python.org/downloads/macos](https://www.python.org/downloads/macos/). Open the `.pkg` file you just downloaded and follow the installer. When it finishes, re-run the check from Step 1 to confirm.

![Python installer on macOS](/docs/guides/python-macos/step2_installer.png)

## Step 3 — Install SpotyVibe
Back in the Terminal, type this to install the SpotyVibe wheel. Replace `spotyvibe-*.whl` with the file name of the wheel you downloaded:

```copy
pip3 install spotyvibe-*.whl
```

If `pip3 install` fails with a permission error, try `pip3 install --user spotyvibe-*.whl`.

![pip install succeeding](/docs/guides/python-macos/step3_install.png)

## Step 4 — Launch SpotyVibe
Type `spotyvibe` and press Enter. A browser tab opens at `http://127.0.0.1:5000` with the app ready. Leave the Terminal window open while you use the app — closing it stops SpotyVibe.

```copy
spotyvibe
```

![SpotyVibe running in Terminal and browser](/docs/guides/python-macos/step4_launch.png)

