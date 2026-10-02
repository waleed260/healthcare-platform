import pytest
from pydantic import ValidationError

from app.modules.clinical_forms.schemas import FormResponseCreate, FormTemplateCreate


def test_form_template_key_is_lowercase_and_structured() -> None:
    payload = FormTemplateCreate(form_key="hair_assessment", name="Hair assessment", field_schema={"fields": []})
    assert payload.form_key == "hair_assessment"


def test_form_template_rejects_unstable_key() -> None:
    with pytest.raises(ValidationError):
        FormTemplateCreate(form_key="Hair Assessment", name="Hair assessment")


def test_form_response_defaults_to_empty_data() -> None:
    payload = FormResponseCreate(template_id="00000000-0000-0000-0000-000000000001")
    assert payload.response_data == {}


from app.modules.clinical_forms.schemas import normalize_field_schema, validate_answers  # noqa: E402

FIELDS = {"fields": [
    {"key": "graft_count", "label": "Graft count", "type": "number", "required": True},
    {"key": "donor_area", "label": "Donor area", "type": "select", "required": True, "options": ["Occipital", "Beard"]},
    {"key": "notes", "label": "Notes", "type": "textarea"},
    {"key": "consented", "label": "Consent on file", "type": "checkbox"},
    {"key": "review_on", "label": "Review date", "type": "date"},
]}


def test_field_schema_normalizes_and_rejects_bad_fields() -> None:
    norm = normalize_field_schema(FIELDS)
    assert [f["key"] for f in norm["fields"]] == ["graft_count", "donor_area", "notes", "consented", "review_on"]
    assert normalize_field_schema({}) == {"fields": []}
    for bad in (
        {"fields": [{"key": "Bad Key", "label": "x", "type": "text"}]},
        {"fields": [{"key": "x", "label": "x", "type": "select"}]},            # select w/o options
        {"fields": [{"key": "x", "label": "x", "type": "text", "options": ["a"]}]},  # options on non-select
        {"fields": [{"key": "a", "label": "x", "type": "text"}, {"key": "a", "label": "y", "type": "text"}]},  # dup
        {"fields": [{"key": "x", "label": "x", "type": "slider"}]},            # bad type
    ):
        with pytest.raises((ValidationError, ValueError)):
            normalize_field_schema(bad)


def test_answer_validation_draft_vs_submit() -> None:
    norm = normalize_field_schema(FIELDS)["fields"]
    schema = {"fields": norm}
    # draft: partial allowed
    validate_answers(schema, {"graft_count": 2500}, require_all=False)
    # submit: required missing -> error
    with pytest.raises(ValueError):
        validate_answers(schema, {"graft_count": 2500}, require_all=True)
    # full valid submit
    validate_answers(schema, {"graft_count": 2500, "donor_area": "Occipital", "consented": True, "review_on": "2026-11-01"}, require_all=True)
    for bad in (
        {"graft_count": "lots"},                 # not a number
        {"donor_area": "Nape"},                  # not an option
        {"consented": "yes"},                    # not a bool
        {"review_on": "01-11-2026"},             # bad date
        {"unknown_field": 1},                    # unknown key
    ):
        with pytest.raises(ValueError):
            validate_answers(schema, bad, require_all=False)
