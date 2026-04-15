"""Asyncio compatibility helpers for cross-platform startup."""

import asyncio
import os


def ensure_windows_proactor_event_loop() -> None:
    """Force Proactor policy on Windows for Playwright subprocess support."""
    if os.name != "nt":
        return

    policy_cls = getattr(asyncio, "WindowsProactorEventLoopPolicy", None)
    if policy_cls is None:
        return

    try:
        current_policy = asyncio.get_event_loop_policy()
        if isinstance(current_policy, policy_cls):
            return
    except Exception:
        pass

    try:
        asyncio.set_event_loop_policy(policy_cls())
    except Exception:
        # Keep startup resilient if policy cannot be changed in this runtime.
        pass
