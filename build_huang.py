#!/usr/bin/env python3
"""
Build a static HTML site from the Jensen Huang knowledge graph Obsidian vault.
Usage: python3 build_huang.py
"""

import os
import re
import shutil
import yaml
import markdown
from pathlib import Path

# ── Config ────────────────────────────────────────────────────────────────────
VAULT = Path("/Users/hongxing/Documents/Obsidian Vault/黄仁勋/黄仁勋")
OUT   = Path("/Users/hongxing/project/webchat/huang-site")

SITE_TITLE = "黄仁勋知识图谱"
SITE_LOGO  = "H"

CATEGORY_DIRS = {
    "keynotes":      "keynotes",
    "interviews":    "interviews",
    "earnings":      "earnings",
    "commencements": "commencements",
    "concepts":      "concepts",
    "methods":       "methods",
    "companies":     "companies",
    "people":        "people",
    "index-pages":   "index-pages",
}

CATEGORY_LABELS = {
    "keynotes":      "演讲",
    "interviews":    "访谈",
    "earnings":      "财报会议",
    "commencements": "毕业演讲",
    "concepts":      "概念",
    "methods":       "方法",
    "companies":     "产品",
    "people":        "人物",
    "index-pages":   "索引",
}

# ── Step 1: Collect all markdown files ────────────────────────────────────────

def collect_files():
    """Return list of dicts: {path, stem, category, frontmatter, body}"""
    files = []

    # Welcome page (homepage)
    welcome = VAULT / "欢迎.md"
    if welcome.exists():
        fm, body = parse_md(welcome)
        files.append({"path": welcome, "stem": "欢迎", "category": "home", "fm": fm, "body": body})

    for cat, dirname in CATEGORY_DIRS.items():
        d = VAULT / dirname
        if not d.is_dir():
            continue
        for f in sorted(d.glob("*.md")):
            fm, body = parse_md(f)
            files.append({"path": f, "stem": f.stem, "category": cat, "fm": fm, "body": body})

    return files


def parse_md(filepath):
    text = filepath.read_text(encoding="utf-8")
    fm = {}
    body = text
    if text.startswith("---"):
        parts = text.split("---", 2)
        if len(parts) >= 3:
            try:
                fm = yaml.safe_load(parts[1]) or {}
            except yaml.YAMLError:
                pass
            body = parts[2]
    return fm, body

# ── Step 2: Build name→URL mapping ───────────────────────────────────────────

def build_link_map(files):
    """Map note stem (and aliases) → relative URL path."""
    lmap = {}
    for f in files:
        stem = f["stem"]
        cat  = f["category"]
        if cat == "home":
            url = "/index.html"
        else:
            url = f"/{cat}/{stem}.html"
        lmap[stem] = url
        # Also register aliases from frontmatter
        for alias in f["fm"].get("aliases", []):
            if alias not in lmap:
                lmap[alias] = url
    return lmap


# ── Step 3: Convert wikilinks ─────────────────────────────────────────────────

def convert_wikilinks(text, link_map):
    """Replace [[target|display]] and [[target]] with <a> tags."""
    def replacer(m):
        inner = m.group(1)
        if "|" in inner:
            target, display = inner.split("|", 1)
        else:
            target = display = inner
        target = target.strip()
        display = display.strip()
        url = link_map.get(target)
        if url:
            return f'<a href="{url}">{display}</a>'
        else:
            return display  # plain text if target not found

    return re.sub(r'\[\[([^\]]+)\]\]', replacer, text)


# ── Step 4: Markdown → HTML ──────────────────────────────────────────────────

def md_to_html(md_text):
    extensions = ['tables', 'fenced_code', 'toc', 'nl2br']
    return markdown.markdown(md_text, extensions=extensions)


# ── Step 5: Count backlinks (references) ─────────────────────────────────────

def count_references(files):
    """Count how many times each stem is referenced via [[...]] across all files."""
    counts = {}
    for f in files:
        raw = f["body"]
        for m in re.finditer(r'\[\[([^\]|]+?)(?:\|[^\]]+)?\]\]', raw):
            target = m.group(1).strip()
            counts[target] = counts.get(target, 0) + 1
    return counts


def build_backlinks(files, link_map):
    """Build a map: target_stem → list of {stem, category, title, excerpt} that link to it.

    Also resolves aliases so that e.g. [[Flywheel Effect]] linking to 飞轮效应.md
    shows up as a backlink on the 飞轮效应 page.
    """
    # Build alias→canonical stem map
    alias_to_stem = {}
    for f in files:
        stem = f["stem"]
        alias_to_stem[stem] = stem
        for alias in f["fm"].get("aliases", []):
            alias_to_stem[alias] = stem

    backlinks = {}  # target_stem → list of source info
    for f in files:
        src_stem = f["stem"]
        src_cat = f["category"]
        src_title = f["fm"].get("title", src_stem)
        raw = f["body"]

        # Find all unique targets this file links to
        seen_targets = set()
        for m in re.finditer(r'\[\[([^\]|]+?)(?:\|[^\]]+)?\]\]', raw):
            target_raw = m.group(1).strip()
            target_stem = alias_to_stem.get(target_raw, target_raw)
            if target_stem == src_stem:
                continue  # skip self-links
            if target_stem in seen_targets:
                continue
            seen_targets.add(target_stem)

            # Extract a short excerpt around the link
            start = max(0, m.start() - 60)
            end = min(len(raw), m.end() + 60)
            excerpt = raw[start:end].replace("\n", " ").strip()
            # Clean up markdown formatting in excerpt
            excerpt = re.sub(r'\*\*([^*]+)\*\*', r'\1', excerpt)
            excerpt = re.sub(r'\[\[([^\]|]+?)(?:\|([^\]]+))?\]\]', lambda x: x.group(2) or x.group(1), excerpt)
            if start > 0:
                excerpt = "…" + excerpt
            if end < len(raw):
                excerpt = excerpt + "…"

            if target_stem not in backlinks:
                backlinks[target_stem] = []
            backlinks[target_stem].append({
                "stem": src_stem,
                "category": src_cat,
                "title": src_title,
                "excerpt": excerpt,
            })

    return backlinks


# ── Step 6: HTML Template ────────────────────────────────────────────────────

