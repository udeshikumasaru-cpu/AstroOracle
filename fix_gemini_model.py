#!/usr/bin/env python3
"""
fix_gemini_model.py
===================
Run this ONCE to patch astro_script_generator.py in-place.

Fixes two bugs confirmed in the GitHub Actions logs:

  BUG 1 - Gemini 404 error
    models/gemini-1.5-flash is not found for API version v1beta
    -> Replaces deprecated model name with gemini-2.0-flash-lite
       (fastest + cheapest current model, same REST API)

  BUG 2 - Wrong API version in endpoint URL
    v1beta does not support gemini-1.5-flash generateContent
    -> Replaces v1beta with v1 (stable) in any hardcoded URLs

Usage:
    python fix_gemini_model.py
    python fix_gemini_model.py --dry-run
"""

import re, sys, shutil
from pathlib import Path

TARGET = Path("astro_script_generator.py")
BACKUP = Path("astro_script_generator.py.bak")

REPLACEMENTS = [
    (r"gemini-1\.5-flash-latest",  "gemini-2.0-flash-lite"),
    (r"gemini-1\.5-flash-001",     "gemini-2.0-flash-lite"),
    (r"gemini-1\.5-flash",         "gemini-2.0-flash-lite"),
    (r"gemini-1\.5-pro-latest",    "gemini-2.0-flash"),
    (r"gemini-1\.5-pro-001",       "gemini-2.0-flash"),
    (r"gemini-1\.5-pro",           "gemini-2.0-flash"),
    (r"generativelanguage\.googleapis\.com/v1beta/models",
     "generativelanguage.googleapis.com/v1/models"),
]

def patch(dry_run=False):
    if not TARGET.exists():
        print(f"ERROR: {TARGET} not found. Run from the same folder as your bot.")
        sys.exit(1)
    original = TARGET.read_text(encoding="utf-8")
    patched, hits = original, []
    for pattern, replacement in REPLACEMENTS:
        new, n = re.subn(pattern, replacement, patched)
        if n:
            hits.append((pattern, replacement, n))
            patched = new
    if not hits:
        print("OK - No deprecated model strings found. File already up to date.")
        return
    total = sum(h[2] for h in hits)
    print(f"Found {total} replacement(s):
")
    for pat, rep, n in hits:
        print(f"  [{n}x]  {pat}  ->  {rep}")
    if dry_run:
        print("
[DRY RUN] No files changed."); return
    shutil.copy2(TARGET, BACKUP)
    print(f"
Backup saved -> {BACKUP}")
    TARGET.write_text(patched, encoding="utf-8")
    print(f"SUCCESS: {TARGET} patched.
")
    print("Next steps:")
    print("  1. Re-run:  python astro_main.py")
    print("  2. Gemini fallback will now work when Groq hits its daily quota.")
    print("  3. Optional: set env var GEMINI_MODEL=gemini-2.0-flash to override.
")

if __name__ == "__main__":
    patch(dry_run="--dry-run" in sys.argv or "-n" in sys.argv)
