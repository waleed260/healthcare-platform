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
