"""
CBS full-stats scraper

Fetches projection/stat tables for each position and writes a merged CSV
containing player, team, position, and all stat columns found (season totals).

Usage:
  python scrape_cbs_fullstats.py --url "https://www.cbssports.com/fantasy/football/stats/" --out cli\projections\cbs_fullstats.csv

Notes:
- Prefers season-total columns like 'fpts' over per-game 'fppg'.
- Normalizes headers to snake_case.
- Dependencies: requests, beautifulsoup4, pandas
"""
from __future__ import annotations
import argparse
import os
import re
from typing import List

import requests
from bs4 import BeautifulSoup
import pandas as pd

USER_AGENT = "RedTiger-DraftAssistant/1.0 (+https://github.com/mattwailes/RedTiger-DraftAssistant)"
DEFAULT_POSITIONS = ["QB", "RB", "WR", "TE", "K", "DEF"]


def fetch_html(url: str) -> str:
    resp = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=30)
    resp.raise_for_status()
    return resp.text


def normalize_col(col: str) -> str:
    col = str(col)
    # remove parentheses and extra whitespace
    col = re.sub(r"\s+", " ", col)
    col = col.strip()
    col = col.replace("%", "pct")
    # keep alphanumerics and spaces
    col = re.sub(r"[^A-Za-z0-9 ]", " ", col)
    col = col.strip().lower().replace(" ", "_")
    col = re.sub(r"_+", "_", col)
    if col == "":
        col = "col"
    return col


def table_rows_from_html(html: str, prefer_position: str = "") -> List[dict]:
    """Parse tables with BeautifulSoup, return list of row dicts keyed by normalized header names."""
    soup = BeautifulSoup(html, 'html.parser')
    tables = soup.find_all('table')
    out_rows = []
    for table in tables:
        # find header cells (bottom-most header row)
        thead = table.find('thead')
        if thead:
            header_trs = thead.find_all('tr')
            if header_trs:
                ths = header_trs[-1].find_all('th')
            else:
                ths = table.find_all('th')
        else:
            ths = []
            for tr in table.find_all('tr'):
                row_ths = tr.find_all('th')
                if row_ths:
                    ths = row_ths
        headers = [th.get_text(separator=' ').strip() for th in ths]
        if not headers:
            # try to infer headers from first row
            first_tr = table.find('tr')
            if first_tr:
                cells = first_tr.find_all(['th','td'])
                headers = [c.get_text(separator=' ').strip() for c in cells]
        if not headers:
            continue
        norm_headers = [normalize_col(h) for h in headers]
        if not any('player' in h or 'name' in h for h in norm_headers):
            # skip tables not looking like player lists
            continue
        # parse rows
        for tr in table.find_all('tr'):
            tds = tr.find_all('td')
            if not tds:
                continue
            cells = [td.get_text(separator=' ').strip() for td in tds]
            # if number of cells >= headers, map directly; otherwise try to handle merged player cell
            row = {}
            if len(cells) >= len(norm_headers):
                for i, h in enumerate(norm_headers):
                    row[h] = cells[i] if i < len(cells) else ''
            else:
                # assume first cell is player cell containing name/pos/team; remaining cells map to last headers
                player_cell = cells[0]
                tail_cells = cells[1:]
                # map last len(tail_cells) headers to tail_cells
                for i, val in enumerate(tail_cells):
                    h = norm_headers[i+1] if i+1 < len(norm_headers) else f'col_{i}'
                    row[h] = val
                row[norm_headers[0]] = player_cell
            # ensure position present
            if 'position' not in row or not row.get('position'):
                row['position'] = prefer_position
            row['position_filter'] = prefer_position
            out_rows.append(row)
    return out_rows


def pick_season_columns(df: pd.DataFrame) -> pd.DataFrame:
    # if 'fpts' exists, prefer that; keep 'fppg' too
    # nothing to change right now; return df
    return df


def rows_from_position(html: str, pos: str) -> pd.DataFrame:
    rows = table_rows_from_html(html, prefer_position=pos)
    if not rows:
        return pd.DataFrame()
    df = pd.DataFrame(rows)
    return df


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--url', default='https://www.cbssports.com/fantasy/football/stats/', help='Base CBS stats URL')
    ap.add_argument('--out', default='cli\\projections\\cbs_fullstats.csv', help='Output CSV path')
    ap.add_argument('--positions', nargs='*', default=DEFAULT_POSITIONS, help='Positions to fetch')
    args = ap.parse_args()

    base_html = fetch_html(args.url)
    positions = [p.upper() for p in args.positions]

    frames = []
    seen = set()
    for pos in positions:
        print(f'Fetching position {pos} ...')
        if '?' in args.url:
            pos_url = args.url + f'&position={pos.lower()}'
        else:
            pos_url = args.url + f'?position={pos.lower()}'
        try:
            html = fetch_html(pos_url)
        except Exception as e:
            print(f'Failed to fetch {pos_url}: {e}; using base page')
            html = base_html
        df = rows_from_position(html, pos)
        if df.empty:
            print(f'  no table found for {pos}')
            continue
        # normalize player/team/position columns
        if 'player' in df.columns:
            df['player_raw'] = df['player'].astype(str)
        else:
            df['player_raw'] = ''
        # extract a clean player name from the raw player cell
        def extract_player_name(s: str) -> str:
            parts = [p.strip() for p in re.split(r"[\n,]+", str(s)) if p.strip()]
            # prefer a part with at least one space (first + last) and not an uppercase team code
            candidate = ''
            for p in parts:
                if re.search(r"[A-Za-z]", p) and ' ' in p and not re.fullmatch(r"[A-Z]{1,3}", p):
                    if len(p) > len(candidate):
                        candidate = p
            if candidate:
                return candidate
            # fallback: first non-empty part
            return parts[0] if parts else ''
        df['player'] = df['player_raw'].apply(extract_player_name)

        # extract team from player_raw if not present
        if 'team' in df.columns and df['team'].notna().any():
            df['team'] = df['team'].astype(str).str.strip()
        else:
            def extract_team(s: str) -> str:
                m = re.search(r"\b([A-Z]{2,3})\b", str(s))
                return m.group(1) if m else ''
            df['team'] = df['player_raw'].apply(extract_team)

        # position
        if 'position' not in df.columns or df['position'].isnull().all():
            def extract_pos(s: str) -> str:
                m = re.search(r"\b(QB|RB|WR|TE|K|DEF)\b", str(s), re.I)
                return m.group(1).upper() if m else pos
            df['position'] = df['player_raw'].apply(extract_pos)
        else:
            df['position'] = df['position'].astype(str).str.strip().str.upper().replace({'nan': pos})

        # coerce numeric columns where possible
        for c in df.columns:
            if c in ('player', 'player_raw', 'team', 'position', 'position_filter'):
                continue
            # try to convert to numeric
            df[c] = pd.to_numeric(df[c].astype(str).str.replace(',', '').str.replace('%', ''), errors='coerce')
        # dedupe by player/team/position
        key_cols = ['player', 'team', 'position']
        df = df.drop_duplicates(subset=key_cols)
        frames.append(df)
    if not frames:
        print('No frames collected; exiting')
        return
    combined = pd.concat(frames, ignore_index=True, sort=False)
    # reorder columns: player, team, position, position_filter, then others
    cols = list(combined.columns)
    front = ['player', 'team', 'position', 'position_filter']
    rest = [c for c in cols if c not in front]
    ordered = front + rest
    combined = combined[ordered]
    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    combined.to_csv(args.out, index=False)
    print(f'Saved {len(combined)} rows with columns: {ordered} to {args.out}')


if __name__ == '__main__':
    main()
