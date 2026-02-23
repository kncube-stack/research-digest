from __future__ import annotations

import html
import json
import re
from datetime import datetime
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Dict, List
from urllib.parse import parse_qs, urlparse

from .config import AppConfig
from .pipeline import DigestPipeline
from .store import DigestStore, slugify


_BASE_PATH = ""


def set_base_path(path: str) -> None:
    """Set the URL prefix for all internal links (e.g. '/research-digest')."""
    global _BASE_PATH
    _BASE_PATH = path.rstrip("/")


def _bp(path: str) -> str:
    """Prepend the base path to an internal URL."""
    return f"{_BASE_PATH}{path}"


def _html_page(title: str, body: str) -> str:
    return f"""<!doctype html>
<html lang=\"en\">
<head>
  <meta charset=\"utf-8\" />
  <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\" />
  <title>{html.escape(title)}</title>
  <meta name=\"description\" content=\"A readable weekly digest of newly published research, tuned for clarity over jargon.\" />
  <link rel=\"stylesheet\" href=\"{_bp('/static/styles.css')}\" />
  <link rel=\"icon\" href=\"data:image/svg+xml,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 100 100'><text y='.9em' font-size='90'>🔬</text></svg>\" />
</head>
<body>
{body}
<footer class=\"site-footer\">
  Research Digest &middot; An automated weekly review of peer-reviewed science &middot; Not medical advice
</footer>
</body>
</html>
"""


def _escape(value: object) -> str:
    return html.escape(str(value or ""))


def _word_excerpt(text: str, max_words: int = 34) -> str:
    words = str(text or "").split()
    if len(words) <= max_words:
        return " ".join(words)
    return " ".join(words[:max_words]).rstrip(" ,;:") + "..."


def _render_bullet_block(text: str) -> str:
    lines = [line.strip() for line in (text or "").splitlines() if line.strip()]
    if not lines:
        return "<p>Not specified.</p>"
    items = "".join(f"<li>{_escape(line.lstrip('- ').strip())}</li>" for line in lines)
    return f"<ul>{items}</ul>"


def _render_post_card(post: Dict[str, object]) -> str:
    headline = _escape(post.get("headline") or post.get("title") or post.get("paper_title") or "")
    paper_title = _escape(post.get("paper_title"))
    deck = _escape(post.get("deck") or post.get("one_sentence_takeaway") or "")
    journal = _escape(post.get("journal"))
    pub_date = _escape(post.get("publication_date"))
    study_type = _escape(post.get("study_type"))
    oa = _escape(post.get("open_access_status"))
    doi = post.get("doi") or ""
    link = _escape(f"https://doi.org/{doi}" if doi else (post.get("best_link") or ""))
    slug = str(post.get("slug") or slugify(str(post.get("headline") or post.get("paper_title") or "post")))
    tags = post.get("tags") or post.get("topic_tags") or []
    tags_html = "".join(f"<span class=\"tag\">{_escape(tag)}</span>" for tag in tags)

    post_url = _bp(f"/post/{slug}")
    return f"""
    <article class=\"card\">
      <div class=\"tags\">{tags_html}</div>
      <h3><a href=\"{post_url}\">{headline}</a></h3>
      <p class=\"paper-title\">{paper_title}</p>
      <p class=\"meta\">{journal} &middot; {pub_date} &middot; {study_type} &middot; {oa}</p>
      <p class=\"dek\">{deck}</p>
      <p class=\"actions\"><a href=\"{post_url}\">Read story &rarr;</a> <span class=\"dot\">&middot;</span> <a href=\"{link}\" target=\"_blank\" rel=\"noopener\">Open paper</a></p>
    </article>
    """


