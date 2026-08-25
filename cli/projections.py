"""
Loads per-source projection CSVs, blends them into one weighted projection
per player, and computes Value-Based Drafting (VBD) scores against
replacement-level baselines derived from your league's roster settings.

Expected CSV columns per source (case-insensitive, extra columns ignored):
    player, team, position, proj_points

Yahoo/ESPN/FantasyPros exports rarely match this exactly -- see README for
quick instructions on getting each into this shape.
"""

import difflib
import os
import re
from dataclasses import dataclass, field

import pandas as pd

REQUIRED_COLS = {"player", "team", "position", "proj_points"}


def _normalize_name(name: str) -> str:
    """Lowercase, strip suffixes/punctuation so names match across sources."""
    name = name.lower().strip()
    name = re.sub(r"[.'\-]", "", name)
    name = re.sub(r"\b(jr|sr|ii|iii|iv|v)\b", "", name)
    name = re.sub(r"\s+", " ", name).strip()
    return name


def load_projection_csv(path: str, source_name: str) -> pd.DataFrame:
    df = pd.read_csv(path)
    df.columns = [c.strip().lower() for c in df.columns]
    missing = REQUIRED_COLS - set(df.columns)
    if missing:
        raise ValueError(
            f"{path} is missing columns {missing}. "
            f"Expected columns: {sorted(REQUIRED_COLS)}"
        )
    df = df[["player", "team", "position", "proj_points"]].copy()
    df["position"] = df["position"].str.upper().str.strip()
    df["team"] = df["team"].str.upper().str.strip()
    df["norm_name"] = df["player"].apply(_normalize_name)
    df["source"] = source_name
    return df


def load_all_projections(projections_dir: str, sources: list[str]) -> dict[str, pd.DataFrame]:
    """Loads {source}.csv for each source name in `sources` from projections_dir."""
    out = {}
    for source in sources:
        path = os.path.join(projections_dir, f"{source}.csv")
        if not os.path.exists(path):
            print(f"  [!] Skipping '{source}': no file at {path}")
            continue
        out[source] = load_projection_csv(path, source)
    if not out:
        raise FileNotFoundError(
            f"No projection CSVs found in {projections_dir}/. "
            f"Expected files like: {[s + '.csv' for s in sources]}"
        )
    return out


def blend_projections(
    source_dfs: dict[str, pd.DataFrame],
    weights: dict[str, float],
) -> pd.DataFrame:
    """
    Weighted-average projected points across sources, matched by normalized
    player name. Weights are renormalized to sum to 1 over sources actually
    present (so it's fine if you're missing a source's CSV).
    """
    present_weights = {s: w for s, w in weights.items() if s in source_dfs}
    total = sum(present_weights.values())
    if total == 0:
        raise ValueError("None of the configured SOURCE_WEIGHTS sources were loaded.")
    norm_weights = {s: w / total for s, w in present_weights.items()}

    all_players = pd.concat(source_dfs.values(), ignore_index=True)
    canonical = (
        all_players.sort_values("proj_points", ascending=False)
        .drop_duplicates("norm_name")[["norm_name", "player", "team", "position"]]
        .set_index("norm_name")
    )

    pivot = all_players.pivot_table(
        index="norm_name", columns="source", values="proj_points", aggfunc="mean"
    )

    blended_points = pd.Series(0.0, index=pivot.index)
    coverage = pd.Series(0.0, index=pivot.index)
    for source, w in norm_weights.items():
        if source not in pivot.columns:
            continue
        col = pivot[source]
        blended_points += col.fillna(0) * w
        coverage += col.notna().astype(float) * w
    # Rescale by actual coverage so a player missing from one source isn't
    # unfairly dragged down -- e.g. if only 2 of 3 weighted sources have them.
    coverage = coverage.replace(0, pd.NA)
    blended_points = (blended_points / coverage).fillna(0)

    result = canonical.join(blended_points.rename("proj_points"))
    result = result.join(pivot.add_prefix("pts_"))
    return result.reset_index(drop=True).sort_values("proj_points", ascending=False)


def compute_replacement_baselines(
    blended: pd.DataFrame, roster_spots: dict, num_teams: int
) -> dict[str, float]:
    """
    Replacement level per position = the projection of the Nth-best player
    at that position, where N = (starters at that position across the
    league) + a share of FLEX starters (split evenly across RB/WR/TE).
    """
    flex_eligible = ["RB", "WR", "TE"]
    flex_spots = roster_spots.get("FLEX", 0)
    flex_share = flex_spots / len(flex_eligible) if flex_spots else 0

    baselines = {}
    for pos, starters in roster_spots.items():
        if pos == "FLEX":
            continue
        n = starters * num_teams
        if pos in flex_eligible:
            n += round(flex_share * num_teams)
        pos_players = blended[blended["position"] == pos].sort_values(
            "proj_points", ascending=False
        )
        if len(pos_players) >= n and n > 0:
            baselines[pos] = pos_players.iloc[n - 1]["proj_points"]
        elif len(pos_players):
            baselines[pos] = pos_players["proj_points"].min()
        else:
            baselines[pos] = 0.0
    return baselines


def add_vbd(blended: pd.DataFrame, baselines: dict[str, float]) -> pd.DataFrame:
    blended = blended.copy()
    blended["baseline"] = blended["position"].map(baselines).fillna(0)
    blended["vbd"] = blended["proj_points"] - blended["baseline"]
    return blended.sort_values("vbd", ascending=False).reset_index(drop=True)


def find_player(df: pd.DataFrame, query: str, limit: int = 5) -> pd.DataFrame:
    """Fuzzy-find a player by name (for manually marking picks)."""
    norm_query = _normalize_name(query)
    df = df.copy()
    df["_score"] = df["player"].apply(
        lambda p: difflib.SequenceMatcher(None, norm_query, _normalize_name(p)).ratio()
    )
    return df.sort_values("_score", ascending=False).head(limit).drop(columns="_score")
