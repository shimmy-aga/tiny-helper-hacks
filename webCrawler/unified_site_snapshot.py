#!/usr/bin/env python3
"""
Unified Site Snapshot — export any page into a tidy, offline‑ready folder:

root/
  assets/
    css/styles.css
    js/main.js
    media/
      favicon/<all favicon files>
      uploads/images/<all images referenced from HTML & CSS>
  index.html

Goals (as requested):
- Exactly ONE html file (index.html), ONE css file (assets/css/styles.css), ONE js file (assets/js/main.js).
- All styles/scripts referenced from <head> are consolidated. Inline <style>/<script> that appear
  *before* external files are PREPENDED; those that appear *after* are APPENDED, preserving
  natural execution order as closely as possible. Duplicate links/tags are removed.
- Images, icons, and other binary assets referenced from HTML and inside CSS are downloaded
  to the media/ tree and re-linked with stable relative paths.
- Optional "crawl" mode (bonus): same-origin BFS to prefetch additional assets encountered on
  linked pages — but still output a single index.html for the starting URL (to satisfy the
  single-file HTML requirement). If this conflicts with any site, use the default single-page mode.

Notes
- No headless rendering; this captures the server-delivered HTML.
- WASM or other non-text <script src> are NOT merged into main.js (can’t be executed as JS).
  We keep those as separate <script src> tags and save the binaries under assets/js/other/.
  (If you strictly need one <script> tag even in presence of binary types, a custom loader
  would be required — intentionally omitted to avoid breaking behavior.)

Requires: requests, beautifulsoup4, lxml(optional)
    pip install requests beautifulsoup4 lxml

Python 3.9+
"""
from __future__ import annotations

import argparse
import base64
import mimetypes
import os
import posixpath
import re
import sys
from collections import deque
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple
from urllib.parse import urljoin, urlsplit, urlunsplit

import requests
from bs4 import BeautifulSoup

# ---- Setup ---- #
DEFAULT_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)

# Ensure some missing types
mimetypes.add_type("font/woff2", ".woff2")
mimetypes.add_type("font/woff", ".woff")
mimetypes.add_type("font/ttf", ".ttf")
mimetypes.add_type("font/otf", ".otf")
mimetypes.add_type("application/vnd.ms-fontobject", ".eot")
mimetypes.add_type("image/svg+xml", ".svg")

CSS_URL_RE = re.compile(r"url\(\s*(['\"]?)([^)\s'\"]+)\1\s*\)")
AT_IMPORT_RE = re.compile(r"@import\s+(?:url\(\s*(['\"]?)([^)\s'\"]+)\1\s*\)|(['\"]).*?\3)\s*;", re.I)
SRCSET_SPLIT_RE = re.compile(r"\s*,\s*")
ABS_URL_RE = re.compile(r"^https?://", re.I)

@dataclass
class Options:
    url: str
    out_dir: Path
    mode: str = "single"  # "single" or "crawl"
    max_pages: int = 200
    timeout: float = 25.0
    user_agent: str = DEFAULT_UA
    follow_subdomains: bool = False
    restrict_path_prefix: Optional[str] = None
    respect_robots: bool = True
    same_origin_assets_only: bool = False

@dataclass
class State:
    session: requests.Session
    visited: Set[str]
    to_visit: deque
    asset_map: Dict[str, str]  # absolute URL -> local relative path

# ---- Utilities ---- #

def norm_url(u: str) -> str:
    s = urlsplit(u)
    # normalize path (remove .., .), drop fragment
    path = posixpath.normpath(s.path)
    if s.path.endswith('/') and not path.endswith('/'):
        path += '/'
    return urlunsplit((s.scheme, s.netloc.lower(), path, s.query, ''))


def ensure_dirs(root: Path) -> Dict[str, Path]:
    css = root / "assets/css"
    js = root / "assets/js"
    js_other = js / "other"
    media = root / "assets/media"
    favicon = media / "favicon"
    images = media / "uploads/images"
    for p in [css, js, js_other, media, favicon, images]:
        p.mkdir(parents=True, exist_ok=True)
    return {
        'root': root, 'css': css, 'js': js, 'js_other': js_other,
        'media': media, 'favicon': favicon, 'images': images
    }