def _render_home(posts: List[Dict[str, object]], week_key: str) -> str:
    generated = datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")
    stats = {
        "count": len(posts),
        "oa": sum(1 for p in posts if p.get("open_access_status") == "OPEN_ACCESS"),
        "paywalled": sum(1 for p in posts if p.get("open_access_status") == "PAYWALLED"),
    }

    featured_html = ""
    grid_html = ""
    remainder_count = 0

    if posts:
        featured = posts[0]
        slug = str(featured.get("slug") or slugify(str(featured.get("headline") or featured.get("paper_title") or "post")))
        feat_url = _bp(f"/post/{slug}")
        tags = featured.get("tags") or featured.get("topic_tags") or []
        tags_html = "".join(f"<span class=\"tag\">{_escape(tag)}</span>" for tag in tags)
        feat_doi = featured.get("doi") or ""
        feat_link = f"https://doi.org/{feat_doi}" if feat_doi else (featured.get("best_link") or "")
        feat_deck = _word_excerpt(str(featured.get("deck") or featured.get("summary") or ""), 60)

        featured_html = f"""
        <section class=\"feature-wrap\">
          <article class=\"feature-card\">
            <p class=\"feature-kicker\">Featured this week</p>
            <div class=\"tags\">{tags_html}</div>
            <h2><a href=\"{feat_url}\">{_escape(featured.get('headline') or featured.get('title') or '')}</a></h2>
            <p class=\"paper-title\">{_escape(featured.get('paper_title'))}</p>
            <p class=\"meta\">{_escape(featured.get('journal'))} &middot; {_escape(featured.get('publication_date'))} &middot; {_escape(featured.get('study_type'))}</p>
            <p class=\"feature-summary\">{_escape(feat_deck)}</p>
            <p class=\"actions\"><a href=\"{feat_url}\">Read full story &rarr;</a> <span class=\"dot\">&middot;</span> <a href=\"{_escape(feat_link)}\" target=\"_blank\" rel=\"noopener\">Open paper</a></p>
          </article>
        </section>
        """

        remainder = posts[1:]
        remainder_count = len(remainder)
        if remainder:
            grid_html = "".join(_render_post_card(post) for post in remainder)
        else:
            grid_html = ""
    else:
        featured_html = """
        <section class=\"feature-wrap\">
          <article class=\"feature-card empty\">
            <p class=\"feature-kicker\">This week&#39;s issue</p>
            <h2>No qualifying papers this week</h2>
            <p class=\"feature-summary\">The digest searched configured sources but found no new peer-reviewed papers that met your current filters. Check back next week or try adjusting your topics.</p>
          </article>
        </section>
        """

    grid_section = ""
    if grid_html:
        grid_section = f"""
        <div class=\"section-label\">More stories <span class=\"count\">{remainder_count}</span></div>
        <section class=\"cards-grid\">{grid_html}</section>
        """

    body = f"""
    <header class=\"mast\">
      <div class=\"mast-inner\">
        <div class=\"nameplate\">
          <div class=\"nameplate-icon\">RD</div>
          <div class=\"nameplate-text\">Research Digest</div>
        </div>
        <p class=\"eyebrow\">Weekly Edition</p>
        <h1>Science Summary</h1>
        <p class=\"subtitle\">A digest of newly published papers across Nutrition and Psychology.</p>
        <div class=\"toolbar\">
          <span class=\"week\">{_escape(week_key)}</span>
          <a class=\"btn\" href=\"{_bp('/refresh')}\">Refresh issue</a>
          <a class=\"btn ghost\" href=\"{_bp('/digest.json')}\">JSON feed</a>
        </div>
        <div class=\"stats\">
          <span>{stats['count']} stories</span>
          <span>{stats['oa']} open access</span>
          <span>{stats['paywalled']} paywalled</span>
        </div>
        <p class=\"stamp\">Generated {generated}</p>
      </div>
    </header>

    <main class=\"container\">
      {featured_html}
      {grid_section}
    </main>
    """
    return _html_page("Research Digest", body)


def _render_glance_table(glance_text: str) -> str:
    """Render the study-at-a-glance markdown-ish block as an HTML table."""
    if not glance_text:
        return "<p>Not available.</p>"
    rows = ""
    for line in glance_text.strip().splitlines():
        line = line.strip()
        if not line:
            continue
        # Strip **label:** formatting
        m = re.match(r"\*\*(.+?):\*\*\s*(.*)", line)
        if m:
            label = html.escape(m.group(1))
            value = html.escape(m.group(2))
            rows += f"<tr><th>{label}</th><td>{value}</td></tr>"
        else:
            rows += f"<tr><td colspan=\"2\">{html.escape(line)}</td></tr>"
    return f"<table class=\"glance-table\">{rows}</table>"


