#!/usr/bin/env python3
"""Convert the plain-text paper into a polished standalone HTML reading version
that matches the publications site's visual identity."""
import re, html, os

HERE = os.path.dirname(os.path.abspath(__file__))
SLUG = "2026-organizational-accounts-of-malfunction-the-dual"
TXT = os.path.join(HERE, "txt", "barandiaran-2026-organizational-accounts-malfunction.txt")
OUT_DIR = os.path.join(HERE, "html")
os.makedirs(OUT_DIR, exist_ok=True)
OUT = os.path.join(OUT_DIR, SLUG + ".html")

with open(TXT, encoding="utf-8") as f:
    raw = f.read()

lines = raw.split("\n")

# --- header block ---
title = lines[0].strip()
author = lines[2].strip()
affil = lines[3].strip()
email = lines[4].strip()
venue = lines[6].strip()
doi_line = lines[7].strip()
recv = lines[8].strip()
copyright_line = lines[9].strip()

# find abstract, keywords, body start
abs_idx = next(i for i, l in enumerate(lines) if l.strip() == "Abstract")
abstract = lines[abs_idx + 2].strip()
kw_idx = next(i for i, l in enumerate(lines) if l.strip().startswith("Keywords:"))
keywords = [k.strip() for k in lines[kw_idx].split(":", 1)[1].split("·") if k.strip()]
refs_idx = next(i for i, l in enumerate(lines) if l.strip() == "References")

body_lines = lines[kw_idx + 1:refs_idx]
ref_lines = [l.strip() for l in lines[refs_idx + 1:] if l.strip()]

# --- footnote extraction across whole body ---
footnotes = {}
def _fn(m):
    n = m.group(1); text = m.group(2).strip()
    footnotes[int(n)] = text
    return f"__FN{n}__"
body_text = "\n".join(body_lines)
body_text = re.sub(r"\[FOOTNOTE (\d+) BEGINS:\s*(.*?)\s*END OF FOOTNOTE \1\]", _fn, body_text, flags=re.S)

def esc(s):
    return html.escape(s, quote=False)

def inline(s):
    """escape then restore footnote markers as superscript links."""
    s = esc(s)
    def sup(m):
        n = m.group(1)
        return (f'<sup class="fn-ref" id="fnref{n}">'
                f'<a href="#fn{n}" aria-label="Footnote {n}">{n}</a></sup>')
    return re.sub(r"__FN(\d+)__", sup, s)

# --- walk body, build sections ---
out = []
toc = []
para_buf = []

def flush_para():
    if para_buf:
        text = " ".join(x.strip() for x in para_buf if x.strip())
        if text:
            out.append(f"<p>{inline(text)}</p>")
        para_buf.clear()

sec_n = 0
for line in body_text.split("\n"):
    s = line.strip()
    if not s:
        flush_para(); continue
    m_fig = re.match(r"^\[FIGURE (\d+):\s*(.*)\]$", s, re.S)
    m_sec = re.match(r"^= SECTION\s+([\dA-Za-z.]+)\s+(.*?)\s*=$", s)
    m_sub = re.match(r"^== SUBSECTION\s+([\d.]+)\s+(.*?)\s*==$", s)
    if m_sec:
        flush_para()
        num, ttl = m_sec.group(1), m_sec.group(2)
        aid = "sec-" + num
        out.append(f'<h2 id="{aid}"><span class="secnum">{esc(num)}</span> {inline(ttl)}</h2>')
        toc.append((1, aid, f"{num}. {ttl}"))
    elif m_sub:
        flush_para()
        num, ttl = m_sub.group(1), m_sub.group(2)
        aid = "sec-" + num
        out.append(f'<h3 id="{aid}"><span class="secnum">{esc(num)}</span> {inline(ttl)}</h3>')
        toc.append((2, aid, f"{num} {ttl}"))
    elif m_fig:
        flush_para()
        n, cap = m_fig.group(1), m_fig.group(2)
        out.append(
            f'<figure class="paper-fig" id="fig{n}">'
            f'<div class="fig-placeholder">Figure {n}</div>'
            f'<figcaption><strong>Figure {esc(n)}.</strong> {inline(cap)}</figcaption>'
            f'</figure>')
    else:
        para_buf.append(s)
flush_para()