CSS = r"""
*{box-sizing:border-box;margin:0;padding:0}

:root{
  --bg:#FBF7F1;
  --bg2:#F5EDE2;
  --text:#1B1B18;
  --text2:#5A6670;
  --gold:#CC7A00;
  --gold-light:#E09520;
  --gold-glow:rgba(204,122,0,.12);
  --navy:#1E1710;
  --navy-light:#352C20;
  --cream:#FFF9F0;
  --border:#DEE2E6;
  --card:#FFFFFF;
  --link:#B06A00;
  --serif:'Noto Serif SC','Crimson Pro',Georgia,'Times New Roman',serif;
  --sans:'DM Sans',-apple-system,BlinkMacSystemFont,'PingFang SC','Microsoft YaHei',sans-serif;
  --sidebar-w:260px;
}

html{font-size:15px;scroll-behavior:smooth}
body{
  font-family:var(--sans);
  color:var(--text);
  background:var(--bg);
  display:flex;
  min-height:100vh;
  line-height:1.8;
  -webkit-font-smoothing:antialiased;
}

/* ===== SIDEBAR ===== */
.sidebar{
  width:var(--sidebar-w);
  background:var(--navy);
  position:fixed;top:0;left:0;bottom:0;
  overflow-y:auto;
  z-index:100;
  display:flex;
  flex-direction:column;
}
.sidebar-header{padding:20px 16px 16px;border-bottom:1px solid rgba(255,255,255,.08)}
.logo{
  color:#fff;
  font-size:17px;
  font-weight:700;
  text-decoration:none;
  letter-spacing:.5px;
  font-family:var(--serif);
  display:block;
}
.logo:hover{color:var(--gold-light)}

.sidebar-nav{flex:1;padding:8px 0;overflow-y:auto}
.sidebar-nav::-webkit-scrollbar{width:4px}
.sidebar-nav::-webkit-scrollbar-thumb{background:rgba(255,255,255,.15);border-radius:2px}

.nav-link{
  display:block;
  padding:6px 16px;
  color:#cbd5e1;
  text-decoration:none;
  font-size:13px;
  white-space:nowrap;
  overflow:hidden;
  text-overflow:ellipsis;
  border-left:3px solid transparent;
  transition:all .15s;
}
.nav-link:hover{background:rgba(255,255,255,.06);color:#fff}
.nav-link.active{
  color:#fff;
  background:rgba(204,122,0,.15);
  border-left-color:var(--gold);
  font-weight:600;
}
.nav-home{font-size:14px;padding:10px 16px;font-weight:500;margin-bottom:4px}
.nav-changelog{
  margin-top:auto;
  padding:14px 16px;
  font-size:12px;
  color:rgba(255,255,255,.4);
  border-top:1px solid rgba(255,255,255,.08);
}
.nav-changelog:hover{color:rgba(255,255,255,.7)}
.nav-changelog.active{color:var(--gold-light)}
.sidebar-nav{display:flex;flex-direction:column;height:100%}

.nav-group{margin-bottom:2px}
.nav-group-title{
  padding:8px 16px;
  color:#cbd5e1;
  font-size:12px;
  font-weight:600;
  text-transform:uppercase;
  letter-spacing:.5px;
  cursor:pointer;
  display:flex;
  align-items:center;
  gap:6px;
  user-select:none;
  transition:color .15s;
}
.nav-group-title:hover{color:#fff}
.caret{
  display:inline-block;
  width:0;height:0;
  border-left:5px solid #cbd5e1;
  border-top:4px solid transparent;
  border-bottom:4px solid transparent;
  transition:transform .2s;
}
.nav-group.open .nav-group-title .caret{transform:rotate(90deg);border-left-color:#fff}
.nav-group-title .badge{
  margin-left:auto;
  background:rgba(255,255,255,.1);
  color:#cbd5e1;
  font-size:11px;
  padding:1px 6px;
  border-radius:8px;
  font-weight:400;
}
.nav-group-items{display:none;padding-left:8px}
.nav-group.open .nav-group-items{display:block}

.hamburger{
  display:none;
  position:fixed;
  top:12px;left:12px;
  z-index:200;
  background:var(--navy);
  color:#fff;
  border:none;
  font-size:20px;
  padding:6px 10px;
  border-radius:6px;
  cursor:pointer;
}

/* ===== MAIN ===== */
.main{
  margin-left:max(var(--sidebar-w), calc((100vw - 1160px) / 2));
  flex:1;
  position:relative;
  max-width:1160px;
  padding:0;
}

/* grain overlay */
.main::after{
  content:'';
  position:fixed;
  top:0;left:var(--sidebar-w);right:0;bottom:0;
  pointer-events:none;
  opacity:.03;
  z-index:999;
  background-image:url("data:image/svg+xml,%3Csvg viewBox='0 0 256 256' xmlns='http://www.w3.org/2000/svg'%3E%3Cfilter id='n'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='.85' numOctaves='4' stitchTiles='stitch'/%3E%3C/filter%3E%3Crect width='100%25' height='100%25' filter='url(%23n)'/%3E%3C/svg%3E");
}

/* ===== FAV / BOOKMARK BUTTON ===== */
.fav-wrap{
  position:absolute;
  top:24px;right:48px;
  z-index:50;
  display:flex;
  align-items:center;
  gap:10px;
}
.sister-link{
  display:inline-flex;
  align-items:center;
  gap:6px;
  padding:8px 16px;
  background:var(--card);
  border:1px solid var(--border);
  border-radius:24px;
  color:var(--navy);
  font-size:13px;
  font-weight:600;
  font-family:var(--sans);
  text-decoration:none;
  box-shadow:0 2px 8px rgba(0,0,0,.04);
  transition:all .25s;
  white-space:nowrap;
}
.sister-link:hover{
  border-color:var(--gold);
  color:var(--gold);
  box-shadow:0 4px 16px var(--gold-glow);
  transform:translateY(-1px);
}
.sister-link .arrow{
  color:var(--gold);
  font-weight:700;
}
.fav-btn{
  display:inline-flex;
  align-items:center;
  gap:6px;
  padding:8px 18px;
  background:var(--card);
  border:1px solid var(--border);
  border-radius:24px;
  color:var(--gold);
  font-size:16px;
  cursor:pointer;
  transition:all .25s;
  font-family:var(--sans);
  box-shadow:0 2px 8px rgba(0,0,0,.04);
}
.fav-btn:hover{
  border-color:var(--gold);
  box-shadow:0 4px 16px var(--gold-glow);
  transform:translateY(-1px);
}
.fav-label{
  font-size:13px;
  color:var(--text2);
  font-weight:500;
}
.fav-btn:hover .fav-label{color:var(--gold)}
.fav-pop{
  display:none;
  position:absolute;
  right:0;top:48px;
  background:var(--card);
  border:1px solid var(--border);
  border-radius:10px;
  padding:14px 16px;
  box-shadow:0 8px 32px rgba(0,0,0,.12);
  font-size:13px;
  min-width:240px;
  z-index:51;
  color:var(--text);
  line-height:1.6;
}
.fav-pop.show{display:block}
.fav-pop kbd{
  background:var(--bg2);
  padding:2px 7px;
  border-radius:4px;
  font-size:12px;
  border:1px solid var(--border);
  font-family:var(--sans);
  color:var(--navy);
  font-weight:600;
}
.fav-pop-copy{
  display:block;
  width:100%;
  margin-top:10px;
  padding:8px 0;
  background:var(--bg);
  border:1px solid var(--border);
  border-radius:6px;
  color:var(--text2);
  font-size:12px;
  cursor:pointer;
  text-align:center;
  transition:all .15s;
  font-family:var(--sans);
}
.fav-pop-copy:hover{
  border-color:var(--gold);
  color:var(--gold);
}
.fav-pop-copy.copied{
  background:#ecfdf5;
  border-color:#6ee7b7;
  color:#059669;
}

@media(max-width:768px){
  .fav-wrap{right:16px;top:12px;gap:6px}
  .sister-link{padding:6px 12px;font-size:11px}
  .fav-btn{padding:6px 14px}
  .fav-label{font-size:12px}
}

/* ===== CHANGELOG ===== */
.article.changelog h2{
  border-bottom-color:var(--gold);
  display:flex;
  align-items:center;
  gap:10px;
  flex-wrap:wrap;
}
.version{
  display:inline-flex;
  align-items:center;
  background:var(--gold);
  color:#fff;
  font-size:13px;
  font-weight:700;
  padding:3px 11px;
  border-radius:6px;
  font-family:var(--sans);
  letter-spacing:.3px;
}
.changelog-date{
  font-size:14px;
  color:var(--text2);
  font-weight:500;
  font-family:var(--sans);
}
.change-list{
  list-style:none;
  padding:0;
  margin:16px 0;
}
.change-list li{
  padding:10px 0 10px 18px;
  position:relative;
  border-bottom:1px solid var(--border);
  font-size:14px;
  line-height:1.75;
}
.change-list li:last-child{border-bottom:none}
.change-list li::before{
  content:"";
  position:absolute;
  left:0;
  top:20px;
  width:6px;
  height:6px;
  border-radius:50%;
  background:var(--gold);
}
.change-type{
  display:inline-block;
  font-size:11px;
  padding:2px 8px;
  border-radius:4px;
  color:#fff;
  font-weight:600;
  margin-right:8px;
  font-family:var(--sans);
  vertical-align:1px;
  letter-spacing:.2px;
}
.change-type.feat{background:#059669}
.change-type.fix{background:#dc2626}
.change-type.plan{background:#3b82f6}
.change-list li strong{color:var(--navy);font-weight:700}

/* ===== ARTICLE (content pages) ===== */
.article{max-width:820px;padding:48px 48px 80px}
.meta{
  font-size:13px;
  color:var(--text2);
  margin-bottom:16px;
  display:flex;
  align-items:center;
  gap:8px;
}
.type-badge{
  font-size:11px;
  padding:2px 8px;
  border-radius:4px;
  color:#fff;
  font-weight:600;
}
.type-概念{background:#7C5E2A}
.type-方法{background:#5E4A8B}
.type-产品{background:#1A6B7C}
.type-人物{background:#8B2F2F}
.type-演讲{background:#2A6B4F}
.type-毕业演讲{background:#7E6B30}
.type-访谈{background:#3A5E8B}
.type-财报会议{background:#4A6E2A}
.type-索引{background:#6B6560}

.article h1{
  font-family:var(--serif);
  font-size:28px;
  line-height:1.3;
  margin-bottom:24px;
  font-weight:900;
  color:var(--navy);
  letter-spacing:-.5px;
}
.article h2{
  font-family:var(--serif);
  font-size:21px;
  margin:36px 0 14px;
  padding-bottom:8px;
  border-bottom:2px solid var(--border);
  font-weight:700;
  color:var(--navy);
}
.article h3{
  font-family:var(--serif);
  font-size:17px;
  margin:24px 0 10px;
  font-weight:600;
  color:var(--navy-light);
}
.article p{margin:10px 0}
.article ul,.article ol{padding-left:24px;margin:10px 0}
.article li{margin:4px 0}

.article a{
  color:var(--link);
  text-decoration:none;
  background:linear-gradient(to bottom,transparent 60%,var(--gold-glow) 60%);
  transition:background .2s;
}
.article a:hover{background:linear-gradient(to bottom,transparent 40%,rgba(204,122,0,.2) 40%)}

.article blockquote{
  background:var(--cream);
  border-left:4px solid var(--gold);
  padding:14px 20px;
  margin:16px 0;
  border-radius:0 8px 8px 0;
  font-style:italic;
  color:#B06A00;
  font-family:var(--serif);
}
.article blockquote p{margin:0}
.article blockquote a{background:none;color:var(--gold)}
.article blockquote a:hover{text-decoration:underline}

.article table{border-collapse:collapse;width:100%;margin:16px 0;font-size:14px}
.article th,.article td{border:1px solid var(--border);padding:8px 12px;text-align:left}
.article th{background:var(--bg2);font-weight:600;color:var(--navy)}
.article strong{font-weight:700}
.article hr{border:none;border-top:1px solid var(--border);margin:32px 0}
.article code{
  background:var(--bg2);
  padding:2px 6px;
  border-radius:3px;
  font-size:13px;
  font-family:'SF Mono',Menlo,Consolas,monospace;
  color:#B06A00;
}

/* ===== KNOWLEDGE GRAPH PAGE ===== */
.main.full-bleed{max-width:none;padding:0;margin-left:var(--sidebar-w)}
.main.full-bleed::after{display:none}
.graph-wrap{position:relative;width:100%;height:100vh;overflow:hidden;background:var(--bg)}
.graph-wrap svg{width:100%;height:100%;display:block}
.graph-toolbar{position:absolute;top:16px;right:16px;display:flex;gap:8px;z-index:10}
.graph-toolbar button{
  padding:6px 14px;background:var(--card);border:1px solid var(--border);
  border-radius:8px;font-size:12px;color:var(--text);cursor:pointer;
  font-family:var(--sans);transition:all .15s;font-weight:500;
}
.graph-toolbar button:hover{border-color:var(--gold);color:var(--gold)}
.graph-title{position:absolute;top:16px;left:16px;z-index:10}
.graph-title h1{font-family:var(--serif);font-size:20px;color:var(--navy);margin:0}
.graph-title p{font-size:12px;color:var(--text2);margin:4px 0 0;font-family:var(--sans)}
.graph-tooltip{
  position:absolute;padding:8px 14px;background:var(--navy);color:#fff;
  border-radius:8px;font-size:12px;pointer-events:none;opacity:0;transition:opacity .15s;
  box-shadow:0 4px 16px rgba(0,0,0,.2);z-index:20;white-space:nowrap;font-family:var(--sans);
}
.graph-tooltip strong{display:block;font-size:13px;margin-bottom:2px}
.graph-tooltip span{color:rgba(255,255,255,.6)}
.graph-legend{
  position:absolute;bottom:16px;left:16px;display:flex;gap:12px;z-index:10;
  flex-wrap:wrap;max-width:calc(100% - 32px);
  background:rgba(255,255,255,.92);padding:8px 14px;border-radius:8px;
  border:1px solid var(--border);font-family:var(--sans);
}
.legend-item{display:flex;align-items:center;gap:5px;font-size:11px;color:var(--text2);cursor:pointer;user-select:none}
.legend-dot{width:10px;height:10px;border-radius:50%;flex-shrink:0}
.legend-item.dimmed{opacity:.3}
.nav-graph{
  padding:14px 16px 6px;
  font-size:12px;
  color:rgba(255,255,255,.4);
  border-top:1px solid rgba(255,255,255,.08);
  margin-top:auto;
}
.nav-graph:hover{color:rgba(255,255,255,.7)}
.nav-graph.active{color:var(--gold-light)}
/* When graph link present, changelog should not push it to bottom */
.nav-graph + .nav-changelog{margin-top:0;border-top:none;padding-top:6px;padding-bottom:14px}

/* ===== BACKLINKS PANEL (right sidebar) ===== */
.main.has-backlinks{
  display:grid;
  grid-template-columns:minmax(0,820px) 280px;
  gap:0 24px;
  max-width:1160px;
}
.main-content{min-width:0}

.backlinks-panel{
  grid-column:2;
  grid-row:1/-1;
  position:sticky;
  top:24px;
  max-height:calc(100vh - 48px);
  overflow-y:auto;
  padding:24px 0 24px 20px;
  border-left:1px solid var(--border);
  font-size:13px;
  align-self:start;
}
.backlinks-panel::-webkit-scrollbar{width:3px}
.backlinks-panel::-webkit-scrollbar-thumb{background:var(--border);border-radius:2px}

.bl-panel-header{
  display:flex;
  align-items:center;
  justify-content:space-between;
  margin-bottom:12px;
}
.bl-panel-title{
  font-family:var(--serif);
  font-size:14px;
  font-weight:700;
  color:var(--navy);
  display:flex;
  align-items:center;
  gap:8px;
}
.bl-count{
  font-size:11px;
  background:var(--bg2);
  padding:1px 7px;
  border-radius:10px;
  color:var(--text2);
  font-weight:600;
}
.bl-panel-actions{display:flex;gap:4px}
.bl-action{
  background:none;
  border:1px solid var(--border);
  border-radius:4px;
  padding:2px 8px;
  font-size:11px;
  color:var(--text2);
  cursor:pointer;
  font-family:var(--sans);
  transition:all .15s;
}
.bl-action:hover{border-color:var(--gold);color:var(--gold)}

.bl-group{margin-bottom:4px}
.bl-group-header{
  display:flex;
  align-items:center;
  gap:6px;
  background:none;
  border:none;
  cursor:pointer;
  padding:5px 0;
  width:100%;
  text-align:left;
  font-size:13px;
  font-family:var(--sans);
}
.bl-group-header:hover{background:rgba(0,0,0,.02);border-radius:4px}

.bl-caret{
  display:inline-block;
  width:0;height:0;
  border:4px solid transparent;
  border-left:5px solid var(--text2);
  transition:transform .15s;
  flex-shrink:0;
}
.bl-group.open .bl-caret{transform:rotate(90deg)}

.bl-source-name{
  color:var(--navy);
  font-weight:600;
  flex:1;
  min-width:0;
  overflow:hidden;
  text-overflow:ellipsis;
  white-space:nowrap;
}
.bl-mention-cat{
  font-size:10px;
  color:var(--text2);
  background:var(--bg2);
  padding:0 5px;
  border-radius:8px;
  flex-shrink:0;
  margin-left:4px;
}

.bl-snippets{display:none;padding:4px 0 4px 14px}
.bl-group.open .bl-snippets{display:block}

.bl-snippet{
  padding:6px 0;
  border-bottom:1px solid var(--border);
  line-height:1.6;
  color:var(--text2);
  font-size:12px;
}
.bl-snippet:last-child{border-bottom:none}
.bl-go-link{
  display:inline-block;
  font-size:11px;
  color:var(--link);
  text-decoration:none;
  padding:4px 0 2px;
  font-weight:600;
  transition:color .15s;
}
.bl-go-link:hover{color:var(--gold);text-decoration:underline}

/* ===== HOMEPAGE ===== */
.hero-section{
  position:relative;
  padding:72px 48px 56px;
  max-width:900px;
  margin:0 auto;
}
.hero-eyebrow{
  display:inline-flex;
  align-items:center;
  gap:8px;
  font-size:12px;
  font-weight:600;
  letter-spacing:2px;
  text-transform:uppercase;
  color:var(--gold);
  margin-bottom:20px;
  opacity:0;
  animation:fadeUp .6s ease forwards;
}
.hero-eyebrow::before{content:'';width:24px;height:1px;background:var(--gold)}
.hero-title{
  font-family:var(--serif);
  font-size:clamp(32px,5vw,48px);
  font-weight:900;
  line-height:1.25;
  letter-spacing:-1px;
  color:var(--navy);
  margin-bottom:6px;
  opacity:0;
  animation:fadeUp .6s ease .1s forwards;
}
.hero-title .gold{color:var(--gold)}
.hero-sub{
  font-size:17px;
  color:var(--text2);
  line-height:1.8;
  margin-top:16px;
  max-width:640px;
  font-family:var(--serif);
  font-weight:400;
  opacity:0;
  animation:fadeUp .6s ease .2s forwards;
}
.hero-sub b{color:var(--navy);font-weight:700}

.stats-row{
  display:grid;
  grid-template-columns:repeat(4,1fr);
  gap:0;
  max-width:900px;
  margin:0 auto 48px;
  padding:0 48px;
  border-top:1px solid var(--border);
  border-bottom:1px solid var(--border);
  opacity:0;
  animation:fadeUp .6s ease .3s forwards;
}
.stat-item{
  text-align:center;
  padding:28px 12px;
  position:relative;
  transition:background .3s;
  text-decoration:none;
  color:inherit;
}
.stat-item:not(:last-child)::after{
  content:'';
  position:absolute;
  right:0;top:20%;
  height:60%;
  width:1px;
  background:var(--border);
}
.stat-item:hover{background:var(--gold-glow)}
.stat-num{
  font-family:var(--serif);
  font-size:42px;
  font-weight:900;
  color:var(--navy);
  line-height:1;
  margin-bottom:6px;
  letter-spacing:-2px;
}
.stat-label{
  font-size:13px;
  color:var(--text2);
  font-weight:500;
  letter-spacing:.5px;
}

.main-inner{max-width:900px;padding:0 48px 80px;margin:0 auto}

.nav-cards{
  display:grid;
  grid-template-columns:repeat(4,1fr);
  gap:16px;
  margin-bottom:56px;
  opacity:0;
  animation:fadeUp .6s ease .4s forwards;
}
.nav-card{
  position:relative;
  padding:28px 20px 24px;
  background:var(--card);
  border:1px solid var(--border);
  border-radius:14px;
  text-decoration:none;
  transition:all .3s cubic-bezier(.4,0,.2,1);
  overflow:hidden;
  display:block;
  color:inherit;
}
.nav-card::before{
  content:'';
  position:absolute;
  top:0;left:0;right:0;
  height:3px;
  background:var(--gold);
  opacity:0;
  transition:opacity .3s;
}
.nav-card:hover{
  transform:translateY(-4px);
  box-shadow:0 12px 32px rgba(0,0,0,.08);
  border-color:var(--gold-light);
}
.nav-card:hover::before{opacity:1}
.nav-card-icon{font-size:32px;margin-bottom:14px;display:block;line-height:1}
.nav-card-title{
  font-family:var(--serif);
  font-size:16px;
  font-weight:700;
  color:var(--navy);
  margin-bottom:4px;
}
.nav-card-sub{font-size:13px;color:var(--text2)}
.nav-card-arrow{
  position:absolute;
  bottom:20px;right:20px;
  font-size:18px;
  color:var(--border);
  transition:all .3s;
}
.nav-card:hover .nav-card-arrow{color:var(--gold);transform:translateX(4px)}

.section{margin-bottom:48px}
.section-header{display:flex;align-items:center;gap:12px;margin-bottom:20px}
.section-line{flex:1;height:1px;background:var(--border)}
.section-title{
  font-family:var(--serif);
  font-size:22px;
  font-weight:700;
  color:var(--navy);
  white-space:nowrap;
}
.section-count{
  font-size:12px;
  color:var(--gold);
  font-weight:600;
  background:var(--gold-glow);
  padding:3px 10px;
  border-radius:12px;
  white-space:nowrap;
}

.tag-cloud{display:flex;flex-wrap:wrap;gap:10px}
.tag{
  display:inline-flex;
  align-items:center;
  gap:6px;
  padding:8px 18px;
  background:var(--card);
  border:1px solid var(--border);
  border-radius:24px;
  font-size:14px;
  color:var(--text);
  text-decoration:none;
  transition:all .25s cubic-bezier(.4,0,.2,1);
  font-weight:500;
}
.tag:hover{
  border-color:var(--gold);
  color:var(--navy);
  box-shadow:0 4px 16px var(--gold-glow);
  transform:translateY(-2px);
}
.tag-n{
  font-size:11px;
  font-weight:700;
  color:#fff;
  background:var(--gold);
  padding:2px 8px;
  border-radius:10px;
  min-width:20px;
  text-align:center;
}
.tag.tier-1{
  font-size:16px;
  padding:10px 22px;
  font-weight:700;
  border-color:var(--gold-light);
  background:linear-gradient(135deg,#FFFDF5,#FFF8E7);
}
.tag.tier-1 .tag-n{font-size:12px;padding:3px 10px;background:var(--gold)}
.tag.tier-2{font-size:15px;padding:9px 20px;font-weight:600}

.people-grid{
  display:grid;
  grid-template-columns:repeat(auto-fill,minmax(180px,1fr));
  gap:14px;
}
.person-card{
  display:flex;
  flex-direction:column;
  align-items:center;
  padding:24px 16px 20px;
  background:var(--card);
  border:1px solid var(--border);
  border-radius:14px;
  text-decoration:none;
  transition:all .3s;
  text-align:center;
  color:inherit;
}
.person-card:hover{
  transform:translateY(-3px);
  box-shadow:0 8px 24px rgba(0,0,0,.06);
  border-color:var(--gold-light);
}
.person-avatar{
  width:56px;height:56px;
  border-radius:50%;
  background:linear-gradient(135deg,var(--navy),var(--navy-light));
  display:flex;
  align-items:center;
  justify-content:center;
  font-size:22px;
  margin-bottom:12px;
  color:var(--gold-light);
  font-family:var(--serif);
  font-weight:700;
  box-shadow:0 4px 12px rgba(26,35,50,.15);
}
.person-name{
  font-family:var(--serif);
  font-size:15px;
  font-weight:700;
  color:var(--navy);
  margin-bottom:4px;
}
.person-refs{font-size:12px;color:var(--text2)}

.gold-divider{display:flex;align-items:center;gap:16px;margin:56px 0}
.gold-divider::before,.gold-divider::after{
  content:'';
  flex:1;
  height:1px;
  background:linear-gradient(to right,transparent,var(--border),transparent);
}
.gold-divider-diamond{
  width:8px;height:8px;
  background:var(--gold);
  transform:rotate(45deg);
  flex-shrink:0;
}

.footer-promo{
  position:relative;
  overflow:hidden;
  padding:40px;
  background:var(--navy);
  border-radius:20px;
  color:#fff;
  display:flex;
  gap:40px;
  align-items:center;
}
.footer-promo::before{
  content:'';
  position:absolute;
  top:-50%;right:-20%;
  width:400px;height:400px;
  border-radius:50%;
  background:radial-gradient(circle,rgba(204,122,0,.15),transparent 70%);
}
.promo-story{flex:1;position:relative;z-index:1;min-width:0}
.promo-story h3{
  font-family:var(--serif);
  font-size:20px;
  font-weight:700;
  margin-bottom:12px;
  color:var(--gold-light);
}
.promo-story p{font-size:14px;color:rgba(255,255,255,.75);line-height:1.8;margin:8px 0}
.promo-credit{
  margin-top:16px !important;
  padding-top:14px;
  border-top:1px solid rgba(255,255,255,.12);
  font-size:13px !important;
}
.promo-credit strong{color:var(--gold-light);font-weight:700}

.promo-qr{
  flex-shrink:0;
  position:relative;
  z-index:1;
  text-align:center;
}
.qr-img{
  display:block;
  width:140px;
  height:140px;
  border-radius:12px;
  border:3px solid rgba(255,255,255,.15);
  box-shadow:0 8px 24px rgba(0,0,0,.25);
  background:#fff;
  padding:6px;
}
.qr-text{
  font-size:12px;
  color:rgba(255,255,255,.6);
  margin-top:10px;
  letter-spacing:.5px;
}

/* ===== ANIMATIONS ===== */
@keyframes fadeUp{
  from{opacity:0;transform:translateY(16px)}
  to{opacity:1;transform:translateY(0)}
}
.section{opacity:0;animation:fadeUp .5s ease forwards}
.section:nth-child(1){animation-delay:.45s}
.section:nth-child(2){animation-delay:.55s}
.section:nth-child(3){animation-delay:.65s}
.section:nth-child(4){animation-delay:.75s}

/* ===== RESPONSIVE ===== */
@media(max-width:1024px){
  .main.has-backlinks{display:block}
  .backlinks-panel{
    position:static;
    max-height:none;
    overflow-y:visible;
    border-left:none;
    border-top:1px solid var(--border);
    padding:24px 16px;
    margin-top:24px;
    max-width:820px;
  }
}

@media(max-width:768px){
  .sidebar{transform:translateX(-100%);transition:transform .3s}
  .sidebar.open{transform:translateX(0)}
  .hamburger{display:block}
  .main{margin-left:0;max-width:100%}
  .main::after{left:0}
  .main.has-backlinks{display:block}
  .article{padding:48px 16px 60px}
  .backlinks-panel{padding:16px 12px;margin-top:16px}
  .hero-section{padding:44px 20px 20px}
  .hero-eyebrow{font-size:10px;margin-bottom:12px}
  .hero-title{font-size:26px}
  .hero-sub{font-size:14px;line-height:1.6;margin-top:10px}
  .stats-row{padding:0 16px;margin:0 0 20px}
  .stat-item{padding:16px 4px}
  .stat-num{font-size:28px;letter-spacing:-1px}
  .stat-label{font-size:11px}
  .main-inner{padding:0 20px 60px}
  .nav-cards{grid-template-columns:1fr 1fr;gap:10px;margin-bottom:36px}
  .nav-card{padding:20px 14px 18px}
  .nav-card-icon{font-size:24px;margin-bottom:8px}
  .nav-card-title{font-size:14px}
  .nav-card-sub{font-size:12px}
  .footer-promo{flex-direction:column;text-align:center;padding:28px 20px;gap:24px}
  .people-grid{grid-template-columns:repeat(2,1fr)}
}
"""

