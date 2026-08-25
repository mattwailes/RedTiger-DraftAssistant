# Fantasy Football Draft Assistant

A local draft-day tool that blends multiple projection sources into one
ranking, computes Value-Based Drafting (VBD) scores against your league's
actual roster/replacement levels, and optionally syncs live picks from
Yahoo so drafted players auto-disappear from your board.

## Quick start (works today, no Yahoo needed)

```bash
pip install -r requirements.txt
python draft_assistant.py
```

Sample projection files are in `projections/*.sample.csv` so you can try it
immediately. Copy them to `projections/fantasypros.csv` and `espn.csv` (real
filenames, no `.sample`) with real full-season exports before your draft —
those real files are gitignored so you never accidentally commit projection
data you don't have redistribution rights to.

## Getting real projection CSVs

The assistant expects each source as `projections/<source>.csv` with columns:

```
player,team,position,proj_points
```

- **FantasyPros**: My Rankings / Projections page → Export to CSV. Rename
  columns to match the format above (usually just a header rename).
- **ESPN**: Fantasy Football → Players → Projections tab → export/copy into
  a CSV in this format.
- **Yahoo**: Fantasy Football → Research → Players → Projections; same deal.
- **Your own source**: any CSV in this shape works — add its name and
  weight to `SOURCE_WEIGHTS` in `config.py`.

Missing a source on draft day? No problem — the assistant automatically
skips missing files and rescales the remaining weights, and even
individual missing players (present in one source but not another) are
handled by coverage-weighted averaging rather than penalized.

## Configure your league

Edit `config.py`:
- `NUM_TEAMS`, `YOUR_DRAFT_SLOT`, `SCORING`
- `ROSTER_SPOTS` — must match your league's actual starting lineup; this
  directly drives the replacement-level baseline math
- `SOURCE_WEIGHTS` — how much to trust each projection source

## Using it live

At each `>` prompt:

| Command | Effect |
|---|---|
| *(enter)* | Show top available players, overall and by position |
| `take <name>` | Mark a player drafted by anyone (removes from pool) |
| `me <name>` | Mark a player drafted **by you** (removes + adds to your roster) |
| `roster` | Show your roster and filled position counts |
| `sync` | Pull the latest picks from Yahoo's live draft board (see below) |
| `quit` | Exit |

Player name matching is fuzzy (`take mccaffrey` will find "Christian
McCaffrey"), so you don't need exact spelling mid-draft.

The "need-adjusted VBD" column nudges recommendations toward positions
you still need starters at, without ever fully hiding pure value — it's a
~15% boost/discount, not a hard filter, so you stay in control.

## Yahoo live sync (optional)

This connects the assistant directly to your live Yahoo draft board so
picks by other managers auto-remove from your pool — you won't need to
manually track anyone else's picks.

1. **Apply for Yahoo Fantasy Sports API access**: as of mid-2026 Yahoo
   moved to an application-review process (a few days' lead time, not
   instant). Apply at https://sports.yahoo.com/developer/access/ and be
   specific in the use-case field — e.g. "personal fantasy football draft
   tool, read-only access to my own league(s)."
2. Once approved, create an app at https://developer.yahoo.com/apps/create/
   and save the credentials into `oauth2.json` in this folder:
   ```json
   {"consumer_key": "YOUR_CLIENT_ID", "consumer_secret": "YOUR_CLIENT_SECRET"}
   ```
3. `pip install yahoo_fantasy_api yahoo_oauth`
4. Run `sync` from the assistant during your draft — first call opens a
   browser to authorize, then caches a token so future runs don't
   re-prompt.

If you skip this setup entirely, the assistant still works fine — just use
`take <name>` to log every pick manually as it happens.

## Files

| File | Purpose |
|---|---|
| `config.py` | League settings, roster spots, source weights |
| `projections.py` | CSV loading, blending, VBD calculation, fuzzy player search |
| `yahoo_client.py` | Optional Yahoo OAuth + live draft board polling |
| `draft_assistant.py` | Main interactive CLI — run this on draft day |
| `projections/*.csv` | Drop your exported projection files here |

## Ideas for next steps

- Add a `tier` column (cluster players by VBD gaps) so you can see when a
  positional cliff is coming
- Auto-adjust `SOURCE_WEIGHTS` based on each source's historical accuracy
- Track opponents' roster construction to flag when a run on a position
  is likely
