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

- `get_profile`: profile, shortcuts, and pin state
- `get_enrollment`: courses, meetings, instructors, grades, and LMS links
- `get_service_indicators`: holds
- `get_todo_items`: academic tasks
- `get_advisors`: advisor contacts
- `get_advising_appointments`: advising appointments
- `get_special_periods`: academic calendar periods
- `get_important_dates`: university deadlines and closures
- `get_campus_alerts`: UMass Lowell and system IT alerts
- `sync_pinned_shortcuts`: replace dashboard shortcut pins
