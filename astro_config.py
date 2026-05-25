import os

# ── API Keys ────────────────────────────────────────────────────────────────
GROQ_API_KEY   = os.environ.get("GROQ_API_KEY")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")

# ── Channel identity ─────────────────────────────────────────────────────────
CHANNEL_NAME = "Astro Oracle"

# ── Zodiac signs (tropical order) ────────────────────────────────────────────
ZODIAC_SIGNS = [
    "Aries", "Taurus", "Gemini", "Cancer",
    "Leo", "Virgo", "Libra", "Scorpio",
    "Sagittarius", "Capricorn", "Aquarius", "Pisces",
]

# ── Local dedup / tracking DB ─────────────────────────────────────────────────
# Stores which videos have already been uploaded this week so reruns are safe.
UPLOADED_ASTRO_DB = os.environ.get("UPLOADED_ASTRO_DB", "astro_uploaded.json")

# ── Output file paths ─────────────────────────────────────────────────────────
ASTRO_OUTPUT_VIDEO  = os.environ.get("ASTRO_OUTPUT_VIDEO",  "astro_output.mp4")
ASTRO_THUMBNAIL     = os.environ.get("ASTRO_THUMBNAIL",     "astro_thumbnail.jpg")
ASTRO_SHORT_VIDEO   = os.environ.get("ASTRO_SHORT_VIDEO",   "astro_short.mp4")
ASTRO_SHORT_THUMB   = os.environ.get("ASTRO_SHORT_THUMB",   "astro_short_thumb.jpg")