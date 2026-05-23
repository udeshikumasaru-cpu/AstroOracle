import os, base64, pickle, json, sys
from google.auth.transport.requests import Request

raw = os.environ.get("YOUTUBE_TOKEN_B64", "")
if not raw:
    print("YOUTUBE_TOKEN_B64 missing", file=sys.stderr)
    sys.exit(1)

cleaned = "".join(raw.split())

try:
    creds = pickle.loads(base64.b64decode(cleaned))
except Exception as e:
    print(f"Failed to load credentials: {e}", file=sys.stderr)
    sys.exit(1)

print(f"Credentials loaded. Valid: {creds.valid}, Expired: {creds.expired}")

if creds.expired and creds.refresh_token:
    creds.refresh(Request())
    print("Token refreshed OK")
elif creds.expired and not creds.refresh_token:
    print("ERROR: token is expired and has no refresh_token.", file=sys.stderr)
    print("Re-run generate_token.py locally and update the YOUTUBE_TOKEN_B64 secret.", file=sys.stderr)
    sys.exit(1)

# Save as JSON for the main pipeline (also consumed by youtube_uploader_astro.py)
token_data = json.loads(creds.to_json())
with open("token.json", "w") as f:
    json.dump(token_data, f)
print("token.json written")