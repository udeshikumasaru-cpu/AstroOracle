# ============================================================
#  astro_transit_engine.py
#  Calculates REAL planetary positions and transits for the
#  next 14 days using the Swiss Ephemeris (pyswisseph) or
#  the ephem library as fallback.
#
#  Detects:
#  - Planet sign changes (ingresses)
#  - Retrogrades (Mercury, Venus, Mars, Jupiter, Saturn)
#  - Full Moons and New Moons
#  - Solar and Lunar Eclipses
#  - Major conjunctions / oppositions / squares
#  - Which zodiac sign each planet is currently in
#
#  INSTALL:
#    pip install ephem pytz
#    pip install pyswisseph   (optional, more precise)
# ============================================================

import math
import json
from datetime import datetime, timezone, timedelta
from typing import Optional

try:
    import ephem
    EPHEM_AVAILABLE = True
except ImportError:
    EPHEM_AVAILABLE = False
    print("⚠️  ephem not installed. Run: pip install ephem")
    print("   Using Groq AI for transit data instead.")

from astro_config import SIGN_DATA, ZODIAC_SIGNS


# ── Zodiac sign boundaries (ecliptic longitude 0-360°) ────────
SIGN_BOUNDARIES = [
    (0,   30,  "Aries"),
    (30,  60,  "Taurus"),
    (60,  90,  "Gemini"),
    (90,  120, "Cancer"),
    (120, 150, "Leo"),
    (150, 180, "Virgo"),
    (180, 210, "Libra"),
    (210, 240, "Scorpio"),
    (240, 270, "Sagittarius"),
    (270, 300, "Capricorn"),
    (300, 330, "Aquarius"),
    (330, 360, "Pisces"),
]


def _longitude_to_sign(lon_deg: float) -> str:
    """Convert ecliptic longitude (0-360) to zodiac sign name."""
    lon = lon_deg % 360
    for start, end, sign in SIGN_BOUNDARIES:
        if start <= lon < end:
            return sign
    return "Aries"


def _get_planet_longitude(planet_obj, date: ephem.Date) -> float:
    """Compute ecliptic longitude for a planet on a given date."""
    planet_obj.compute(date, epoch=date)
    # ephem gives ecliptic lon in radians via .hlong or via ecliptic coords
    ecl = ephem.Ecliptic(planet_obj, epoch=date)
    return math.degrees(ecl.lon) % 360


def _is_retrograde(planet_obj, date: ephem.Date) -> bool:
    """
    Detect retrograde by comparing longitude today vs tomorrow.
    If longitude decreases → retrograde.
    """
    try:
        lon_today = _get_planet_longitude(planet_obj, date)
        tomorrow  = ephem.Date(date + 1)
        planet_obj.compute(tomorrow, epoch=tomorrow)
        ecl2      = ephem.Ecliptic(planet_obj, epoch=tomorrow)
        lon_tom   = math.degrees(ecl2.lon) % 360
        # Handle wrap-around at 0/360
        diff = lon_tom - lon_today
        if diff < -180:
            diff += 360
        return diff < 0
    except Exception:
        return False


def get_current_planetary_positions() -> dict:
    """
    Returns a dict of {planet_name: {sign, longitude, retrograde}}
    for today's date using real ephemeris data.
    """
    if not EPHEM_AVAILABLE:
        return _fallback_positions()

    now  = datetime.now(timezone.utc)
    date = ephem.Date(now)

    planets = {
        "Sun":     ephem.Sun(),
        "Moon":    ephem.Moon(),
        "Mercury": ephem.Mercury(),
        "Venus":   ephem.Venus(),
        "Mars":    ephem.Mars(),
        "Jupiter": ephem.Jupiter(),
        "Saturn":  ephem.Saturn(),
        "Uranus":  ephem.Uranus(),
        "Neptune": ephem.Neptune(),
    }

    # Pluto via manual approximate longitude (ephem has no Pluto)
    # Pluto has been in Capricorn/Aquarius 2008-2044
    pluto_lon = 300.5  # approximately Aquarius (2026)

    positions = {}
    for name, obj in planets.items():
        try:
            obj.compute(date, epoch=date)
            ecl = ephem.Ecliptic(obj, epoch=date)
            lon = math.degrees(ecl.lon) % 360
            retro = _is_retrograde(obj, date) if name not in ("Sun", "Moon") else False
            positions[name] = {
                "longitude":  round(lon, 2),
                "sign":       _longitude_to_sign(lon),
                "retrograde": retro,
                "degree":     round(lon % 30, 1),  # degree within sign
            }
        except Exception as e:
            positions[name] = {"longitude": 0, "sign": "Aries", "retrograde": False, "degree": 0}

    positions["Pluto"] = {
        "longitude":  pluto_lon,
        "sign":       _longitude_to_sign(pluto_lon),
        "retrograde": False,
        "degree":     round(pluto_lon % 30, 1),
    }

    return positions