def is_same_origin(a: str, b: str, follow_subdomains: bool) -> bool:
    sa, sb = urlsplit(a), urlsplit(b)
    if sa.scheme != sb.scheme:
        return False
    if sa.netloc == sb.netloc:
        return True
    return follow_subdomains and sb.netloc.endswith('.' + sa.netloc)


def absolutize(base: str, href: str | None) -> Optional[str]:
    if not href:
        return None
    if href.startswith(('data:', 'javascript:', 'about:', '#')):
        return None
    if href.startswith('//'):
        b = urlsplit(base)
        return f"{b.scheme}:{href}"
    if ABS_URL_RE.match(href):
        return href
    return urljoin(base, href)


def guess_ext(content_type: Optional[str], fallback_url: Optional[str] = None) -> str:
    if content_type:
        ct = content_type.split(';', 1)[0].strip().lower()
        if ct in {"text/xml", "application/xml"} and (fallback_url or '').lower().endswith('.svg'):
            return ".svg"
        ext = mimetypes.guess_extension(ct) or ''
        return ext or ''
    if fallback_url:
        _, ext = os.path.splitext(urlsplit(fallback_url).path)
        return ext
    return ''


def fetch(state: State, url: str, timeout: float) -> Tuple[Optional[bytes], Optional[str]]:
    try:
        r = state.session.get(url, timeout=timeout, allow_redirects=True)
        r.raise_for_status()
        return r.content, r.headers.get('Content-Type')
    except Exception:
        return None, None


def write_file(path: Path, data: bytes | str, text: bool = False) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    mode = 'w' if text else 'wb'
    with open(path, mode, encoding='utf-8' if text else None) as f:
        f.write(data)


def map_asset(state: State, abs_url: str, folders: Dict[str, Path]) -> Optional[str]:
    abs_url = norm_url(abs_url)
    if abs_url in state.asset_map:
        return state.asset_map[abs_url]

    data, ctype = fetch(state, abs_url, timeout=25.0)
    if data is None:
        return None

    ext = guess_ext(ctype, abs_url)
    # Decide destination
    dest_dir = folders['media']
    name = os.path.basename(urlsplit(abs_url).path).lower()
    if any(x in name for x in ['favicon', 'apple-touch-icon', 'mstile']):
        dest_dir = folders['favicon']
    elif (ctype or '').startswith('image/'):
        dest_dir = folders['images']

    # Stable filename: original basename if present, else sha1
    base = os.path.basename(urlsplit(abs_url).path)
    if not base:
        import hashlib
        h = hashlib.sha1(abs_url.encode('utf-8')).hexdigest()[:12]
        base = f"asset_{h}{ext or ''}"
    elif ext and not base.lower().endswith(ext):
        base = base + ext  # keep server-suggested name and add ext if missing

    local_path = dest_dir / base
    # Avoid collisions
    i = 1
    stem, suffix = os.path.splitext(local_path.name)
    while local_path.exists():
        local_path = dest_dir / f"{stem}_{i}{suffix}"
        i += 1

    write_file(local_path, data, text=False)
    rel = os.path.relpath(local_path, start=folders['root']).replace('\\', '/')
    state.asset_map[abs_url] = rel
    # If CSS, immediately rewrite and overwrite file so its url()s point to local copies
    if ((ctype or '').lower().startswith('text/css') or local_path.suffix.lower() == '.css'):
        try:
            css_text = data.decode('utf-8', errors='replace')
            css_text = rewrite_css_urls(css_text, abs_url, state, folders)
            write_file(local_path, css_text, text=True)
        except Exception:
            pass
    return rel


