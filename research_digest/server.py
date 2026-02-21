from __future__ import annotations

import html
import json
from datetime import datetime
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Dict, List
from urllib.parse import parse_qs, urlparse

from .config import AppConfig
from .pipeline import DigestPipeline
from .store import DigestStore, slugify


def _html_page(title: str, body: str) -> str:
    return f"""<!doctype html>
<html lang=\"en\">
<head>
  <meta charset=\"utf-8\" />
  <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\" />
  <title>{html.escape(title)}</title>
  <link rel=\"stylesheet\" href=\"/static/styles.css\" />
</head>
<body>
{body}
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
    post_title = _escape(post.get("title"))
    paper_title = _escape(post.get("paper_title"))
    takeaway = _escape(post.get("one_sentence_takeaway"))
    journal = _escape(post.get("journal"))
    pub_date = _escape(post.get("publication_date"))
    study_type = _escape(post.get("study_type"))
    oa = _escape(post.get("open_access_status"))
    link = _escape(post.get("best_link"))
    slug = str(post.get("slug") or slugify(str(post.get("title") or post.get("paper_title") or "post")))
    tags = post.get("topic_tags") or []
    tags_html = "".join(f"<span class=\"tag\">{_escape(tag)}</span>" for tag in tags)

    return f"""
    <article class=\"card\">
      <div class=\"tags\">{tags_html}</div>
      <h3><a href=\"/post/{slug}\">{post_title}</a></h3>
      <p class=\"paper-title\">{paper_title}</p>
      <p class=\"meta\">{journal} | {pub_date} | {study_type} | {oa}</p>
      <p class=\"dek\">{takeaway}</p>
      <p class=\"actions\"><a href=\"/post/{slug}\">Read story</a> <span class=\"dot\">|</span> <a href=\"{link}\" target=\"_blank\" rel=\"noopener\">Open paper</a></p>
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

    if posts:
        featured = posts[0]
        slug = str(featured.get("slug") or slugify(str(featured.get("title") or featured.get("paper_title") or "post")))
        tags = featured.get("topic_tags") or []
        tags_html = "".join(f"<span class=\"tag\">{_escape(tag)}</span>" for tag in tags)

        featured_html = f"""
        <section class=\"feature-wrap\">
          <article class=\"feature-card\">
            <p class=\"feature-kicker\">Featured this week</p>
            <div class=\"tags\">{tags_html}</div>
            <h2><a href=\"/post/{slug}\">{_escape(featured.get('title'))}</a></h2>
            <p class=\"paper-title\">{_escape(featured.get('paper_title'))}</p>
            <p class=\"meta\">{_escape(featured.get('journal'))} | {_escape(featured.get('publication_date'))} | {_escape(featured.get('study_type'))}</p>
            <p class=\"feature-summary\">{_escape(_word_excerpt(str(featured.get('summary') or ''), 60))}</p>
            <p class=\"actions\"><a href=\"/post/{slug}\">Read full story</a> <span class=\"dot\">|</span> <a href=\"{_escape(featured.get('best_link'))}\" target=\"_blank\" rel=\"noopener\">Open paper</a></p>
          </article>
        </section>
        """

        remainder = posts[1:]
        if remainder:
            grid_html = "".join(_render_post_card(post) for post in remainder)
        else:
            grid_html = ""
    else:
        featured_html = """
        <section class=\"feature-wrap\">
          <article class=\"feature-card empty\">
            <p class=\"feature-kicker\">Featured this week</p>
            <h2>No qualifying papers this week</h2>
            <p class=\"feature-summary\">The app searched configured sources but found no new peer-reviewed papers that met your current filters.</p>
          </article>
        </section>
        """

    body = f"""
    <header class=\"mast\">
      <div class=\"mast-inner\">
        <p class=\"eyebrow\">Research Digest</p>
        <h1>Your Weekly Science Magazine</h1>
        <p class=\"subtitle\">A readable digest of newly published papers across your chosen topics, tuned for clarity over jargon.</p>
        <div class=\"toolbar\">
          <span class=\"week\">{_escape(week_key)}</span>
          <a class=\"btn\" href=\"/refresh\">Refresh issue</a>
          <a class=\"btn ghost\" href=\"/digest.json\">JSON API</a>
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
      {f'<section class="cards-grid">{grid_html}</section>' if grid_html else ''}
    </main>
    """
    return _html_page("Research Digest", body)


def _render_post(post: Dict[str, object]) -> str:
    title = _escape(post.get("title"))
    paper_title = _escape(post.get("paper_title"))
    authors = _escape(post.get("authors"))
    journal = _escape(post.get("journal"))
    pub_date = _escape(post.get("publication_date"))
    study_type = _escape(post.get("study_type"))
    takeaway = _escape(post.get("one_sentence_takeaway"))
    summary = _escape(post.get("summary"))
    oa = _escape(post.get("open_access_status"))
    best_link = _escape(post.get("best_link"))
    doi = _escape(post.get("doi"))
    tags = post.get("topic_tags") or []
    tags_html = "".join(f"<span class=\"tag\">{_escape(tag)}</span>" for tag in tags)

    why = _render_bullet_block(str(post.get("why_it_matters") or ""))
    limits = _render_bullet_block(str(post.get("limitations_and_caveats") or ""))

    extra = post.get("extra_links") or {}
    links = []
    for key in ("publisher", "pdf", "pubmed", "pmc"):
        value = extra.get(key)
        if value:
            links.append(
                f"<li><strong>{_escape(key)}:</strong> <a href=\"{_escape(value)}\" target=\"_blank\" rel=\"noopener\">{_escape(value)}</a></li>"
            )
    links_html = "".join(links) if links else "<li>No additional links available.</li>"

    body = f"""
    <header class=\"mast slim\">
      <div class=\"mast-inner\">
        <p class=\"eyebrow\">Story</p>
        <h1>{title}</h1>
        <p class=\"subtitle\">{paper_title}</p>
        <div class=\"tags\">{tags_html}</div>
        <div class=\"toolbar\">
          <a class=\"btn\" href=\"/\">Back to issue</a>
          <a class=\"btn ghost\" href=\"{best_link}\" target=\"_blank\" rel=\"noopener\">Open paper</a>
        </div>
      </div>
    </header>

    <main class=\"container post-layout\">
      <article class=\"post-main\">
        <section class=\"post-block pullquote\">
          <h2>The takeaway</h2>
          <p>{takeaway}</p>
        </section>

        <section class=\"post-block\">
          <h2>The story</h2>
          <p class=\"story-text\">{summary}</p>
        </section>

        <section class=\"post-block\">
          <h2>Why this matters</h2>
          {why}
        </section>

        <section class=\"post-block\">
          <h2>What to keep in mind</h2>
          {limits}
        </section>
      </article>

      <aside class=\"post-side\">
        <section class=\"post-block\">
          <h2>Paper details</h2>
          <p><strong>Authors:</strong> {authors}</p>
          <p><strong>Journal:</strong> {journal}</p>
          <p><strong>Date:</strong> {pub_date}</p>
          <p><strong>Study type:</strong> {study_type}</p>
          <p><strong>Access:</strong> {oa}</p>
          <p><strong>DOI:</strong> {doi or 'N/A'}</p>
        </section>

        <section class=\"post-block\">
          <h2>Links</h2>
          <ul>{links_html}</ul>
        </section>
      </aside>
    </main>
    """
    return _html_page(str(post.get("title") or "Research Digest Post"), body)


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
            self._send_html(
                _html_page("Not found", "<main class='container'><h1>404</h1><p>Page not found.</p></main>"),
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
