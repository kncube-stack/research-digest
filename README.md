# Research Digest

Research Digest is a local web app that automatically scouts recent peer-reviewed papers and turns them into blog-style drafts (Substack-like) for your configured topic set.

## What it does

- Searches multiple sources each week:
  - Crossref
  - PubMed
  - Publisher RSS feeds (configurable)
  - Optional Unpaywall OA checks
- Filters to the configured `TIME_WINDOW_DAYS` and excludes likely preprints/non-peer-reviewed records.
- Defaults to human studies only (`HUMAN_STUDIES_ONLY=true`).
- Ranks papers using a transparent rubric:
  - Journal tier
  - Open access status
  - Topic-match strength
  - Study type priority
  - Recency/novelty
- Deduplicates across weeks by DOI (and title fallback for no-DOI items).
- Generates post drafts in strict JSON shape and serves them as a blog-style site.

## Quick start

1. Copy `config.example.json` to `config.json` and edit if needed.
2. (Optional, recommended) Set `UNPAYWALL_EMAIL` in `config.json` for better OA detection.
3. Run:

```bash
python3 app.py --config config.json --host 127.0.0.1 --port 8000
```

4. Open:

- `http://127.0.0.1:8000/` (web app)
- `http://127.0.0.1:8000/api/digest` (strict JSON array)

## CLI usage

- Force a new weekly generation before serving:

```bash
python3 app.py --config config.json --refresh-on-start
```

- Generate once and print JSON (no server):

```bash
python3 app.py --config config.json --once-json
```

## Data storage

- SQLite DB file defaults to `digest.db` in project root.
- Weekly runs are keyed by ISO week.
- Seen-paper dedupe is persisted in `seen_doi` / `seen_titles` tables.

## Config highlights

- `TOPICS`: append any new topics you want tracked.
- `MIN_PAPERS_PER_TOPIC`: best-effort coverage per topic.
- `MAX_PAPERS_PER_WEEK`: cap total posts.
- `OPEN_ACCESS_PRIORITY`: when true, OA papers are ranked higher.
- `HUMAN_STUDIES_ONLY`: when true, keeps only papers identified as human studies.
- `SUMMARY_MIN_WORDS` / `SUMMARY_MAX_WORDS`: control long-form article-style summary length.
- `RSS_FEEDS`: add/remove publisher feeds.

## Notes

- If no credible papers meet filters within the time window, output is `[]` for API and an empty-state card in UI.
- Summary text is generated from accessible metadata/abstract text only and explicitly avoids invented effect sizes or claims.

## Netlify deployment

This repo is now wired for Netlify static deployment via `netlify.toml`.

### Local static build test

```bash
python3 scripts/build_static_site.py --config config.json --db digest.db --out site --refresh
```

Preview local output:

- `site/index.html`
- `site/digest.json` (also served at `/api/digest` on Netlify via redirect)
- `site/post/<slug>/index.html`

### Deploy with Netlify CLI

1. Authenticate:

```bash
npx netlify status
# if not logged in:
npx netlify login
```

2. Link or create site:

```bash
npx netlify link
# or, if not yet created:
npx netlify init
```

3. Deploy preview:

```bash
npx netlify deploy
```

4. Deploy production:

```bash
npx netlify deploy --prod
```

### Config for deployed builds

- Add your real `config.json` to the repo (or inject config at build time) so Netlify builds with your topics and preferences.
- For stronger OA detection, set `UNPAYWALL_EMAIL` in your `config.json`.

## GitHub Pages (Netlify alternative)

This repo includes a weekly GitHub Pages workflow:

- Workflow file: `.github/workflows/deploy-pages.yml`
- Build output: `site/`
- JSON endpoint: `/digest.json` (and alias `/api/digest`)

### How it updates

- Runs weekly every Monday at 13:00 UTC.
- Can also be triggered manually from the Actions tab (`Publish Research Digest`).
- Also runs on pushes to `main`.

### Config used in GitHub Actions

- The workflow uses `config.json` if present.
- If `config.json` is absent, it falls back to `config.example.json`.

If you want your exact topics/settings live on GitHub Pages, update `config.example.json` in the repo (or add your own secure config flow).
