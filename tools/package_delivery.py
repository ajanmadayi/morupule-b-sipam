from __future__ import annotations

import argparse
import hashlib
import json
import sys
import zipfile
from datetime import datetime, timezone
from pathlib import Path


DEFAULT_EXCLUDES = {
    ".venv",
    "venv",
    "__pycache__",
    ".pytest_cache",
    "uploads",
    "kks_staging",
    "backups",
    "instance",
    "dist",
}

EXCLUDED_SUFFIXES = {
    ".pyc",
    ".pyo",
    ".log",
    ".db",
    ".sqlite",
    ".sqlite3",
}


def should_include(path: Path, root: Path) -> bool:
    relative_parts = path.relative_to(root).parts
    if any(part in DEFAULT_EXCLUDES for part in relative_parts):
        return False
    if path.suffix.lower() in EXCLUDED_SUFFIXES:
        return False
    return True


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def collect_files(root: Path) -> list[Path]:
    return sorted(
        path for path in root.rglob("*")
        if path.is_file() and should_include(path, root)
    )


def build_manifest(root: Path, files: list[Path]) -> dict:
    return {
        "application": "S-PULSE",
        "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "source_root": str(root),
        "file_count": len(files),
        "excluded_runtime_data": sorted(DEFAULT_EXCLUDES),
        "files": [
            {
                "path": str(path.relative_to(root)).replace("\\", "/"),
                "bytes": path.stat().st_size,
                "sha256": sha256_file(path),
            }
            for path in files
        ],
    }


def create_package(root: Path, output: Path) -> tuple[Path, dict]:
    root = root.resolve()
    output = output.resolve()
    files = collect_files(root)
    manifest = build_manifest(root, files)
    output.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in files:
            archive.write(path, path.relative_to(root).as_posix())
        archive.writestr("DELIVERY_MANIFEST.json", json.dumps(manifest, indent=2))
    manifest["archive"] = str(output)
    manifest["archive_bytes"] = output.stat().st_size
    manifest["archive_sha256"] = sha256_file(output)
    return output, manifest


def main() -> int:
    parser = argparse.ArgumentParser(description="Create a clean S-PULSE delivery ZIP.")
    parser.add_argument(
        "--root",
        default=str(Path(__file__).resolve().parents[1]),
        help="Project root to package",
    )
    parser.add_argument(
        "--output",
        default="",
        help="Output ZIP path. Defaults to dist/spulse-delivery-<timestamp>.zip",
    )
    args = parser.parse_args()

    root = Path(args.root)
    if not root.exists():
        print(f"FAILED: root not found: {root}", file=sys.stderr)
        return 1
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    output = Path(args.output) if args.output else root / "dist" / f"spulse-delivery-{timestamp}.zip"
    try:
        archive, manifest = create_package(root, output)
    except Exception as error:
        print(f"FAILED: {error}", file=sys.stderr)
        return 1
    print(f"Created: {archive}")
    print(f"Files: {manifest['file_count']}")
    print(f"Archive bytes: {manifest['archive_bytes']}")
    print(f"SHA-256: {manifest['archive_sha256']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