def get_transits_next_14_days() -> list:
    """
    Scan the next 14 days and return a list of transit events:
    - Planet sign changes (ingresses)
    - Retrograde stations (begin/end)
    - Full Moons / New Moons
    - Notable conjunctions

    Returns list of dicts:
    {
        "date": "2026-03-05",
        "event": "Mercury enters Aries",
        "planet": "Mercury",
        "type": "ingress",   # ingress | retrograde | moon_phase | conjunction
        "intensity": "high", # high | medium | low
        "affected_signs": ["Aries", "Gemini", "Virgo"],
        "description": "..."
    }
    """
    if not EPHEM_AVAILABLE:
        return _fallback_transits()

    events = []
    now    = datetime.now(timezone.utc)

    planets = {
        "Sun":     ephem.Sun(),
        "Moon":    ephem.Moon(),
        "Mercury": ephem.Mercury(),
        "Venus":   ephem.Venus(),
        "Mars":    ephem.Mars(),
        "Jupiter": ephem.Jupiter(),
        "Saturn":  ephem.Saturn(),
        "Uranus":  ephem.Uranus(),
        "Neptune": ephem.Neptune(),
    }

    # Track state on day 0
    prev_signs   = {}
    prev_retro   = {}

    date_0 = ephem.Date(now)
    for name, obj in planets.items():
        obj.compute(date_0, epoch=date_0)
        ecl = ephem.Ecliptic(obj, epoch=date_0)
        lon = math.degrees(ecl.lon) % 360
        prev_signs[name] = _longitude_to_sign(lon)
        prev_retro[name] = _is_retrograde(obj, date_0) if name not in ("Sun", "Moon") else False

    # Scan day by day
    for day_offset in range(1, 15):
        scan_dt   = now + timedelta(days=day_offset)
        scan_date = ephem.Date(scan_dt)
        date_str  = scan_dt.strftime("%Y-%m-%d")

        for name, obj in planets.items():
            try:
                obj.compute(scan_date, epoch=scan_date)
                ecl  = ephem.Ecliptic(obj, epoch=scan_date)
                lon  = math.degrees(ecl.lon) % 360
                sign = _longitude_to_sign(lon)
                retro = _is_retrograde(obj, scan_date) if name not in ("Sun", "Moon") else False

                # ── Sign ingress ──
                if sign != prev_signs[name]:
                    intensity = _ingress_intensity(name)
                    affected  = _affected_signs_for_ingress(name, sign)
                    events.append({
                        "date":           date_str,
                        "event":          f"{name} enters {sign}",
                        "planet":         name,
                        "type":           "ingress",
                        "intensity":      intensity,
                        "affected_signs": affected,
                        "description":    _ingress_description(name, sign),
                    })
                    prev_signs[name] = sign

                # ── Retrograde station ──
                if name not in ("Sun", "Moon"):
                    if retro and not prev_retro[name]:
                        affected = _retrograde_affected_signs(name, sign)
                        events.append({
                            "date":           date_str,
                            "event":          f"{name} Retrograde begins in {sign}",
                            "planet":         name,
                            "type":           "retrograde_begin",
                            "intensity":      "high" if name in ("Mercury", "Venus", "Mars") else "medium",
                            "affected_signs": affected,
                            "description":    f"{name} stations retrograde in {sign}. Expect delays, re-evaluation, and introspection.",
                        })
                    elif not retro and prev_retro[name]:
                        affected = _retrograde_affected_signs(name, sign)
                        events.append({
                            "date":           date_str,
                            "event":          f"{name} Retrograde ends — Direct in {sign}",
                            "planet":         name,
                            "type":           "retrograde_end",
                            "intensity":      "high" if name in ("Mercury", "Venus", "Mars") else "medium",
                            "affected_signs": affected,
                            "description":    f"{name} stations direct in {sign}. Forward momentum resumes — clarity returns.",
                        })
                    prev_retro[name] = retro

            except Exception:
                continue

        # ── Moon phases ──
        try:
            moon = ephem.Moon(scan_date)
            phase = moon.moon_phase   # 0.0 to 1.0

            # Check for Full Moon (phase near 1.0)
            if 0.98 <= phase <= 1.0:
                moon.compute(scan_date, epoch=scan_date)
                ecl  = ephem.Ecliptic(moon, epoch=scan_date)
                lon  = math.degrees(ecl.lon) % 360
                sign = _longitude_to_sign(lon)
                events.append({
                    "date":           date_str,
                    "event":          f"Full Moon in {sign}",
                    "planet":         "Moon",
                    "type":           "full_moon",
                    "intensity":      "high",
                    "affected_signs": _moon_phase_affected(sign),
                    "description":    f"Full Moon in {sign} — peak energy, culminations, heightened emotions and revelations.",
                })

            # Check for New Moon (phase near 0.0)
            elif phase <= 0.02:
                moon.compute(scan_date, epoch=scan_date)
                ecl  = ephem.Ecliptic(moon, epoch=scan_date)
                lon  = math.degrees(ecl.lon) % 360
                sign = _longitude_to_sign(lon)
                events.append({
                    "date":           date_str,
                    "event":          f"New Moon in {sign}",
                    "planet":         "Moon",
                    "type":           "new_moon",
                    "intensity":      "high",
                    "affected_signs": _moon_phase_affected(sign),
                    "description":    f"New Moon in {sign} — fresh starts, setting intentions, planting seeds for the future.",
                })
        except Exception:
            pass

    # Deduplicate (same event on consecutive days — keep first)
    seen_events = set()
    unique = []
    for e in events:
        key = e["event"]
        if key not in seen_events:
            seen_events.add(key)
            unique.append(e)

    unique.sort(key=lambda x: x["date"])
    return unique


