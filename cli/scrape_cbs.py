"""
Simple CBS projections scraper

Usage:
  python scrape_cbs.py --url "https://www.cbssports.com/fantasy/football/stats/" --out cli\projections\cbs.csv

The script finds the most-likely projections table on the page by matching header
names (player/name and points/proj/fpts) and writes a CSV with columns:
  player,team,position,proj_points

This is intentionally defensive: CBS HTML can change, so the parser tries a few
header-name heuristics. If it fails, save the page and re-run with --html <file>.

Dependencies: requests, beautifulsoup4, pandas
"""

from __future__ import annotations
import argparse
import os
import re
from typing import List, Dict, Optional

import requests
from bs4 import BeautifulSoup
import pandas as pd

USER_AGENT = "RedTiger-DraftAssistant/1.0 (+https://github.com/mattwailes/RedTiger-DraftAssistant)"

# Header normalized names mapping heuristics
PLAYER_ALIASES = {"player", "name", "player/team"}
TEAM_ALIASES = {"team", "tm"}
POSITION_ALIASES = {"pos", "position"}
POINTS_ALIASES = {"fpts", "fppg", "fantasy points", "projected", "proj", "fantasy points (ppr)", "projected points"}


def fetch_html(url: str) -> str:
    resp = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=30)
    resp.raise_for_status()
    return resp.text


def normalize_header(h: str) -> str:
    return re.sub(r"[^a-z0-9]", "", h.lower())


def find_table_with_projections(soup: BeautifulSoup) -> Optional[BeautifulSoup]:
    tables = soup.find_all("table")
    best = None
    best_score = 0
    for table in tables:
        ths = table.find_all("th")
        headers = [normalize_header(th.get_text(separator=" ")) for th in ths]
        score = 0
        if any("player" in h or "name" in h for h in headers):
            score += 2
        if any(any(alias.replace(" ", "") in h for alias in POINTS_ALIASES) for h in headers):
            score += 2
        if any(any(alias in h for alias in POSITION_ALIASES) for h in headers):
            score += 1
        # debug: show headers and score
        if headers:
            print(f"inspect: table headers: {headers} score={score}")
        if score > best_score:
            best_score = score
            best = table
    # require at least player+points signal
    if best_score >= 3:
        return best
    return None


def extract_from_table(table: BeautifulSoup) -> List[Dict[str, str]]:
    # Build header map
    # Prefer the bottom-most header row (leaf headers) so indices align with data cells
    thead = table.find('thead')
    if thead:
        header_trs = thead.find_all('tr')
        if header_trs:
            ths = header_trs[-1].find_all('th')
        else:
            ths = table.find_all('th')
    else:
        # fallback: use the last table row that contains th elements
        ths = []
        for tr in table.find_all('tr'):
            row_ths = tr.find_all('th')
            if row_ths:
                ths = row_ths
    headers = [th.get_text(separator=" ").strip() for th in ths]
    norm_headers = [normalize_header(h) for h in headers]

    # debug
    if headers:
        print(f"extract_from_table: headers = {headers}")
        print(f"extract_from_table: norm_headers = {norm_headers}")

    # heuristics: find index for player/team/pos/points
    idx_player = None
    idx_team = None
    idx_pos = None
    idx_points = None

    for i, h in enumerate(norm_headers):
        if any(a.replace(" ", "") in h for a in PLAYER_ALIASES) and idx_player is None:
            idx_player = i
        if any(a in h for a in TEAM_ALIASES) and idx_team is None:
            idx_team = i
        if any(a in h for a in POSITION_ALIASES) and idx_pos is None:
            idx_pos = i
        if any(a.replace(" ", "") in h for a in POINTS_ALIASES) and idx_points is None:
            idx_points = i

    print(f"field index guess: idx_player={idx_player}, idx_team={idx_team}, idx_pos={idx_pos}, idx_points={idx_points}")

    rows = []
    row_count = 0
    for tr in table.find_all("tr"):
        tds = tr.find_all(["td"])
        if not tds:
            continue
        cells = [td.get_text(separator=" ").strip() for td in tds]
        # debug first few rows
        if row_count < 3:
            print(f"row[{row_count}] cells = {cells}")
        row_count += 1
        # skip rows that look like summaries
        if idx_player is None or idx_points is None:
            continue
        try:
            player_raw = cells[idx_player]
        except IndexError:
            continue

        # player cell on CBS often contains multiple newline/comma-separated parts
        parts = [p.strip() for p in re.split(r"[\n,]+", player_raw) if p.strip()]
        player_name = ""
        # pick the best candidate: prefer a part with two words (First Last) that isn't an uppercase team code
        for p in parts:
            if re.search(r"[A-Za-z]", p) and " " in p and not re.fullmatch(r"[A-Z]{1,3}", p):
                if len(p) > len(player_name):
                    player_name = p
        if not player_name and parts:
            player_name = parts[0]
        # team is likely a 2-3 letter uppercase code in parts or in a separate column
        for p in parts[::-1]:
            if re.fullmatch(r"[A-Z]{2,3}", p):
                team = p
                break
        # pos like QB/RB/WR/TE
        mpos = re.search(r"\b(QB|RB|WR|TE|K|DEF)\b", player_raw, re.I)
        if mpos:
            pos = mpos.group(1).upper()

        if idx_team is not None and idx_team < len(cells):
            if not team:
                team = cells[idx_team]
        if idx_pos is not None and idx_pos < len(cells):
            if not pos:
                pos = cells[idx_pos]

        # points
        pts = ""
        if idx_points is not None and idx_points < len(cells):
            pts = cells[idx_points]
        # strip non-numeric except dot and minus
        pts_norm = re.sub(r"[^0-9.\-]", "", pts)
        try:
            pts_val = float(pts_norm) if pts_norm else 0.0
        except ValueError:
            pts_val = 0.0

        rows.append({
            "player": player_name,
            "team": team,
            "position": pos.upper() if pos else "",
            "proj_points": pts_val,
        })
    return rows