def _render_post(post: Dict[str, object]) -> str:
    headline = _escape(post.get("headline") or post.get("title") or post.get("paper_title") or "")
    paper_title = _escape(post.get("paper_title"))
    authors = _escape(post.get("authors"))
    journal = _escape(post.get("journal"))
    pub_date = _escape(post.get("publication_date"))
    study_type = _escape(post.get("study_type"))
    oa = _escape(post.get("open_access_status"))
    doi_raw = post.get("doi") or ""
    doi = _escape(doi_raw)
    best_link = _escape(f"https://doi.org/{doi_raw}" if doi_raw else (post.get("best_link") or ""))
    tags = post.get("tags") or post.get("topic_tags") or []
    tags_html = "".join(f"<span class=\"tag\">{_escape(tag)}</span>" for tag in tags)

    deck = _escape(post.get("deck") or post.get("one_sentence_takeaway") or "")
    glance_html = _render_glance_table(str(post.get("study_at_a_glance") or ""))
    what_did = _escape(post.get("what_they_did") or post.get("summary") or "")
    what_found = _escape(post.get("what_they_found") or "")
    why = _render_bullet_block(str(post.get("why_it_matters") or ""))
    caveats = _render_bullet_block(str(post.get("caveats_and_alternative_explanations") or post.get("limitations_and_caveats") or ""))
    read_paper = _escape(post.get("read_the_paper") or "")

    extra = post.get("extra_links") or {}
    links = []
    for key in ("publisher", "pdf", "pubmed", "pmc"):
        value = extra.get(key)
        if value:
            label = key.upper() if key in ("pdf", "pmc") else key.capitalize()
            links.append(
                f"<li><strong>{_escape(label)}:</strong> <a href=\"{_escape(value)}\" target=\"_blank\" rel=\"noopener\">{_escape(value)}</a></li>"
            )
    links_html = "".join(links) if links else "<li>No additional links available.</li>"

    oa_display = oa.replace("_", " ").title() if oa else "Unknown"

    body = f"""
    <header class=\"mast slim\">
      <div class=\"mast-inner\">
        <div class=\"nameplate\">
          <div class=\"nameplate-icon\">RD</div>
          <div class=\"nameplate-text\">Science Summary</div>
        </div>
        <p class=\"eyebrow\">Story</p>
        <h1>{headline}</h1>
        <p class=\"subtitle\">{paper_title}</p>
        <div class=\"tags\">{tags_html}</div>
        <div class=\"toolbar\">
          <a class=\"btn\" href=\"{_bp('/')}\">&larr; Back to issue</a>
          <a class=\"btn ghost\" href=\"{best_link}\" target=\"_blank\" rel=\"noopener\">Open paper</a>
        </div>
      </div>
    </header>

    <main class=\"container post-layout\">
      <article class=\"post-main\">
        <section class=\"post-block pullquote\">
          <h2>Deck</h2>
          <p>{deck}</p>
        </section>

        <section class=\"post-block\">
          <h2>Study at a glance</h2>
          {glance_html}
        </section>

        <section class=\"post-block\">
          <h2>What they did</h2>
          <p class=\"story-text\">{what_did}</p>
        </section>

        <section class=\"post-block\">
          <h2>What they found</h2>
          <p>{what_found}</p>
        </section>

        <section class=\"post-block\">
          <h2>Why it matters</h2>
          {why}
        </section>

        <section class=\"post-block\">
          <h2>Caveats &amp; alternative explanations</h2>
          {caveats}
        </section>

        <section class=\"post-block\">
          <h2>Read the paper</h2>
          <p style=\"font-family:var(--font-ui);font-size:0.9rem;white-space:pre-line\">{read_paper}</p>
        </section>
      </article>

      <aside class=\"post-side\">
        <section class=\"post-block\">
          <h2>Paper details</h2>
          <p><strong>Authors:</strong> {authors}</p>
          <p><strong>Journal:</strong> {journal}</p>
          <p><strong>Published:</strong> {pub_date}</p>
          <p><strong>Study type:</strong> {study_type}</p>
          <p><strong>Access:</strong> {oa_display}</p>
          <p><strong>DOI:</strong> {doi or 'N/A'}</p>
        </section>

        <section class=\"post-block\">
          <h2>Links</h2>
          <ul>{links_html}</ul>
        </section>
      </aside>
    </main>
    """
    return _html_page(str(post.get("headline") or post.get("title") or "Science Summary"), body)