JS = """
document.addEventListener('DOMContentLoaded', function() {
  // Toggle sidebar nav groups
  document.querySelectorAll('.nav-group-title').forEach(function(el) {
    el.addEventListener('click', function() {
      this.parentElement.classList.toggle('open');
    });
  });

  // Backlinks: toggle individual groups
  document.querySelectorAll('.bl-group-header').forEach(function(header) {
    header.addEventListener('click', function() {
      this.closest('.bl-group').classList.toggle('open');
    });
  });

  // Favorite / bookmark popup
  var favBtn = document.getElementById('fav-btn');
  var favPop = document.getElementById('fav-pop');
  if (favBtn && favPop) {
    var isMac = /Mac|iPhone|iPad/.test(navigator.platform);
    var key = isMac ? '\u2318 + D' : 'Ctrl + D';
    favPop.innerHTML =
      '\u6309 <kbd>' + key + '</kbd> \u6536\u85cf\u672c\u9875\u5230\u6d4f\u89c8\u5668\u4e66\u7b7e' +
      '<button class="fav-pop-copy" id="fav-pop-copy">\u590d\u5236\u672c\u9875\u94fe\u63a5</button>';

    favBtn.addEventListener('click', function(e) {
      e.stopPropagation();
      favPop.classList.toggle('show');
    });
    document.addEventListener('click', function(e) {
      if (!favPop.contains(e.target) && e.target !== favBtn) {
        favPop.classList.remove('show');
      }
    });

    var copyBtn = document.getElementById('fav-pop-copy');
    if (copyBtn) {
      copyBtn.addEventListener('click', function(e) {
        e.stopPropagation();
        navigator.clipboard.writeText(window.location.href).then(function() {
          copyBtn.textContent = '\u2713 \u5df2\u590d\u5236';
          copyBtn.classList.add('copied');
          setTimeout(function() {
            copyBtn.textContent = '\u590d\u5236\u672c\u9875\u94fe\u63a5';
            copyBtn.classList.remove('copied');
          }, 1500);
        });
      });
    }
  }

  // Backlinks: expand/collapse all
  document.querySelectorAll('.bl-expand-all').forEach(function(btn) {
    btn.addEventListener('click', function() {
      this.closest('.backlinks-panel').querySelectorAll('.bl-group').forEach(function(g) {
        g.classList.add('open');
      });
    });
  });
  document.querySelectorAll('.bl-collapse-all').forEach(function(btn) {
    btn.addEventListener('click', function() {
      this.closest('.backlinks-panel').querySelectorAll('.bl-group').forEach(function(g) {
        g.classList.remove('open');
      });
    });
  });
});
"""


