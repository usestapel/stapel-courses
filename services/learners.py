"""Learner display cards for the author/staff views, asked by name.

``CARDS_FUNCTION`` (default ``profiles.public_cards``) answers
``{user_ids} -> {profiles: {user_id: card}, missing}``; courses never imports
profiles. Batched per page and degrading instead of failing: an unreachable
or failing Function, an empty setting, or an id it does not know leaves the
card ``None`` and the view shows ``user_id`` only.
"""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

DISPLAY_NAME_MAX_LENGTH = 255
AVATAR_REF_MAX_LENGTH = 255


def learner_cards(user_ids) -> dict[str, dict]:
    """``{user_id: {user_id, display_name, avatar_ref}}`` for the ids that have a card."""
    from stapel_core.comm import call, function_unreachable_reason

    from ..conf import courses_settings

    ids = sorted({str(u) for u in user_ids if u})
    name = str(courses_settings.CARDS_FUNCTION or "")
    if not ids or not name or function_unreachable_reason(name):
        return {}
    try:
        reply = call(name, {"user_ids": ids})
    except Exception:  # noqa: BLE001 — a missing card is data, not an error
        logger.info("courses: %r unavailable", name, exc_info=True)
        return {}
    profiles = reply.get("profiles") if isinstance(reply, dict) else None
    if not isinstance(profiles, dict):
        return {}
    cards = {}
    for user_id, card in profiles.items():
        if str(user_id) not in ids or not isinstance(card, dict):
            continue
        avatar = card.get("avatar")
        ref = avatar.get("ref") if isinstance(avatar, dict) else None
        cards[str(user_id)] = {
            "user_id": str(user_id),
            "display_name": str(card.get("display_name") or "")[:DISPLAY_NAME_MAX_LENGTH],
            "avatar_ref": str(ref)[:AVATAR_REF_MAX_LENGTH] if ref else None,
        }
    return cards
