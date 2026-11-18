#!/usr/bin/env python3
"""Find the authors' own keywords for publications not yet in data/keywords.json.

    python3 extract_keywords.py          # after sync_zotero.py, before build_site.py

For each new item it reads the first pages of its PDF (pdfs/{slug}.pdf, then
the Zotero attachments) and looks for a "Keywords" / "Key words" / "Index
terms" / "Palabras clave" / "Mots-clés" / "Parole chiave" section. Results are
added with "source": "pdf-auto" — check them and fix by hand if needed (then
set "source": "pdf"). Items without any keyword section are recorded as
"source": "none" so they are not scanned again; the site shows derived
"Topics" for those. Existing entries are never changed.

Needs pdftotext (poppler-utils).
"""
import json
import os
import re
import shutil
import subprocess
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(ROOT, "data")
HEAD = re.compile(r"(?:^|\n)[ \t]*(key[ \t]*-?[ \t]*words?|index terms|palabras[ \t-]+clave|"
                  r"paraules[ \t-]+clau|mots[- ]cl[ée]s|parole[ \t-]+chiave)\b[ \t]*[:.—–-]?[ \t]*", re.I)
STOP = re.compile(r"\n\s*\n|\b(?:1\.?\s+)?introduction\b|\babstract\b|\bresumen\b|©|copyright|"
                  r"\bcorrespond|\breceived\b|https?://|\*|\bA version of this paper", re.I)


def zotero_dir():
    for c in (os.environ.get("ZOTERO_DIR", ""), os.path.expanduser("~/Zotero"),
              os.path.join(ROOT, "..", "Zotero")):
        if c and os.path.isdir(os.path.join(c, "storage")):
            return c
    return ""


def parse(chunk):
    chunk = re.sub(r"^(?:[ \t\n|:]|\d{1,2}[ \t]*\n)+", "", chunk)  # stray footnote numbers
    m = STOP.search(chunk)
    if m:
        chunk = chunk[:m.start()]
    chunk = chunk.strip().rstrip(".")
    parts = re.split(r"\s*[·•;\x01\uf0b7]\s*|\s*,\s*|\s{3,}|\.\s+(?=[A-ZÁÉÍÓÚ])", chunk)
    out = []
    for p in parts:
        if "\n" in p and len(" ".join(p.split())) > 60:
            p = p.split("\n")[0]                       # keyword followed by unrelated text
        p = re.sub(r"\s+", " ", p).strip(" .:-–—|")
        p = re.sub(r"(?<=[a-z])\d+$", "", p)          # footnote markers ("yachay1")
        p = re.sub(r"^\d+\s+", "", p)
        if 1 < len(p) <= 60 and not p.isdigit():
            out.append(p[0].upper() + p[1:])
    return list(dict.fromkeys(out))[:15]


def main():
    if not shutil.which("pdftotext"):
        sys.exit("pdftotext not found (install poppler-utils).")
    recs = json.load(open(os.path.join(DATA, "zotero.json"), encoding="utf-8"))
    site = json.load(open(os.path.join(DATA, "site.json"), encoding="utf-8"))
    kpath = os.path.join(DATA, "keywords.json")
    kw = json.load(open(kpath, encoding="utf-8")) if os.path.exists(kpath) else {}
    exclude = set(site.get("exclude", {}))
    slugs = site.get("slugs", {})
    zdir = zotero_dir()
    added = []
    for r in recs:
        k = r["Key"]
        if k in kw or k in exclude:
            continue
        pdfs = []
        if k in slugs:
            pdfs.append(os.path.join(ROOT, "pdfs", slugs[k] + ".pdf"))
        pdfs += [a if os.path.isabs(a) else os.path.join(zdir, a) for a in r.get("pdf_attachments", [])]
        found = None
        for p in pdfs:
            if not os.path.exists(p):
                continue
            text = subprocess.run(["pdftotext", "-l", "4", p, "-"], capture_output=True,
                                  text=True, timeout=120).stdout
            m = HEAD.search(text)
            if m:
                found = parse(text[m.end():m.end() + 600])
                if found:
                    break
        if found:
            kw[k] = {"source": "pdf-auto", "keywords": found}
            added.append(f"  {k}  {r['Title'][:60]}\n      → {'; '.join(found)}")
        else:
            kw[k] = {"source": "none", "keywords": []}
            added.append(f"  {k}  {r['Title'][:60]}\n      → no keyword section found"
                         + (f" (Zotero tags: {r['Manual Tags'] or r['Automatic Tags']})"
                            if (r['Manual Tags'] or r['Automatic Tags']) else ""))
    json.dump(kw, open(kpath, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"{len(added)} new item(s) checked." + (" Review these in data/keywords.json:" if added else ""))
    print("\n".join(added))


if __name__ == "__main__":
    main()
