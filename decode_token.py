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

# Save as JSON for the main pipeline
token_data = json.loads(creds.to_json())
with open("token.json", "w") as f:
    json.dump(token_data, f)
print("token.json written")

# Save refreshed pickle back for the secret update step
import pickle
refreshed_b64 = base64.b64encode(pickle.dumps(creds)).decode()
with open("token_refreshed_b64.txt", "w") as f:
    f.write(refreshed_b64)
print("token_refreshed_b64.txt written")