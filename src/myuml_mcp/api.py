"""Typed client for the MyUML endpoints captured from the native iOS application."""

import json
import re
from gzip import decompress
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from pydantic import BaseModel, ConfigDict, Field, RootModel, field_validator, model_validator

API_BASE = "https://www.uml.edu/api/myuml/v1.0"
ALERTS_BASE = "https://umasslowell.azure-api.net/alerts"


_CAMEL_CASE_BOUNDARY = re.compile(r"(?<!^)(?=[A-Z])")


def snake_case(value: str) -> str:
    return _CAMEL_CASE_BOUNDARY.sub("_", value).lower()


def agent_data(value: Any) -> Any:
    """Convert parsed API data to the server's snake-case, omit-null contract."""
    if isinstance(value, BaseModel):
        return agent_data(value.model_dump(exclude_none=True))
    if isinstance(value, dict):
        return {snake_case(str(key)): agent_data(item) for key, item in value.items() if item is not None}
    if isinstance(value, list):
        return [agent_data(item) for item in value]
    return value


class APIObject(RootModel[dict[str, Any]]):
    """An endpoint-specific JSON object whose field names are normalized on output."""

    @model_validator(mode="before")
    @classmethod
    def accept_object(cls, value: Any) -> Any:
        if not isinstance(value, dict):
            raise TypeError("Expected an API object.")
        return value


