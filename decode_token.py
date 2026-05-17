"""
decode_token.py — Called by GitHub Actions to decode YOUTUBE_TOKEN_B64
and proactively refresh it before the main pipeline runs.
"""
import os, base64, json, sys
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request

# Read secret from environment
raw = os.environ.get("YOUTUBE_TOKEN_B64", "")
if not raw:
    print("❌ YOUTUBE_TOKEN_B64 env var is empty.", file=sys.stderr)
    sys.exit(1)

# Strip ALL whitespace (handles Windows \r\n, trailing newlines, spaces)
cleaned = "".join(raw.split())

# Decode base64
try:
    decoded = base64.b64decode(cleaned).decode("utf-8")
except Exception as e:
    print(f"❌ base64 decode failed: {e}", file=sys.stderr)
    sys.exit(1)

# Validate JSON
try:
    data = json.loads(decoded)
except Exception as e:
    print(f"❌ token.json is not valid JSON: {e}", file=sys.stderr)
    sys.exit(1)

# Write to disk
with open("token.json", "w") as f:
    f.write(decoded)
print("✅ token.json written.")

# Refresh the OAuth token
creds = Credentials(
    token=data.get("token"),
    refresh_token=data.get("refresh_token"),
    token_uri=data.get("token_uri", "https://oauth2.googleapis.com/token"),
    client_id=data.get("client_id"),
    client_secret=data.get("client_secret"),
    scopes=data.get("scopes"),
)

if creds.refresh_token:
    creds.refresh(Request())
    updated = json.loads(creds.to_json())
    with open("token.json", "w") as f:
        json.dump(updated, f)
    print("✅ Token refreshed and written back to token.json")
else:
    print("⚠️  No refresh_token found — skipping refresh.")