def build_sidebar_html(files, current_stem=""):
    """Build navy sidebar matching the Buffett site structure."""
    groups = {
        "index-pages":   [],
        "keynotes":      [],
        "interviews":    [],
        "earnings":      [],
        "commencements": [],
        "concepts":      [],
        "methods":       [],
        "companies":     [],
        "people":        [],
    }
    for f in files:
        cat = f["category"]
        if cat in groups:
            groups[cat].append(f)

    # Sort time-based docs ascending; alphabetical for the rest
    groups["keynotes"].sort(key=lambda x: x["stem"])
    groups["interviews"].sort(key=lambda x: x["stem"])
    groups["earnings"].sort(key=lambda x: x["stem"])
    groups["commencements"].sort(key=lambda x: x["stem"])
    for cat in ["concepts", "methods", "companies", "people", "index-pages"]:
        groups[cat].sort(key=lambda x: x["stem"])

    # Home link at top
    home_active = " active" if current_stem == "欢迎" else ""
    html = f'<a href="/index.html" class="nav-link nav-home{home_active}">🏛 首页</a>\n'

    order = [
        ("index-pages",   "索引"),
        ("keynotes",      "演讲"),
        ("interviews",    "访谈"),
        ("earnings",      "财报会议"),
        ("commencements", "毕业演讲"),
        ("methods",       "方法"),
        ("concepts",      "概念"),
        ("companies",     "产品"),
        ("people",        "人物"),
    ]
    for cat, label in order:
        # Open the group containing the current page
        contains_current = any(item["stem"] == current_stem for item in groups[cat])
        is_open = " open" if (cat == "index-pages" or contains_current) else ""
        # Skip 更新日志 from index-pages group since it has its own footer link
        group_items = [f for f in groups[cat] if not (cat == "index-pages" and f["stem"] == "更新日志")]
        html += f'<div class="nav-group{is_open}">\n'
        html += f'  <div class="nav-group-title"><span class="caret"></span>{label}<span class="badge">{len(group_items)}</span></div>\n'
        html += f'  <div class="nav-group-items">\n'
        for f in group_items:
            url = f"/{cat}/{f['stem']}.html"
            active = " active" if f["stem"] == current_stem else ""
            display = f["stem"]
            html += f'    <a href="{url}" class="nav-link{active}" title="{display}">{display}</a>\n'
        html += '  </div>\n</div>\n'

    # Footer: knowledge graph link (always shown)
    graph_active = " active" if current_stem == "知识图谱" else ""
    html += f'<a href="/graph.html" class="nav-link nav-graph{graph_active}">🕸️ 知识图谱</a>\n'

    # Footer: changelog link (if 更新日志.md exists)
    has_changelog = any(f["stem"] == "更新日志" and f["category"] == "index-pages" for f in files)
    if has_changelog:
        changelog_active = " active" if current_stem == "更新日志" else ""
        html += f'<a href="/index-pages/更新日志.html" class="nav-link nav-changelog{changelog_active}">📋 更新日志</a>\n'

    return html


