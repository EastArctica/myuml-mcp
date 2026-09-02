import json
from pathlib import Path

import pytest

from myuml_mcp.api import EnrollmentRecord, ShortcutSyncResult
from myuml_mcp.server import get_term_classes, mcp, replace_pinned_shortcuts


class Client:
    def __init__(self, records: list[EnrollmentRecord]) -> None:
        self.records = records
        self.pinned: list[str] | None = None

    def enrollment(self) -> list[EnrollmentRecord]:
        return self.records

    def replace_pinned_shortcuts(self, shortcut_ids: list[str]) -> ShortcutSyncResult:
        self.pinned = shortcut_ids
        return ShortcutSyncResult(ok=True)


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch) -> Client:
    fixture = Path(__file__).parent / "fixtures" / "enrollment.json"
    result = Client([EnrollmentRecord.model_validate(value) for value in json.loads(fixture.read_text())])
    monkeypatch.setattr("myuml_mcp.server._client", lambda: result)
    return result


def test_term_classes_forwards_include_meetings(client: Client) -> None:
    result = get_term_classes("2251", include_meetings=False)

    assert "meetings" not in result["classes"][0]
    assert mcp._tool_manager._tools["get_term_classes"].parameters["properties"]["include_meetings"]["default"] is True


def test_replace_pinned_shortcuts_requires_confirmation(client: Client) -> None:
    with pytest.raises(ValueError, match="confirm=true"):
        replace_pinned_shortcuts(["calendar"])

    assert replace_pinned_shortcuts(["calendar"], confirm=True) == {"ok": True}
    assert client.pinned == ["calendar"]
    annotations = mcp._tool_manager._tools["replace_pinned_shortcuts"].annotations
    assert annotations.read_only_hint is False
    assert annotations.destructive_hint is True
    assert annotations.idempotent_hint is True


def test_replace_pinned_shortcuts_rejects_unsafe_ids(client: Client) -> None:
    with pytest.raises(ValueError, match="unique, non-empty"):
        replace_pinned_shortcuts(["calendar", "calendar"], confirm=True)
