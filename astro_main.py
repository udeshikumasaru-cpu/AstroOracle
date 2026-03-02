#!/usr/bin/env python3
"""
astro_main.py — Astro Oracle YouTube Automation Engine

WEEKLY OUTPUT:
  1 x Weekly Omnibus Video  (all 12 signs, ~18 min)
  12 x Per-Sign Videos      (~9 min each)
  12 x Per-Sign Shorts      (45 sec each)
  N x Transit Specials      (auto-triggered for major events)
  TOTAL: 25+ videos/week, fully automated

RUN MODES:
  python astro_main.py                  -> Full weekly run
  python astro_main.py omnibus          -> Omnibus only
  python astro_main.py sign Aries       -> Single sign
  python astro_main.py transit          -> Transit specials only
  python astro_main.py shorts           -> All Shorts
  python astro_main.py shorts Scorpio   -> One sign Short
  python astro_main.py debug            -> Show data, no upload

CRON (every Sunday 08:00 UTC):
  0 8 * * 0  cd /path/to/bot && python astro_main.py >> /var/log/astro.log 2>&1
"""

import os, sys, json, time
from datetime import datetime, timezone, timedelta

from astro_config import (
    UPLOADED_ASTRO_DB, ZODIAC_SIGNS, CHANNEL_NAME,
    ASTRO_OUTPUT_VIDEO, ASTRO_THUMBNAIL,
    ASTRO_SHORT_VIDEO, ASTRO_SHORT_THUMB,
)
from astro_transit_engine import build_astro_week_context
from astro_script_generator import (
    generate_weekly_omnibus_script, generate_sign_script,
    generate_transit_special_script,
    build_omnibus_seo, build_sign_seo, build_transit_special_seo,
)
from astro_video_renderer import (
    make_hook_slide, make_planet_overview_slide, make_sign_slide,
    make_transit_special_slide, make_closing_slide, render_astro_video,
)
from astro_thumbnail import (
    make_omnibus_thumbnail, make_sign_thumbnail, make_transit_thumbnail,
)
from astro_shorts import render_sign_short, build_sign_short_seo
from youtube_uploader_astro import upload_video_astro


# ------------------------------------------------------------------
# DB helpers
# ------------------------------------------------------------------
def load_db():
    if not os.path.exists(UPLOADED_ASTRO_DB):
        return {}
    with open(UPLOADED_ASTRO_DB) as f:
        data = json.load(f)
    raw    = data.get("processed", {})
    cutoff = (datetime.now(timezone.utc) - timedelta(days=14)).isoformat()
    pruned = {k: v for k, v in raw.items() if v >= cutoff}
    if len(pruned) != len(raw):
        _save_db(pruned)
    return pruned

def _save_db(d):
    with open(UPLOADED_ASTRO_DB, "w") as f:
        json.dump({"processed": d}, f, indent=2)

def mark_done(key):
    db = load_db(); db[key] = datetime.now(timezone.utc).isoformat(); _save_db(db)
    print(f"   Marked done: {key}")

def is_done(key):
    return key in load_db()

def _week_key():
    now = datetime.now(timezone.utc)
    return f"{now.year}-W{now.isocalendar()[1]:02d}"


# ------------------------------------------------------------------
# Upload helper
# ------------------------------------------------------------------
def _upload(video_path, title, description, thumbnail, tags, category="22"):
    return upload_video_astro(
        video_path=video_path, title=title, description=description,
        thumbnail_path=thumbnail, tags=tags, privacy="public",
        category_id=category, default_language="en",
    )


# ------------------------------------------------------------------
# PIPELINE 1 — Omnibus
# ------------------------------------------------------------------
def run_omnibus_pipeline(ctx):
    wk = f"omnibus_{_week_key()}"
    if is_done(wk):
        print(f"Omnibus already done this week"); return

    week, major, pos, trans = (
        ctx["week_label"], ctx.get("major_transits",[]),
        ctx.get("positions",{}), ctx.get("transits",[])
    )
    print(f"\n{'='*55}\n  OMNIBUS PIPELINE — {week}\n{'='*55}\n")

    script = generate_weekly_omnibus_script(ctx)
    with open(f"script_omnibus_{_week_key()}.txt","w",encoding="utf-8") as f: f.write(script)

    thumb  = make_omnibus_thumbnail(week, major)
    slides = [make_hook_slide(week, major), make_planet_overview_slide(pos, week)]
    for i in range(0, len(ZODIAC_SIGNS), 2):
        for s in ZODIAC_SIGNS[i:i+2]:
            st = [t for t in trans if s in t.get("affected_signs",[])]
            slides.append(make_sign_slide(s, week, pos, st))
    for t in major[:2]: slides.append(make_transit_special_slide(t))
    slides.append(make_closing_slide(week))

    video         = render_astro_video(script, ctx, slides, ASTRO_OUTPUT_VIDEO)
    title,desc,tags = build_omnibus_seo(ctx)
    vid_id        = _upload(video, title, desc, thumb, tags)
    mark_done(wk)
    print(f"OMNIBUS UPLOADED: https://www.youtube.com/watch?v={vid_id}")
    return vid_id


