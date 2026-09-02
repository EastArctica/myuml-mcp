"""Compact, agent-oriented projections of MyUML enrollment data."""

from datetime import datetime
from zoneinfo import ZoneInfo

from pydantic import BaseModel, Field

from .api import RawEnrollment

TIMEZONE = ZoneInfo("America/New_York")
DAY_CODES = {"M": "MO", "T": "TU", "W": "WE", "R": "TH", "F": "FR", "S": "SA", "U": "SU"}


class Term(BaseModel):
    id: str
    name: str


class Meeting(BaseModel):
    days: list[str]
    start: str
    end: str
    timezone: str = "America/New_York"
    location: str | None = None
    instructors: list[str]


class Class(BaseModel):
    class_number: int
    course: str
    title: str
    topic: str | None = Field(default=None, exclude_if=lambda value: value is None)
    section: str
    credits: float
    status: str
    meetings: list[Meeting] | None = Field(default=None, exclude_if=lambda value: value is None)

class TermClasses(BaseModel):
    term: Term
    course_count: int
    total_credits: float
    classes: list[Class]


class ClassesResult(TermClasses):
    retrieved_at: datetime


class EnrollmentHistory(BaseModel):
    retrieved_at: datetime
    term_count: int
    terms: list[TermClasses]


def active_term(records: list[RawEnrollment]) -> str:
    today = datetime.now(TIMEZONE).date()
    for record in records:
        for meeting in record.meetings:
            if meeting.start_date and meeting.end_date:
                start = datetime.fromisoformat(meeting.start_date).date()
                end = datetime.fromisoformat(meeting.end_date).date()
                if start <= today <= end and not record.withdrawn and record.status.lower() == "enrolled":
                    return record.term.id
    return max((record.term.id for record in records if not record.withdrawn and record.status.lower() == "enrolled"), default="")


def normalize(records: list[RawEnrollment], term_id: str, include_withdrawn: bool = False, *, include_meetings: bool = True, include_retrieved_at: bool = True) -> ClassesResult | TermClasses:
    selected = [record for record in records if record.term.id == term_id and (include_withdrawn or not record.withdrawn)]
    if not selected:
        raise RuntimeError(f"No enrollment records found for term '{term_id}'.")
    classes = [
        Class(
            class_number=record.class_number, course=record.course, title=record.title, topic=record.topic, section=record.section,
            credits=record.credits, status=record.status.lower(),
            meetings=[Meeting(days=[DAY_CODES.get(day, day) for day in meeting.days], start=meeting.start[:5], end=meeting.end[:5], location=meeting.location, instructors=[person.get("DisplayName") for person in meeting.instructors if person.get("DisplayName")]) for meeting in record.meetings if meeting.start and meeting.end] if include_meetings else None,
        ) for record in selected
    ]
    values = {"term": Term(id=selected[0].term.id, name=selected[0].term.name), "course_count": len(classes), "total_credits": sum(course.credits for course in classes), "classes": classes}
    return ClassesResult(retrieved_at=datetime.now(TIMEZONE), **values) if include_retrieved_at else TermClasses(**values)
