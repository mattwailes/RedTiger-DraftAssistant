"""
League configuration for the draft assistant.
Edit these values to match your actual Yahoo league settings
(Yahoo > League > Settings will show you all of this).
"""

# --- League shape ---
NUM_TEAMS = 12
YOUR_DRAFT_SLOT = 6          # 1-indexed position in the draft order
DRAFT_TYPE = "snake"         # "snake" or "auction"
SCORING = "half_ppr"         # "standard", "half_ppr", or "ppr"

# --- Roster construction (used to compute replacement-level baselines) ---
# Counts are STARTING spots per team. Bench spots don't affect baseline math.
ROSTER_SPOTS = {
    "QB": 1,
    "RB": 2,
    "WR": 2,
    "TE": 1,
    "FLEX": 1,     # eligible: RB/WR/TE
    "K": 1,
    "DST": 1,
}
BENCH_SPOTS = 6

# --- Projection source weights ---
# Must sum to 1.0. Raise FantasyPros if you trust consensus most; raise your
# own CSV's weight if you have a favorite source (e.g. a subscription model).
SOURCE_WEIGHTS = {
    "fantasypros": 0.5,
    "espn": 0.25,
    "yahoo": 0.25,
}

# --- File locations ---
# Drop exported projection CSVs here before running. See README for the
# expected column format for each source.
PROJECTIONS_DIR = "projections"
