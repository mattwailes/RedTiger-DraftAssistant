"""
CBS projections scraper (all positions)

This script iterates target positions (QB,RB,WR,TE,K,DEF) and attempts to
fetch position-filtered CBS fantasy projections pages, extracting player,
team, position, and proj_points into a single merged CSV.

Usage:
  python scrape_cbs_allpos.py --url "https://www.cbssports.com/fantasy/football/stats/" --out cli\projections\cbs_all.csv

Dependencies: requests, beautifulsoup4, pandas
"""
from __future__ import annotations
import argparse
import os
import re
from typing import List, Dict

import requests
from bs4 import BeautifulSoup
import pandas as pd

USER_AGENT = "RedTiger-DraftAssistant/1.0 (+https://github.com/mattwailes/RedTiger-DraftAssistant)"
DEFAULT_POSITIONS = ["QB", "RB", "WR", "TE", "K", "DEF"]


def fetch_html(url: str) -> str:
    resp = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=30)
    resp.raise_for_status()
    return resp.text


def rows_from_html(html: str, prefer_position: str = "") -> List[Dict[str, str]]:
    rows: List[Dict[str, str]] = []
    # Try pandas first (convenient for complex tables)
    try:
        dfs = pd.read_html(html)
    except Exception:
        dfs = []
    for df in dfs:
        cols = [str(c).strip().lower() for c in df.columns.astype(str)]
        if not any(("player" in c or "name" in c) for c in cols):
            continue
        if not any(("pts" in c or "fpts" in c or "points" in c or "proj" in c) for c in cols):
            continue
        # map columns
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
            pos_col = str(r.get(col_map.get("position", ""), "")).strip()
            pts_raw = r.get(col_map.get("proj_points", ""), 0)
            try:
                pts_val = float(str(pts_raw).replace(",", ""))
            except Exception:
                try:
                    pts_val = float(re.sub(r"[^0-9.\-]", "", str(pts_raw)))
                except Exception:
                    pts_val = 0.0
            position_value = pos_col.upper() if pos_col else prefer_position
            rows.append({"player": player, "team": team, "position": position_value, "proj_points": pts_val})
        if rows:
            return rows
    # pandas didn't produce; fallback to HTML table extraction
    soup = BeautifulSoup(html, "html.parser")
    tables = soup.find_all("table")
    for table in tables:
        # simple heuristic: table has a player-like column and numeric values
        ths = table.find_all("th")
        headers = [re.sub(r"[^a-z0-9]", "", th.get_text(separator=" ").lower()) for th in ths]
        if not any("player" in h or "name" in h for h in headers):
            # still try extracting rows in case headers are absent
            pass
        extracted = []
        for tr in table.find_all("tr"):
            tds = tr.find_all("td")
            if not tds:
                continue
            cells = [td.get_text(separator=" ").strip() for td in tds]
            # attempt to detect player cell and proj cell
            # player often in first cell
            player_cell = cells[0]
            # find any numeric cell representing points (choose last numeric-looking cell)
            pts_val = 0.0
            for cell in reversed(cells):
                num = re.sub(r"[^0-9.\-]", "", cell)
                if num:
                    try:
                        pts_val = float(num)
                        break
                    except Exception:
                        continue
            # parse player cell for name/team/pos
            parts = [p.strip() for p in re.split(r"[\n,]+", player_cell) if p.strip()]
            player_name = ""
            team = ""
            pos = ""
            for p in parts:
                if re.search(r"[A-Za-z]", p) and " " in p and not re.fullmatch(r"[A-Z]{1,3}", p):
                    if len(p) > len(player_name):
                        player_name = p
            for p in parts[::-1]:
                if re.fullmatch(r"[A-Z]{2,3}", p):
                    team = p
                    break
            mpos = re.search(r"\b(QB|RB|WR|TE|K|DEF)\b", player_cell, re.I)
            if mpos:
                pos = mpos.group(1).upper()
            if not player_name:
                player_name = parts[0] if parts else ""
            position_value = pos or prefer_position
            extracted.append({"player": player_name, "team": team, "position": position_value, "proj_points": pts_val})
        if extracted:
            return extracted
    return []


def save_csv(rows: List[Dict[str, str]], out_path: str) -> None:
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    df = pd.DataFrame(rows)
    for c in ["player", "team", "position", "proj_points"]:
        if c not in df.columns:
            df[c] = ""
    df = df[["player", "team", "position", "proj_points"]]
    df.to_csv(out_path, index=False)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", help="CBS projections page URL", default="https://www.cbssports.com/fantasy/football/stats/")
    ap.add_argument("--out", help="Output CSV path", default="cli\\projections\\cbs_all.csv")
    ap.add_argument("--positions", nargs="*", help="Positions to fetch (e.g. QB RB WR TE K DEF)", default=DEFAULT_POSITIONS)
    ap.add_argument("--discover-positions", action="store_true", help="Discover position links from the base page and include them")
    args = ap.parse_args()

    print(f"Using positions: {args.positions}")
    base_html = fetch_html(args.url)
    positions = [p.upper() for p in args.positions]
    if args.discover_positions:
        soup = BeautifulSoup(base_html, "html.parser")
        discovered = []
        for a in soup.find_all("a", href=True):
            m = re.search(r"position=([A-Za-z]+)", a["href"])
            if m:
                discovered.append(m.group(1).upper())
        for p in discovered:
            if p not in positions:
                positions.append(p)
        if discovered:
            print(f"Discovered positions on page: {discovered}")

    all_rows: List[Dict[str, str]] = []
    seen = set()
    for pos in positions:
        print(f"Processing position {pos} ...")
        if "?" in args.url:
            pos_url = args.url + f"&position={pos.lower()}"
        else:
            pos_url = args.url + f"?position={pos.lower()}"
        try:
            html = fetch_html(pos_url)
        except Exception as e:
            print(f"Failed to fetch {pos_url}: {e}")
            # try base html as fallback
            html = base_html
        rows = rows_from_html(html, prefer_position=pos)
        print(f"  rows found for {pos}: {len(rows)}")
        for r in rows:
            key = (r.get("player", "").strip().lower(), r.get("team", "").strip().upper(), r.get("position", ""))
            if key in seen:
                continue
            seen.add(key)
            all_rows.append(r)

    if not all_rows:
        print("No projection rows collected. Exiting.")
        return
    save_csv(all_rows, args.out)
    print(f"Saved {len(all_rows)} total projections to {args.out}")


if __name__ == "__main__":
    main()