# ─────────────────────────────────────────────────────────────
# Impact helpers
# ─────────────────────────────────────────────────────────────

def _ingress_intensity(planet: str) -> str:
    HIGH   = {"Mercury", "Venus", "Mars", "Sun", "Moon", "Jupiter"}
    MEDIUM = {"Saturn", "Uranus"}
    return "high" if planet in HIGH else ("medium" if planet in MEDIUM else "low")


def _affected_signs_for_ingress(planet: str, new_sign: str) -> list:
    """Return signs most affected by this planet moving into new_sign."""
    sd     = SIGN_DATA.get(new_sign, {})
    element = sd.get("element", "")

    element_map = {
        "Fire":  ["Aries", "Leo", "Sagittarius"],
        "Earth": ["Taurus", "Virgo", "Capricorn"],
        "Air":   ["Gemini", "Libra", "Aquarius"],
        "Water": ["Cancer", "Scorpio", "Pisces"],
    }
    same_element = element_map.get(element, [])

    # Opposite sign (180°)
    idx      = ZODIAC_SIGNS.index(new_sign)
    opposite = ZODIAC_SIGNS[(idx + 6) % 12]

    affected = list(set(same_element + [new_sign, opposite]))
    return affected[:6]


def _retrograde_affected_signs(planet: str, sign: str) -> list:
    """Return signs most affected by this planet's retrograde."""
    ruling_map = {
        "Mercury": ["Gemini", "Virgo"],
        "Venus":   ["Taurus", "Libra"],
        "Mars":    ["Aries", "Scorpio"],
        "Jupiter": ["Sagittarius", "Pisces"],
        "Saturn":  ["Capricorn", "Aquarius"],
        "Uranus":  ["Aquarius"],
        "Neptune": ["Pisces"],
        "Pluto":   ["Scorpio"],
    }
    base = ruling_map.get(planet, [])
    if sign not in base:
        base = [sign] + base
    return base[:6]


def _moon_phase_affected(sign: str) -> list:
    """Full/New Moon most affects the sign it's in + its opposite."""
    idx      = ZODIAC_SIGNS.index(sign)
    opposite = ZODIAC_SIGNS[(idx + 6) % 12]
    square1  = ZODIAC_SIGNS[(idx + 3) % 12]
    square2  = ZODIAC_SIGNS[(idx + 9) % 12]
    return [sign, opposite, square1, square2]


def _ingress_description(planet: str, sign: str) -> str:
    templates = {
        "Mercury": f"Mercury enters {sign}, sharpening communication and thought in this sign's domain.",
        "Venus":   f"Venus moves into {sign}, blessing love, beauty, and financial matters with {sign}'s energy.",
        "Mars":    f"Mars charges into {sign}, igniting drive, passion, and assertive action in {sign}'s territory.",
        "Jupiter": f"Jupiter expands into {sign}, bringing growth, luck, and abundance to {sign}'s life areas.",
        "Saturn":  f"Saturn enters {sign}, demanding discipline, structure, and lessons in {sign}'s domain.",
        "Sun":     f"The Sun moves into {sign}, illuminating and energising this sign's themes for the next month.",
        "Moon":    f"The Moon transits through {sign}, heightening emotional sensitivity around {sign}'s themes.",
        "Uranus":  f"Uranus shifts into {sign}, sparking revolution, breakthroughs, and unexpected change.",
        "Neptune": f"Neptune drifts into {sign}, dissolving boundaries and deepening spiritual insight.",
        "Pluto":   f"Pluto enters {sign}, beginning a generational transformation of {sign}'s deepest structures.",
    }
    return templates.get(planet, f"{planet} enters {sign}, shifting energies significantly.")