def create_handler(config: AppConfig, store: DigestStore, pipeline: DigestPipeline):
    static_dir = Path(__file__).resolve().parent / "static"

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802
            parsed = urlparse(self.path)
            path = parsed.path

            if path == "/static/styles.css":
                self._serve_css(static_dir / "styles.css")
                return

            if path in ("/api/digest", "/digest.json"):
                params = parse_qs(parsed.query)
                refresh = params.get("refresh", ["0"])[0] == "1"
                self._serve_digest_json(refresh=refresh)
                return

            if path == "/refresh":
                self._refresh_and_redirect()
                return

            if path.startswith("/post/"):
                slug = path.split("/post/", 1)[1].strip("/")
                if not slug:
                    self._not_found()
                    return
                self._serve_post(slug)
                return

            if path == "/health":
                self._send_text("ok", status=HTTPStatus.OK)
                return

            if path == "/":
                self._serve_home()
                return

            self._not_found()

        def log_message(self, format: str, *args) -> None:  # noqa: A003
            return

        def _serve_home(self) -> None:
            try:
                posts = pipeline.ensure_weekly_digest()
            except Exception:
                posts = store.get_latest_digest() or []
            week = pipeline.week_key()
            html_out = _render_home(posts, week)
            self._send_html(html_out)

        def _serve_post(self, slug: str) -> None:
            post = store.get_post_by_slug(slug)
            if not post:
                try:
                    pipeline.ensure_weekly_digest()
                except Exception:
                    pass
                post = store.get_post_by_slug(slug)
            if not post:
                self._not_found()
                return
            self._send_html(_render_post(post))

        def _serve_digest_json(self, refresh: bool) -> None:
            try:
                posts = pipeline.ensure_weekly_digest(force=refresh)
            except Exception:
                posts = store.get_latest_digest() or []

            body = json.dumps(posts, ensure_ascii=False, indent=2)
            encoded = body.encode("utf-8")
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(encoded)))
            self.end_headers()
            self.wfile.write(encoded)

        def _refresh_and_redirect(self) -> None:
            try:
                pipeline.ensure_weekly_digest(force=True)
            except Exception:
                pass
            self.send_response(HTTPStatus.SEE_OTHER)
            self.send_header("Location", "/")
            self.end_headers()

        def _serve_css(self, path: Path) -> None:
            if not path.exists():
                self._not_found()
                return
            css = path.read_text(encoding="utf-8")
            encoded = css.encode("utf-8")
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", "text/css; charset=utf-8")
            self.send_header("Content-Length", str(len(encoded)))
            self.end_headers()
            self.wfile.write(encoded)

        def _send_html(self, body: str, status: HTTPStatus = HTTPStatus.OK) -> None:
            encoded = body.encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(encoded)))
            self.end_headers()
            self.wfile.write(encoded)

        def _send_text(self, body: str, status: HTTPStatus = HTTPStatus.OK) -> None:
            encoded = body.encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.send_header("Content-Length", str(len(encoded)))
            self.end_headers()
            self.wfile.write(encoded)

        def _not_found(self) -> None:
            body = """
            <header class="mast slim">
              <div class="mast-inner">
                <div class="nameplate">
                  <div class="nameplate-icon">RD</div>
                  <div class="nameplate-text">Research Digest</div>
                </div>
                <p class="eyebrow">Error</p>
                <h1>Page not found</h1>
                <p class="subtitle">The story you&#39;re looking for doesn&#39;t exist or may have moved.</p>
                <div class="toolbar">
                  <a class="btn" href="{_bp('/')}">&larr; Back to issue</a>
                </div>
              </div>
            </header>
            """
            self._send_html(
                _html_page("Not found — Research Digest", body),
                status=HTTPStatus.NOT_FOUND,
            )

    return Handler


def run_server(
    config: AppConfig,
    store: DigestStore,
    pipeline: DigestPipeline,
    host: str = "127.0.0.1",
    port: int = 8000,
) -> None:
    handler_cls = create_handler(config=config, store=store, pipeline=pipeline)
    server = ThreadingHTTPServer((host, port), handler_cls)
    print(f"Research Digest running at http://{host}:{port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
