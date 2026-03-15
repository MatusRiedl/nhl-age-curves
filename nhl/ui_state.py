"""Session-state helpers for chart and dialog rerun orchestration."""

from __future__ import annotations

import streamlit as st


DIALOG_OPENED_THIS_RUN_SESSION_KEY = "_dialog_opened_this_run"
LAST_HANDLED_CHART_SELECTION_SIGNATURE_SESSION_KEY = "_last_handled_chart_selection_signature"
CHART_SELECTION_RESET_NONCE_SESSION_KEY = "_chart_selection_reset_nonce"


def _get_session_state():
    """Return Streamlit's session state proxy or a patched test double."""
    return getattr(st, "session_state", None)


def session_state_get(key: str, default=None):
    """Read one session-state value from either a mapping or attribute proxy."""
    session_state = _get_session_state()
    if session_state is None:
        return default

    if hasattr(session_state, "get"):
        try:
            return session_state.get(key, default)
        except Exception:
            pass

    return getattr(session_state, key, default)


def session_state_set(key: str, value) -> None:
    """Write one session-state value to either a mapping or attribute proxy."""
    session_state = _get_session_state()
    if session_state is None:
        return

    try:
        session_state[key] = value
        return
    except Exception:
        pass

    try:
        setattr(session_state, key, value)
    except Exception:
        pass


def session_state_pop(key: str, default=None):
    """Pop one session-state value from either a mapping or attribute proxy."""
    session_state = _get_session_state()
    if session_state is None:
        return default

    if hasattr(session_state, "pop"):
        try:
            return session_state.pop(key, default)
        except Exception:
            pass

    value = getattr(session_state, key, default)
    if hasattr(session_state, key):
        try:
            delattr(session_state, key)
        except Exception:
            pass
    return value


def is_dialog_opened_this_run() -> bool:
    """Return whether a dialog has already been opened in the current rerun."""
    return bool(session_state_get(DIALOG_OPENED_THIS_RUN_SESSION_KEY, False))


def mark_dialog_opened_this_run() -> None:
    """Reserve the single-dialog slot for the current rerun."""
    session_state_set(DIALOG_OPENED_THIS_RUN_SESSION_KEY, True)


def reset_dialog_opened_this_run() -> None:
    """Clear the single-dialog slot at the start of a full app rerun."""
    session_state_set(DIALOG_OPENED_THIS_RUN_SESSION_KEY, False)


def dialog_slot_available() -> bool:
    """Return whether another dialog may be opened during this rerun."""
    return not is_dialog_opened_this_run()


def get_chart_selection_reset_nonce() -> int:
    """Return the current chart remount nonce used to clear sticky selections."""
    try:
        return int(session_state_get(CHART_SELECTION_RESET_NONCE_SESSION_KEY, 0) or 0)
    except Exception:
        return 0


def bump_chart_selection_reset_nonce() -> int:
    """Advance the chart remount nonce so the next rerun gets a fresh widget key."""
    next_nonce = get_chart_selection_reset_nonce() + 1
    session_state_set(CHART_SELECTION_RESET_NONCE_SESSION_KEY, next_nonce)
    return next_nonce