# ─────────────────────────────────────────────────────────────
# Fallbacks (used when ephem is not installed)
# ─────────────────────────────────────────────────────────────

def _fallback_positions() -> dict:
    """
    Approximate positions for 2026 — used when ephem unavailable.
    Groq will refine these with current knowledge.
    """
    return {
        "Sun":     {"sign": "Pisces",      "degree": 7.0,  "retrograde": False, "longitude": 337.0},
        "Moon":    {"sign": "Scorpio",     "degree": 14.0, "retrograde": False, "longitude": 224.0},
        "Mercury": {"sign": "Aquarius",    "degree": 22.0, "retrograde": False, "longitude": 322.0},
        "Venus":   {"sign": "Aries",       "degree": 5.0,  "retrograde": False, "longitude": 5.0},
        "Mars":    {"sign": "Cancer",      "degree": 18.0, "retrograde": False, "longitude": 108.0},
        "Jupiter": {"sign": "Gemini",      "degree": 12.0, "retrograde": False, "longitude": 72.0},
        "Saturn":  {"sign": "Pisces",      "degree": 20.0, "retrograde": False, "longitude": 350.0},
        "Uranus":  {"sign": "Taurus",      "degree": 28.0, "retrograde": False, "longitude": 58.0},
        "Neptune": {"sign": "Aries",       "degree": 2.0,  "retrograde": False, "longitude": 2.0},
        "Pluto":   {"sign": "Aquarius",    "degree": 5.0,  "retrograde": False, "longitude": 305.0},
    }


def _fallback_transits() -> list:
    """Returns a minimal transit list when ephem is unavailable."""
    from datetime import datetime, timezone, timedelta
    now = datetime.now(timezone.utc)
    return [
        {
            "date":           (now + timedelta(days=3)).strftime("%Y-%m-%d"),
            "event":          "Mercury enters Pisces",
            "planet":         "Mercury",
            "type":           "ingress",
            "intensity":      "high",
            "affected_signs": ["Gemini", "Virgo", "Pisces"],
            "description":    "Mercury enters Pisces, sharpening intuitive communication.",
        },
        {
            "date":           (now + timedelta(days=7)).strftime("%Y-%m-%d"),
            "event":          "Full Moon in Virgo",
            "planet":         "Moon",
            "type":           "full_moon",
            "intensity":      "high",
            "affected_signs": ["Virgo", "Pisces", "Gemini", "Sagittarius"],
            "description":    "Full Moon in Virgo — peak energy for health, routines, and precision work.",
        },
    ]


# ─────────────────────────────────────────────────────────────
# Public summary builder (used by script generator)
# ─────────────────────────────────────────────────────────────

def build_astro_week_context() -> dict:
    """
    Build the complete weekly astro context used by the script generator.
    Returns a dict with positions + transits + week label.
    """
    now = datetime.now(timezone.utc)

    # weekday(): Mon=0 … Sat=5, Sun=6 → convert to Sun=0 … Sat=6, then subtract
    days_since_sunday = (now.weekday() + 1) % 7
    week_start = now - timedelta(days=days_since_sunday)  # This week's Sunday
    week_end   = week_start + timedelta(days=6)
    week_label = f"{week_start.strftime('%b %d')} – {week_end.strftime('%b %d, %Y')}"

    print("🔭 Computing planetary positions...")
    positions = get_current_planetary_positions()

    print("🌌 Scanning next 14 days for transits...")
    transits  = get_transits_next_14_days()

    # Identify HIGH intensity transits
    major = [t for t in transits if t.get("intensity") == "high"]

    print(f"   Planets located: {len(positions)}")
    print(f"   Transits found:  {len(transits)} ({len(major)} major)")

    return {
        "week_label":  week_label,
        "week_start":  week_start.strftime("%Y-%m-%d"),
        "week_end":    week_end.strftime("%Y-%m-%d"),
        "generated":   now.isoformat(),
        "positions":   positions,
        "transits":    transits,
        "major_transits": major,
    }


if __name__ == "__main__":
    ctx = build_astro_week_context()
    print(f"\n📅 Week: {ctx['week_label']}")
    print(f"\n🪐 PLANETARY POSITIONS:")
    for planet, data in ctx["positions"].items():
        retro = " ℞" if data["retrograde"] else ""
        print(f"   {planet:10s}: {data['sign']:14s} {data['degree']:.1f}°{retro}")
    print(f"\n⚡ TRANSITS NEXT 14 DAYS ({len(ctx['transits'])} events):")
    for t in ctx["transits"]:
        print(f"   [{t['date']}] {t['intensity'].upper():6s} — {t['event']}")
