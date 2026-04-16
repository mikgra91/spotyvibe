---
title: Create your Spotify developer app
subtitle: A free Spotify developer account with your own app credentials.
---

## Step 1 — Open the Spotify Developer Dashboard
Go to [developer.spotify.com/dashboard](https://developer.spotify.com/dashboard) and log in with your Spotify account (or create one if you don't have one).
![Spotify Developer Dashboard](/docs/guides/spotify/step1_dashboard.png)

## Step 2 — Create a new app
Click **Create app**. Give it any name (e.g. `SpotyVibe`) and any description. Select **Web API** as the API you want to use.
![Create app](/docs/guides/spotify/step2_create.png)

## Step 3 — Set the Redirect URI
Paste this exact URL into the **Redirect URIs** field and click **Add**:

```copy
http://127.0.0.1:5000/callback
```

This tells Spotify where to send the authentication response back to SpotyVibe.
![Redirect URI](/docs/guides/spotify/step3_redirect.png)

## Step 4 — Copy your Client ID and Secret
After creating the app, you'll see the **Client ID** on the app's overview page. Click **Show client secret** to reveal the secret. Copy both values and paste them into SpotyVibe.
![Client ID and Secret](/docs/guides/spotify/step4_secret.png)

