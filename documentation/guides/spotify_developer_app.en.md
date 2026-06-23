---
title: Create your Spotify developer app
subtitle: A free Spotify developer account with your own app credentials.
---

## Step 1 — Log in at Spotify for Developers
Go to [developer.spotify.com](https://developer.spotify.com) and click **Log in** in the top-right corner.
![Log in button on the Spotify for Developers page](/docs/guides/spotify/step1_login.png)

Sign in with your regular Spotify account — or click **Sign up** at the bottom if you don't have one yet.
![Spotify login form](/docs/guides/spotify/step2_login_form.png)

## Step 2 — Open the Dashboard
Click your profile name in the top-right corner and select **Dashboard** from the menu.
![Profile menu with the Dashboard entry](/docs/guides/spotify/step3_dashboard_menu.png)

## Step 3 — Create a new app
On the Dashboard, click **Create app**.
![Create app button on the Dashboard](/docs/guides/spotify/step4_create_app.png)

## Step 4 — Fill in the app details and Redirect URI
Give the app any name (e.g. `SpotyVibe`) and any description. Then paste this exact URL into the **Redirect URIs** field and click **Add**:

```copy
http://127.0.0.1:5000/callback
```

This tells Spotify where to send the authentication response back to SpotyVibe. Under **Which API/SDKs are you planning to use?** select **Web API**, accept the developer terms, and save the app.
![App creation form with Redirect URI and Web API selected](/docs/guides/spotify/step5_app_form.png)

## Step 5 — Copy your Client ID and Secret
On the app's settings page you'll see the **Client ID**. Click **Show client secret** to reveal the secret. Copy both values and paste them into SpotyVibe.
![Client ID and Client secret fields on the app settings page](/docs/guides/spotify/step6_credentials.png)
