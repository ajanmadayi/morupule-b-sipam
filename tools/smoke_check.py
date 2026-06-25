from __future__ import annotations

import argparse
import http.cookiejar
import json
import sys
import urllib.error
import urllib.parse
import urllib.request


DEFAULT_CHECKS = (
    ("GET", "/api/health", 200, None),
    ("GET", "/", 200, None),
    ("GET", "/api/me", 200, None),
    ("GET", "/api/dashboard", 200, None),
    ("GET", "/api/assets?reference=1", 200, None),
    ("GET", "/api/logbooks", 200, None),
    ("GET", "/api/events", 200, None),
    ("GET", "/api/corrective/summary", 200, None),
    ("GET", "/api/preventive/summary", 200, None),
    ("GET", "/api/permits/summary", 200, None),
    ("GET", "/api/infobox/summary", 200, None),
    ("GET", "/api/reports/summary", 200, None),
    ("GET", "/api/admin/logbooks", 200, "admin"),
    ("GET", "/api/users", 200, "admin"),
    ("GET", "/api/audit-logs/actions", 200, "admin"),
    ("GET", "/api/system/status", 200, "admin"),
    ("GET", "/api/system/backups", 200, "admin"),
)

SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "same-origin",
}


class SmokeFailure(RuntimeError):
    pass


def build_opener() -> urllib.request.OpenerDirector:
    jar = http.cookiejar.CookieJar()
    return urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))


def request(
    opener: urllib.request.OpenerDirector,
    base_url: str,
    method: str,
    path: str,
    data: dict[str, str] | None = None,
) -> urllib.response.addinfourl:
    encoded = None
    headers = {}
    if data is not None:
        encoded = urllib.parse.urlencode(data).encode("utf-8")
        headers["Content-Type"] = "application/x-www-form-urlencoded"
    return opener.open(
        urllib.request.Request(
            f"{base_url.rstrip('/')}{path}",
            data=encoded,
            headers=headers,
            method=method,
        ),
        timeout=20,
    )


def login(
    opener: urllib.request.OpenerDirector,
    base_url: str,
    employee_no: str,
    password: str,
) -> None:
    response = request(
        opener,
        base_url,
        "POST",
        "/login",
        {"employee_no": employee_no, "password": password},
    )
    body = response.read()
    if response.geturl().endswith("/login"):
        raise SmokeFailure(f"Login failed for {employee_no}; still on /login ({len(body)} bytes)")


def read_json(response: urllib.response.addinfourl) -> object:
    payload = response.read().decode("utf-8")
    return json.loads(payload) if payload else None


def check_security_headers(response: urllib.response.addinfourl) -> None:
    for header, expected in SECURITY_HEADERS.items():
        actual = response.headers.get(header)
        if actual != expected:
            raise SmokeFailure(f"{header} expected {expected!r}, got {actual!r}")
    csp = response.headers.get("Content-Security-Policy", "")
    if "frame-ancestors 'none'" not in csp:
        raise SmokeFailure("Content-Security-Policy missing frame-ancestors 'none'")
    permissions = response.headers.get("Permissions-Policy", "")
    if "camera=()" not in permissions or "microphone=()" not in permissions:
        raise SmokeFailure("Permissions-Policy missing disabled device permissions")


def run(args: argparse.Namespace) -> list[str]:
    user_opener = build_opener()
    admin_opener = build_opener()
    login(user_opener, args.base_url, args.user, args.password)
    login(admin_opener, args.base_url, args.admin_user, args.admin_password)

    results: list[str] = []
    for method, path, expected_status, required_role in DEFAULT_CHECKS:
        opener = admin_opener if required_role == "admin" else user_opener
        response = request(opener, args.base_url, method, path)
        if response.status != expected_status:
            raise SmokeFailure(f"{path} expected HTTP {expected_status}, got {response.status}")
        if path == "/":
            check_security_headers(response)
            response.read()
        else:
            read_json(response)
        results.append(f"OK {method} {path}")
    return results


def main() -> int:
    parser = argparse.ArgumentParser(description="Smoke-check the Morupule B SIPAM web app.")
    parser.add_argument("--base-url", default="http://127.0.0.1:5035")
    parser.add_argument("--user", default="MBPS-0104")
    parser.add_argument("--password", default="SIPAM@2026")
    parser.add_argument("--admin-user", default="MBPS-ADMIN")
    parser.add_argument("--admin-password", default="SIPAM@2026")
    args = parser.parse_args()
    try:
        for line in run(args):
            print(line)
    except (SmokeFailure, urllib.error.URLError, urllib.error.HTTPError, TimeoutError) as error:
        print(f"FAILED: {error}", file=sys.stderr)
        return 1
    print("Smoke check passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
