"""
nhl.async_preloader — Background cache warming for category data.

Fires off threads to preload Goalie and Team data while the user is viewing
Skaters. Uses threading (not asyncio) for simplicity with Streamlit's
synchronous execution model. Results are cached via @st.cache_data decorators
on the underlying functions.

No Streamlit imports in this module — it only calls the data_loaders functions.

Functions in this module are called from app.py after session state is initialized.
"""

import threading
from typing import Callable


def _preload_in_thread(target: Callable, name: str) -> None:
    """Start a daemon thread to run the target function.

    Args:
        target: The function to execute (should be a @st.cache_data wrapped function).
        name: Human-readable name for the thread.
    """
    t = threading.Thread(target=target, name=name, daemon=True)
    t.start()


def preload_goalie_data() -> None:
    """Preload Goalie category data in background threads.

    Warms the cache for:
        - get_id_to_name_map("Goalie")
        - get_clone_details_map("Goalie")
    """
    from nhl.data_loaders import get_clone_details_map, get_id_to_name_map

    _preload_in_thread(lambda: get_id_to_name_map("Goalie"), "preload_goalie_names")
    _preload_in_thread(lambda: get_clone_details_map("Goalie"), "preload_goalie_details")


def preload_team_data() -> None:
    """Preload Team category data in a background thread.

    Warms the cache for:
        - load_all_team_seasons()
    """
    from nhl.data_loaders import load_all_team_seasons

    _preload_in_thread(load_all_team_seasons, "preload_team_seasons")


def preload_all_categories(current_category: str = "Skater") -> None:
    """Preload data for categories not currently active.

    Called once at app startup after session state is initialized.
    Spawns background threads that populate the Streamlit cache so that
    when the user switches categories, the data is already available.

    Args:
        current_category: The currently selected category ("Skater", "Goalie", or "Team").
                         Data for other categories is preloaded in background.
    """
    # Preload Goalie data if not currently viewing Goalies
    if current_category != "Goalie":
        preload_goalie_data()

    # Preload Team data if not currently viewing Teams
    if current_category != "Team":
        preload_team_data()

    # Note: Skater data is loaded on-demand since that's the default category.
    # If we start on Goalie or Team mode, Skater data will be preloaded too.
    if current_category != "Skater":
        from nhl.data_loaders import get_clone_details_map, get_id_to_name_map

        _preload_in_thread(lambda: get_id_to_name_map("Skater"), "preload_skater_names")
        _preload_in_thread(lambda: get_clone_details_map("Skater"), "preload_skater_details")
