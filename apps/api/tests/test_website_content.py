import pytest
from pydantic import ValidationError

from app.main import app
from app.modules.website_content.schemas import FormCreate, PostCreate, TestimonialCreate, validate_answers

FIELDS = [
    {"key": "name", "label": "Full name", "type": "text", "required": True, "maps_to": "full_name"},
    {"key": "phone", "label": "Phone", "type": "phone", "required": True, "maps_to": "phone"},
    {"key": "service", "label": "Service", "type": "dropdown", "required": False, "options": ["Whitening", "Implants"]},
    {"key": "when", "label": "Preferred date", "type": "date"},
    {"key": "consent", "label": "I agree to be contacted", "type": "consent", "required": True},
]


def test_form_definition_rules() -> None:
    assert FormCreate(name="Enquiry", fields=FIELDS).action == "lead"
    for broken in (
        [f for f in FIELDS if f["key"] != "consent"],
        [f for f in FIELDS if f["key"] != "name"],
        [f for f in FIELDS if f["key"] != "phone"],
        FIELDS + [FIELDS[0]],
        [*FIELDS[:2], {"key": "Bad Key", "label": "x", "type": "text"}, FIELDS[-1]],
        [*FIELDS[:2], {"key": "pick", "label": "x", "type": "dropdown"}, FIELDS[-1]],
    ):
        with pytest.raises(ValidationError):
            FormCreate(name="Bad", fields=broken)


def test_answer_validation() -> None:
    good = {"name": " Amina ", "phone": "+92 300 1234567", "service": "Implants", "when": "2026-10-20", "consent": True}
    cleaned = validate_answers(FIELDS, good)
    assert cleaned["name"] == "Amina" and cleaned["consent"] == "yes"
    for patch in ({"consent": False}, {"phone": "abc"}, {"service": "Surgery"}, {"when": "20/10/2026"}, {"name": ""}, {"extra": "x"}, {"name": 5}):
        with pytest.raises(ValueError):
            validate_answers(FIELDS, {**good, **patch})


def test_post_and_testimonial_schemas() -> None:
    PostCreate(slug="five-tips", title="Five tips")
    with pytest.raises(ValidationError):
        PostCreate(slug="Bad Slug", title="x")
    TestimonialCreate(author_name="Amina", rating=5, body="Great care", consent_confirmed=True)
    with pytest.raises(ValidationError):
        TestimonialCreate(author_name="A", rating=6, body="x", consent_confirmed=True)


def test_routes_registered() -> None:
    paths = set(app.openapi()["paths"])
    for expected in ("/api/v1/website-content/forms", "/api/v1/public/sites/slug/{clinic_slug}/forms/{form_id}/submit", "/api/v1/website-content/posts", "/api/v1/public/sites/slug/{clinic_slug}/posts/{post_slug}", "/api/v1/website-content/testimonials/{testimonial_id}/moderate", "/api/v1/public/sites/slug/{clinic_slug}/testimonials"):
        assert expected in paths