# ------------------------------------------------------------------
# PIPELINE 2 — Per-sign
# ------------------------------------------------------------------
def run_sign_pipeline(sign, ctx, upload_short=True):
    wk = f"sign_{sign.lower()}_{_week_key()}"
    if is_done(wk):
        print(f"{sign} already done this week"); return

    week  = ctx["week_label"]
    pos   = ctx.get("positions",{})
    trans = [t for t in ctx.get("transits",[]) if sign in t.get("affected_signs",[])]

    print(f"\n{'='*50}\n  {sign.upper()} PIPELINE — {week}\n{'='*50}\n")

    script = generate_sign_script(sign, ctx)
    with open(f"script_{sign.lower()}_{_week_key()}.txt","w",encoding="utf-8") as f: f.write(script)

    thumb  = make_sign_thumbnail(sign, week)
    slides = [
        make_hook_slide(f"{sign} — {week}", trans[:2]),
        make_sign_slide(sign, week, pos, trans),
        make_transit_special_slide(trans[0]) if trans else make_closing_slide(week),
        make_closing_slide(week),
    ]
    video_out    = ASTRO_OUTPUT_VIDEO.replace(".mp4", f"_{sign.lower()}.mp4")
    video        = render_astro_video(script, ctx, slides, video_out)
    title,desc,tags = build_sign_seo(sign, ctx)
    vid_id       = _upload(video, title, desc, thumb, tags)
    mark_done(wk)
    print(f"{sign} uploaded: https://www.youtube.com/watch?v={vid_id}")

    if upload_short:
        sk = f"short_{sign.lower()}_{_week_key()}"
        if not is_done(sk):
            try:
                sv      = render_sign_short(sign, week, ctx, pos)
                st,sd_,stags = build_sign_short_seo(sign, week, ctx)
                sthumb  = f"astro_thumb_{sign.lower()}.jpg"
                sid     = _upload(sv, st, sd_, sthumb, stags)
                mark_done(sk)
                print(f"{sign} Short: https://www.youtube.com/shorts/{sid}")
            except Exception as e:
                print(f"Short failed (non-fatal): {e}")
    return vid_id


# ------------------------------------------------------------------
# PIPELINE 3 — Transit special
# ------------------------------------------------------------------
def run_transit_pipeline(transit, ctx):
    tk = f"transit_{transit['event'].replace(' ','_')}_{transit['date']}"
    if is_done(tk):
        print(f"Transit already done: {transit['event']}"); return

    week   = ctx["week_label"]
    pos    = ctx.get("positions",{})
    print(f"\nTRANSIT PIPELINE — {transit['event']}\n")

    script = generate_transit_special_script(transit, ctx)
    thumb  = make_transit_thumbnail(transit)
    slides = [make_hook_slide(f"ALERT: {transit['event']}", [transit]),
               make_transit_special_slide(transit)]
    for sign in ZODIAC_SIGNS:
        st = [transit] if sign in transit.get("affected_signs",[]) else []
        slides.append(make_sign_slide(sign, week, pos, st))
    slides.append(make_closing_slide(week))

    tvid         = ASTRO_OUTPUT_VIDEO.replace(".mp4", f"_transit_{transit['planet'].lower()}.mp4")
    video        = render_astro_video(script, ctx, slides, tvid)
    title,desc,tags = build_transit_special_seo(transit, ctx)
    vid_id       = _upload(video, title, desc, thumb, tags)
    mark_done(tk)
    print(f"Transit uploaded: https://www.youtube.com/watch?v={vid_id}")
    return vid_id


