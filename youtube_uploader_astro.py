# ============================================================
#  youtube_uploader_astro.py
#  YouTube upload wrapper for Astro Oracle channel.
#  Uses the SAME OAuth token as the cricket bot
#  but sets category_id=22 (People & Blogs) for astrology.
# ============================================================

import os, re, sys, time, pickle, base64, socket, tempfile
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaFileUpload
from google.auth.transport.requests import Request

YOUTUBE_CLIENT_SECRET = "client_secret.json"
YOUTUBE_TOKEN_PICKLE  = "youtube_token.pkl"
SCOPES = [
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube",
]
MAX_RETRIES = 10
RETRIABLE_STATUS = {500, 502, 503, 504}
RETRIABLE_EXCEPTIONS = (socket.error, ConnectionResetError)


def _sanitize_tags(tags):
    FORBIDDEN = re.compile(r'[,<>&"\'\u2014\u2013\u2012\u2010]')
    clean, total = [], 0
    for tag in tags:
        if not tag: continue
        tag = FORBIDDEN.sub('', str(tag)).strip()
        tag = re.sub(r'\s+', ' ', tag).strip()
        if len(tag) > 30: tag = tag[:30].rsplit(' ', 1)[0].strip()
        if not tag or len(tag) < 2: continue
        cost = len(tag) + 1
        if total + cost > 498: break
        clean.append(tag)
        total += cost
    return clean


def _get_credentials():
    """
    Load credentials in priority order:
      1. YOUTUBE_TOKEN_B64 env var  (GitHub Actions / CI)
      2. youtube_token.pkl file     (local dev, or written by workflow)
    After loading, refresh if expired and persist the refreshed token
    back to both the pickle file and update the in-memory b64 copy.
    """
    creds = None
    token_b64 = os.environ.get("YOUTUBE_TOKEN_B64", "").strip()

    if token_b64:
        try:
            creds = pickle.loads(base64.b64decode(token_b64))
            print("   🔑 Credentials loaded from YOUTUBE_TOKEN_B64 env var.")
        except Exception as e:
            print(f"   ⚠️  Failed to decode YOUTUBE_TOKEN_B64: {e}")
            creds = None

    if creds is None and os.path.exists(YOUTUBE_TOKEN_PICKLE):
        try:
            with open(YOUTUBE_TOKEN_PICKLE, "rb") as f:
                creds = pickle.load(f)
            print(f"   🔑 Credentials loaded from {YOUTUBE_TOKEN_PICKLE}.")
        except Exception as e:
            print(f"   ⚠️  Failed to load {YOUTUBE_TOKEN_PICKLE}: {e}")
            creds = None

    if creds is None:
        raise RuntimeError(
            "No YouTube credentials found.\n"
            "  • Locally: run  python generate_token.py\n"
            "  • GitHub Actions: update the YOUTUBE_TOKEN_B64 secret."
        )

    # ── Refresh if expired ────────────────────────────────────────────────────
    if creds.expired and creds.refresh_token:
        print("   🔄 Token expired — refreshing...")
        try:
            creds.refresh(Request())
            print("   ✅ Token refreshed successfully.")
            # Persist refreshed token to pickle so subsequent uploads in the
            # same run don't need to refresh again.
            with open(YOUTUBE_TOKEN_PICKLE, "wb") as f:
                pickle.dump(creds, f)
        except Exception as e:
            raise RuntimeError(
                f"Token refresh failed: {e}\n"
                "Re-run generate_token.py locally and update the GitHub secret."
            )
    elif creds.expired and not creds.refresh_token:
        raise RuntimeError(
            "Token is expired and has no refresh_token.\n"
            "Re-run generate_token.py locally and update the GitHub secret."
        )

    return creds


def upload_video_astro(video_path, title, description, thumbnail_path,
                       tags, privacy="public", category_id="22",
                       default_language="en"):
    """
    Upload a video to YouTube and optionally set a thumbnail.
    Returns the YouTube video ID on success.
    Raises on unrecoverable errors.
    """
    if not os.path.exists(video_path):
        raise FileNotFoundError(f"Video not found: {video_path}")

    tags = _sanitize_tags(tags)

    # ── Write client_secret.json from env if not already on disk ─────────────
    secret_json = os.environ.get("YOUTUBE_CLIENT_SECRET_JSON", "").strip()
    if secret_json and not os.path.exists(YOUTUBE_CLIENT_SECRET):
        with open(YOUTUBE_CLIENT_SECRET, "w") as f:
            f.write(secret_json)
        print(f"   ✅ {YOUTUBE_CLIENT_SECRET} written from env var.")

    creds   = _get_credentials()
    youtube = build("youtube", "v3", credentials=creds)

    body = {
        "snippet": {
            "title":           title[:100],
            "description":     description[:5000],
            "tags":            tags,
            "categoryId":      category_id,
            "defaultLanguage": default_language,
        },
        "status": {
            "privacyStatus":          privacy,
            "selfDeclaredMadeForKids": False,
        },
    }

    media = MediaFileUpload(
        video_path,
        mimetype="video/mp4",
        resumable=True,
        chunksize=10 * 1024 * 1024,
    )
    request = youtube.videos().insert(
        part=",".join(body.keys()), body=body, media_body=media
    )

    video_id, retry = None, 0
    while video_id is None:
        try:
            status, response = request.next_chunk()
            if status:
                print(f"\r   Progress: {int(status.progress() * 100)}%", end="", flush=True)
            if response:
                print()
                video_id = response.get("id")
                if not video_id:
                    raise RuntimeError(f"Upload succeeded but no video ID in response: {response}")
                print(f"   ✅ https://www.youtube.com/watch?v={video_id}")

        except HttpError as e:
            if e.resp.status in RETRIABLE_STATUS:
                retry += 1
                if retry > MAX_RETRIES:
                    raise
                wait = min(2 ** retry, 64)
                print(f"\n   ⚠️  HTTP {e.resp.status} — retrying in {wait}s... (attempt {retry}/{MAX_RETRIES})")
                time.sleep(wait)
            else:
                # Surface the full error for easier debugging
                raise RuntimeError(f"YouTube API error {e.resp.status}: {e}") from e

        except RETRIABLE_EXCEPTIONS as e:
            retry += 1
            if retry > MAX_RETRIES:
                raise
            wait = min(2 ** retry, 64)
            print(f"\n   ⚠️  Network error ({e}) — retrying in {wait}s... (attempt {retry}/{MAX_RETRIES})")
            time.sleep(wait)

    # ── Set thumbnail ─────────────────────────────────────────────────────────
    if thumbnail_path and os.path.exists(thumbnail_path):
        try:
            youtube.thumbnails().set(
                videoId=video_id,
                media_body=MediaFileUpload(thumbnail_path, mimetype="image/jpeg"),
            ).execute()
            print("   ✅ Thumbnail set")
        except HttpError as e:
            print(f"   ⚠️  Thumbnail failed (non-fatal): {e}")
    elif thumbnail_path:
        print(f"   ⚠️  Thumbnail not found at '{thumbnail_path}' — skipping.")

    return video_id
