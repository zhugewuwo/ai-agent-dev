#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Build a static course website (juejin-course style) from markdown chapters."""
import os
import re
import html
import shutil
import unicodedata
from markdown_it import MarkdownIt
from markdown_it.common.utils import escapeHtml

SRC = os.path.join(os.path.dirname(os.path.abspath(__file__)), "content")
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "site")
BOOK_TITLE = "AI Agents 开发实践"
BOOK_SUBTITLE = "从模型调用到生产级 AI 产品的完整链路"
REPO = "https://github.com/Cookieboty/Autix"

# Box-drawing / arrow glyphs used by the ASCII flow charts in the course.
BOX_CHARS = set("─│┌┐└┘├┤┬┴┼▶◀▼▲╭╮╯╰═║╔╗╚╝━┃┏┓┗┛┣┫┳┻╋")
# Usable inner width of the article column, in CSS px (800 max-width - 2*16 padding - scrollbar).
DIAGRAM_INNER = 736
DIAGRAM_MIN_FONT = 9.0
DIAGRAM_MAX_FONT = 13.5


def cell_width(s):
    """Terminal cell count: East-Asian wide glyphs count as two columns."""
    return sum(2 if unicodedata.east_asian_width(c) in ("W", "F") else 1 for c in s)


def diagram_font_size(content):
    cells = max((cell_width(line) for line in content.splitlines()), default=0)
    if cells == 0:
        return None
    # Monospace advance width is roughly 0.6em; shrink so the widest line fits.
    size = DIAGRAM_INNER / (cells * 0.6)
    return round(max(DIAGRAM_MIN_FONT, min(DIAGRAM_MAX_FONT, size)), 1)


def is_diagram(content):
    """True for hand-drawn ASCII flow charts (not code that happens to contain a dash)."""
    if not any(c in BOX_CHARS for c in content):
        return False
    cells = max((cell_width(line) for line in content.splitlines()), default=0)
    # Diagrams in this course are at most ~160 columns wide; wider blocks are JSON/code.
    return cells <= 170



def strip_frontmatter(text):
    return re.sub(r"\A---\r?\n.*?\r?\n---\r?\n", "", text, count=1, flags=re.S)


def read_chapters():
    chapters = []
    for name in os.listdir(SRC):
        if not name.endswith(".md"):
            continue
        m = re.match(r"^(\d+)-(.+)\.md$", name)
        if not m:
            continue
        num = int(m.group(1))
        slug = m.group(2)
        with open(os.path.join(SRC, name), encoding="utf-8") as f:
            text = strip_frontmatter(f.read())
        chapters.append({"num": num, "slug": slug, "text": text, "file": name})
    chapters.sort(key=lambda c: c["num"])
    return chapters


def sidebar_title(slug):
    """Strip a leading 第N章： / 第2.5章： prefix for the sidebar."""
    t = re.sub(r"^第\s*[0-9一二三四五六七八九十.]+\s*章\s*[:：]?\s*", "", slug).strip()
    return t or slug


def chapter_title(text, num):
    for line in text.splitlines():
        line = line.strip()
        if line.startswith("# "):
            t = line[2:].strip()
            t = re.sub(r"^第\s*[0-9一二三四五六七八九十.]+\s*章\s*[:：]?\s*", "", t).strip()
            return t or f"第 {num} 章"
        if line.startswith("## "):
            t = line[3:].strip()
            if t:
                return t
    return f"第 {num} 章"


def reading_time(text):
    # approximate: count CJK chars + latin words
    cjk = len(re.findall(r"[\u4e00-\u9fff]", text))
    words = len(re.findall(r"[A-Za-z0-9_]+", text))
    minutes = cjk / 400.0 + words / 200.0
    total = max(20, int(round(minutes * 60)))
    mm, ss = divmod(total, 60)
    if mm == 0:
        return f"{ss}秒"
    return f"{mm}分{ss}秒"


def build_renderer():
    md = MarkdownIt("commonmark", {"html": True, "linkify": False, "typographer": False})
    md.enable(["table", "strikethrough"])

    orig_fence = md.renderer.rules["fence"]

    def fence_override(tokens, idx, options, env):
        tok = tokens[idx]
        if tok.info.strip().split()[0:1] == ["mermaid"]:
            return '<div class="mermaid">' + escapeHtml(tok.content) + "</div>\n"
        return orig_fence(tokens, idx, options, env)

    md.renderer.rules["fence"] = fence_override
    return md


def render_chapter(md, text):
    """Render markdown to html and collect h2/h3 toc with anchors."""
    tokens = md.parse(text)
    toc = []
    used = {}
    # assign ids to headings
    for i, tok in enumerate(tokens):
        if tok.type == "heading_open" and tok.tag in ("h2", "h3"):
            inline = tokens[i + 1]
            title = inline.content
            base = re.sub(r"[^\w\u4e00-\u9fff]+", "-", title).strip("-").lower() or "sec"
            idx = used.get(base, 0)
            used[base] = idx + 1
            hid = base if idx == 0 else f"{base}-{idx}"
            tok.attrSet("id", hid)
            toc.append({"id": hid, "text": title, "level": int(tok.tag[1])})
        elif tok.type == "fence" and tok.info.strip() != "mermaid" and is_diagram(tok.content):
            size = diagram_font_size(tok.content)
            tok.attrSet("class", "diagram")
            if size is not None:
                tok.attrSet("style", f"font-size:{size}px")
    body = md.renderer.render(tokens, md.options, {})
    return body, toc