# ------------------------------------------------------------------
# Debug
# ------------------------------------------------------------------
def debug_mode():
    print("\nDEBUG MODE — computing astro context...\n")
    ctx = build_astro_week_context()
    print(f"Week: {ctx['week_label']}")
    print("\nPLANETARY POSITIONS:")
    for p, d in ctx["positions"].items():
        r = " RETROGRADE" if d["retrograde"] else ""
        print(f"  {p:12s}: {d['sign']:14s} {d['degree']:.1f}deg{r}")
    print(f"\nTRANSITS NEXT 14 DAYS ({len(ctx['transits'])}):")
    for t in ctx["transits"]:
        print(f"  [{t['date']}] {t['intensity'].upper():6s} {t['event']}")
    print(f"\nMAJOR TRANSITS ({len(ctx['major_transits'])}):")
    for t in ctx["major_transits"]:
        print(f"  {t['event']} on {t['date']}")
    db = load_db(); wk = _week_key()
    print(f"\nDB STATUS (week {wk}):")
    print(f"  Omnibus: {'DONE' if f'omnibus_{wk}' in db else 'PENDING'}")
    for sign in ZODIAC_SIGNS:
        v = 'DONE' if f'sign_{sign.lower()}_{wk}' in db else 'PENDING'
        s = 'DONE' if f'short_{sign.lower()}_{wk}' in db else 'PENDING'
        print(f"  {sign:14s}: video={v}  short={s}")


# ------------------------------------------------------------------
# Entry point
# ------------------------------------------------------------------
def run_weekly(mode="all", sign_filter=None):
    print(f"\n{'='*55}")
    print(f"  ASTRO ORACLE — {mode.upper()} RUN")
    print(f"  {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}")
    print(f"{'='*55}\n")

    ctx = build_astro_week_context()
    print(f"Week: {ctx['week_label']} | Major transits: {len(ctx['major_transits'])}")
    uploaded = skipped = failed = 0

    if mode in ("all","omnibus"):
        try:
            v = run_omnibus_pipeline(ctx)
            uploaded += 1 if v else 0; skipped += 0 if v else 1
        except Exception as e:
            print(f"Omnibus failed: {e}"); import traceback; traceback.print_exc(); failed+=1

    if mode in ("all","signs","sign"):
        for sign in ([sign_filter] if sign_filter else ZODIAC_SIGNS):
            if sign not in ZODIAC_SIGNS: print(f"Unknown sign: {sign}"); continue
            try:
                v = run_sign_pipeline(sign, ctx, upload_short=(mode!="omnibus"))
                uploaded += 1 if v else 0; skipped += 0 if v else 1; time.sleep(5)
            except Exception as e:
                print(f"{sign} failed: {e}"); import traceback; traceback.print_exc(); failed+=1

    if mode in ("all","transit"):
        for t in ctx.get("major_transits",[]):
            try:
                v = run_transit_pipeline(t, ctx)
                uploaded += 1 if v else 0; skipped += 0 if v else 1; time.sleep(5)
            except Exception as e:
                print(f"Transit failed: {e}"); failed+=1

    if mode == "shorts":
        pos = ctx.get("positions",{}); week = ctx["week_label"]
        for sign in ([sign_filter] if sign_filter else ZODIAC_SIGNS):
            sk = f"short_{sign.lower()}_{_week_key()}"
            if is_done(sk): skipped+=1; continue
            try:
                sv = render_sign_short(sign, week, ctx, pos)
                st,sd_,stags = build_sign_short_seo(sign, week, ctx)
                sth = f"astro_thumb_{sign.lower()}.jpg"
                sid = _upload(sv, st, sd_, sth, stags)
                mark_done(sk); uploaded+=1
                print(f"{sign} Short: https://www.youtube.com/shorts/{sid}")
            except Exception as e:
                print(f"{sign} Short failed: {e}"); failed+=1

    print(f"\n{'='*55}")
    print(f"  RUN COMPLETE — Uploaded:{uploaded}  Skipped:{skipped}  Failed:{failed}")
    if failed:
        print(f"  NOTE: If failures show 'Script too short: 0 words', this is")
        print(f"  caused by Groq daily quota + broken Gemini fallback.")
        print(f"  Fix: run  python fix_gemini_model.py  then re-run the pipeline.")
    print(f"{'='*55}\n")


if __name__ == "__main__":
    args = sys.argv[1:]
    if not args or args[0] == "all":        run_weekly("all")
    elif args[0] == "omnibus":              run_weekly("omnibus")
    elif args[0] == "signs":               run_weekly("signs")
    elif args[0] == "sign" and len(args)>=2: run_weekly("sign", args[1].capitalize())
    elif args[0] == "transit":             run_weekly("transit")
    elif args[0] == "shorts":
        sf = args[1].capitalize() if len(args)>=2 else None
        run_weekly("shorts", sf)
    elif args[0] == "debug":               debug_mode()
    else:
        print(__doc__)