class RawTerm(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    id: str = Field(alias="Id")
    name: str = Field(alias="Description")


class RawMeeting(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    days: str | None = Field(alias="FormattedDays", default=None)
    start: str | None = Field(alias="DailyStartTime", default=None)
    end: str | None = Field(alias="DailyEndTime", default=None)
    start_date: str | None = Field(alias="StartDate", default=None)
    end_date: str | None = Field(alias="EndDate", default=None)
    location: str | None = Field(alias="LocationDescription", default=None)
    instructors: list[dict[str, Any]] = Field(alias="Instructors", default_factory=list)

    @field_validator("instructors", mode="before")
    @classmethod
    def null_instructors_are_empty(cls, value: Any) -> Any:
        return [] if value is None else value


class Profile(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    id_number: str = Field(alias="IdNumber")
    first_name: str = Field(alias="FirstName")
    last_name: str = Field(alias="LastName")
    image: str | None = Field(alias="Image", default=None)
    is_valid: bool = Field(alias="IsValid")
    features: list[str] = Field(alias="Features")
    shortcuts: list[APIObject] = Field(alias="Shortcuts", default_factory=list)

    @field_validator("shortcuts", mode="before")
    @classmethod
    def null_shortcuts_are_empty(cls, value: Any) -> Any:
        return [] if value is None else value


class Advisor(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    id: str = Field(alias="Id")
    person_id: str = Field(alias="PersonId")
    first_name: str = Field(alias="FirstName")
    last_name: str = Field(alias="LastName")
    display_name: str = Field(alias="DisplayName")
    email_address: str = Field(alias="EmailAddress")
    role: str = Field(alias="Role")
    academic_career: str = Field(alias="AcademicCareer")
    academic_program: str = Field(alias="AcademicProgram")
    academic_plan: str = Field(alias="AcademicPlan")


class SpecialPeriod(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    id: str = Field(alias="Id")
    title: str = Field(alias="Title")
    description: str | None = Field(alias="Description")
    start: str = Field(alias="Start")
    end: str = Field(alias="End")
    is_all_day: bool = Field(alias="IsAllDay")
    is_blackout: bool = Field(alias="IsBlackout")
    day_override: str | None = Field(alias="DayOverride")


class ImportantDate(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    id: str = Field(alias="Id")
    description: str = Field(alias="Description")
    date: str = Field(alias="Date")


class CampusAlerts(BaseModel):
    umass_lowell: dict[str, Any]
    umass_system_it: dict[str, Any]


class ServiceIndicator(APIObject):
    pass


class TodoItem(APIObject):
    pass


class AdvisingAppointment(APIObject):
    pass


class ShortcutSyncResult(BaseModel):
    ok: bool


class EnrollmentRecord(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    course: str = Field(alias="CourseNumber")
    title: str = Field(alias="Title")
    topic: str | None = Field(alias="Topic", default=None)
    term: RawTerm = Field(alias="Term")
    section: str = Field(alias="Section")
    class_number: int = Field(alias="ClassNumber")
    credits: float = Field(alias="Credits")
    status: str = Field(alias="EnrollmentStatusName")
    withdrawn: bool = Field(alias="IsWithdrawn")
    meetings: list[RawMeeting] = Field(alias="Meetings", default_factory=list)
    lms: APIObject | None = Field(alias="Lms", default=None)

    @field_validator("meetings", mode="before")
    @classmethod
    def null_meetings_are_empty(cls, value: Any) -> Any:
        return [] if value is None else value


class MyUMLClient:
    def __init__(self, access_token: str) -> None:
        self._access_token = access_token

    def _request(
        self, path: str, *, method: str = "GET", payload: dict[str, Any] | None = None, auth: bool = True
    ) -> Any:
        headers = {"Accept": "application/json", "User-Agent": "MyUML SDK/0.1.0"}
        if auth:
            headers["Authorization"] = f"Bearer {self._access_token}"
        body = json.dumps(payload).encode() if payload is not None else None
        if body:
            headers["Content-Type"] = "application/json"
        try:
            with urlopen(
                Request(f"{API_BASE if auth else ALERTS_BASE}{path}", data=body, headers=headers, method=method),
                timeout=30,
            ) as response:
                if response.status == 204:
                    return {"ok": True}
                content = response.read()
                return json.loads(
                    decompress(content) if response.headers.get("Content-Encoding") == "gzip" else content
                )
        except HTTPError as error:
            if error.code in (401, 403):
                raise RuntimeError("MyUML authentication failed.") from error
            raise RuntimeError(
                f"MyUML API request failed ({error.code}): {error.read().decode(errors='replace')}"
            ) from error
        except URLError as error:
            raise RuntimeError(f"Could not reach the MyUML API: {error.reason}") from error

    def enrollment(self) -> list[EnrollmentRecord]:
        return [EnrollmentRecord.model_validate(value) for value in self._request("/me/academics/enrollment")]

    def profile(self) -> Profile:
        return Profile.model_validate(self._request("/me"))

    def service_indicators(self) -> list[ServiceIndicator]:
        return [ServiceIndicator.model_validate(value) for value in self._request("/me/academics/service_indicators")]

    def todo_items(self) -> list[TodoItem]:
        return [TodoItem.model_validate(value) for value in self._request("/me/academics/todo_items")]

    def advisors(self) -> list[Advisor]:
        return [Advisor.model_validate(value) for value in self._request("/me/academics/advisors")]

    def advising_appointments(self) -> list[AdvisingAppointment]:
        return [
            AdvisingAppointment.model_validate(value) for value in self._request("/me/calendar/advising_appointments")
        ]

    def special_periods(self) -> list[SpecialPeriod]:
        return [SpecialPeriod.model_validate(value) for value in self._request("/calendar/special_periods")]

    def important_dates(self) -> list[ImportantDate]:
        return [ImportantDate.model_validate(value) for value in self._request("/calendar/important_dates")]

    def campus_alerts(self) -> CampusAlerts:
        return CampusAlerts(
            umass_lowell=self._request("/lowell/web/text", auth=False),
            umass_system_it=self._request("/umassp/uits", auth=False),
        )

    def replace_pinned_shortcuts(self, shortcut_ids: list[str]) -> ShortcutSyncResult:
        self._request(
            "/me/shortcuts/sync",
            method="POST",
            payload={"PinnedShortcuts": shortcut_ids, "ClientLastModifiedTimestamp": None},
        )
        return ShortcutSyncResult(ok=True)
