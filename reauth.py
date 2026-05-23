from google_auth_oauthlib.flow import InstalledAppFlow

# Must match the scopes used by the rest of the pipeline
SCOPES = [
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube",
    "https://www.googleapis.com/auth/youtube.readonly",
]

# Consistent filename used across all pipeline scripts
flow = InstalledAppFlow.from_client_secrets_file("client_secret.json", SCOPES)
creds = flow.run_local_server(port=0)

# Save as token.json (used by decode_token.py and youtube_uploader_astro.py)
import json
with open("token.json", "w") as f:
    f.write(creds.to_json())

# Also save as pickle for local dev / generate_token.py compatibility
import pickle
with open("youtube_token.pkl", "wb") as f:
    pickle.dump(creds, f)

print(creds.to_json())  # Copy this for your GitHub secret
print("\n✅ token.json and youtube_token.pkl written.")