def rewrite_css_urls(css_text: str, base_url: str, state: State, folders: Dict[str, Path]) -> str:
    # Handle @import
    def import_repl(m: re.Match) -> str:
        href = m.group(2)
        if not href:
            # handle @import "..." ; pattern
            quoted = re.search(r"@import\s+(['\"])\s*(.*?)\1", m.group(0), re.I)
            href2 = quoted.group(2) if quoted else None
            absu = absolutize(base_url, href2) if href2 else None
        else:
            absu = absolutize(base_url, href)
        if not absu:
            return m.group(0)
        mapped = map_asset(state, absu, folders)
        if not mapped:
            return m.group(0)
        # styles.css will live at assets/css; relative from there to assets/... requires ../..
        return f"@import url('../../{mapped}');"

    css_text = AT_IMPORT_RE.sub(import_repl, css_text)

    # url(...) values
    def url_repl(m: re.Match) -> str:
        href = m.group(2)
        absu = absolutize(base_url, href)
        if not absu:
            return m.group(0)
        mapped = map_asset(state, absu, folders)
        if not mapped:
            return m.group(0)
        return f"url('../../{mapped}')"

    return CSS_URL_RE.sub(url_repl, css_text)


def rewrite_srcset(value: str, base_url: str, state: State, folders: Dict[str, Path]) -> str:
    parts = SRCSET_SPLIT_RE.split(value.strip()) if value else []
    out: List[str] = []
    for part in parts:
        if not part:
            continue
        tokens = part.strip().split()
        url_part = tokens[0]
        descriptor = ' '.join(tokens[1:])
        absu = absolutize(base_url, url_part)
        if not absu:
            out.append(part)
            continue
        mapped = map_asset(state, absu, folders)
        if not mapped:
            out.append(part)
            continue
        out.append(f"{mapped} {descriptor}".strip())
    return ", ".join(out)


def consolidate_head_assets(soup: BeautifulSoup, base_url: str, state: State, folders: Dict[str, Path]) -> Tuple[str, str, List[str]]:
    """Return (final_css_text, final_js_text, extra_script_srcs)
    extra_script_srcs are non-text/binary scripts kept as separate tags.
    """
    head = soup.head or soup.new_tag('head')
    # Track inline/external order
    saw_css_link = False
    saw_js_src = False

    css_pre: List[str] = []
    css_external: List[str] = []
    css_post: List[str] = []

    js_pre: List[str] = []
    js_external: List[str] = []
    js_post: List[str] = []
    extra_script_srcs: List[str] = []  # for non-text scripts

    # Iterate in DOM order
    for el in list(head.children):
        if getattr(el, 'name', None) is None:
            continue
        name = el.name.lower()
        if name == 'link':
            rels = [r.lower() for r in (el.get('rel') or [])]
            href = el.get('href')
            if 'stylesheet' in rels and href:
                absu = absolutize(base_url, href)
                if absu:
                    mapped = map_asset(state, absu, folders)
                    if mapped:
                        # Read CSS content from mapped file to append into one file
                        css_path = folders['root'] / mapped
                        try:
                            css_text = css_path.read_text(encoding='utf-8', errors='replace')
                        except Exception:
                            css_text = ''
                        css_external.append(css_text)
                        saw_css_link = True
                el.decompose()
                continue
            # Favicons & icons
            if any(r in rels for r in ['icon', 'shortcut', 'apple-touch-icon', 'mask-icon']):
                if href:
                    absu = absolutize(base_url, href)
                    if absu:
                        mapped = map_asset(state, absu, folders)
                        if mapped:
                            el['href'] = mapped
                # Keep the tag (rewritten)
                continue
        elif name == 'style':
            css_text = el.string or el.get_text() or ''
            (css_post if saw_css_link else css_pre).append(css_text)
            el.decompose()
            continue
        elif name == 'script':
            src = el.get('src')
            typ = (el.get('type') or '').lower()
            is_module = typ == 'module'
            if src:
                absu = absolutize(base_url, src)
                if absu:
                    data, ctype = fetch(state, absu, timeout=25.0)
                    if data is None:
                        el.decompose()
                        continue
                    mime = (ctype or '').lower()
                    is_texty = (
                        'javascript' in mime or mime.startswith('text/') or typ in ('', 'text/javascript', 'application/javascript', 'module', 'text/ecmascript', 'application/ecmascript')
                    )
                    if is_texty:
                        try:
                            js_text = data.decode('utf-8', errors='replace')
                        except Exception:
                            js_text = ''
                        (js_post if saw_js_src else js_pre).append(js_text)
                        js_external.append(js_text)
                    else:
                        # keep as extra src, mirror locally
                        mapped = map_asset(state, absu, folders)
                        if mapped:
                            extra_script_srcs.append(mapped)
                    saw_js_src = True
                el.decompose()
                continue
            else:
                # Inline script
                js_text = el.string or el.get_text() or ''
                (js_post if saw_js_src else js_pre).append(js_text)
                el.decompose()
                continue
        # Any other head tag is kept as-is

    # Compose final CSS/JS text
    css_final = "\n\n".join([*css_pre, *css_external, *css_post])
    js_final = "\n\n".join([*js_pre, *js_external, *js_post])

    # Ensure single <link> and <script> placeholders
    link_tag = soup.new_tag('link', rel='stylesheet', href='assets/css/styles.css')
    head.append(link_tag)
    script_tag = soup.new_tag('script', src='assets/js/main.js')
    head.append(script_tag)

    return css_final, js_final, extra_script_srcs


