import pytest

from app.modules.clinical_tools.schemas import TOOL_KEYS, validate_tool_state


def test_tool_state_validation() -> None:
    assert set(TOOL_KEYS) == {"dental_chart", "norwood", "graft_plan", "skin_map"}
    assert validate_tool_state("dental_chart", {"teeth": {"11": "crown", "12": "healthy"}})["teeth"] == {"11": "crown"}
    assert validate_tool_state("norwood", {"stage": "III_vertex"})["stage"] == "III_vertex"
    assert validate_tool_state("graft_plan", {"zones": {"hairline": 1500, "crown": 500}})["total"] == 2000
    assert validate_tool_state("skin_map", {"regions": {"cheek_left": ["acne", "acne", "scarring"]}})["regions"]["cheek_left"] == ["acne", "scarring"]
    for bad in (
        ("dental_chart", {"teeth": {"11": "gold"}}),
        ("dental_chart", {"teeth": {"99": "crown"}}),
        ("norwood", {"stage": "XII"}),
        ("graft_plan", {"zones": {"beard": 10}}),
        ("graft_plan", {"zones": {"hairline": 99999}}),
        ("skin_map", {"regions": {"elbow": ["acne"]}}),
        ("skin_map", {"regions": {"nose": ["tattoo"]}}),
    ):
        with pytest.raises(ValueError):
            validate_tool_state(*bad)
