# RedTiger Draft Assistant

Two tools for the same job — turning blended fantasy football projections
into a live, ranked "who should I pick next" recommendation.

- **[`cli/`](cli/)** — a terminal-based draft-day assistant. Point it at
  your league's roster settings and projection CSVs; it computes
  value-based-drafting (VBD) scores and, once Yahoo API access is set up,
  can auto-sync your live draft board so opponents' picks disappear from
  the pool automatically.

- **[`web/`](web/)** — a browser-based draft board (React + Vite) with the
  same VBD engine, plus tunable scoring rules (positional need, tier
  cliffs, bye week conflicts) and an optional AI "why this pick" advisor.

Start with whichever fits your draft: `cli/` if you want live Yahoo sync,
`web/` if you want a visual board you can run locally or deploy.

## Setup

Each tool has its own README with full setup steps:
- [`cli/README.md`](cli/README.md)
- [`web/README.md`](web/README.md)

## Secrets

Never commit `cli/oauth2.json` (your Yahoo Client ID/Secret) or a `.env`
file with an Anthropic API key — both are covered by `.gitignore`.
Templates are provided (`cli/oauth2.json.example`) so you know the shape
without the real values.