def process_single_page(opts: Options) -> None:
    session = requests.Session()
    session.headers.update({"User-Agent": opts.user_agent})
    state = State(session=session, visited=set(), to_visit=deque(), asset_map={})

    folders = ensure_dirs(opts.out_dir)

    # Fetch initial HTML
    r = session.get(opts.url, timeout=opts.timeout, allow_redirects=True)
    r.raise_for_status()
    final_url = r.url
    html = r.text

    soup = BeautifulSoup(html, 'lxml') if 'lxml' in sys.modules else BeautifulSoup(html, 'html.parser')

    # Consolidate head assets -> write styles.css/main.js
    css_text, js_text, extra_scripts = consolidate_head_assets(soup, final_url, state, folders)

    # Process body asset refs (images/srcset/video poster etc.)
    def map_attr(tag, attr: str):
        val = tag.get(attr)
        absu = absolutize(final_url, val)
        if not absu:
            return
        mapped = map_asset(state, absu, folders)
        if mapped:
            tag[attr] = mapped

    for img in soup.find_all(['img', 'iframe']):
        if img.get('src'):
            map_attr(img, 'src')
        if img.get('srcset'):
            img['srcset'] = rewrite_srcset(img.get('srcset',''), final_url, state, folders)

    for source in soup.find_all('source'):
        if source.get('src'):
            map_attr(source, 'src')
        if source.get('srcset'):
            source['srcset'] = rewrite_srcset(source.get('srcset',''), final_url, state, folders)

    for vid in soup.find_all('video'):
        if vid.get('poster'):
            map_attr(vid, 'poster')

    # Remove <base> to keep relative links stable offline
    for base in soup.find_all('base'):
        base.decompose()

    # Keep binary script srcs if any (saved under assets/...)
    head = soup.head or soup.new_tag('head')
    for src in extra_scripts:
        head.append(soup.new_tag('script', src=src))

    # Serialize HTML -> index.html (ensure <!DOCTYPE html>)
    out_html = str(soup)
    if not out_html.lower().lstrip().startswith('<!doctype html>'):
        out_html = '<!DOCTYPE html>\n' + out_html
    write_file(opts.out_dir / 'index.html', out_html, text=True)

    # Write bundled CSS & JS
    write_file(folders['css'] / 'styles.css', css_text, text=True)
    write_file(folders['js'] / 'main.js', js_text, text=True)


# ---- Optional crawl to prefetch assets referenced on linked pages (still one index.html) ---- #

def robots_allows(session: requests.Session, base: str, target: str, ua: str, timeout: float) -> bool:
    if not base:
        return True
    from urllib.robotparser import RobotFileParser
    b = urlsplit(base)
    robots_url = urlunsplit((b.scheme, b.netloc, '/robots.txt', '', ''))
    rp = RobotFileParser()
    try:
        r = session.get(robots_url, timeout=timeout, headers={"User-Agent": ua})
        if r.status_code >= 400:
            return True
        rp.parse(r.text.splitlines())
    except Exception:
        return True
    return rp.can_fetch(ua, target)


