#!/usr/bin/env python3
"""Kept for compatibility with the old update recipe: runs build_site.py,
which now builds index.html, citations, landing pages, llms.txt, JSON and
sitemap.xml from data/zotero.json (see DEPLOYMENT.md)."""
import os, runpy
runpy.run_path(os.path.join(os.path.dirname(os.path.abspath(__file__)), "build_site.py"),
               run_name="__main__")
