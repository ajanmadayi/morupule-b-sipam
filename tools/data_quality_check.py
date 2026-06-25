from __future__ import annotations

import argparse
import sqlite3
import sys
from pathlib import Path


CORE_TABLES = {
    "assets": "KKS assets",
    "logbooks": "Logbooks",
    "event_entries": "Event Log entries",
    "work_requests": "Corrective work requests",
    "work_orders": "Corrective work orders",
    "recurrent_tasks": "Preventive recurrent tasks",
    "preventive_tasks": "Generated preventive tasks",
    "safety_permits": "PTW / LoA records",
    "inbox_items": "Infobox items",
    "users": "Users",
    "audit_logs": "Audit logs",
    "backup_runs": "Backup records",
    "restore_runs": "Restore records",
}


CHECK_QUERIES = (
    (
        "assets_without_kks",
        """
        SELECT COUNT(*) FROM assets
        WHERE TRIM(COALESCE(kks_code, '')) = ''
        """,
        "Assets without KKS code",
    ),
    (
        "active_users_without_role",
        """
        SELECT COUNT(*) FROM users
        WHERE status = 'active' AND TRIM(COALESCE(role_name, '')) = ''
        """,
        "Active users without role",
    ),
    (
        "open_events_without_subject",
        """
        SELECT COUNT(*) FROM event_entries
        WHERE state = 'open' AND TRIM(COALESCE(subject, '')) = ''
        """,
        "Open Event Log entries without subject",
    ),
    (
        "work_requests_without_asset",
        """
        SELECT COUNT(*) FROM work_requests
        WHERE asset_id IS NULL
        """,
        "Corrective requests without KKS asset",
    ),
    (
        "active_permits_without_asset",
        """
        SELECT COUNT(*) FROM safety_permits
        WHERE status IN ('prepared', 'issued', 'received', 'cleared') AND asset_id IS NULL
        """,
        "Active permit records without KKS asset",
    ),
    (
        "available_backups_not_verified",
        """
        SELECT COUNT(*) FROM backup_runs
        WHERE status = 'available' AND integrity != 'verified'
        """,
        "Available recovery points not verified",
    ),
)


def connect(database_path: Path) -> sqlite3.Connection:
    if not database_path.exists():
        raise FileNotFoundError(f"Database not found: {database_path}")
    connection = sqlite3.connect(database_path)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def table_exists(connection: sqlite3.Connection, table: str) -> bool:
    row = connection.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?",
        (table,),
    ).fetchone()
    return row is not None


def count_rows(connection: sqlite3.Connection, table: str) -> int | None:
    if not table_exists(connection, table):
        return None
    return int(connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])


def run_checks(database_path: Path) -> tuple[list[str], list[str]]:
    lines: list[str] = []
    warnings: list[str] = []
    with connect(database_path) as connection:
        integrity = connection.execute("PRAGMA integrity_check").fetchone()[0]
        lines.append(f"Database: {database_path}")
        lines.append(f"Integrity: {integrity}")
        if integrity != "ok":
            warnings.append(f"SQLite integrity check returned {integrity!r}")

        foreign_key_issues = connection.execute("PRAGMA foreign_key_check").fetchall()
        lines.append(f"Foreign key issues: {len(foreign_key_issues)}")
        if foreign_key_issues:
            warnings.append(f"{len(foreign_key_issues)} foreign key issue(s) found")

        lines.append("")
        lines.append("Record counts:")
        for table, label in CORE_TABLES.items():
            count = count_rows(connection, table)
            if count is None:
                lines.append(f"- {label}: missing table")
                warnings.append(f"Missing required table: {table}")
            else:
                lines.append(f"- {label}: {count:,}")

        lines.append("")
        lines.append("Data checks:")
        for key, sql, label in CHECK_QUERIES:
            try:
                value = int(connection.execute(sql).fetchone()[0])
            except sqlite3.Error as error:
                value = -1
                warnings.append(f"{key} failed: {error}")
            status = "OK" if value == 0 else "REVIEW"
            lines.append(f"- {label}: {value:,} [{status}]")
            if value > 0:
                warnings.append(f"{label}: {value:,}")
    return lines, warnings


def main() -> int:
    parser = argparse.ArgumentParser(description="Offline SQLite data-quality check for Morupule B SIPAM.")
    parser.add_argument(
        "--database",
        default=str(Path(__file__).resolve().parents[1] / "morupule_sipam.db"),
        help="Path to morupule_sipam.db",
    )
    args = parser.parse_args()
    try:
        lines, warnings = run_checks(Path(args.database))
    except Exception as error:
        print(f"FAILED: {error}", file=sys.stderr)
        return 1
    print("\n".join(lines))
    if warnings:
        print("")
        print("Warnings:")
        for warning in warnings:
            print(f"- {warning}")
        return 2
    print("")
    print("Data quality check passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
