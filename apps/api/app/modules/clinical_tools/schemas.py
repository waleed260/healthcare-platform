from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

TOOL_KEYS = ("dental_chart", "norwood", "graft_plan", "skin_map")
# Per-tool allowed value sets keep stored state bounded and consistent with the UI widgets.
TOOTH_STATES = {"healthy", "caries", "filled", "crown", "implant", "missing", "root_canal"}
NORWOOD_STAGES = {"I", "II", "IIa", "III", "IIIa", "III_vertex", "IV", "IVa", "V", "Va", "VI", "VII"}
GRAFT_ZONES = {"hairline", "temporal_left", "temporal_right", "midscalp", "crown"}
SKIN_REGIONS = {"forehead", "glabella", "nose", "cheek_left", "cheek_right", "perioral", "chin", "jaw_left", "jaw_right", "neck"}
SKIN_CONCERNS = {"acne", "scarring", "pigmentation", "redness", "wrinkles", "dryness", "oiliness", "laxity", "pores"}


def _notes(value: Any) -> str:
    if value in (None, ""):
        return ""
    if not isinstance(value, str) or len(value) > 5000:
        raise ValueError("notes must be text up to 5000 characters")
    return value


def validate_tool_state(tool_key: str, state: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(state, dict):
        raise ValueError("state must be an object")
    notes = _notes(state.get("notes"))
    if tool_key == "dental_chart":
        teeth = state.get("teeth", {})
        if not isinstance(teeth, dict) or len(teeth) > 52:
            raise ValueError("teeth must be an object with at most 52 entries")
        cleaned = {}
        for key, val in teeth.items():
            if not (isinstance(key, str) and key.isdigit() and 1 <= int(key) <= 85):
                raise ValueError(f"invalid tooth number '{key}'")
            if val not in TOOTH_STATES:
                raise ValueError(f"invalid tooth state '{val}'")
            if val != "healthy":
                cleaned[key] = val
        return {"teeth": cleaned, "notes": notes}
    if tool_key == "norwood":
        stage = state.get("stage")
        if stage is not None and stage not in NORWOOD_STAGES:
            raise ValueError("invalid Norwood stage")
        return {"stage": stage, "notes": notes}
    if tool_key == "graft_plan":
        zones = state.get("zones", {})
        if not isinstance(zones, dict):
            raise ValueError("zones must be an object")
        cleaned = {}
        for zone, count in zones.items():
            if zone not in GRAFT_ZONES:
                raise ValueError(f"invalid graft zone '{zone}'")
            if isinstance(count, bool) or not isinstance(count, int) or not (0 <= count <= 20000):
                raise ValueError(f"graft count for '{zone}' must be 0-20000")
            if count:
                cleaned[zone] = count
        return {"zones": cleaned, "total": sum(cleaned.values()), "notes": notes}
    # skin_map
    regions = state.get("regions", {})
    if not isinstance(regions, dict):
        raise ValueError("regions must be an object")
    cleaned = {}
    for region, concerns in regions.items():
        if region not in SKIN_REGIONS:
            raise ValueError(f"invalid skin region '{region}'")
        if not isinstance(concerns, list) or len(concerns) > len(SKIN_CONCERNS):
            raise ValueError("concerns must be a list")
        bad = [c for c in concerns if c not in SKIN_CONCERNS]
        if bad:
            raise ValueError(f"invalid skin concerns: {bad}")
        unique = sorted(set(concerns))
        if unique:
            cleaned[region] = unique
    return {"regions": cleaned, "notes": notes}


class ToolStateUpsert(BaseModel):
    model_config = ConfigDict(extra="forbid")

    state: dict[str, Any] = Field(default_factory=dict)
    tool_key: Literal["dental_chart", "norwood", "graft_plan", "skin_map"]

    @field_validator("state")
    @classmethod
    def _state(cls, value: dict[str, Any], info) -> dict[str, Any]:
        return value  # validated against tool_key in the route (needs both fields)
