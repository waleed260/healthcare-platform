from types import SimpleNamespace
from unittest.mock import Mock
from uuid import uuid4

import pytest

from app.modules.identity import routes as identity_routes
from app.modules.websites import routes as website_routes
from app.modules.websites.publishing import REQUIRED_LEGAL_SLUGS, validate_publish_snapshot


def _request() -> SimpleNamespace:
    return SimpleNamespace(state=SimpleNamespace(request_id="request-test"))


@pytest.mark.parametrize(
    ("role", "effective_permissions"),
    [
        ("owner", ["website.edit", "website.publish"]),
        ("website_editor", ["website.edit"]),
    ],
)
def test_auth_me_returns_website_permissions_for_role(monkeypatch, role, effective_permissions):
    user_id, clinic_id = uuid4(), uuid4()
    session = {"user_id": user_id, "clinic_id": clinic_id, "display_name": role, "normalized_email": f"{role}@example.test"}
    monkeypatch.setattr(identity_routes, "_session_or_401", lambda db, token: session)
    db = Mock()
    db.execute.side_effect = [
        Mock(scalars=lambda: Mock(all=lambda: effective_permissions)),
        Mock(scalars=lambda: Mock(all=lambda: [])),
    ]

    result = identity_routes.me(_request(), db, "session-token")

    permissions = set(result["data"]["permissions"])
    assert ("website.edit" in permissions) is (role in {"owner", "website_editor"})
    assert ("website.publish" in permissions) is (role == "owner")


@pytest.mark.parametrize(
    "snapshot",
    [
        {"pages": [{"slug": "home"}]},
        {
            "pages": [{"slug": slug} for slug in REQUIRED_LEGAL_SLUGS],
            "brand": {"text_color": "#777777", "background_color": "#ffffff"},
        },
    ],
)
def test_website_validation_matches_publish_validation_message(monkeypatch, snapshot):
    website_id, clinic_id = uuid4(), uuid4()
    monkeypatch.setattr(website_routes, "_authorized", lambda db, token, permission: {"clinic_id": clinic_id})
    db = Mock()
    db.execute.side_effect = [
        Mock(mappings=lambda: Mock(one_or_none=lambda: {"snapshot": snapshot})),
        Mock(scalar_one=lambda: 0),
    ]

    with pytest.raises(ValueError) as publish_validation:
        validate_publish_snapshot(snapshot)

    result = website_routes.website_validation(website_id, _request(), db, "session-token")

    assert result["data"] == {
        "valid": False,
        "code": "PUBLISH_VALIDATION_FAILED",
        "message": str(publish_validation.value),
    }
