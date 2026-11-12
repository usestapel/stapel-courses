"""Selling a course through the orders seam (spec §5) — orders is never imported.

The order facts are delivered through the real in-process bus (``emit``) and
through the handlers directly; both must be idempotent.
"""
import pytest
from stapel_core.comm import call, emit, mutate_and_emit

from stapel_courses import actions
from stapel_courses.models import CoursePurchase, Enrollment

from .factories import V1, Event, make_course, simple_course

pytestmark = pytest.mark.django_db


def sellable(**fields):
    course, _, lessons = simple_course(access="purchased", price="49.90", currency="usd", **fields)
    course.currency = "USD"
    course.save()
    return course, lessons


def placed(order_id, user, *courses, extra_lines=()):
    return {
        "order_id": order_id, "user_id": str(user.pk), "currency": "USD", "total": "49.90",
        "placed_at": "2026-11-12T10:00:00+00:00",
        "lines": [
            {"purchasable_type": "course", "purchasable_key": str(c.pk), "quantity": 1,
             "unit_price": "49.90", "seller_id": None}
            for c in courses
        ] + list(extra_lines),
    }


def deliver(name, payload):
    with mutate_and_emit() as scoped:
        scoped(name, payload, key=str(payload.get("order_id")))


class TestResolver:
    def test_answers_the_purchasables_contract(self):
        course, _ = sellable()
        free = make_course(access="free")
        draft = make_course(access="purchased", price="5.00", currency="USD", status="draft")
        answer = call("courses.purchasables", {"keys": [str(course.pk), str(free.pk), str(draft.pk), "x"]})
        assert set(answer) == {str(course.pk), str(draft.pk)}
        item = answer[str(course.pk)]
        assert item == {"title": course.title, "price": "49.90", "currency": "USD", "available": True,
                        "max_quantity": 1, "seller_id": course.author_id, "image": None, "url": None}
        assert answer[str(draft.pk)]["available"] is False

    def test_url_template(self, settings):
        settings.STAPEL_COURSES = {"COURSE_URL_TEMPLATE": "/learn/{slug}"}
        course, _ = sellable(slug="paid-one")
        assert call("courses.purchasables", {"keys": [str(course.pk)]})[str(course.pk)]["url"] == "/learn/paid-one"

    def test_preset_registers_the_course_type(self):
        from stapel_courses.preset import SETTINGS_DEFAULTS

        assert SETTINGS_DEFAULTS["STAPEL_ORDERS"]["PURCHASABLE_TYPES"] == {
            "course": {"resolve": "courses.purchasables"}
        }


