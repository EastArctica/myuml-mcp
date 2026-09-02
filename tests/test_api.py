from myuml_mcp.api import APIObject, EnrollmentRecord, RawMeeting, agent_data


def test_nullable_upstream_meeting_fields_accept_missing_and_null() -> None:
    assert RawMeeting.model_validate({}).start is None
    assert RawMeeting.model_validate({"DailyStartTime": None, "DailyEndTime": None}).end is None
    assert RawMeeting.model_validate({"Instructors": None}).instructors == []
    assert (
        EnrollmentRecord.model_validate(
            {
                "CourseNumber": "COMP.1010",
                "Title": "Test",
                "Term": {"Id": "2267", "Description": "Fall 2026"},
                "Section": "001",
                "ClassNumber": 1,
                "Credits": 3,
                "EnrollmentStatusName": "Enrolled",
                "IsWithdrawn": False,
                "Meetings": None,
            }
        ).meetings
        == []
    )


def test_agent_data_normalizes_generic_endpoint_objects_and_omits_nulls() -> None:
    value = APIObject.model_validate(
        {"ServiceIndicatorCode": "HOLD", "Comment": None, "NestedValue": {"DisplayName": "Office"}}
    )

    assert agent_data(value) == {"service_indicator_code": "HOLD", "nested_value": {"display_name": "Office"}}
