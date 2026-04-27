"""OAuth2 Authorization Code + PKCE flow for Gateway JWT auth.

Starts a local HTTP server, opens the browser to the authorize endpoint,
catches the callback with the auth code, and exchanges it for a JWT token.

Required environment variables:
  GATEWAY_CLIENT_ID       — OAuth2 client ID
  GATEWAY_CLIENT_SECRET   — OAuth2 client secret
  GATEWAY_TOKEN_URL       — Token endpoint URL
  GATEWAY_AUTHORIZE_URL   — Authorization endpoint URL

Optional:
  GATEWAY_REDIRECT_PORT   — Local callback port (default: 8765)
"""

import hashlib
import http.server
import json
import os
import secrets
import time
import urllib.parse
import urllib.request
import webbrowser
from base64 import urlsafe_b64decode, urlsafe_b64encode
from pathlib import Path


TOKEN_CACHE_FILE = Path(__file__).parent.parent.parent / ".gateway-token.json"

# Refresh token 60 seconds before actual expiry
EXPIRY_BUFFER_SECONDS = 60


def _require_env(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise RuntimeError(f"Required environment variable {name} is not set")
    return value


def _decode_jwt_payload(token: str) -> dict:
    """Decode JWT payload without verification (just to read exp claim)."""
    parts = token.split(".")
    if len(parts) != 3:
        return {}
    # Add padding
    payload_b64 = parts[1] + "=" * (4 - len(parts[1]) % 4)
    try:
        return json.loads(urlsafe_b64decode(payload_b64))
    except (json.JSONDecodeError, ValueError):
        return {}


def _is_token_valid(token: str) -> bool:
    """Check if a JWT token is still valid (not expired)."""
    payload = _decode_jwt_payload(token)
    exp = payload.get("exp")
    if not exp:
        return False
    return time.time() < (exp - EXPIRY_BUFFER_SECONDS)


def _generate_pkce() -> tuple[str, str]:
    """Generate PKCE code_verifier and code_challenge."""
    verifier = secrets.token_urlsafe(64)
    challenge = urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    return verifier, challenge


def _exchange_code(code: str, code_verifier: str, redirect_uri: str) -> dict:
    """Exchange authorization code for tokens."""
    client_id = _require_env("GATEWAY_CLIENT_ID")
    client_secret = _require_env("GATEWAY_CLIENT_SECRET")
    token_url = _require_env("GATEWAY_TOKEN_URL")

    data = urllib.parse.urlencode(
        {
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": redirect_uri,
            "client_id": client_id,
            "client_secret": client_secret,
            "code_verifier": code_verifier,
        }
    ).encode()

    req = urllib.request.Request(token_url, data=data, method="POST")
    req.add_header("Content-Type", "application/x-www-form-urlencoded")

    resp = urllib.request.urlopen(req, timeout=15)
    return json.loads(resp.read().decode())


def get_cached_token() -> str | None:
    """Return a valid cached token, or None if missing/expired."""
    if not TOKEN_CACHE_FILE.exists():
        return None
    try:
        cached = json.loads(TOKEN_CACHE_FILE.read_text())
    except (json.JSONDecodeError, OSError):
        return None
    token = cached.get("id_token") or cached.get("access_token")
    if token and _is_token_valid(token):
        return token
    return None


def get_token_interactive(port: int | None = None) -> str:
    """Run full OAuth2 PKCE flow with browser. Returns the access/id token.

    Uses cached token if still valid; otherwise opens browser for auth.
    """
    cached = get_cached_token()
    if cached:
        return cached

    client_id = _require_env("GATEWAY_CLIENT_ID")
    authorize_url = _require_env("GATEWAY_AUTHORIZE_URL")
    port = port or int(os.environ.get("GATEWAY_REDIRECT_PORT", "8765"))
    redirect_uri = f"http://localhost:{port}/callback"

    code_verifier, code_challenge = _generate_pkce()
    state = secrets.token_urlsafe(16)

    result = {"code": None, "error": None}

    class CallbackHandler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            parsed = urllib.parse.urlparse(self.path)
            params = urllib.parse.parse_qs(parsed.query)

            if params.get("state", [None])[0] != state:
                result["error"] = "State mismatch"
                self.send_response(400)
                self.end_headers()
                self.wfile.write(b"State mismatch - possible CSRF")
                return

            if "error" in params:
                result["error"] = params["error"][0]
                self.send_response(400)
                self.end_headers()
                self.wfile.write(f"Error: {params['error'][0]}".encode())
                return

            result["code"] = params.get("code", [None])[0]
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"<html><body><h2>Authenticated! You can close this tab.</h2></body></html>")

        def log_message(self, format, *args):
            pass  # Suppress logs

    server = http.server.HTTPServer(("localhost", port), CallbackHandler)
    server.timeout = 120

    params = urllib.parse.urlencode(
        {
            "response_type": "code",
            "client_id": client_id,
            "redirect_uri": redirect_uri,
            "scope": "openid",
            "state": state,
            "code_challenge": code_challenge,
            "code_challenge_method": "S256",
        }
    )
    auth_url = f"{authorize_url}?{params}"

    print("Opening browser for authentication...")
    print(f"If browser doesn't open, visit: {auth_url}")
    webbrowser.open(auth_url)

    server.handle_request()
    server.server_close()

    if result["error"]:
        raise RuntimeError(f"OAuth error: {result['error']}")
    if not result["code"]:
        raise RuntimeError("No authorization code received")

    token_data = _exchange_code(result["code"], code_verifier, redirect_uri)

    TOKEN_CACHE_FILE.write_text(json.dumps(token_data, indent=2))
    print("Token cached to .gateway-token.json")

    return token_data.get("id_token") or token_data.get("access_token")


if __name__ == "__main__":
    token = get_token_interactive()
    print(f"\nToken (first 50 chars): {token[:50]}...")