def wrap_page(title, body_html, files, current_stem="", right_html="", wide=False, page_type=""):
    sidebar = build_sidebar_html(files, current_stem)

    extra_class = f" {page_type}" if page_type else ""
    if page_type == "graph":
        # Knowledge graph: full-bleed canvas, no inner article wrapper
        main_class = "main full-bleed"
        main_inner = body_html
    elif wide:
        # Homepage layout
        main_class = "main"
        main_inner = body_html
    elif right_html:
        # Article + backlinks panel layout
        main_class = "main has-backlinks"
        main_inner = f'<div class="main-content article{extra_class}">{body_html}</div>{right_html}'
    else:
        # Article without backlinks
        main_class = "main"
        main_inner = f'<div class="article{extra_class}">{body_html}</div>'

    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{title} - 黄仁勋知识图谱</title>
<link rel="icon" type="image/svg+xml" href="/assets/favicon.svg">
<link rel="icon" type="image/png" sizes="32x32" href="/assets/favicon-32.png">
<link rel="icon" type="image/png" sizes="16x16" href="/assets/favicon-16.png">
<link rel="apple-touch-icon" sizes="180x180" href="/assets/favicon-180.png">
<link rel="shortcut icon" href="/assets/favicon.ico">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Noto+Serif+SC:wght@400;600;700;900&family=Crimson+Pro:ital,wght@0,400;0,700;1,400&family=DM+Sans:wght@400;500;600;700&display=swap" rel="stylesheet">
<!-- Google tag (gtag.js) -->
<script async src="https://www.googletagmanager.com/gtag/js?id=G-WLE88B2LL3"></script>
<script>
  window.dataLayer = window.dataLayer || [];
  function gtag(){{dataLayer.push(arguments);}}
  gtag('js', new Date());
  gtag('config', 'G-WLE88B2LL3');
</script>
<style>{CSS}</style>
</head>
<body>
<button class="hamburger" aria-label="菜单" onclick="document.querySelector('.sidebar').classList.toggle('open')">☰</button>
<aside class="sidebar">
  <div class="sidebar-header"><a href="/index.html" class="logo">黄仁勋知识图谱</a></div>
  <div class="sidebar-nav">
    {sidebar}
  </div>
