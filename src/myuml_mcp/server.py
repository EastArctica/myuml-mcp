"""Tools backed by endpoints observed in the MyUML mobile-app HAR capture."""

import json
import os
import platform
import secrets
import subprocess
import sys
import webbrowser
from base64 import urlsafe_b64decode
from binascii import Error as Base64Error
from datetime import datetime
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Any
from urllib.error import URLError
from urllib.parse import urlencode, urlparse
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

from mcp.server.mcpserver import MCPServer

from .api import MyUMLClient
from .schedule import ClassesResult, EnrollmentHistory, TermClasses, active_term, normalize

API_BASE = "https://www.uml.edu/api/myuml/v1.0"
ALERTS_BASE = "https://umasslowell.azure-api.net/alerts"
SSO_APP_FLOW = "https://www.uml.edu/sso/auth/applicationflow"
APP_URI = "umasslowell+8E541630036E4DDC9B8CD457F198A94E://auth?packageName=edu.uml.myuml"
APP_SCHEME = "umasslowell+8e541630036e4ddc9b8cd457f198a94e"

mcp = MCPServer(
    name="MyUML",
    description="Read academic and calendar data from UMass Lowell's MyUML service.",
)


def _token_path() -> Path:
    config_home = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
    return config_home / "myuml-mcp" / "token"


def _load_token() -> str | None:
    return os.environ.get("MYUML_TOKEN") or (_token_path().read_text().strip() if _token_path().is_file() else None)


def _client() -> MyUMLClient:
    token = _load_token()
    if not token:
        raise RuntimeError("MyUML is not configured. Run 'myuml-mcp login' or set MYUML_TOKEN.")
    return MyUMLClient(token)


def _login_state_path() -> Path:
    return Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache")) / "myuml-mcp" / "login.json"


def _token_from_uri(uri: str) -> str:
    fragment = urlparse(uri).fragment
    decoded = urlsafe_b64decode(fragment + "=" * (-len(fragment) % 4))
    token = json.loads(decoded)["accessTokens"]["uml.mobile.myuml"]
    if not isinstance(token, str):
        raise TypeError("token is not a string")
    return token


@mcp.tool()
def get_current_classes() -> ClassesResult:
    """Return the authenticated student's enrolled classes for the current academic term, including meeting times, locations, instructors, and credit total. Use for “what classes do I have?”, schedule checks, and current-term planning. Does not return prior terms, grades, or withdrawn classes."""
    records = _client().enrollment()
    return normalize(records, active_term(records))


@mcp.tool()
def get_term_classes(term_id: str, include_withdrawn: bool = False) -> ClassesResult:
    """Return normalized classes for one MyUML term ID. Use get_current_classes first to discover the current term ID."""
    result = normalize(_client().enrollment(), term_id, include_withdrawn)
    assert isinstance(result, ClassesResult)
    return result


@mcp.tool()
def get_enrollment_history(term_start: str | None = None, term_end: str | None = None, include_withdrawn: bool = False) -> EnrollmentHistory:
    """Return compact enrollment history, optionally bounded by inclusive MyUML term IDs."""
    records = _client().enrollment()
    term_ids = sorted({record.term.id for record in records})
    term_ids = [term_id for term_id in term_ids if (term_start is None or term_id >= term_start) and (term_end is None or term_id <= term_end)]
    terms = [normalize(records, term_id, include_withdrawn, include_retrieved_at=False) for term_id in term_ids]
    return EnrollmentHistory(retrieved_at=datetime.now(ZoneInfo("America/New_York")), term_count=len(terms), terms=[term for term in terms if isinstance(term, TermClasses)])


@mcp.tool()
def get_profile() -> dict[str, Any]:
    """Get the signed-in student's MyUML profile, available shortcuts, and shortcut pin state."""
    return _client().profile()


@mcp.tool()
def get_enrollment() -> list[dict[str, Any]]:
    """Get enrolled and recent classes, including meetings, instructors, grades, and Canvas links."""
    return [record.model_dump() for record in _client().enrollment()]


@mcp.tool()
def get_service_indicators() -> list[dict[str, Any]]:
    """Get academic service indicators (holds) on the student's record."""
    return _client().service_indicators()


@mcp.tool()
def get_todo_items() -> list[dict[str, Any]]:
    """Get academic to-do items assigned to the student."""
    return _client().todo_items()


@mcp.tool()
def get_advisors() -> list[dict[str, Any]]:
    """Get the student's academic advisors and contact details."""
    return _client().advisors()


@mcp.tool()
def get_advising_appointments() -> list[dict[str, Any]]:
    """Get the student's advising appointments."""
    return _client().advising_appointments()


@mcp.tool()
def get_special_periods() -> list[dict[str, Any]]:
    """Get MyUML calendar special periods, such as add/drop or registration periods."""
    return _client().special_periods()


@mcp.tool()
def get_important_dates() -> list[dict[str, Any]]:
    """Get university important dates, deadlines, and closures."""
    return _client().important_dates()


