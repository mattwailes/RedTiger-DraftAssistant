"""
Interactive draft-day assistant.

Run it live during your draft:
    python draft_assistant.py

Commands at each prompt:
    <enter>       show top available players (overall + by position need)
    take <name>   mark a player as drafted (by you or anyone else) and
                  remove them from the pool
    me <name>     mark a player as drafted BY YOU (adds to your roster)
    roster        show your current roster
    sync          pull latest picks from Yahoo's live draft board
                  (only works if Yahoo auth is set up -- see yahoo_client.py)
    quit          exit
"""

import sys

import pandas as pd

import config
import projections as proj

pd.set_option("display.max_rows", 30)
pd.set_option("display.width", 120)


class DraftState:
    def __init__(self, pool: pd.DataFrame):
        self.pool = pool  # available players, has 'player','position','vbd', etc.
        self.your_roster: list[dict] = []
        self.drafted: set[str] = set()

    def remove_player(self, player_row: pd.Series):
        self.pool = self.pool[self.pool["player"] != player_row["player"]]
        self.drafted.add(player_row["player"])

    def roster_position_counts(self) -> dict:
        counts = {}
        for p in self.your_roster:
            counts[p["position"]] = counts.get(p["position"], 0) + 1
        return counts


def positional_need_score(state: DraftState) -> dict:
    """
    Rough need multiplier per position: bigger if you still need starters
    there, smaller (but never zero) once a position is filled, so the
    assistant nudges you toward roster balance without ever hiding value.
    """
    have = state.roster_position_counts()
    need = {}
    for pos, starters in config.ROSTER_SPOTS.items():
        if pos == "FLEX":
            continue
        filled = have.get(pos, 0)
        remaining = max(starters - filled, 0)
        need[pos] = 1.15 if remaining > 0 else 0.95
    return need


def show_top(state: DraftState, n: int = 15):
    if state.pool.empty:
        print("No players left in the pool.")
        return
    need = positional_need_score(state)
    view = state.pool.copy()
    view["need_adj_vbd"] = view.apply(
        lambda r: r["vbd"] * need.get(r["position"], 1.0), axis=1
    )
    top = view.sort_values("need_adj_vbd", ascending=False).head(n)
    print("\n=== Top available (need-adjusted VBD) ===")
    print(top[["player", "position", "team", "proj_points", "vbd", "need_adj_vbd"]]
          .to_string(index=False))

    print("\n=== Best available by position ===")
    for pos in ["QB", "RB", "WR", "TE", "K", "DST"]:
        pos_players = state.pool[state.pool["position"] == pos].head(3)
        if pos_players.empty:
            continue
        names = ", ".join(
            f"{r.player} ({r.vbd:+.1f})" for r in pos_players.itertuples()
        )
        print(f"  {pos:4s}: {names}")
    print()


def show_roster(state: DraftState):
    if not state.your_roster:
        print("Your roster is empty so far.")
        return
    print("\n=== Your roster ===")
    for p in state.your_roster:
        print(f"  {p['position']:4s} {p['player']} ({p['proj_points']:.1f} proj pts)")
    counts = state.roster_position_counts()
    print(f"  -> position counts: {counts}\n")


def handle_take(state: DraftState, query: str, mine: bool):
    matches = proj.find_player(state.pool, query, limit=5)
    if matches.empty:
        print(f"No match for '{query}' in remaining pool.")
        return
    best = matches.iloc[0]
    print(f"  -> Matched: {best['player']} ({best['position']}, {best['team']})")
    state.remove_player(best)
    if mine:
        state.your_roster.append(best.to_dict())
        print(f"  Added to YOUR roster.")


def try_yahoo_sync(state: DraftState):
    try:
        import yahoo_client
        league = yahoo_client.get_league()
        drafted_names = yahoo_client.get_drafted_player_names(league)
    except Exception as e:
        print(f"  [!] Yahoo sync unavailable: {e}")
        return
    new = 0
    for name in drafted_names:
        if name in state.drafted:
            continue
        matches = proj.find_player(state.pool, name, limit=1)
        if not matches.empty:
            state.remove_player(matches.iloc[0])
            new += 1
    print(f"  Synced. {new} newly drafted players removed from pool.")


def main():
    print("Loading and blending projections...")
    source_dfs = proj.load_all_projections(
        config.PROJECTIONS_DIR, list(config.SOURCE_WEIGHTS.keys())
    )
    blended = proj.blend_projections(source_dfs, config.SOURCE_WEIGHTS)
    baselines = proj.compute_replacement_baselines(
        blended, config.ROSTER_SPOTS, config.NUM_TEAMS
    )
    print("Replacement-level baselines by position:")
    for pos, val in baselines.items():
        print(f"  {pos:4s}: {val:.1f} pts")
    pool = proj.add_vbd(blended, baselines)

    state = DraftState(pool)
    print(f"\nLoaded {len(pool)} players. Ready to draft.")
    print("Type 'help' any time for the command list.\n")

    while True:
        try:
            cmd = input("> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break

        if cmd == "" or cmd == "show":
            show_top(state)
        elif cmd in ("q", "quit", "exit"):
            break
        elif cmd == "help":
            print(__doc__)
        elif cmd == "roster":
            show_roster(state)
        elif cmd == "sync":
            try_yahoo_sync(state)
        elif cmd.startswith("take "):
            handle_take(state, cmd[len("take "):], mine=False)
        elif cmd.startswith("me "):
            handle_take(state, cmd[len("me "):], mine=True)
        else:
            print("Unrecognized command. Type 'help' for options.")


if __name__ == "__main__":
    sys.exit(main())