</aside>
<main class="{main_class}">
{main_inner}
</main>
<script>{JS}</script>
</body>
</html>"""


def build_backlinks_html(stem, backlinks_map, link_map):
    """Build the right-sidebar backlinks panel matching Buffett style."""
    bl = backlinks_map.get(stem, [])
    if not bl:
        return ""

    cat_labels = {
        "letters": "信",
        "concepts": "概念",
        "companies": "产品",
        "people": "人物",
        "index-pages": "索引",
    }

    items_html = ""
    for item in bl:
        url = link_map.get(item["stem"], "#")
        cat_label = cat_labels.get(item["category"], "")
        excerpt_safe = item["excerpt"].replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        items_html += f'''<div class="bl-group">
  <button class="bl-group-header">
    <span class="bl-caret"></span>
    <span class="bl-source-name">{item["title"]}</span>
    <span class="bl-mention-cat">{cat_label}</span>
  </button>
  <div class="bl-snippets">
    <div class="bl-snippet">{excerpt_safe}</div>
    <a href="{url}" class="bl-go-link">查看原文 \u2192</a>
  </div>
</div>
'''

    return f'''<aside class="backlinks-panel">
  <div class="bl-panel-header">
    <h3 class="bl-panel-title">链接到本页 <span class="bl-count">{len(bl)}</span></h3>
    <div class="bl-panel-actions">
      <button class="bl-action bl-expand-all">展开</button>
      <button class="bl-action bl-collapse-all">折叠</button>
    </div>
  </div>
  {items_html}
</aside>
'''


# ── Step 7: Build homepage ───────────────────────────────────────────────────

def build_homepage(files, link_map, ref_counts):
    concept_files = [f for f in files if f["category"] == "concepts"]
    concept_ranked = sorted(concept_files, key=lambda f: ref_counts.get(f["stem"], 0), reverse=True)[:15]

    method_files = [f for f in files if f["category"] == "methods"]
    method_ranked = sorted(method_files, key=lambda f: ref_counts.get(f["stem"], 0), reverse=True)[:10]

    company_files = [f for f in files if f["category"] == "companies"]
    company_ranked = sorted(company_files, key=lambda f: ref_counts.get(f["stem"], 0), reverse=True)[:12]

    people_files = [f for f in files if f["category"] == "people"]

    sources_total = (
        len([f for f in files if f["category"] == "keynotes"])
        + len([f for f in files if f["category"] == "interviews"])
        + len([f for f in files if f["category"] == "earnings"])
        + len([f for f in files if f["category"] == "commencements"])
    )

    # Person initials and role
    people_data = {
        "黄仁勋":                          ("黄", "NVIDIA 创始人 / CEO，34 年 longest-running tech CEO"),
        "Chris Malachowsky":              ("C", "NVIDIA 联合创始人"),
        "Curtis Priem":                   ("P", "NVIDIA 联合创始人，首席架构师"),
        "Bill Dally":                     ("D", "NVIDIA 首席科学家"),
        "Morris Chang":                   ("张", "TSMC 创始人，黄仁勋的导师"),
        "Sam Altman":                     ("S", "OpenAI CEO，Stargate 大单的合作方"),
        "Mark Zuckerberg":                ("Z", "Meta CEO，SIGGRAPH 2024 fireside 对谈伙伴"),
        "Lex Fridman":                    ("L", "Lex Fridman Podcast 主持人，#494 神级访谈"),
        "Ben Gilbert 与 David Rosenthal": ("A", "Acquired Podcast 主持双人组"),
    }

    total_links = sum(ref_counts.values())

    arrow = "\u2192"

    # Hero (with bookmark button)
    html = f'''
<div class="fav-wrap">
  <a href="https://bezos.feima.ai/" class="sister-link" target="_blank" rel="noopener">贝佐斯知识图谱 <span class="arrow">→</span></a>
  <a href="https://musk.feima.ai/" class="sister-link" target="_blank" rel="noopener">马斯克知识图谱 <span class="arrow">→</span></a>
  <button class="fav-btn" id="fav-btn" aria-label="收藏本站">☆<span class="fav-label">收藏</span></button>
  <div class="fav-pop" id="fav-pop"></div>
</div>

<section class="hero-section">
  <div class="hero-eyebrow">Jensen Huang · Mind & Method</div>
  <h1 class="hero-title">黄仁勋<span class="gold">知识图谱</span></h1>
  <p class="hero-sub"><b>{sources_total} 份</b>一手素材，<b>{len(concept_files)} 个</b>核心思想，<b>{len(method_files)} 个</b>工作方法<br>
  从 GTC 主题演讲到 Acquired / Lex Fridman / BG2 长访谈——追踪 NVIDIA 创始人 32 年的思想演变</p>
</section>

<div class="stats-row">
  <a href="/index-pages/素材总览.html" class="stat-item"><div class="stat-num">{sources_total}</div><div class="stat-label">份一手素材</div></a>
  <a href="/index-pages/核心思想索引.html" class="stat-item"><div class="stat-num">{len(concept_files)}</div><div class="stat-label">核心思想</div></a>
  <a href="/index-pages/工作方法索引.html" class="stat-item"><div class="stat-num">{len(method_files)}</div><div class="stat-label">工作方法</div></a>
  <a href="/index-pages/公司与产品索引.html" class="stat-item"><div class="stat-num">{len(company_files)}</div><div class="stat-label">公司/产品</div></a>
  <a href="/index-pages/人物索引.html" class="stat-item"><div class="stat-num">{len(people_files)}</div><div class="stat-label">关键人物</div></a>
</div>

<div class="main-inner">
<div class="nav-cards nav-cards-5">
  <a href="/index-pages/素材总览.html" class="nav-card">
    <span class="nav-card-icon">📜</span>
    <div class="nav-card-title">素材总览</div>
    <div class="nav-card-sub">GTC 演讲 + 长访谈 + 财报 + 毕业演讲</div>
    <span class="nav-card-arrow">{arrow}</span>
  </a>
  <a href="/index-pages/核心思想索引.html" class="nav-card">
    <span class="nav-card-icon">💡</span>
    <div class="nav-card-title">核心思想</div>
    <div class="nav-card-sub">{len(concept_files)} 个概念，含加速计算 / AI 工厂 / Token 经济</div>
    <span class="nav-card-arrow">{arrow}</span>
  </a>
  <a href="/index-pages/工作方法索引.html" class="nav-card">
    <span class="nav-card-icon">⚡</span>
    <div class="nav-card-title">工作方法</div>
    <div class="nav-card-sub">{len(method_files)} 个可操作的实践</div>
    <span class="nav-card-arrow">{arrow}</span>
  </a>
  <a href="/index-pages/公司与产品索引.html" class="nav-card">
    <span class="nav-card-icon">🚀</span>
    <div class="nav-card-title">公司与产品</div>
    <div class="nav-card-sub">{len(company_files)} 家公司与重要产品</div>
    <span class="nav-card-arrow">{arrow}</span>
  </a>
  <a href="/index-pages/人物索引.html" class="nav-card">
    <span class="nav-card-icon">👤</span>
    <div class="nav-card-title">关键人物</div>
    <div class="nav-card-sub">{len(people_files)} 位关键人物</div>
    <span class="nav-card-arrow">{arrow}</span>
  </a>
</div>

<div class="section">
  <div class="section-header">
    <h2 class="section-title">核心概念</h2>
    <div class="section-line"></div>
    <span class="section-count">TOP {len(concept_ranked)}</span>
  </div>
  <div class="tag-cloud">
'''
    # Tag tiering: top 3 = tier-1, next 3 = tier-2, rest = default
    for i, f in enumerate(concept_ranked):
        url = link_map.get(f["stem"], "#")
        count = ref_counts.get(f["stem"], 0)
        tier = " tier-1" if i < 3 else (" tier-2" if i < 6 else "")
        html += f'    <a href="{url}" class="tag{tier}">{f["stem"]}<span class="tag-n">{count}</span></a>\n'

    html += '''  </div>
</div>

<div class="section">
  <div class="section-header">
    <h2 class="section-title">工作方法</h2>
    <div class="section-line"></div>
    <span class="section-count">''' + str(len(method_ranked)) + ''' 个</span>
  </div>
  <p style="font-size:14px;color:var(--text2);margin:-8px 0 16px;font-family:var(--serif)">黄仁勋的工作方法在硅谷自成一派——扁平管理、不开 1-on-1、群发邮件、Mission is the Boss——每张方法卡都附带"你能用上吗？"的实操建议。</p>
  <div class="tag-cloud">
'''
    for i, f in enumerate(method_ranked):
        url = link_map.get(f["stem"], "#")
        count = ref_counts.get(f["stem"], 0)
        tier = " tier-1" if i < 3 else (" tier-2" if i < 6 else "")
        html += f'    <a href="{url}" class="tag{tier}">{f["stem"]}<span class="tag-n">{count}</span></a>\n'

    html += '''  </div>
</div>

<div class="section">
  <div class="section-header">
    <h2 class="section-title">公司与产品</h2>
    <div class="section-line"></div>
    <span class="section-count">TOP ''' + str(len(company_ranked)) + '''</span>
  </div>
  <div class="tag-cloud">
'''
    for i, f in enumerate(company_ranked):
        url = link_map.get(f["stem"], "#")
        count = ref_counts.get(f["stem"], 0)
        tier = " tier-1" if i < 3 else (" tier-2" if i < 6 else "")
        html += f'    <a href="{url}" class="tag{tier}">{f["stem"]}<span class="tag-n">{count}</span></a>\n'

    html += '''  </div>
</div>

<div class="section">
  <div class="section-header">
    <h2 class="section-title">关键人物</h2>
    <div class="section-line"></div>
    <span class="section-count">''' + str(len(people_files)) + ''' 位</span>
  </div>
  <div class="people-grid">
'''
    for f in people_files:
        url = link_map.get(f["stem"], "#")
        avatar, role = people_data.get(f["stem"], ("·", ""))
        count = ref_counts.get(f["stem"], 0)
        html += f'''    <a href="{url}" class="person-card">
      <div class="person-avatar">{avatar}</div>
      <div class="person-name">{f["stem"]}</div>
      <div class="person-refs">被引用 {count} 次</div>
    </a>
'''

    html += '''  </div>
</div>

<div class="gold-divider"><span class="gold-divider-diamond"></span></div>

<div class="footer-promo">
  <div class="promo-story">
    <h3>关于本站</h3>
    <p>把黄仁勋散落在 GTC 主题演讲、Acquired / Lex Fridman / BG2 长访谈、NVIDIA 财报会议、NTU / Caltech 毕业演讲中的思想，整理成一张可以漫游的知识图谱。从 2021 年 GTC 第一次讲清 [[AI 工厂]] 概念，到 2026 年 Lex Fridman 上"AGI 已经实现"的判断，跨越近 5 年的范式转变。</p>
    <p>独有视角：<strong>NVIDIA 加速曲线追踪</strong>（CUDA → Hopper → Blackwell → Vera Rubin）和 <strong>8 个工作方法卡</strong>——黄仁勋的扁平管理 / 不开 1-on-1 / 群发邮件 / Mission is the Boss 在硅谷自成一派，每张卡都附带"你能用上吗？"的实操建议。</p>
    <p class="promo-credit">本站是由作者与 <strong>Claude Code</strong> 共同完成的。想了解和交流更多 AI 机会的话，欢迎扫码关注公众号。</p>
  </div>
  <div class="promo-qr">
    <img src="/assets/qrcode.jpg" alt="公众号二维码" class="qr-img">
    <p class="qr-text">扫码关注公众号</p>
  </div>
</div>

</div>
'''
    return html


# ── Step 8: Main build ───────────────────────────────────────────────────────

def build_graph_data(files):
    """Compute (nodes, edges) for the D3 force-directed knowledge graph.

    A node = one knowledge page (concept/method/company/person/letter/index).
    An edge = an undirected wikilink relationship between two pages.
    """
    import json as _json  # local import keeps function self-contained

    type_labels = {
        "keynotes":       "演讲",
        "interviews":     "访谈",
        "earnings":       "财报会议",
        "commencements":  "毕业演讲",
        "concepts":       "核心思想",
        "methods":        "工作方法",
        "companies":      "产品",
        "people":         "人物",
        "index-pages":    "索引",
    }

    # Build alias→canonical stem map
    alias_to_stem = {}
    for f in files:
        if f["category"] == "home":
            continue
        alias_to_stem[f["stem"]] = f["stem"]
        for alias in f["fm"].get("aliases", []) or []:
            alias_to_stem[alias] = f["stem"]

    # Compute out-links per stem (deduped per source page)
    out_links = {}
    for f in files:
        if f["category"] == "home" or f["stem"] == "更新日志":
            continue
        stem = f["stem"]
        out_links.setdefault(stem, set())
        for m in re.finditer(r'\[\[([^\]|]+?)(?:\|[^\]]+)?\]\]', f["body"]):
            target_raw = m.group(1).strip()
            target = alias_to_stem.get(target_raw)
            if target and target != stem and target != "更新日志":
                out_links[stem].add(target)

    # In-degree per stem (from out_links)
    in_links = {}
    for src, targets in out_links.items():
        for t in targets:
            in_links.setdefault(t, set()).add(src)

    # Build node list (excluding home and changelog)
    nodes = []
    for f in files:
        if f["category"] == "home" or f["stem"] == "更新日志":
            continue
        stem = f["stem"]
        nodes.append({
            "id":        stem,
            "type":      type_labels.get(f["category"], f["category"]),
            "dir":       f["category"],
            "file":      f"{stem}.html",
            "links":     len(out_links.get(stem, set())),
            "backlinks": len(in_links.get(stem, set())),
        })

    # Build edges (undirected, deduped)
    node_ids = {n["id"] for n in nodes}
    seen = set()
    edges = []
    for src, targets in out_links.items():
        if src not in node_ids:
            continue
        for t in targets:
            if t not in node_ids:
                continue
            key = tuple(sorted([src, t]))
            if key in seen:
                continue
            seen.add(key)
            edges.append({"source": src, "target": t})

    return nodes, edges


def build_graph_page(files):
    """Return body HTML for the knowledge graph page."""
    import json as _json
    nodes, edges = build_graph_data(files)
    raw_json = _json.dumps({"nodes": nodes, "edges": edges}, ensure_ascii=False)

    # Color palette per type — Buffett-style warm/serif tones, plus a distinct
    # gold for the "工作方法" dimension that is unique to the Huang knowledge base.
    type_colors = {
        "核心思想":  "#7C5E2A",  # warm brown
        "工作方法":  "#B8860B",  # gold (unique dimension)
        "产品":      "#1A6B7C",  # teal
        "人物":      "#8B2F2F",  # red
        "演讲":      "#2A6B4F",  # forest green
        "访谈":      "#4A4E8A",  # indigo
        "财报会议":  "#6B4F7C",  # plum
        "毕业演讲":  "#7E6B30",  # ochre
        "索引":      "#6B6560",  # warm gray
    }
    type_colors_json = _json.dumps(type_colors, ensure_ascii=False)

    return f"""<div class="graph-wrap" id="graph-wrap">
  <div class="graph-title"><h1>知识图谱</h1><p id="graph-stats"></p></div>
  <div class="graph-toolbar">
    <button id="btn-zoom-in" title="放大">＋</button>
    <button id="btn-zoom-out" title="缩小">－</button>
    <button id="btn-reset" title="重置视图">重置</button>
  </div>
  <div class="graph-legend" id="graph-legend"></div>
  <div class="graph-tooltip" id="tooltip"></div>
  <svg id="graph-svg"></svg>