PAGE = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<meta name="referrer" content="no-referrer">
<title>{page_title} - {book_title}</title>
<link rel="stylesheet" href="assets/style.css">
<link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/highlight.js@11.9.0/styles/github.min.css">
</head>
<body>
<header class="topbar">
  <div class="topbar-inner">
    <a class="topbar-title" href="index.html">{book_title}</a>
    <div class="topbar-right">
      <a class="login-btn" href="{repo}" target="_blank" rel="noopener">项目源码</a>
    </div>
  </div>
</header>

<div class="layout">
  <aside class="sidebar">
    <nav class="chapter-list">
      <ol>
        {chapter_items}
      </ol>
    </nav>
  </aside>

  <main class="content">
    <article class="markdown-body">
      {body}
    </article>
    <div class="pager">
      {prev_link}
      {next_link}
    </div>
  </main>

  <aside class="toc">
    <div class="toc-head"><span>目录</span><span class="toc-toggle">≫</span></div>
    <ul>{toc_items}</ul>
  </aside>
</div>

<script src="https://cdn.jsdelivr.net/npm/highlight.js@11.9.0/lib/common.min.js"></script>
<script>hljs.highlightAll();</script>
<script type="module">
  import mermaid from 'https://cdn.jsdelivr.net/npm/mermaid@11/dist/mermaid.esm.min.mjs';
  mermaid.initialize({{ startOnLoad: true, theme: 'neutral', securityLevel: 'strict', fontFamily: 'inherit' }});
</script>
<script src="assets/app.js"></script>
</body>
</html>
"""


def make_chapter_items(chapters, active_id):
    items = []
    for c in chapters:
        cls = " class=\"active\"" if c["id"] == active_id else ""
        items.append(
            f'<li{cls}><a href="{c["id"]}.html">'
            f'<span class="num">{c["disp"]}</span>'
            f'<span class="info"><span class="t">{html.escape(c["sidebar"])}</span>'
            f'<span class="d">阅读时长: {c["time"]}</span></span>'
            f'</a></li>'
        )
    return "\n        ".join(items)


def main():
    if os.path.isdir(OUT):
        shutil.rmtree(OUT)
    os.makedirs(os.path.join(OUT, "assets"), exist_ok=True)
    web = os.path.join(os.path.dirname(os.path.abspath(__file__)), "web")
    for asset in ("style.css", "app.js"):
        shutil.copy(os.path.join(web, asset), os.path.join(OUT, "assets", asset))
    open(os.path.join(OUT, ".nojekyll"), "w").close()

    md = build_renderer()
    chapters = read_chapters()
    for i, c in enumerate(chapters):
        c["disp"] = i + 1
        c["id"] = f"ch-{c['num']}"
        c["title"] = c["slug"]
        c["sidebar"] = sidebar_title(c["slug"])
        c["time"] = reading_time(c["text"])
        c["html"], c["toc"] = render_chapter(md, f"# {c['title']}\n\n{c['text']}")

    for i, c in enumerate(chapters):
        toc_items = "\n      ".join(
            f'<li class="lv{t["level"]}"><a href="#{t["id"]}">{html.escape(t["text"])}</a></li>'
            for t in c["toc"]
        ) or '<li class="muted">—</li>'
        prev_link = next_link = ""
        if i > 0:
            p = chapters[i - 1]
            prev_link = f'<a class="prev" href="{p["id"]}.html">← {html.escape(p["title"])}</a>'
        if i < len(chapters) - 1:
            n = chapters[i + 1]
            next_link = f'<a class="next" href="{n["id"]}.html">{html.escape(n["title"])} →</a>'
        page = PAGE.format(
            page_title=html.escape(c["title"]),
            book_title=html.escape(BOOK_TITLE),
            repo=REPO,
            chapter_items=make_chapter_items(chapters, c["id"]),
            body=c["html"],
            toc_items=toc_items,
            prev_link=prev_link,
            next_link=next_link,
        )
        with open(os.path.join(OUT, f'{c["id"]}.html'), "w", encoding="utf-8") as f:
            f.write(page)

    # index redirects to first chapter but is also a landing overview
    first = chapters[0]
    chapter_items = make_chapter_items(chapters, None)
    cards = "\n      ".join(
        f'<a class="card" href="{c["id"]}.html"><span class="card-num">{c["disp"]:02d}</span>'
        f'<span class="card-t">{html.escape(c["title"])}</span>'
        f'<span class="card-d">{c["time"]}</span></a>'
        for c in chapters
    )
    index = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<meta name="referrer" content="no-referrer">
<title>{html.escape(BOOK_TITLE)}</title>
<link rel="stylesheet" href="assets/style.css">
</head>
<body class="landing-body">
<header class="topbar">
  <div class="topbar-inner">
    <a class="topbar-title" href="index.html">{html.escape(BOOK_TITLE)}</a>
    <div class="topbar-right">
      <a class="login-btn" href="{REPO}" target="_blank" rel="noopener">项目源码</a>
    </div>
  </div>
</header>
<div class="landing">
  <h1>{html.escape(BOOK_TITLE)}</h1>
  <p class="sub">{html.escape(BOOK_SUBTITLE)}</p>
  <p class="desc">共 {len(chapters)} 篇 · 从一次普通的 API 调用出发，一步步构建一个真实的 AI 产品。</p>
  <a class="start-btn" href="{first['id']}.html">开始学习</a>
  <div class="cards">
      {cards}
  </div>
</div>
</body>
</html>
"""
    with open(os.path.join(OUT, "index.html"), "w", encoding="utf-8") as f:
        f.write(index)

    print(f"Generated {len(chapters)} chapters into {OUT}")


if __name__ == "__main__":
    main()
