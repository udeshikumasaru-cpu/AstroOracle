from google_auth_oauthlib.flow import InstalledAppFlow

SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]

flow = InstalledAppFlow.from_client_secrets_file("client_secrets.json", SCOPES)
creds = flow.run_local_server(port=0)

# Save the new credentials
import json
with open("token.json", "w") as f:
    f.write(creds.to_json())

print(creds.to_json())  # Copy this for your GitHub secret