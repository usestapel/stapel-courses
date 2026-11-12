"""Action subscriptions of stapel-courses. Handlers are idempotent
(delivery is at-least-once).

- ``orders.order.placed`` / ``.paid`` / ``.status_changed`` /
  ``.refunded`` — course purchases (``services/purchases.py``); a fact for
  another purchasable type or an unknown course is someone else's event and
  is ignored.
- ``user.merged`` (stapel-auth) — a guest's learning follows it into the
  account on sign-in.
- ``user.deleted`` / ``gdpr.erasure.requested`` are answered by
  ``register_gdpr_owner`` (``apps.py``), not here.
"""
import json
import logging
from pathlib import Path

from stapel_core.comm import on_action

logger = logging.getLogger(__name__)

_CONSUMES = Path(__file__).resolve().parent / "schemas" / "consumes"


def _schema(name: str) -> dict:
    return json.loads((_CONSUMES / f"{name}.json").read_text(encoding="utf-8"))


@on_action("orders.order.placed", schema=_schema("orders.order.placed"))
def handle_order_placed(event):
    from .services.purchases import order_placed

    touched = order_placed(event.payload or {})
    if touched:
        logger.info("orders.order.placed %s: %d course purchase(s)", event.event_id, touched)


@on_action("orders.order.paid", schema=_schema("orders.order.paid"))
def handle_order_paid(event):
    from .services.purchases import order_paid

    order_paid(str((event.payload or {}).get("order_id") or ""))


@on_action("orders.order.status_changed", schema=_schema("orders.order.status_changed"))
def handle_order_status_changed(event):
    from .services.purchases import order_cancelled, order_confirmed

    payload = event.payload or {}
    order_id = str(payload.get("order_id") or "")
    if payload.get("to") == "cancelled":
        order_cancelled(order_id, reason="order_cancelled")
    elif payload.get("to") == "confirmed":
        order_confirmed(order_id)


@on_action("orders.order.refunded", schema=_schema("orders.order.refunded"))
def handle_order_refunded(event):
    from .services.purchases import order_cancelled

    order_cancelled(str((event.payload or {}).get("order_id") or ""), reason="order_refunded")


@on_action("user.merged", schema=_schema("user.merged"))
def handle_user_merged(event):
    """Re-parent the guest's enrollments, progress, attempts and certificates."""
    from .services.enrollments import merge_users

    payload = event.payload or {}
    from_user_id = str(payload.get("from_user_id") or "")
    into_user_id = str(payload.get("into_user_id") or "")
    if not from_user_id or not into_user_id:
        logger.error("user.merged without from/into user id: %s", event.event_id)
        return
    if from_user_id == into_user_id:
        return
    moved = merge_users(from_user_id, into_user_id)
    if any(moved.values()):
        logger.info("user.merged %s -> %s: %s", from_user_id, into_user_id, moved)