def save_csv(rows: List[Dict[str, str]], out_path: str) -> None:
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    df = pd.DataFrame(rows)
    # Ensure columns exist
    for c in ["player", "team", "position", "proj_points"]:
        if c not in df.columns:
            df[c] = ""
    df = df[["player", "team", "position", "proj_points"]]
    df.to_csv(out_path, index=False)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", help="CBS projections page URL", default="https://www.cbssports.com/fantasy/football/stats/")
    ap.add_argument("--html", help="Optional: path to local HTML file to parse instead of fetching URL")
    ap.add_argument("--out", help="Output CSV path", default="cli\\projections\\cbs.csv")
    args = ap.parse_args()

    if args.html:
        with open(args.html, "r", encoding="utf-8") as f:
            html = f.read()
    else:
        print(f"Fetching {args.url} ...")
        html = fetch_html(args.url)

    soup = BeautifulSoup(html, "html.parser")
    table = find_table_with_projections(soup)
    if not table:
        print("Warning: couldn't confidently find projections table by header heuristics.")
        # First fallback: try pandas.read_html which can handle complex tables
        try:
            dfs = pd.read_html(html)
        except Exception:
            dfs = []
        print(f"pandas.read_html found {len(dfs)} tables")
        for i, df in enumerate(dfs):
            cols = [str(c).strip().lower() for c in df.columns.astype(str)]
            print(f"  table[{i}] cols: {cols}")
            try:
                print(df.head(3).to_string())
            except Exception:
                pass
            if not any(("player" in c or "name" in c) for c in cols):
                continue
            if not any(("pts" in c or "fpts" in c or "points" in c or "proj" in c) for c in cols):
                continue
            # map likely columns
            col_map = {}
            for i, c in enumerate(cols):
                if ("player" in c or "name" in c) and "player" not in col_map:
                    col_map["player"] = df.columns[i]
                if ("team" in c or c == "tm") and "team" not in col_map:
                    col_map["team"] = df.columns[i]
                if ("pos" in c or "position" in c) and "position" not in col_map:
                    col_map["position"] = df.columns[i]
                if ("fpts" in c or "pts" in c or "points" in c or "proj" in c) and "proj_points" not in col_map:
                    col_map["proj_points"] = df.columns[i]
            rows = []
            for _, r in df.iterrows():
                player = str(r.get(col_map.get("player", ""), "")).strip()
                team = str(r.get(col_map.get("team", ""), "")).strip()
                pos = str(r.get(col_map.get("position", ""), "")).strip()
                pts_raw = r.get(col_map.get("proj_points", ""), 0)
                try:
                    pts_val = float(str(pts_raw).replace(",", ""))
                except Exception:
                    try:
                        pts_val = float(re.sub(r"[^0-9.\-]", "", str(pts_raw)))
                    except Exception:
                        pts_val = 0.0
                rows.append({
                    "player": player,
                    "team": team,
                    "position": pos.upper() if pos else "",
                    "proj_points": pts_val,
                })
            if rows:
                save_csv(rows, args.out)
                print(f"Saved {len(rows)} projections to {args.out} via pandas.read_html fallback")
                return

        # Second fallback: try earlier table-extraction heuristics
        tables = soup.find_all("table")
        for t in tables:
            rows = extract_from_table(t)
            if rows:
                print(f"Found {len(rows)} rows in a fallback table")
                save_csv(rows, args.out)
                print(f"Saved to {args.out}")
                return
        print("No tables yielded projection rows. Consider saving the page and re-running with --html <file>")
        return

    # Prefer pandas.read_html on the chosen table (handles complex table structures)
    rows = []
    try:
        df_list = pd.read_html(str(table))
    except Exception:
        df_list = []
    if df_list:
        df = df_list[0]
        print(f"pandas parsed chosen table with columns: {[str(c) for c in df.columns.astype(str)]}")
        # try to map columns
        cols = [str(c).strip().lower() for c in df.columns.astype(str)]
        col_map = {}
        for i, c in enumerate(cols):
            if ("player" in c or "name" in c) and "player" not in col_map:
                col_map["player"] = df.columns[i]
            if ("team" in c or c == "tm") and "team" not in col_map:
                col_map["team"] = df.columns[i]
            if ("pos" in c or "position" in c) and "position" not in col_map:
                col_map["position"] = df.columns[i]
            if ("fpts" in c or "pts" in c or "points" in c or "proj" in c) and "proj_points" not in col_map:
                col_map["proj_points"] = df.columns[i]
        for _, r in df.iterrows():
            player = str(r.get(col_map.get("player", ""), "")).strip()
            team = str(r.get(col_map.get("team", ""), "")).strip()
            pos = str(r.get(col_map.get("position", ""), "")).strip()
            pts_raw = r.get(col_map.get("proj_points", ""), 0)
            try:
                pts_val = float(str(pts_raw).replace(",", ""))
            except Exception:
                try:
                    pts_val = float(re.sub(r"[^0-9.\-]", "", str(pts_raw)))
                except Exception:
                    pts_val = 0.0
            rows.append({
                "player": player,
                "team": team,
                "position": pos.upper() if pos else "",
                "proj_points": pts_val,
            })
    # fallback to original extractor if pandas didn't produce rows
    if not rows:
        rows = extract_from_table(table)
    if not rows:
        print("No rows extracted from chosen table. Try --html fallback.")
        return
    save_csv(rows, args.out)
    print(f"Saved {len(rows)} projections to {args.out}")


if __name__ == "__main__":
    main()
