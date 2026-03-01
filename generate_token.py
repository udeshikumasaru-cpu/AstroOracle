#!/usr/bin/env python3
"""
generate_token.py — YouTube OAuth2 Token Generator
====================================================
Run this ONCE to authorise your YouTube channel.
It will open a browser window asking you to log in
to the Google account that owns your YouTube channel.

After approval, it saves youtube_token.pkl — the
main bot then uses this file for all future uploads
without needing to log in again.

SETUP (do this before running):
  1. Go to https://console.cloud.google.com/
  2. Create a project (or select existing)
  3. Enable "YouTube Data API v3"
  4. Go to APIs & Services → Credentials
  5. Create OAuth 2.0 Client ID → Desktop App
  6. Download JSON → save as "client_secret.json"
     in the same folder as this script
  7. Go to OAuth consent screen → add your Google
     account as a Test User (if app is in test mode)
  8. Run:  python generate_token.py

REQUIREMENTS:
  pip install google-auth google-auth-oauthlib google-auth-httplib2 google-api-python-client
"""

import os
import pickle
import sys
import webbrowser

# ── Dependency check ──────────────────────────────────────────
MISSING = []
try:
    from google_auth_oauthlib.flow import InstalledAppFlow
except ImportError:
    MISSING.append("google-auth-oauthlib")

try:
    from google.auth.transport.requests import Request
except ImportError:
    MISSING.append("google-auth")

try:
    from googleapiclient.discovery import build
except ImportError:
    MISSING.append("google-api-python-client")

if MISSING:
    print("\n❌  Missing packages. Run:\n")
    print(f"    pip install {' '.join(MISSING)}\n")
    sys.exit(1)

# ── Config ────────────────────────────────────────────────────
CLIENT_SECRET_FILE = "client_secret.json"
TOKEN_PICKLE_FILE  = "youtube_token.pkl"
SCOPES = [
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube",
    "https://www.googleapis.com/auth/youtube.readonly",
]


def check_existing_token():
    """Check if a valid token already exists."""
    if not os.path.exists(TOKEN_PICKLE_FILE):
        return None
    try:
        with open(TOKEN_PICKLE_FILE, "rb") as f:
            creds = pickle.load(f)
        if creds and creds.valid:
            return creds
        if creds and creds.expired and creds.refresh_token:
            print("🔄  Refreshing existing token...")
            creds.refresh(Request())
            with open(TOKEN_PICKLE_FILE, "wb") as f:
                pickle.dump(creds, f)
            print("✅  Token refreshed successfully.")
            return creds
    except Exception as e:
        print(f"⚠️  Could not load existing token: {e}")
    return None


def generate_new_token():
    """Run the OAuth flow to generate a new token."""
    if not os.path.exists(CLIENT_SECRET_FILE):
        print(f"\n❌  '{CLIENT_SECRET_FILE}' not found!\n")
        print("Steps to fix:")
        print("  1. Go to https://console.cloud.google.com/")
        print("  2. APIs & Services → Credentials")
        print("  3. Create OAuth 2.0 Client ID → Desktop App")
        print("  4. Download JSON → rename to 'client_secret.json'")
        print("  5. Place it in:", os.path.abspath("."))
        print("  6. Re-run this script\n")
        sys.exit(1)

    print("\n🌐  Opening browser for Google OAuth authorisation...")
    print("    → Log in with the Google account that OWNS your YouTube channel.\n")

    try:
        flow = InstalledAppFlow.from_client_secrets_file(CLIENT_SECRET_FILE, SCOPES)
        # Try local server first (opens browser automatically)
        try:
            creds = flow.run_local_server(
                port=8080,
                prompt="consent",
                authorization_prompt_message="",
                success_message="✅ Authorisation complete! You can close this tab.",
                open_browser=True,
            )
        except OSError:
            # Port 8080 busy — try another port
            creds = flow.run_local_server(
                port=0,
                prompt="consent",
                open_browser=True,
            )
    except Exception as e:
        print(f"\n⚠️  Browser flow failed: {e}")
        print("   Trying console (copy-paste) flow instead...\n")
        flow = InstalledAppFlow.from_client_secrets_file(CLIENT_SECRET_FILE, SCOPES)
        creds = flow.run_console()

    return creds


