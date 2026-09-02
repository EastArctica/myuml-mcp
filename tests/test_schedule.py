import json
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from myuml_mcp.api import EnrollmentRecord, RawTerm
from myuml_mcp.schedule import active_term, normalize


def records() -> list[EnrollmentRecord]:
    fixture = Path(__file__).parent / "fixtures" / "enrollment.json"
    return [EnrollmentRecord.model_validate(value) for value in json.loads(fixture.read_text())]


def test_active_term_does_not_select_future_registration() -> None:
    assert active_term(records(), today=datetime(2026, 9, 2, tzinfo=ZoneInfo("America/New_York"))) == "2251"


def test_active_term_can_use_a_current_tba_term_name() -> None:
    tba = records()[2].model_copy(update={"term": RawTerm(id="2267", name="Fall 2026")})

    assert active_term([tba], today=datetime(2026, 9, 2, tzinfo=ZoneInfo("America/New_York"))) == "2267"


def test_normalize_retains_tba_online_meetings() -> None:
    result = normalize(records(), "2251")
    online = result.classes[1].meetings[0]

    assert online.days == []
    assert online.location == "Online"
    assert online.is_tba is True
    assert online.start is None
    assert online.end is None
