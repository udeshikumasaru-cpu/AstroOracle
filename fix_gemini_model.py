import re, sys, shutil
from pathlib import Path

TARGET = Path("astro_script_generator.py")
BACKUP = Path(str(TARGET) + ".bak")

# Map old model names → current model names.
# The ("v1beta/models", "v1/models") entry previously included here was dead
# code — the google-generativeai SDK manages API URLs internally and that
# string never appears in astro_script_generator.py.
REPS = [
    ("gemini-1.5-flash-latest", "gemini-2.0-flash-lite"),
    ("gemini-1.5-flash-001",    "gemini-2.0-flash-lite"),
    ("gemini-1.5-flash",        "gemini-2.0-flash-lite"),
    ("gemini-1.5-pro",          "gemini-2.0-flash"),
]

def patch():
    if not TARGET.exists():
        print(f"ERROR: {TARGET} not found")
        sys.exit(1)

    src = TARGET.read_text(encoding="utf-8")
    out = src
    hits = []
    for old, new in REPS:
        patched, n = re.subn(re.escape(old), new, out)
        if n:
            hits.append((old, new, n))
            out = patched

    if not hits:
        print("Already up to date.")
        return

    for old, new, n in hits:
        print(f"  [{n}x] {old} -> {new}")

    shutil.copy2(TARGET, BACKUP)
    TARGET.write_text(out, encoding="utf-8")
    print("SUCCESS. Run: python astro_main.py")

patch()
