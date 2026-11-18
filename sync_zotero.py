#!/usr/bin/env python3
"""Read the MY_PUBLICATIONS collection straight from the local Zotero database
and save it as data/zotero.json — the single source of metadata for the site.

    python3 sync_zotero.py

Zotero can stay open: the database (plus its write-ahead log) is copied to a
temporary folder first and only the copy is read. Nothing in Zotero changes.

Each record keeps the field names of Zotero's own CSV export ("Item Type",
"Publication Title", "Manual Tags", ...) so the citation builders work on it
unchanged, plus structured creators, typed tags and PDF attachment paths.

Settings (data/site.json): "zotero_collection" (collection key), and
"exclude" (Zotero keys left off the site, e.g. a preprint superseded by the
published article). Override the Zotero folder with ZOTERO_DIR.
"""
import json
import os
import shutil
import sqlite3
import sys
import tempfile

ROOT = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(ROOT, "data")


def zotero_dir():
    for c in (os.environ.get("ZOTERO_DIR", ""), os.path.expanduser("~/Zotero"),
              os.path.join(ROOT, "..", "Zotero")):
        if c and os.path.exists(os.path.join(c, "zotero.sqlite")):
            return os.path.abspath(c)
    sys.exit("Zotero data folder not found (set ZOTERO_DIR).")


def load_settings():
    p = os.path.join(DATA, "site.json")
    return json.load(open(p, encoding="utf-8")) if os.path.exists(p) else {}


def split_date(raw):
    """Zotero stores dates as 'YYYY-MM-DD original' (00 = unknown part)."""
    raw = (raw or "").strip()
    if not raw:
        return "", ""
    sql, _, orig = raw.partition(" ")
    parts = [p for p in sql.split("-") if p and set(p) != {"0"}]
    return "-".join(parts), (orig or sql)


def main():
    settings = load_settings()
    coll_key = settings.get("zotero_collection", "4TC5W55M")
    exclude = set(settings.get("exclude", {}))
    zdir = zotero_dir()
    tmp = tempfile.mkdtemp()
    try:
        for suffix in ("", "-wal"):
            src = os.path.join(zdir, "zotero.sqlite" + suffix)
            if os.path.exists(src):
                shutil.copy2(src, os.path.join(tmp, "z.sqlite" + suffix))
        db = sqlite3.connect(os.path.join(tmp, "z.sqlite"))
        c = db.cursor()
        row = c.execute("select collectionID, collectionName from collections where key=?",
                        (coll_key,)).fetchone()
        if not row:
            sys.exit(f"Collection {coll_key} not found in Zotero.")
        cid, cname = row
        deleted = {r[0] for r in c.execute("select itemID from deletedItems")}
        ids = [r[0] for r in c.execute(
            "select itemID from collectionItems where collectionID=? order by orderIndex", (cid,))]
        out, skipped = [], []
        for iid in ids:
            if iid in deleted:
                continue
            key, typ, modified, added = c.execute(
                "select i.key, it.typeName, i.dateModified, i.dateAdded from items i "
                "join itemTypes it using(itemTypeID) where itemID=?", (iid,)).fetchone()
            if typ in ("attachment", "note", "annotation"):
                continue
            if key in exclude:
                skipped.append(key)
                continue
            f = dict(c.execute(
                "select fi.fieldName, v.value from itemData d join fields fi using(fieldID) "
                "join itemDataValues v using(valueID) where d.itemID=?", (iid,)).fetchall())
            creators = []
            for ctype, last, first, mode in c.execute(
                    "select ct.creatorType, cr.lastName, cr.firstName, cr.fieldMode "
                    "from itemCreators ic join creators cr using(creatorID) "
                    "join creatorTypes ct using(creatorTypeID) where ic.itemID=? "
                    "order by ic.orderIndex", (iid,)):
                if mode == 1 or not first:
                    creators.append({"type": ctype, "literal": last})
                else:
                    creators.append({"type": ctype, "family": last, "given": first})
            tags = [{"name": n, "auto": bool(t)} for n, t in c.execute(
                "select t.name, it.type from itemTags it join tags t using(tagID) "
                "where it.itemID=?", (iid,))]
            atts = []
            for akey, path, ctype, aid in c.execute(
                    "select i.key, a.path, a.contentType, i.itemID from itemAttachments a "
                    "join items i using(itemID) where a.parentItemID=?", (iid,)):
                if aid in deleted or ctype != "application/pdf" or not path:
                    continue
                if path.startswith("storage:"):
                    atts.append(f"storage/{akey}/{path[len('storage:'):]}")
                else:
                    atts.append(path)  # linked file (absolute path)

            def people(kind):
                return "; ".join(
                    (f"{p['family']}, {p['given']}" if "family" in p else p["literal"])
                    for p in creators if p["type"] == kind)
            date, date_orig = split_date(f.get("date"))
            rec = {
                "Key": key,
                "Item Type": typ,
                "Publication Year": date[:4],
                "Author": people("author"),
                "Editor": people("editor"),
                "Title": f.get("title", ""),
                "Short Title": f.get("shortTitle", ""),
                "Publication Title": f.get("publicationTitle") or f.get("bookTitle")
                or f.get("proceedingsTitle") or "",
                "Conference Name": f.get("conferenceName", ""),
                "Journal Abbreviation": f.get("journalAbbreviation", ""),
                "ISBN": f.get("ISBN", ""),
                "ISSN": f.get("ISSN", ""),
                "DOI": f.get("DOI", ""),
                "Url": f.get("url", ""),
                "Abstract Note": f.get("abstractNote", ""),
                "Date": date,
                "Date Original": date_orig,
                "Pages": f.get("pages", ""),
                "Issue": f.get("issue", ""),
                "Volume": f.get("volume", ""),
                "Series": f.get("series", ""),
                "Publisher": f.get("publisher") or f.get("university")
                or f.get("institution") or f.get("repository") or "",
                "Place": f.get("place", ""),
                "Language": f.get("language", ""),
                "Rights": f.get("rights", ""),
                "Type": f.get("thesisType") or f.get("reportType") or "",
                "Number": f.get("reportNumber") or f.get("archiveID") or "",
                "Extra": f.get("extra", ""),
                "Manual Tags": "; ".join(t["name"] for t in tags if not t["auto"]),
                "Automatic Tags": "; ".join(t["name"] for t in tags if t["auto"]),
                "Date Added": added,
                "Date Modified": modified,
                "creators": creators,
                "pdf_attachments": atts,
            }
            out.append(rec)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    os.makedirs(DATA, exist_ok=True)
    path = os.path.join(DATA, "zotero.json")
    old = {}
    if os.path.exists(path):
        old = {r["Key"]: r for r in json.load(open(path, encoding="utf-8"))}
    json.dump(out, open(path, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    new = [r for r in out if r["Key"] not in old]
    changed = [r for r in out if r["Key"] in old and old[r["Key"]] != r]
    gone = [k for k in old if k not in {r["Key"] for r in out}]
    print(f"Zotero collection '{cname}': {len(out)} items → data/zotero.json "
          f"(excluded: {len(skipped)})")
    if old:
        for r in new:
            print(f"  NEW      {r['Key']}  {r['Publication Year']}  {r['Title'][:70]}")
        for r in changed:
            print(f"  CHANGED  {r['Key']}  {r['Publication Year']}  {r['Title'][:70]}")
        for k in gone:
            print(f"  REMOVED  {k}  {old[k]['Title'][:70]}")


if __name__ == "__main__":
    main()