@mcp.tool()
def get_campus_alerts() -> dict[str, Any]:
    """Get active UMass Lowell and UMass system IT alerts."""
    return _client().campus_alerts()


@mcp.tool()
def replace_pinned_shortcuts(pinned_shortcut_ids: list[str]) -> dict[str, Any]:
    """Replace the MyUML dashboard's pinned shortcuts with the supplied shortcut IDs. Use get_profile first to discover IDs."""
    return _client().sync_pinned_shortcuts(pinned_shortcut_ids)


def login() -> None:
    """Authenticate through browser SSO and save the MyUML token for this user."""
    token: list[str] = []
    nonce = secrets.token_urlsafe(24)

    class CallbackHandler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            self.send_error(404)

        def do_POST(self) -> None:
            if self.path != f"/{nonce}":
                self.send_error(404)
                return
            token.append(self.rfile.read(int(self.headers.get("Content-Length", "0"))).decode())
            self.send_response(204)
            self.end_headers()

        def log_message(self, format: str, *args: object) -> None:
            return

    server = HTTPServer(("127.0.0.1", 0), CallbackHandler)
    state = _login_state_path()
    state.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    state.write_text(json.dumps({"port": server.server_port, "nonce": nonce}))
    state.chmod(0o600)
    cleanup = _install_protocol_handler()
    login_url = f"{SSO_APP_FLOW}?{urlencode({'appUri': APP_URI})}"
    print("Opening UMass Lowell sign-in in your browser. Complete sign-in there.")
    print("After signing in, select 'Continue to iOS app' to finish MyUML setup.")
    print(f"If the browser does not open, visit: {login_url}")
    try:
        webbrowser.open(login_url)
        server.timeout = 1
        while not token:
            server.handle_request()
    finally:
        state.unlink(missing_ok=True)
        cleanup()
        server.server_close()

    path = _token_path()
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    path.write_text(token[0] + "\n")
    path.chmod(0o600)
    print(f"MyUML token saved to {path}")


def receive_uri(uri: str) -> None:
    """Entry point invoked by the temporary OS URL-scheme handler."""
    try:
        token = _token_from_uri(uri)
        state = json.loads(_login_state_path().read_text())
        request = Request(f"http://127.0.0.1:{state['port']}/{state['nonce']}", data=token.encode(), method="POST")
        urlopen(request, timeout=5).close()
    except (Base64Error, KeyError, OSError, ValueError, json.JSONDecodeError, URLError) as error:
        print(f"MyUML login redirect could not be received: {error}", file=sys.stderr)


def _install_protocol_handler() -> Any:
    system = platform.system()
    command = f'"{sys.executable}" -m myuml_mcp receive-uri %u'
    if system == "Linux":
        applications = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local/share")) / "applications"
        desktop = applications / "myuml-mcp-login.desktop"
        applications.mkdir(parents=True, exist_ok=True)
        previous = subprocess.run(["xdg-mime", "query", "default", f"x-scheme-handler/{APP_SCHEME}"], capture_output=True, check=False, text=True).stdout.strip()
        desktop.write_text(f"[Desktop Entry]\nType=Application\nName=MyUML Login\nNoDisplay=true\nExec={command}\nMimeType=x-scheme-handler/{APP_SCHEME};\n")
        subprocess.run(["xdg-mime", "default", desktop.name, f"x-scheme-handler/{APP_SCHEME}"], check=True)
        def cleanup() -> None:
            if previous:
                subprocess.run(["xdg-mime", "default", previous, f"x-scheme-handler/{APP_SCHEME}"], check=False)
            desktop.unlink(missing_ok=True)
        return cleanup
    if system == "Windows":
        print("Warning: temporary protocol handling is untested on Windows.", file=sys.stderr)
        import winreg
        key = winreg.CreateKey(winreg.HKEY_CURRENT_USER, fr"Software\Classes\{APP_SCHEME}\shell\open\command")
        winreg.SetValue(key, "", winreg.REG_SZ, command.replace("%u", "%1"))
        winreg.CloseKey(key)
        return lambda: None
    if system == "Darwin":
        print("Warning: temporary protocol handling is untested on macOS.", file=sys.stderr)
        raise RuntimeError("macOS temporary URL handler registration is not yet available.")
    raise RuntimeError(f"Unsupported platform: {system}")


def main() -> None:
    """Run the server over standard input/output for an MCP client."""
    if len(sys.argv) == 2 and sys.argv[1] in {"login", "setup"}:
        login()
        return
    if len(sys.argv) == 3 and sys.argv[1] == "receive-uri":
        receive_uri(sys.argv[2])
        return
    if not _load_token():
        print(
            "Warning: MyUML server is unauthenticated. Run 'myuml-mcp login' or set MYUML_TOKEN.",
            file=sys.stderr,
        )
    mcp.run(transport="stdio")
