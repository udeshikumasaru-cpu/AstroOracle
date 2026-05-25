import os

# ── API Keys ──────────────────────────────────────────────────────────────────
GROQ_API_KEY   = os.environ.get("GROQ_API_KEY")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")

# ── Channel identity ──────────────────────────────────────────────────────────
CHANNEL_NAME   = "Astro Oracle"
CHANNEL_HANDLE = "@AstroOracle"          # used by astro_shorts.py

# ── Zodiac signs (tropical order) ─────────────────────────────────────────────
ZODIAC_SIGNS = [
    "Aries", "Taurus", "Gemini", "Cancer",
    "Leo", "Virgo", "Libra", "Scorpio",
    "Sagittarius", "Capricorn", "Aquarius", "Pisces",
]

# ── Per-sign metadata ─────────────────────────────────────────────────────────
# Keys used across astro_thumbnail.py, astro_video_renderer.py, astro_shorts.py:
#   symbol, color (RGB tuple), dates, element, planet
SIGN_DATA = {
    "Aries":       {"symbol": "♈", "color": (220,  50,  50), "dates": "Mar 21 – Apr 19", "element": "Fire",  "planet": "Mars"},
    "Taurus":      {"symbol": "♉", "color": ( 80, 180,  80), "dates": "Apr 20 – May 20", "element": "Earth", "planet": "Venus"},
    "Gemini":      {"symbol": "♊", "color": (220, 200,  50), "dates": "May 21 – Jun 20", "element": "Air",   "planet": "Mercury"},
    "Cancer":      {"symbol": "♋", "color": (100, 180, 220), "dates": "Jun 21 – Jul 22", "element": "Water", "planet": "Moon"},
    "Leo":         {"symbol": "♌", "color": (240, 140,  20), "dates": "Jul 23 – Aug 22", "element": "Fire",  "planet": "Sun"},
    "Virgo":       {"symbol": "♍", "color": (140, 200, 100), "dates": "Aug 23 – Sep 22", "element": "Earth", "planet": "Mercury"},
    "Libra":       {"symbol": "♎", "color": (200, 130, 200), "dates": "Sep 23 – Oct 22", "element": "Air",   "planet": "Venus"},
    "Scorpio":     {"symbol": "♏", "color": (160,  40,  80), "dates": "Oct 23 – Nov 21", "element": "Water", "planet": "Pluto"},
    "Sagittarius": {"symbol": "♐", "color": (220, 100,  40), "dates": "Nov 22 – Dec 21", "element": "Fire",  "planet": "Jupiter"},
    "Capricorn":   {"symbol": "♑", "color": ( 80, 100, 140), "dates": "Dec 22 – Jan 19", "element": "Earth", "planet": "Saturn"},
    "Aquarius":    {"symbol": "♒", "color": ( 60, 180, 200), "dates": "Jan 20 – Feb 18", "element": "Air",   "planet": "Uranus"},
    "Pisces":      {"symbol": "♓", "color": (100, 100, 220), "dates": "Feb 19 – Mar 20", "element": "Water", "planet": "Neptune"},
}

# ── Brand colours (RGB tuples — no alpha) ─────────────────────────────────────
BRAND_BG_COLOR      = (  8,   2,  30)   # deep space navy
BRAND_PRIMARY_COLOR = ( 90,  50, 180)   # cosmic purple
BRAND_ACCENT_COLOR  = (255, 210,  80)   # golden yellow
BRAND_GLOW_COLOR    = (180, 130, 255)   # soft violet glow

# ── TTS / audio ───────────────────────────────────────────────────────────────
TTS_VOICE          = os.environ.get("TTS_VOICE",     "en-US-AriaNeural")
TTS_VOICE_ALT      = os.environ.get("TTS_VOICE_ALT", "en-US-GuyNeural")

# ── Video encoding ────────────────────────────────────────────────────────────
VIDEO_FPS   = int(os.environ.get("VIDEO_FPS",   "24"))
VIDEO_CODEC = os.environ.get("VIDEO_CODEC",     "libx264")
AUDIO_CODEC = os.environ.get("AUDIO_CODEC",     "aac")

# ── Output file paths ─────────────────────────────────────────────────────────
ASTRO_VOICE_FILE  = os.environ.get("ASTRO_VOICE_FILE",  "astro_voice.mp3")
ASTRO_OUTPUT_VIDEO= os.environ.get("ASTRO_OUTPUT_VIDEO","astro_output.mp4")
ASTRO_THUMBNAIL   = os.environ.get("ASTRO_THUMBNAIL",   "astro_thumbnail.jpg")

ASTRO_SHORT_VIDEO = os.environ.get("ASTRO_SHORT_VIDEO", "astro_short.mp4")
ASTRO_SHORT_VOICE = os.environ.get("ASTRO_SHORT_VOICE", "astro_short_voice.mp3")
ASTRO_SHORT_THUMB = os.environ.get("ASTRO_SHORT_THUMB", "astro_short_thumb.jpg")

# ── Dedup / tracking DB ───────────────────────────────────────────────────────
# JSON file that records which videos were already uploaded this week,
# preventing duplicate uploads on reruns.
UPLOADED_ASTRO_DB = os.environ.get("UPLOADED_ASTRO_DB", "astro_uploaded.json")