</div>
<script src="https://cdn.jsdelivr.net/npm/d3@7/dist/d3.min.js"></script>
<script>
(function(){{
var raw = {raw_json};
var typeColors = {type_colors_json};

var nodes = raw.nodes.map(function(n){{
  var size = Math.max(2.5, Math.sqrt(n.backlinks + n.links) * 1.6);
  return {{id:n.id, type:n.type, dir:n.dir, file:n.file, r:size,
    backlinks:n.backlinks, links:n.links, color:typeColors[n.type]||'#999'}};
}});
var nodeMap = {{}};
nodes.forEach(function(n){{ nodeMap[n.id]=n; }});
var edges = raw.edges.filter(function(e){{ return nodeMap[e.source] && nodeMap[e.target]; }});

document.getElementById('graph-stats').textContent =
  nodes.length + ' 个节点 · ' + edges.length + ' 条链接';

// Legend with click-to-toggle
var types = Object.keys(typeColors);
var legendEl = document.getElementById('graph-legend');
var activeTypes = new Set(types);
types.forEach(function(t){{
  var count = nodes.filter(function(n){{return n.type===t}}).length;
  if(count===0) return;
  var item = document.createElement('div');
  item.className = 'legend-item';
  item.innerHTML = '<span class="legend-dot" style="background:'+typeColors[t]+'"></span>'+t+' ('+count+')';
  item.onclick = function(){{
    if(activeTypes.has(t)){{activeTypes.delete(t);item.classList.add('dimmed')}}
    else{{activeTypes.add(t);item.classList.remove('dimmed')}}
    updateVisibility();
  }};
  legendEl.appendChild(item);
}});

var wrap = document.getElementById('graph-wrap');
var W = wrap.clientWidth, H = wrap.clientHeight;
var svg = d3.select('#graph-svg').attr('viewBox',[0,0,W,H]);
var g = svg.append('g');

var zoom = d3.zoom().scaleExtent([0.1,8]).on('zoom',function(e){{g.attr('transform',e.transform)}});
svg.call(zoom);
document.getElementById('btn-zoom-in').onclick=function(){{svg.transition().call(zoom.scaleBy,1.5)}};
document.getElementById('btn-zoom-out').onclick=function(){{svg.transition().call(zoom.scaleBy,0.67)}};
document.getElementById('btn-reset').onclick=function(){{svg.transition().call(zoom.transform,d3.zoomIdentity)}};

// Concepts/methods/companies/people pull toward center; letters/talks float outward
var coreTypes = new Set(['核心思想','工作方法','产品','人物']);
var simulation = d3.forceSimulation(nodes)
  .force('link',d3.forceLink(edges).id(function(d){{return d.id}}).distance(80).strength(0.12))
  .force('charge',d3.forceManyBody().strength(-280).distanceMax(500))
  .force('center',d3.forceCenter(W/2,H/2))
  .force('collide',d3.forceCollide().radius(function(d){{return d.r+4}}).strength(0.7))
  .force('x',d3.forceX(W/2).strength(function(d){{return coreTypes.has(d.type)?0.08:0.01}}))
  .force('y',d3.forceY(H/2).strength(function(d){{return coreTypes.has(d.type)?0.08:0.01}}))
  .force('radial',d3.forceRadial(function(d){{return coreTypes.has(d.type)?0:Math.min(W,H)*0.4}},W/2,H/2).strength(function(d){{return coreTypes.has(d.type)?0:0.05}}));

var link = g.append('g').attr('class','links')
  .selectAll('line').data(edges).join('line')
  .attr('stroke','#e8e0d4').attr('stroke-width',0.4).attr('stroke-opacity',0.25);

var node = g.append('g').attr('class','nodes')
  .selectAll('circle').data(nodes).join('circle')
  .attr('r',function(d){{return d.r}})
  .attr('fill',function(d){{return d.color}})
  .attr('stroke','#fff').attr('stroke-width',0.5)
  .attr('cursor','pointer')
  .attr('opacity',0.85)
  .call(d3.drag().on('start',dragStart).on('drag',dragging).on('end',dragEnd));

// Permanently label hub nodes (top by backlinks)
var label = g.append('g').attr('class','labels')
  .selectAll('text').data(nodes.filter(function(d){{return d.backlinks>=5}})).join('text')
  .text(function(d){{return d.id}})
  .attr('font-size','8px')
  .attr('fill','#555').attr('text-anchor','middle')
  .attr('dy',function(d){{return d.r+9}})
  .attr('font-family','var(--sans)').attr('pointer-events','none');

// Adjacency for fast neighbor lookup
var adj = {{}};
nodes.forEach(function(n){{adj[n.id]=new Set()}});
edges.forEach(function(e){{
  var s=typeof e.source==='object'?e.source.id:e.source;
  var t=typeof e.target==='object'?e.target.id:e.target;
  adj[s].add(t); adj[t].add(s);
}});

// Hover tooltip + neighbor highlight
var hoverLabel = g.append('g').attr('class','hover-labels');
var tooltip = document.getElementById('tooltip');
node.on('mouseover',function(e,d){{
  tooltip.innerHTML = '<strong>'+d.id+'</strong><span>'+d.type+' · 被引用 '+d.backlinks+' 次 · 引用 '+d.links+' 个</span>';
  tooltip.style.opacity=1;
  var neighbors = adj[d.id];
  link.attr('stroke',function(l){{return(l.source.id===d.id||l.target.id===d.id)?d.color:'#e8e0d4'}})
    .attr('stroke-width',function(l){{return(l.source.id===d.id||l.target.id===d.id)?1.4:0.3}})
    .attr('stroke-opacity',function(l){{return(l.source.id===d.id||l.target.id===d.id)?0.75:0.06}});
  node.attr('opacity',function(n){{
    if(n.id===d.id) return 1;
    return neighbors.has(n.id)?0.95:0.08;
  }});
  label.attr('opacity',function(n){{return(n.id===d.id||neighbors.has(n.id))?1:0.05}});
  hoverLabel.selectAll('text').remove();
  var permSet = new Set(nodes.filter(function(n){{return n.backlinks>=5}}).map(function(n){{return n.id}}));
  var showIds = [d].concat(nodes.filter(function(n){{return neighbors.has(n.id)}}))
    .filter(function(n){{return !permSet.has(n.id)}});
  hoverLabel.selectAll('text').data(showIds).join('text')
    .text(function(n){{return n.id}})
    .attr('x',function(n){{return n.x}}).attr('y',function(n){{return n.y+n.r+9}})
    .attr('font-size','7px').attr('fill','#333').attr('text-anchor','middle')
    .attr('font-family','var(--sans)').attr('pointer-events','none');
}}).on('mousemove',function(e){{
  tooltip.style.left=(e.pageX+12)+'px';tooltip.style.top=(e.pageY-30)+'px';
}}).on('mouseout',function(){{
  tooltip.style.opacity=0;
  link.attr('stroke','#e8e0d4').attr('stroke-width',0.4).attr('stroke-opacity',0.25);
  node.attr('opacity',0.85);
  label.attr('opacity',1);
  hoverLabel.selectAll('text').remove();
}}).on('click',function(e,d){{
  window.location.href='/'+d.dir+'/'+d.file;
}});

simulation.on('tick',function(){{
  link.attr('x1',function(d){{return d.source.x}}).attr('y1',function(d){{return d.source.y}})
    .attr('x2',function(d){{return d.target.x}}).attr('y2',function(d){{return d.target.y}});
  node.attr('cx',function(d){{return d.x}}).attr('cy',function(d){{return d.y}});
  label.attr('x',function(d){{return d.x}}).attr('y',function(d){{return d.y}});
}});

function dragStart(e,d){{if(!e.active)simulation.alphaTarget(0.3).restart();d.fx=d.x;d.fy=d.y}}
function dragging(e,d){{d.fx=e.x;d.fy=e.y}}
function dragEnd(e,d){{if(!e.active)simulation.alphaTarget(0);d.fx=null;d.fy=null}}

// Auto-fit after simulation settles
simulation.on('end',function(){{
  var xs=nodes.map(function(n){{return n.x}}), ys=nodes.map(function(n){{return n.y}});
  var x0=d3.min(xs)-30,x1=d3.max(xs)+30,y0=d3.min(ys)-30,y1=d3.max(ys)+30;
  var scale=Math.min(W/(x1-x0),H/(y1-y0))*0.9;
  var tx=W/2-(x0+x1)/2*scale, ty=H/2-(y0+y1)/2*scale;
  svg.transition().duration(500).call(zoom.transform,d3.zoomIdentity.translate(tx,ty).scale(scale));
}});

function updateVisibility(){{
  node.attr('display',function(d){{return activeTypes.has(d.type)?null:'none'}});
  label.attr('display',function(d){{return activeTypes.has(d.type)?null:'none'}});
  link.attr('display',function(d){{return activeTypes.has(d.source.type)&&activeTypes.has(d.target.type)?null:'none'}});
}}
}})();
</script>"""


def main():
    # Clean output
    if OUT.exists():
        shutil.rmtree(OUT)

    # Copy static assets (e.g. QR code, favicon)
    assets_src = Path(__file__).parent / "assets-huang"
    if assets_src.is_dir():
        shutil.copytree(assets_src, OUT / "assets")
        print(f"Copied assets-huang/ ({len(list(assets_src.iterdir()))} files)")

    # Collect
    print("Collecting files...")
    files = collect_files()
    print(f"  Found {len(files)} files")

    # Build link map
    link_map = build_link_map(files)
    print(f"  Built link map with {len(link_map)} entries")

    # Count references
    ref_counts = count_references(files)

    # Build backlinks
    backlinks_map = build_backlinks(files, link_map)
    total_backlinks = sum(len(v) for v in backlinks_map.values())
    print(f"  Built backlinks: {total_backlinks} links across {len(backlinks_map)} pages")

    # Build pages
    page_count = 0

    for f in files:
        stem = f["stem"]
        cat  = f["category"]

        if cat == "home":
            # Homepage
            body_html = build_homepage(files, link_map, ref_counts)
            html = wrap_page("首页", body_html, files, current_stem=stem, wide=True)
            out_path = OUT / "index.html"
        else:
            # Convert wikilinks then markdown
            body_md = convert_wikilinks(f["body"], link_map)
            body_html = md_to_html(body_md)
            # Add type badge meta above content
            type_label_map = {
                "keynotes":      "演讲",
                "interviews":    "访谈",
                "earnings":      "财报会议",
                "commencements": "毕业演讲",
                "concepts":      "概念",
                "methods":       "方法",
                "companies":     "产品",
                "people":        "人物",
                "index-pages":   "索引",
            }
            type_label = type_label_map.get(cat, "")
            # Skip type badge on changelog page
            if type_label and stem != "更新日志":
                body_html = f'<div class="meta"><span class="type-badge type-{type_label}">{type_label}</span></div>\n' + body_html
            # Build backlinks as right sidebar — skip for index pages (they list everything)
            if cat == "index-pages":
                bl_html = ""
            else:
                bl_html = build_backlinks_html(stem, backlinks_map, link_map)
            title = f["fm"].get("title", stem)
            # Apply changelog styling for 更新日志.md
            page_type = "changelog" if stem == "更新日志" else ""
            html = wrap_page(title, body_html, files, current_stem=stem, right_html=bl_html, page_type=page_type)
            out_path = OUT / cat / f"{stem}.html"

        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(html, encoding="utf-8")
        page_count += 1

    # Knowledge graph page (standalone, full-bleed)
    graph_body = build_graph_page(files)
    graph_html = wrap_page("知识图谱", graph_body, files, current_stem="知识图谱", page_type="graph")
    (OUT / "graph.html").write_text(graph_html, encoding="utf-8")
    page_count += 1
    print(f"  Generated graph.html")

    print(f"\nGenerated {page_count} HTML pages in {OUT}")

    # Stats
    total_size = sum(p.stat().st_size for p in OUT.rglob("*.html"))
    print(f"Total size: {total_size / 1024:.0f} KB")
    for d in sorted(OUT.iterdir()):
        if d.is_dir():
            count = len(list(d.glob("*.html")))
            print(f"  {d.name}/: {count} files")
        else:
            print(f"  {d.name}: {d.stat().st_size / 1024:.1f} KB")


if __name__ == "__main__":
    main()