# --- footnotes section ---
fn_html = ""
if footnotes:
    items = []
    for n in sorted(footnotes):
        items.append(
            f'<li id="fn{n}"><span class="fn-num">{n}.</span> {inline(footnotes[n])} '
            f'<a class="fn-back" href="#fnref{n}" aria-label="Back to text">↩</a></li>')
    fn_html = ('<section class="endnotes"><h2 id="notes">Notes</h2>'
               '<ol class="fn-list">' + "\n".join(items) + "</ol></section>")

# --- references ---
ref_html = ""
if ref_lines:
    items = "\n".join(f"<li>{inline(r)}</li>" for r in ref_lines)
    ref_html = ('<section class="references"><h2 id="references">References</h2>'
                f'<ol class="ref-list">{items}</ol></section>')

# --- TOC ---
toc_items = []
for lvl, aid, label in toc:
    cls = "toc-sub" if lvl == 2 else "toc-sec"
    toc_items.append(f'<li class="{cls}"><a href="#{aid}">{esc(label)}</a></li>')
toc_html = "<ul class=\"toc-list\">" + "\n".join(toc_items) + "</ul>"

kw_html = " ".join(f'<span class="kw">{esc(k)}</span>' for k in keywords)
doi_url = doi_line
doi_only = re.sub(r"^https?://(dx\.)?doi\.org/", "", doi_line)

page = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{esc(title)} — Xabier E. Barandiaran</title>
<meta name="description" content="HTML reading version of &quot;{esc(title)}&quot; by {esc(author)}, {esc(venue)}.">
<meta name="citation_title" content="{esc(title)}">
<meta name="citation_author" content="Barandiaran, Xabier E.">
<meta name="citation_journal_title" content="Biological Theory">
<meta name="citation_volume" content="21">
<meta name="citation_issue" content="1">
<meta name="citation_firstpage" content="51">
<meta name="citation_lastpage" content="69">
<meta name="citation_publication_date" content="2026">
<meta name="citation_doi" content="{esc(doi_only)}">
<meta name="citation_pdf_url" content="../pdfs/{SLUG}.pdf">
<link rel="canonical" href="https://publications.barandiaran.net/html/{SLUG}.html">
<link rel="icon" href="https://xabier.barandiaran.net/wp-content/uploads/2020/03/cropped-logo-rojo.png?w=32" sizes="32x32">
<style>
@import url('https://fonts.googleapis.com/css2?family=Libre+Baskerville:ital,wght@0,400;0,700;1,400&display=swap');
:root{{--text:#404040;--text-light:#6b6b6b;--bg:#fff;--accent:#800000;--accent-light:#f4e9e9;--border:#e2dede;--serif:'Libre Baskerville',Georgia,'Times New Roman',Times,serif;}}
*,*:before,*:after{{box-sizing:border-box;}}
body{{margin:0;background:var(--bg);color:var(--text);font-family:var(--serif);font-size:18px;line-height:1.75;}}
a{{color:var(--accent);text-decoration:none;border-bottom:1px solid transparent;}}
a:hover{{border-bottom-color:var(--accent);}}
.wrap{{max-width:44em;margin:0 auto;padding:0 1.6em;}}
.topbar{{border-bottom:1px solid var(--border);padding:1em 0;margin-bottom:2.5em;font-size:.9rem;}}
.paper-header{{margin-bottom:2.5em;}}
h1{{font-size:1.9rem;line-height:1.25;margin:.2em 0 .6em;}}
.byline{{font-size:1.05rem;margin:.2em 0;}}
.affil{{font-size:.9rem;color:var(--text-light);font-style:italic;margin:.3em 0;}}
.pubmeta{{font-size:.85rem;color:var(--text-light);margin:.8em 0 0;line-height:1.5;}}
.pubmeta a{{color:var(--accent);}}
.abstract{{background:#fafafa;border-left:3px solid var(--accent);padding:1.1em 1.4em;margin:2em 0;font-size:.97rem;line-height:1.7;}}
.abstract h2{{font-size:.8rem;text-transform:uppercase;letter-spacing:.06em;color:var(--accent);margin:0 0 .5em;border:none;}}
.keywords{{margin:1em 0 0;display:flex;flex-wrap:wrap;gap:.4em;}}
.kw{{font-size:.72rem;color:var(--text-light);background:#f6f3f3;border:1px solid var(--border);border-radius:999px;padding:.1em .7em;}}
nav.toc{{background:#fbfafa;border:1px solid var(--border);border-radius:5px;padding:1em 1.4em;margin:2.5em 0;font-size:.9rem;}}
nav.toc h2{{font-size:.8rem;text-transform:uppercase;letter-spacing:.06em;color:var(--accent);border:none;margin:0 0 .6em;}}
.toc-list{{list-style:none;margin:0;padding:0;}}
.toc-list li{{margin:.15em 0;}}
.toc-sub{{padding-left:1.4em;font-size:.86rem;color:var(--text-light);}}
.toc-sub a{{color:var(--text-light);}}
h2{{font-size:1.4rem;margin:2em 0 .6em;padding-bottom:.25em;border-bottom:1px solid var(--border);line-height:1.3;}}
h3{{font-size:1.12rem;margin:1.8em 0 .5em;line-height:1.35;}}
.secnum{{color:var(--accent);font-weight:bold;margin-right:.35em;}}
p{{margin:0 0 1.15em;}}
sup.fn-ref a{{border:none;font-size:.7em;padding:0 .1em;}}
.paper-fig{{margin:2em 0;padding:1.2em;background:#fafafa;border:1px solid var(--border);border-radius:5px;}}
.fig-placeholder{{display:flex;align-items:center;justify-content:center;height:120px;background:repeating-linear-gradient(45deg,#f0ecec,#f0ecec 10px,#f6f3f3 10px,#f6f3f3 20px);border:1px dashed var(--border);border-radius:4px;color:var(--text-light);font-style:italic;font-size:.85rem;margin-bottom:.8em;}}
figcaption{{font-size:.85rem;color:var(--text-light);line-height:1.55;}}
.endnotes,.references{{margin-top:3em;padding-top:1.5em;border-top:1px solid var(--border);}}
.fn-list,.ref-list{{padding-left:0;list-style:none;}}
.fn-list li,.ref-list li{{font-size:.85rem;line-height:1.6;color:var(--text-light);margin:0 0 .8em;padding-left:2.2em;text-indent:-2.2em;}}
.fn-num{{color:var(--accent);font-weight:bold;margin-right:.3em;}}
.fn-back{{border:none;font-size:.9em;margin-left:.2em;}}
.footer{{margin:4em 0 3em;padding-top:1.5em;border-top:1px solid var(--border);font-size:.85rem;color:var(--text-light);}}
@media (max-width:45em){{body{{font-size:16px;}}h1{{font-size:1.55rem;}}}}
@media print{{nav.toc,.topbar{{display:none;}}.abstract,.paper-fig{{background:none;}}}}
</style>
</head>
<body>
<div class="wrap">
<div class="topbar"><a href="../index.html">← Back to publications</a> &nbsp;·&nbsp; <a href="../pdfs/{SLUG}.pdf">Download full PDF</a></div>

<header class="paper-header">
<div class="pubmeta">{esc(venue)}</div>
<h1>{esc(title)}</h1>
<p class="byline">{esc(author)}</p>
<p class="affil">{esc(affil)}</p>
<div class="pubmeta"><a href="mailto:{esc(email)}">{esc(email)}</a><br>
<a href="{esc(doi_url)}">{esc(doi_url)}</a><br>
{esc(recv)}<br>{esc(copyright_line)}</div>
</header>

<div class="abstract">
<h2>Abstract</h2>
<p>{inline(abstract)}</p>
<div class="keywords">{kw_html}</div>
</div>

<nav class="toc"><h2>Contents</h2>{toc_html}</nav>

<article>
{chr(10).join(out)}
</article>

{fn_html}
{ref_html}

<div class="footer">
<p>HTML reading version generated from the author's manuscript. Canonical published version: <a href="{esc(doi_url)}">{esc(doi_only)}</a> · <em>{esc(venue)}</em>.</p>
<p>© The Author(s). Open access. <a href="../index.html">Xabier E. Barandiaran — Publications</a></p>
</div>
</div>
</body>
</html>
"""

with open(OUT, "w", encoding="utf-8") as f:
    f.write(page)

print("Wrote", OUT)
print("Sections:", len(toc), "Footnotes:", len(footnotes), "References:", len(ref_lines))
