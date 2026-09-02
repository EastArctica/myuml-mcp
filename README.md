## MyUML MCP

An MCP server for the authenticated data APIs used by UMass Lowell's MyUML
mobile app. The available tools were derived only from the native app API calls.

### Authentication

Run the browser-assisted setup once:

```sh
uv run myuml-mcp login
```

It temporarily registers a handler for the native MyUML redirect URI, opens the
UMass Lowell SSO page, and saves the resulting API token to
`~/.config/myuml-mcp/token` with permissions set to `0600`. The server uses this
token automatically. Use `myuml-mcp setup` as an equivalent alias.

After UMass Lowell sign-in, select **Continue to iOS app**. The temporary
protocol handler receives that native-app redirect and finishes setup.

Alternatively, set `MYUML_TOKEN` to a current bearer token in the MCP server
environment. Environment configuration takes precedence over the saved token.
Tokens are not stored in this project.

```json
{
  "mcpServers": {
    "myuml": {
      "command": "uv",
      "args": ["run", "--directory", "/path/to/myuml-mcp", "myuml-mcp"],
      "env": {}
    }
  }
}
```

### Tools

All tool responses use snake_case keys. Fields whose source value is `null` or absent
are omitted; empty lists and `false` values are retained. Dates and times are returned
as supplied by MyUML, except normalized class meeting times are `HH:MM` in
`America/New_York`.

- `get_current_classes()` returns `{term, course_count, total_credits, classes,
  retrieved_at}` for the enrolled term containing today's dated meeting. If there is
  no active dated meeting, it recognizes a current term name (for example, `Fall
  2026`) or selects the latest enrolled term that has started; it does not select
  future registrations. `classes` includes meetings.
- `get_term_classes(term_id, include_withdrawn=false, include_meetings=true)` returns
  the same shape for one term. Set `include_meetings=false` for a compact response.
- `get_enrollment_history(term_start=null, term_end=null, include_withdrawn=false,
  include_meetings=false)` returns `{retrieved_at, term_count, terms}`. Term bounds
  are inclusive MyUML term IDs. Each term has the class-result shape without
  `retrieved_at`; meetings are omitted unless requested.
- Normalized classes contain `class_number`, `course`, `title`, optional `topic`,
  `section`, `credits`, lowercase `status`, and optional `meetings`. A meeting has
  `days`, optional `start`, optional `end`, `timezone`, optional `location`,
  `instructors`, and `is_tba`. TBA and online meetings are retained even when no
  meeting time is supplied.
- `get_full_enrollment()` returns all MyUML enrollment records as
  `{course, title, topic?, term, section, class_number, credits, status, withdrawn,
  meetings, lms?}`. This endpoint does not supply grades.
- `get_profile()` returns `{id_number, first_name, last_name, image?, is_valid,
  features, shortcuts}`. Shortcut entry fields are forwarded from MyUML using the
  response key policy above.
- `get_holds()` returns hold/service-indicator objects from MyUML. `get_todo_items()`
  and `get_advising_appointments()` likewise return their endpoint's objects. Their
  field sets are service-defined and are normalized to snake_case rather than treated
  as a stable academic-record schema.
- `get_advisors()`, `get_special_periods()`, `get_important_dates()`, and
  `get_campus_alerts()` return the corresponding MyUML data. `get_campus_alerts()`
  has `umass_lowell` and `umass_system_it` objects.
- `replace_pinned_shortcuts(pinned_shortcut_ids, confirm=false)` replaces the entire
  dashboard pin set and returns `{ok: true}`. It is destructive, requires
  `confirm=true`, and rejects duplicate or blank IDs. Call `get_profile()` first to
  inspect the available shortcut IDs.

`replace_pinned_shortcuts` is marked as a non-read-only, destructive, idempotent MCP
tool so capable clients can request appropriate confirmation. No tool in this server
claims to provide grades or other academic data not supplied by the observed MyUML
endpoints.