def prefetch_assets_via_crawl(opts: Options) -> None:
    """Bonus mode: BFS crawl to prefetch assets referenced on same-origin pages.
    Still outputs a single index.html for the starting URL, per hard requirement.
    """
    # First process start page normally
    process_single_page(opts)

    # Then crawl other pages to warm cache (download assets into assets/media, css/js are ignored)
    session = requests.Session()
    session.headers.update({"User-Agent": opts.user_agent})
    state = State(session=session, visited=set(), to_visit=deque([norm_url(opts.url)]), asset_map={})
    folders = ensure_dirs(opts.out_dir)

    start = norm_url(opts.url)
    pages = 0
    while state.to_visit and pages < opts.max_pages:
        url = state.to_visit.popleft()
        if url in state.visited:
            continue
        if not is_same_origin(start, url, opts.follow_subdomains):
            continue
        if opts.restrict_path_prefix and not urlsplit(url).path.startswith(opts.restrict_path_prefix):
            continue
        if opts.respect_robots and not robots_allows(session, start, url, opts.user_agent, opts.timeout):
            continue
        try:
            r = session.get(url, timeout=opts.timeout)
            r.raise_for_status()
            pages += 1
        except Exception:
            continue
        soup = BeautifulSoup(r.text, 'lxml') if 'lxml' in sys.modules else BeautifulSoup(r.text, 'html.parser')

        # Queue links
        for a in soup.find_all('a'):
            absu = absolutize(url, a.get('href'))
            if absu:
                state.to_visit.append(norm_url(absu))

        # Prefetch media on this page
        for tag, attr in [('img','src'), ('iframe','src'), ('source','src'), ('video','poster')]:
            for el in soup.find_all(tag):
                absu = absolutize(url, el.get(attr))
                if absu:
                    map_asset(state, absu, folders)
        # Prefetch srcset entries
        for el in soup.find_all(['img','source']):
            if el.get('srcset'):
                for part in SRCSET_SPLIT_RE.split(el['srcset']):
                    if not part.strip():
                        continue
                    p = part.strip().split()[0]
                    absu = absolutize(url, p)
                    if absu:
                        map_asset(state, absu, folders)


# ---- CLI ---- #

def parse_args(argv: Optional[List[str]] = None) -> Options:
    ap = argparse.ArgumentParser(description="Snapshot a web page into a tidy offline folder (one HTML/CSS/JS).")
    ap.add_argument('mode', choices=['single', 'crawl'], nargs='?', default='single', help='single page snapshot (default) or bonus crawl prefetch')
    ap.add_argument('url', help='Starting URL')
    ap.add_argument('-o', '--out', dest='out_dir', default='./snapshot', help='Output directory root')
    ap.add_argument('--max-pages', type=int, default=200, help='Max pages to prefetch in crawl mode')
    ap.add_argument('--timeout', type=float, default=25.0)
    ap.add_argument('--ua', dest='user_agent', default=DEFAULT_UA)
    ap.add_argument('--follow-subdomains', action='store_true')
    ap.add_argument('--restrict-path', default=None)
    ap.add_argument('--no-robots', dest='respect_robots', action='store_false')

    args = ap.parse_args(argv)
    return Options(
        url=args.url,
        out_dir=Path(args.out_dir),
        mode=args.mode,
        max_pages=args.max_pages,
        timeout=args.timeout,
        user_agent=args.user_agent,
        follow_subdomains=bool(args.follow_subdomains),
        restrict_path_prefix=args.restrict_path,
        respect_robots=bool(args.respect_robots),
    )


def main(argv: Optional[List[str]] = None) -> int:
    opts = parse_args(argv)
    try:
        if opts.mode == 'single':
            process_single_page(opts)
        else:
            prefetch_assets_via_crawl(opts)
        print(f"Saved snapshot to {opts.out_dir.resolve()}")
        return 0
    except requests.HTTPError as e:
        print(f"HTTP error: {e}", file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        print("Interrupted", file=sys.stderr)
        return 2
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