def save_token(creds):
    """Save credentials to pickle file."""
    with open(TOKEN_PICKLE_FILE, "wb") as f:
        pickle.dump(creds, f)
    size = os.path.getsize(TOKEN_PICKLE_FILE)
    print(f"\n✅  Token saved → {TOKEN_PICKLE_FILE} ({size} bytes)")


def verify_token(creds):
    """Verify the token works by fetching channel info."""
    print("\n🔍  Verifying token by fetching your channel info...")
    try:
        youtube = build("youtube", "v3", credentials=creds)
        response = youtube.channels().list(part="snippet,statistics", mine=True).execute()
        items = response.get("items", [])
        if not items:
            print("⚠️  Token works but no channel found on this account.")
            print("   Make sure you logged in with the account that owns the channel.")
            return False

        channel = items[0]
        name    = channel["snippet"]["title"]
        handle  = channel["snippet"].get("customUrl", "N/A")
        subs    = int(channel["statistics"].get("subscriberCount", 0))
        videos  = int(channel["statistics"].get("videoCount", 0))

        print(f"\n{'='*50}")
        print(f"  ✅  CHANNEL VERIFIED")
        print(f"{'='*50}")
        print(f"  Channel Name : {name}")
        print(f"  Handle       : {handle}")
        print(f"  Subscribers  : {subs:,}")
        print(f"  Total Videos : {videos:,}")
        print(f"{'='*50}\n")
        return True

    except Exception as e:
        print(f"⚠️  Verification request failed: {e}")
        print("   The token was saved but could not be verified right now.")
        print("   Try running astro_main.py — if it uploads, the token is fine.")
        return False


def export_token_as_env(creds):
    """
    Optionally export the token as a base64 env var string.
    Useful for running the bot in CI/CD or on a remote server.
    """
    import base64
    token_b64 = base64.b64encode(pickle.dumps(creds)).decode("utf-8")
    env_file = "token_env_export.txt"
    with open(env_file, "w") as f:
        f.write(f"YOUTUBE_TOKEN_B64={token_b64}\n")
    print(f"📋  Base64 token exported → {env_file}")
    print("   Set this as an environment variable on your server:\n")
    print(f"   $env:YOUTUBE_TOKEN_B64 = (Get-Content {env_file})")
    print(f"   # or on Linux:  export YOUTUBE_TOKEN_B64=$(cat {env_file})\n")


def main():
    print("\n" + "="*55)
    print("  ASTRO ORACLE — YouTube OAuth Token Generator")
    print("="*55)

    # Step 1: Check if token already valid
    creds = check_existing_token()

    if creds:
        print(f"\n✅  Valid token already exists in '{TOKEN_PICKLE_FILE}'.")
        choice = input("   Re-generate anyway? (y/N): ").strip().lower()
        if choice != "y":
            verify_token(creds)
            print("Nothing to do. Your bot is ready to upload! 🚀\n")
            return

    # Step 2: Generate new token
    creds = generate_new_token()

    if not creds:
        print("\n❌  Failed to obtain credentials.")
        sys.exit(1)

    # Step 3: Save token
    save_token(creds)

    # Step 4: Verify it works
    verify_token(creds)

    # Step 5: Offer base64 export for server use
    choice = input("Export token as base64 env variable (for server/CI use)? (y/N): ").strip().lower()
    if choice == "y":
        export_token_as_env(creds)

    print("🎉  Setup complete! You can now run:\n")
    print("    python astro_main.py\n")


if __name__ == "__main__":
    main()
