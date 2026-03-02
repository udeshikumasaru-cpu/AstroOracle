import re,sys,shutil
from pathlib import Path
TARGET=Path(chr(97)+chr(115)+chr(116)+chr(114)+chr(111)+chr(95)+chr(115)+chr(99)+chr(114)+chr(105)+chr(112)+chr(116)+chr(95)+chr(103)+chr(101)+chr(110)+chr(101)+chr(114)+chr(97)+chr(116)+chr(111)+chr(114)+chr(46)+chr(112)+chr(121))
BACKUP=Path(str(TARGET)+".bak")
REPS=[("gemini-1.5-flash-latest","gemini-2.0-flash-lite"),("gemini-1.5-flash-001","gemini-2.0-flash-lite"),("gemini-1.5-flash","gemini-2.0-flash-lite"),("gemini-1.5-pro","gemini-2.0-flash"),("v1beta/models","v1/models")]
def patch():
    if not TARGET.exists():print("ERROR: not found");sys.exit(1)
    src=TARGET.read_text(encoding="utf-8");out=src;hits=[]
    for p,r in REPS:
        new,n=re.subn(re.escape(p),r,out)
        if n:hits.append((p,r,n));out=new
    if not hits:print("Already up to date.");return
    [print("  [{}x] {} -> {}".format(n,p,r)) for p,r,n in hits]
    shutil.copy2(TARGET,BACKUP);TARGET.write_text(out,encoding="utf-8")
    print("SUCCESS. Run: python astro_main.py")
patch()
