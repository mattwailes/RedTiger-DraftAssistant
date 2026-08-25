"""
Thin wrapper around the `yahoo_fantasy_api` + `yahoo_oauth` libraries.

Setup (once you have Yahoo API access approved):
    pip install yahoo_fantasy_api yahoo_oauth

    1. Create an app at https://developer.yahoo.com/apps/create/
       (requires your access application to be approved first)
    2. Save the Client ID / Client Secret into oauth2.json in this folder:
         {"consumer_key": "...", "consumer_secret": "..."}
    3. First run will open a browser for you to grant access; a token is
       cached to oauth2.json automatically after that.

This module is optional -- the draft assistant works fine in fully manual
mode (you type player names as they're picked) if you skip Yahoo auth
entirely.
"""

from __future__ import annotations


def get_league(oauth_file: str = "oauth2.json", league_id: str | None = None):
    """
    Returns a yahoo_fantasy_api League object for live draft polling.
    Raises a clear error if the optional dependencies aren't installed.
    """
    try:
        from yahoo_oauth import OAuth2
        import yahoo_fantasy_api as yfa
    except ImportError as e:
        raise ImportError(
            "Yahoo integration needs: pip install yahoo_fantasy_api yahoo_oauth"
        ) from e

    oauth = OAuth2(None, None, from_file=oauth_file)
    game = yfa.Game(oauth, "nfl")

    if league_id is None:
        league_ids = game.league_ids(is_available=True)
        if not league_ids:
            raise RuntimeError("No active NFL leagues found on this Yahoo account.")
        league_id = league_ids[0]
        print(f"  Using league: {league_id} (pass league_id explicitly to pick a different one)")

    return game.to_league(league_id)


def get_drafted_player_names(league) -> set[str]:
    """
    Polls the live draft results and returns the set of already-drafted
    player names (raw, not normalized -- projections.find_player handles
    matching). Call this in a loop during your live draft to auto-remove
    picked players from the assistant's available pool.
    """
    results = league.draft_results()
    names = set()
    for pick in results:
        player_key = pick.get("player_key")
        if not player_key:
            continue
        try:
            info = league.player_details(player_key)
            name = info[0]["name"]["full"] if isinstance(info, list) else info["name"]["full"]
            names.add(name)
        except Exception:
            continue
    return names