class TestActivation:
    def test_placed_then_paid_activates_once(self, learner, client_for, captured_events):
        course, lessons = sellable()
        deliver("orders.order.placed", placed("o-1", learner, course))
        enrollment = Enrollment.objects.get(user_id=str(learner.pk))
        assert (enrollment.status, enrollment.source, enrollment.order_id) == ("pending", "purchase", "o-1")
        assert client_for(learner).get(f"{V1}/courses/{course.slug}/lessons/{lessons[0].pk}/").status_code == 403
        deliver("orders.order.paid", {"order_id": "o-1", "provider_ref": "pay-1"})
        deliver("orders.order.paid", {"order_id": "o-1", "provider_ref": "pay-1"})
        enrollment.refresh_from_db()
        assert enrollment.status == "active" and enrollment.activated_at is not None
        assert [e.event_type for e in captured_events].count("courses.enrollment.activated") == 1
        assert client_for(learner).get(f"{V1}/courses/{course.slug}/lessons/{lessons[0].pk}/").status_code == 200

    def test_placed_replay_is_one_ledger_row(self, learner):
        course, _ = sellable()
        for _ in range(3):
            actions.handle_order_placed(Event(placed("o-2", learner, course)))
        assert CoursePurchase.objects.count() == 1 and Enrollment.objects.count() == 1

    def test_other_purchasable_types_are_ignored(self, learner):
        course, _ = sellable()
        line = {"purchasable_type": "listing", "purchasable_key": str(course.pk), "quantity": 1,
                "unit_price": "1.00", "seller_id": None}
        payload = placed("o-3", learner)
        payload["lines"] = [line]
        actions.handle_order_placed(Event(payload))
        assert not CoursePurchase.objects.exists()

    def test_unknown_course_is_ignored(self, learner):
        payload = placed("o-4", learner)
        payload["lines"] = [{"purchasable_type": "course", "purchasable_key": "999999", "quantity": 1,
                             "unit_price": "1.00", "seller_id": None}]
        actions.handle_order_placed(Event(payload))
        assert not Enrollment.objects.exists()

    def test_access_days_set_the_expiry(self, learner):
        course, _ = sellable(access_days=30)
        actions.handle_order_placed(Event(placed("o-5", learner, course)))
        actions.handle_order_paid(Event({"order_id": "o-5"}))
        enrollment = Enrollment.objects.get()
        assert (enrollment.expires_at - enrollment.activated_at).days == 30

    def test_placed_mode_activates_at_once(self, learner, settings):
        settings.STAPEL_COURSES = {"PURCHASE_ACTIVATION": "placed"}
        course, _ = sellable()
        actions.handle_order_placed(Event(placed("o-6", learner, course)))
        assert Enrollment.objects.get().status == "active"

    def test_confirmed_mode(self, learner, settings):
        course, _ = sellable()
        actions.handle_order_placed(Event(placed("o-7", learner, course)))
        actions.handle_order_status_changed(Event({"order_id": "o-7", "to": "confirmed"}))
        assert Enrollment.objects.get().status == "pending"
        settings.STAPEL_COURSES = {"PURCHASE_ACTIVATION": "confirmed"}
        actions.handle_order_status_changed(Event({"order_id": "o-7", "to": "confirmed"}))
        assert Enrollment.objects.get().status == "active"

    def test_a_second_order_after_a_cancel_reopens(self, learner):
        course, _ = sellable()
        actions.handle_order_placed(Event(placed("o-8", learner, course)))
        actions.handle_order_paid(Event({"order_id": "o-8"}))
        actions.handle_order_status_changed(Event({"order_id": "o-8", "to": "cancelled"}))
        assert Enrollment.objects.get().status == "cancelled"
        actions.handle_order_placed(Event(placed("o-9", learner, course)))
        assert Enrollment.objects.get().status == "pending"
        actions.handle_order_paid(Event({"order_id": "o-9"}))
        enrollment = Enrollment.objects.get()
        assert (enrollment.status, enrollment.order_id) == ("active", "o-9")


class TestDeactivation:
    def test_cancel_closes_the_orders_enrollment(self, learner, captured_events):
        course, _ = sellable()
        actions.handle_order_placed(Event(placed("o-10", learner, course)))
        actions.handle_order_paid(Event({"order_id": "o-10"}))
        actions.handle_order_status_changed(Event({"order_id": "o-10", "to": "cancelled"}))
        actions.handle_order_status_changed(Event({"order_id": "o-10", "to": "cancelled"}))
        assert Enrollment.objects.get().status == "cancelled"
        assert CoursePurchase.objects.get().state == "cancelled"
        cancels = [e.payload for e in captured_events
                   if e.event_type == "courses.enrollment.status_changed" and e.payload["to"] == "cancelled"]
        assert len(cancels) == 1 and cancels[0]["actor"] == "order"

    def test_refund_closes_it_too(self, learner):
        course, _ = sellable()
        actions.handle_order_placed(Event(placed("o-11", learner, course)))
        actions.handle_order_paid(Event({"order_id": "o-11"}))
        actions.handle_order_refunded(Event({"order_id": "o-11"}))
        assert Enrollment.objects.get().status == "cancelled"

    def test_a_staff_grant_is_left_alone(self, learner, staff_client):
        course, _ = sellable()
        staff_client.post(f"{V1}/author/courses/{course.pk}/enrollments/", {"user_id": str(learner.pk)},
                          format="json")
        actions.handle_order_placed(Event(placed("o-12", learner, course)))
        actions.handle_order_status_changed(Event({"order_id": "o-12", "to": "cancelled"}))
        enrollment = Enrollment.objects.get()
        assert (enrollment.status, enrollment.source) == ("active", "staff")

    def test_paid_after_cancel_does_not_reopen(self, learner):
        course, _ = sellable()
        actions.handle_order_placed(Event(placed("o-13", learner, course)))
        actions.handle_order_status_changed(Event({"order_id": "o-13", "to": "cancelled"}))
        actions.handle_order_paid(Event({"order_id": "o-13"}))
        assert Enrollment.objects.get().status == "cancelled"


def test_the_bus_path_reaches_the_handler(learner):
    """``emit`` outside our code reaches the subscription (not only a direct call)."""
    course, _ = sellable()
    with mutate_and_emit():
        emit("orders.order.placed", placed("o-14", learner, course), key="o-14")
    assert CoursePurchase.objects.filter(order_id="o-14").exists()
