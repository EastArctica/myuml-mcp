"""Compact, agent-oriented projections of MyUML enrollment data."""

import re
from datetime import date, datetime
from zoneinfo import ZoneInfo

from pydantic import BaseModel, Field

from .api import EnrollmentRecord

TIMEZONE = ZoneInfo("America/New_York")
DAY_CODES = {"M": "MO", "T": "TU", "W": "WE", "R": "TH", "F": "FR", "S": "SA", "U": "SU"}


class Term(BaseModel):
    id: str
    name: str


class Meeting(BaseModel):
    days: list[str]
    start: str | None = Field(default=None, exclude_if=lambda value: value is None)
    end: str | None = Field(default=None, exclude_if=lambda value: value is None)
    timezone: str = "America/New_York"
    location: str | None = None
    instructors: list[str]
    is_tba: bool


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


def active_term(records: list[EnrollmentRecord], *, today: datetime | None = None) -> str:
    current_date = (today or datetime.now(TIMEZONE)).date()
    started_terms: set[str] = set()
    current_named_terms: set[str] = set()
    for record in records:
        if record.withdrawn or record.status.lower() != "enrolled":
            continue
        if _term_name_includes_date(record.term.name, current_date):
            current_named_terms.add(record.term.id)
        for meeting in record.meetings:
            if meeting.start_date and meeting.end_date:
                try:
                    start = datetime.fromisoformat(meeting.start_date).date()
                    end = datetime.fromisoformat(meeting.end_date).date()
                except ValueError:
                    continue
                if start <= current_date <= end:
                    return record.term.id
                if start <= current_date:
                    started_terms.add(record.term.id)
    return max(current_named_terms or started_terms, default="")


def _term_name_includes_date(term_name: str, current_date: date) -> bool:
    match = re.search(r"\b(spring|summer|fall|winter)\s+(\d{4})\b", term_name, re.IGNORECASE)
    if not match:
        return False
    season, year = match.groups()
    if int(year) != current_date.year:
        return season.lower() == "winter" and int(year) == current_date.year - 1 and current_date.month == 1
    return {
        "spring": current_date.month in {1, 2, 3, 4, 5},
        "summer": current_date.month in {5, 6, 7, 8},
        "fall": current_date.month in {8, 9, 10, 11, 12},
        "winter": current_date.month == 12,
    }[season.lower()]


def normalize(
    records: list[EnrollmentRecord],
    term_id: str,
    include_withdrawn: bool = False,
    *,
    include_meetings: bool = True,
    include_retrieved_at: bool = True,
) -> ClassesResult | TermClasses:
    selected = [
        record for record in records if record.term.id == term_id and (include_withdrawn or not record.withdrawn)
    ]
    if not selected:
        raise RuntimeError(f"No enrollment records found for term '{term_id}'.")
    classes = [
        Class(
            class_number=record.class_number,
            course=record.course,
            title=record.title,
            topic=record.topic,
            section=record.section,
            credits=record.credits,
            status=record.status.lower(),
            meetings=[
                Meeting(
                    days=[DAY_CODES.get(day, day) for day in (meeting.days or "")],
                    start=meeting.start[:5] if meeting.start else None,
                    end=meeting.end[:5] if meeting.end else None,
                    location=meeting.location,
                    instructors=[
                        person.get("DisplayName") for person in meeting.instructors if person.get("DisplayName")
                    ],
                    is_tba=not meeting.days and not meeting.start and not meeting.end,
                )
                for meeting in record.meetings
            ]
            if include_meetings
            else None,
        )
        for record in selected
    ]
    values = {
        "term": Term(id=selected[0].term.id, name=selected[0].term.name),
        "course_count": len(classes),
        "total_credits": sum(course.credits for course in classes),
        "classes": classes,
    }
    return (
        ClassesResult(retrieved_at=datetime.now(TIMEZONE), **values) if include_retrieved_at else TermClasses(**values)
    )
