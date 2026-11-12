"""Business flows of stapel-courses (stapel_core.flows).

The Flow objects live here; HTTP steps are attached in ``views.py`` with
``@flow_step``. Literals are the canonical English source texts.
"""
from stapel_core.flows import Flow

LEARN = Flow(
    "courses.learn",
    title="Take a course",
    description=(
        "A visitor browses the catalog, opens a course outline that says which "
        "lessons are open and why the others are locked, enrolls (free, through a "
        "plan entitlement, or after buying it), works through the lessons while the "
        "progress is saved, and is told when the course is complete."
    ),
    actors=["Learner (guests only when ENROLLMENT_REQUIRES_ACCOUNT is off)"],
)
LEARN.action("courses.enrollment.activated", order=4, note="The enrollment is announced")
LEARN.action("courses.course.completed", order=7, note="Completion is announced")
LEARN.action("courses.certificate.issued", order=8, note="A certificate record is issued once")

PURCHASE = Flow(
    "courses.purchase",
    title="Buy a course",
    description=(
        "A course with the 'purchased' access mode is a purchasable of type "
        "'course' in stapel-orders. The order facts activate the enrollment "
        "(on payment by default) and a cancelled or refunded order closes it again."
    ),
    actors=["Learner", "Orders (by fact)"],
)
PURCHASE.action("orders.order.placed", order=1, note="The order with a course line is placed")
PURCHASE.action("orders.order.paid", order=2, note="Payment activates the enrollment")
PURCHASE.action("courses.enrollment.activated", order=3, note="Access is announced")

QUIZ = Flow(
    "courses.quiz",
    title="Pass a quiz",
    description=(
        "The learner starts an attempt (within the attempt limit), sees the "
        "questions in the order the attempt's stored seed gives, submits, and "
        "the server grades it. Right answers are shown only after submission, "
        "as the quiz's reveal mode allows."
    ),
    actors=["Learner"],
)

AUTHOR = Flow(
    "courses.author",
    title="Build and run a course",
    description=(
        "An author (or staff) creates a course, its modules, lessons, quizzes "
        "and questions, publishes it, grants enrollments by hand, reviews "
        "lessons that need a reviewer, and revokes a certificate."
    ),
    actors=["Author", "Staff"],
)

VERIFY = Flow(
    "courses.verify",
    title="Verify a certificate",
    description=(
        "Anyone with a certificate number checks it is valid and sees only the "
        "fields the deployment publishes."
    ),
    actors=["Anyone"],
)
