from __future__ import annotations

import argparse
import json
import mimetypes
import secrets
import sys
from http.cookiejar import CookieJar
from pathlib import Path
from urllib import error, parse, request


def request_url(
    opener: request.OpenerDirector,
    url: str,
    *,
    method: str = "GET",
    data: bytes | None = None,
    headers: dict[str, str] | None = None,
    timeout: int = 300,
) -> tuple[int, str]:
    req = request.Request(url, data=data, method=method, headers=headers or {})
    try:
        with opener.open(req, timeout=timeout) as response:
            return response.status, response.read().decode("utf-8", errors="replace")
    except error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"{method} {url} failed with HTTP {exc.code}: {body}") from exc


def multipart_file(field_name: str, path: Path) -> tuple[bytes, str]:
    boundary = f"----sipam-kks-{secrets.token_hex(16)}"
    content_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
    body = bytearray()
    body.extend(f"--{boundary}\r\n".encode())
    body.extend(
        (
            f'Content-Disposition: form-data; name="{field_name}"; '
            f'filename="{path.name}"\r\n'
        ).encode()
    )
    body.extend(f"Content-Type: {content_type}\r\n\r\n".encode())
    body.extend(path.read_bytes())
    body.extend(f"\r\n--{boundary}--\r\n".encode())
    return bytes(body), f"multipart/form-data; boundary={boundary}"


def parse_json(payload: str) -> dict:
    try:
        return json.loads(payload)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Expected JSON response, got: {payload[:500]}") from exc


def main() -> int:
    parser = argparse.ArgumentParser(description="Upload and commit a KKS workbook to SIPAM.")
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--employee-no", required=True)
    parser.add_argument("--password", required=True)
    parser.add_argument("workbook", type=Path)
    args = parser.parse_args()

    workbook = args.workbook.resolve()
    if not workbook.exists():
        raise FileNotFoundError(workbook)

    base_url = args.base_url.rstrip("/")
    opener = request.build_opener(request.HTTPCookieProcessor(CookieJar()))

    request_url(opener, f"{base_url}/login")
    login_body = parse.urlencode(
        {"employee_no": args.employee_no, "password": args.password}
    ).encode()
    request_url(
        opener,
        f"{base_url}/login",
        method="POST",
        data=login_body,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )

    status_code, me_payload = request_url(opener, f"{base_url}/api/me")
    me = parse_json(me_payload)
    if not me.get("id"):
        raise RuntimeError(f"Login failed: {me_payload}")
    print(f"Logged in as {me.get('full_name')} ({me.get('employee_no')})")

    multipart_body, multipart_type = multipart_file("file", workbook)
    _, validation_payload = request_url(
        opener,
        f"{base_url}/api/kks-imports/validate",
        method="POST",
        data=multipart_body,
        headers={"Content-Type": multipart_type},
        timeout=600,
    )
    validation = parse_json(validation_payload)
    print(
        "Validated: "
        f"{validation.get('unique_assets')} unique, "
        f"{validation.get('new_assets')} new, "
        f"{validation.get('matched_assets')} matched, "
        f"{validation.get('duplicate_rows')} duplicates"
    )

    staged_id = validation["id"]
    _, import_payload = request_url(
        opener,
        f"{base_url}/api/kks-imports/{staged_id}/commit",
        method="POST",
        timeout=900,
    )
    imported = parse_json(import_payload)
    print(f"Committed staged import {staged_id}: {imported}")

    _, status_payload = request_url(opener, f"{base_url}/api/system/status")
    status = parse_json(status_payload)
    print(f"Live asset count: {status['counts']['assets']}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(str(exc), file=sys.stderr)
        raise SystemExit(1)
