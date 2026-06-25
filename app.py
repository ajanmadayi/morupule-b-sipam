from __future__ import annotations

import sqlite3
import calendar
import os
import json
import csv
import io
import uuid
import zipfile
import tempfile
import shutil
import hashlib
from functools import wraps
from datetime import date, datetime, timedelta
from pathlib import Path

from flask import (
    Flask, abort, g, jsonify, redirect, render_template, request,
    session, url_for, Response, send_from_directory, send_file,
)
from werkzeug.security import check_password_hash, generate_password_hash
from werkzeug.utils import secure_filename


BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = Path(os.environ.get("SIPAM_DATA_DIR", BASE_DIR)).resolve()
DATABASE = Path(os.environ.get("SIPAM_DATABASE", DATA_DIR / "morupule_sipam.db")).resolve()
UPLOAD_DIR = Path(os.environ.get("SIPAM_UPLOAD_FOLDER", DATA_DIR / "uploads")).resolve()
KKS_STAGING_DIR = Path(os.environ.get("SIPAM_KKS_STAGING_FOLDER", DATA_DIR / "kks_staging")).resolve()
BACKUP_DIR = Path(os.environ.get("SIPAM_BACKUP_FOLDER", DATA_DIR / "backups")).resolve()

app = Flask(__name__)
app.config["DATABASE"] = DATABASE
app.config["UPLOAD_FOLDER"] = UPLOAD_DIR
app.config["KKS_STAGING_FOLDER"] = KKS_STAGING_DIR
app.config["BACKUP_FOLDER"] = BACKUP_DIR
app.config["JSON_SORT_KEYS"] = False
app.config["MAX_CONTENT_LENGTH"] = 10 * 1024 * 1024
app.config["SECRET_KEY"] = os.environ.get(
    "SIPAM_SECRET_KEY", "morupule-b-sipam-development-key"
)
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
app.config["SESSION_COOKIE_SECURE"] = os.environ.get("SIPAM_COOKIE_SECURE") == "1"

USER_ROLES = (
    "Shift Leader",
    "Maintenance Approver",
    "Maintenance Planner",
    "C&I Technician",
    "Electrical Technician",
    "Mechanical Technician",
    "System Administrator",
)

ROLE_GROUPS = {
    "Shift Leader": ("SHIFT_LEADERS",),
    "Maintenance Approver": ("MAINT_APPROVERS", "MAINT_PLANNERS"),
    "Maintenance Planner": ("MAINT_PLANNERS",),
    "C&I Technician": ("CI_TEAM",),
    "Electrical Technician": ("ELEC_TEAM",),
    "Mechanical Technician": ("MECH_TEAM",),
    "System Administrator": (),
}

SAFETY_FORM_TYPES = (
    "electrical_ptw",
    "mechanical_ptw",
    "electrical_loa",
    "mechanical_loa",
    "electrical_sft",
    "mechanical_sft",
)

ATTACHMENT_ENTITIES = {
    "event": ("event_entries", "id"),
    "corrective": ("work_requests", "id"),
    "preventive": ("recurrent_tasks", "id"),
    "permit": ("safety_permits", "id"),
}

ALLOWED_ATTACHMENT_EXTENSIONS = {
    "pdf", "png", "jpg", "jpeg", "webp", "doc", "docx", "xls", "xlsx",
    "csv", "txt",
}

CMPT_CATEGORIES = {
    "P": "People (Safety risk)",
    "E": "Environmental",
    "A": "Asset Damage / Production Loss",
    "R": "Reputation / Personnel / Welfare",
}

CMPT_MATRIX = {
    0: {"A": 6, "B": 6, "C": 6, "D": 6, "E": 6},
    1: {"A": 6, "B": 6, "C": 5, "D": 4, "E": 3},
    2: {"A": 6, "B": 5, "C": 4, "D": 3, "E": 2},
    3: {"A": 5, "B": 4, "C": 3, "D": 2, "E": 1},
    4: {"A": 4, "B": 3, "C": 2, "D": 1, "E": 1},
    5: {"A": 3, "B": 2, "C": 1, "D": 1, "E": 1},
}


def calculate_cmpt_priority(severity: int, likelihood: str) -> int:
    return CMPT_MATRIX[severity][likelihood]


def cmpt_response_target(created_at: str, priority: int) -> str | None:
    response_days = {1: 0, 2: 2, 3: 14, 4: 56, 5: 183}
    if priority not in response_days:
        return None
    created = datetime.fromisoformat(created_at)
    return (created + timedelta(days=response_days[priority])).isoformat(timespec="minutes")


def get_db() -> sqlite3.Connection:
    if "db" not in g:
        connection = sqlite3.connect(app.config["DATABASE"])
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        g.db = connection
    return g.db


@app.teardown_appcontext
def close_db(_error: BaseException | None) -> None:
    connection = g.pop("db", None)
    if connection is not None:
        connection.close()


def row_to_dict(row: sqlite3.Row) -> dict:
    return {key: row[key] for key in row.keys()}


def audit_action_name(method: str, path: str) -> str:
    if path.endswith("/claim"):
        return "Claimed Infobox item"
    if path.endswith("/release"):
        return "Released Infobox item"
    if path.endswith("/reset-password"):
        return "Reset user password"
    if "/decision" in path:
        return "Decided work request"
    if "/transition" in path:
        return "Changed permit status"
    if path.endswith("/state"):
        return "Changed event state"
    if path.endswith("/complete"):
        return "Completed preventive task"
    if path.endswith("/generate"):
        return "Generated preventive task"
    return {
        "POST": "Created record",
        "PATCH": "Updated record",
        "DELETE": "Deleted record",
    }.get(method, "Changed record")


def sanitized_request_details() -> str | None:
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return None
    blocked = {"password", "password_hash", "current_password"}
    safe = {
        key: value for key, value in payload.items()
        if key.lower() not in blocked
    }
    return json.dumps(safe, ensure_ascii=True, default=str)[:4000]


def record_audit(
    action: str,
    target: str,
    method: str,
    status_code: int,
    details: str | None = None,
    user: sqlite3.Row | None = None,
) -> None:
    actor = user if user is not None else getattr(g, "current_user", None)
    database = get_db()
    database.execute(
        """
        INSERT INTO audit_logs (
            user_id, employee_no, user_name, role_name, action, target,
            method, status_code, details, ip_address, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            actor["id"] if actor else None,
            actor["employee_no"] if actor else None,
            actor["full_name"] if actor else None,
            actor["role_name"] if actor else None,
            action,
            target,
            method,
            status_code,
            details,
            request.remote_addr,
            datetime.now().isoformat(timespec="seconds"),
        ),
    )
    database.commit()


def report_date_range() -> tuple[str, str]:
    end_value = str(request.args.get("end") or date.today().isoformat())
    start_value = str(
        request.args.get("start") or (date.today() - timedelta(days=30)).isoformat()
    )
    try:
        start_date = date.fromisoformat(start_value)
        end_date = date.fromisoformat(end_value)
    except ValueError:
        abort(400, description="Report dates must use YYYY-MM-DD")
    if start_date > end_date:
        abort(400, description="Report start date cannot be after end date")
    return start_date.isoformat(), end_date.isoformat()


def attachment_rows(entity_type: str, entity_id: int) -> list[dict]:
    rows = get_db().execute(
        """
        SELECT id, entity_type, entity_id, original_name, content_type,
            file_size, uploaded_by_name, created_at
        FROM attachments
        WHERE entity_type = ? AND entity_id = ?
        ORDER BY created_at DESC, id DESC
        """,
        (entity_type, entity_id),
    ).fetchall()
    return [row_to_dict(row) for row in rows]


def validate_attachment_entity(entity_type: str, entity_id: int) -> None:
    entity = ATTACHMENT_ENTITIES.get(entity_type)
    if entity is None:
        abort(400, description="Unsupported attachment entity")
    table, id_column = entity
    row = get_db().execute(
        f"SELECT {id_column} FROM {table} WHERE {id_column} = ?",
        (entity_id,),
    ).fetchone()
    if row is None:
        abort(404)


def init_db() -> None:
    database = get_db()
    database.executescript(
        """
        CREATE TABLE IF NOT EXISTS assets (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            parent_id INTEGER REFERENCES assets(id),
            kks_code TEXT NOT NULL UNIQUE,
            description TEXT NOT NULL,
            hierarchy_level TEXT NOT NULL,
            level_no INTEGER NOT NULL,
            plant_code TEXT,
            system_code TEXT,
            equipment_code TEXT,
            component_code TEXT,
            responsible_area TEXT,
            source_kind TEXT NOT NULL DEFAULT 'reference',
            source_row INTEGER,
            is_reference INTEGER NOT NULL DEFAULT 0,
            status TEXT NOT NULL DEFAULT 'active'
                CHECK (status IN ('active', 'inactive'))
        );

        CREATE TABLE IF NOT EXISTS kks_import_issues (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source_file TEXT NOT NULL,
            source_row INTEGER,
            issue_type TEXT NOT NULL,
            kks_code TEXT,
            description TEXT,
            responsible_area TEXT,
            details TEXT,
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS kks_import_runs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source_file TEXT NOT NULL,
            imported_at TEXT NOT NULL,
            source_rows INTEGER NOT NULL,
            unique_assets INTEGER NOT NULL,
            duplicate_rows INTEGER NOT NULL,
            inferred_parents INTEGER NOT NULL
        );

        CREATE TABLE IF NOT EXISTS kks_staged_imports (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            original_name TEXT NOT NULL,
            stored_name TEXT NOT NULL UNIQUE,
            source_rows INTEGER NOT NULL,
            unique_assets INTEGER NOT NULL,
            duplicate_rows INTEGER NOT NULL,
            blank_kks_rows INTEGER NOT NULL,
            inferred_parents INTEGER NOT NULL,
            new_assets INTEGER NOT NULL,
            matched_assets INTEGER NOT NULL,
            status TEXT NOT NULL CHECK (status IN ('validated', 'imported', 'failed')),
            validated_by TEXT NOT NULL,
            validated_at TEXT NOT NULL,
            imported_by TEXT,
            imported_at TEXT,
            error_message TEXT
        );

        CREATE TABLE IF NOT EXISTS logbooks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            code TEXT NOT NULL UNIQUE,
            name TEXT NOT NULL UNIQUE,
            department TEXT NOT NULL,
            can_create_role TEXT NOT NULL,
            is_shift_leader INTEGER NOT NULL DEFAULT 0
        );

        CREATE TABLE IF NOT EXISTS event_entries (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            parent_id INTEGER REFERENCES event_entries(id) ON DELETE CASCADE,
            source_logbook_id INTEGER NOT NULL REFERENCES logbooks(id),
            entry_no TEXT NOT NULL UNIQUE,
            entry_type TEXT NOT NULL DEFAULT 'Information',
            subject TEXT NOT NULL,
            asset_id INTEGER REFERENCES assets(id),
            event_date TEXT NOT NULL,
            state TEXT NOT NULL CHECK (state IN ('open', 'closed')),
            observation TEXT NOT NULL,
            informant TEXT,
            created_by TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS event_entry_logbooks (
            entry_id INTEGER NOT NULL REFERENCES event_entries(id) ON DELETE CASCADE,
            logbook_id INTEGER NOT NULL REFERENCES logbooks(id) ON DELETE CASCADE,
            is_copy INTEGER NOT NULL DEFAULT 0,
            PRIMARY KEY (entry_id, logbook_id)
        );

        CREATE TABLE IF NOT EXISTS event_state_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            event_id INTEGER NOT NULL REFERENCES event_entries(id) ON DELETE CASCADE,
            previous_state TEXT NOT NULL,
            new_state TEXT NOT NULL,
            changed_by TEXT NOT NULL,
            reason TEXT NOT NULL,
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS event_edit_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            event_id INTEGER NOT NULL REFERENCES event_entries(id) ON DELETE CASCADE,
            changed_by TEXT NOT NULL,
            changes TEXT NOT NULL,
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS event_deletion_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            entry_no TEXT NOT NULL,
            snapshot TEXT NOT NULL,
            deleted_by TEXT NOT NULL,
            reason TEXT NOT NULL,
            deleted_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS shift_handovers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            handover_no TEXT NOT NULL UNIQUE,
            shift_date TEXT NOT NULL,
            shift_name TEXT NOT NULL,
            outgoing_user_id INTEGER NOT NULL REFERENCES users(id),
            incoming_user_id INTEGER REFERENCES users(id),
            status TEXT NOT NULL DEFAULT 'draft'
                CHECK (status IN ('draft', 'submitted', 'accepted')),
            summary TEXT NOT NULL,
            safety_notes TEXT,
            operational_notes TEXT,
            acceptance_notes TEXT,
            submitted_at TEXT,
            accepted_at TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS shift_handover_events (
            handover_id INTEGER NOT NULL REFERENCES shift_handovers(id) ON DELETE CASCADE,
            event_id INTEGER NOT NULL REFERENCES event_entries(id),
            state_at_handover TEXT NOT NULL,
            PRIMARY KEY (handover_id, event_id)
        );

        CREATE TABLE IF NOT EXISTS work_requests (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            request_no TEXT NOT NULL UNIQUE,
            source_event_id INTEGER REFERENCES event_entries(id),
            asset_id INTEGER NOT NULL REFERENCES assets(id),
            name TEXT NOT NULL,
            asset_type TEXT,
            type_of_work TEXT NOT NULL,
            main_department TEXT NOT NULL,
            priority INTEGER NOT NULL CHECK (priority BETWEEN 1 AND 6),
            cmpt_primary TEXT,
            cmpt_impacts TEXT NOT NULL DEFAULT '[]',
            cmpt_severity INTEGER,
            cmpt_likelihood TEXT,
            target_response_at TEXT,
            planned_start TEXT,
            planned_end TEXT,
            reminder_days INTEGER NOT NULL DEFAULT 0,
            show_in_history INTEGER NOT NULL DEFAULT 1,
            observation TEXT NOT NULL,
            author TEXT NOT NULL,
            status TEXT NOT NULL CHECK (status IN ('submitted', 'approved', 'declined')),
            decision_by TEXT,
            decision_reason TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS work_request_edit_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            work_request_id INTEGER NOT NULL REFERENCES work_requests(id) ON DELETE CASCADE,
            changed_by TEXT NOT NULL,
            changes TEXT NOT NULL,
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS work_orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            order_no TEXT NOT NULL UNIQUE,
            work_request_id INTEGER NOT NULL UNIQUE REFERENCES work_requests(id),
            workflow_step TEXT NOT NULL CHECK (
                workflow_step IN (
                    'planning', 'plan_approval', 'permit_decision', 'execution',
                    'work_check', 'rework', 'closed'
                )
            ),
            description_of_work TEXT NOT NULL DEFAULT '',
            maintenance_code TEXT NOT NULL DEFAULT '',
            equipment_condition TEXT NOT NULL DEFAULT '',
            workplace_requirements TEXT NOT NULL DEFAULT '',
            expected_man_hours REAL NOT NULL DEFAULT 0,
            permit_requirement TEXT NOT NULL DEFAULT 'undecided'
                CHECK (permit_requirement IN ('undecided', 'none', 'ptw', 'loa')),
            permit_status TEXT NOT NULL DEFAULT 'not_required'
                CHECK (permit_status IN ('not_required', 'required', 'issued', 'cancelled')),
            plan_approved_by TEXT,
            execution_confirmed_by TEXT,
            execution_started_at TEXT,
            acceptance_status TEXT NOT NULL DEFAULT 'pending'
                CHECK (acceptance_status IN ('pending', 'accepted', 'denied')),
            acceptance_reason TEXT,
            closed_by TEXT,
            completion_summary TEXT,
            actual_man_hours REAL,
            failure_mode TEXT,
            failure_cause TEXT,
            downtime_started_at TEXT,
            restored_at TEXT,
            downtime_hours REAL,
            execution_completed_by TEXT,
            execution_completed_at TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS work_order_supplies (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            work_order_id INTEGER NOT NULL REFERENCES work_orders(id) ON DELETE CASCADE,
            supply_type TEXT NOT NULL CHECK (supply_type IN ('material', 'external_service')),
            description TEXT NOT NULL,
            quantity REAL,
            unit TEXT,
            ordered_at TEXT,
            order_number TEXT
        );

        CREATE TABLE IF NOT EXISTS work_order_artisans (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            work_order_id INTEGER NOT NULL REFERENCES work_orders(id) ON DELETE CASCADE,
            person_name TEXT NOT NULL,
            trade TEXT NOT NULL,
            work_date TEXT,
            planned_hours REAL NOT NULL DEFAULT 0,
            actual_hours REAL,
            overtime_rate REAL NOT NULL DEFAULT 0
        );

        CREATE TABLE IF NOT EXISTS work_order_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            work_order_id INTEGER NOT NULL REFERENCES work_orders(id) ON DELETE CASCADE,
            workflow_step TEXT NOT NULL,
            action TEXT NOT NULL,
            performed_by TEXT NOT NULL,
            note TEXT,
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS schedule_types (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE,
            meter_type TEXT,
            meter_interval REAL,
            calendar_unit TEXT CHECK (calendar_unit IN ('day', 'week', 'month', 'year')),
            interval_count INTEGER NOT NULL DEFAULT 1,
            task_type TEXT NOT NULL DEFAULT 'Preventive work order',
            description TEXT NOT NULL DEFAULT '',
            early_tolerance_days INTEGER NOT NULL DEFAULT 0,
            late_tolerance_days INTEGER NOT NULL DEFAULT 0,
            strategy TEXT NOT NULL CHECK (
                strategy IN ('interval_followup', 'fixed_schedule', 'official_inspection')
            ),
            weekend_adjustment TEXT NOT NULL DEFAULT 'none'
                CHECK (weekend_adjustment IN ('none', 'next_working_day', 'previous_working_day')),
            status TEXT NOT NULL DEFAULT 'active'
                CHECK (status IN ('active', 'inactive'))
        );

        CREATE TABLE IF NOT EXISTS recurrent_tasks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            recurrent_no TEXT NOT NULL UNIQUE,
            name TEXT NOT NULL,
            schedule_type_id INTEGER NOT NULL REFERENCES schedule_types(id),
            primary_asset_id INTEGER NOT NULL REFERENCES assets(id),
            type_of_work TEXT NOT NULL,
            main_department TEXT NOT NULL,
            work_schedule TEXT,
            duration_hours REAL NOT NULL DEFAULT 0,
            reminder_days INTEGER NOT NULL DEFAULT 0,
            start_date TEXT NOT NULL,
            end_date TEXT,
            repetitions INTEGER,
            generated_count INTEGER NOT NULL DEFAULT 0,
            next_target_date TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'active'
                CHECK (status IN ('active', 'completed', 'suspended')),
            created_by TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS recurrent_task_assets (
            recurrent_task_id INTEGER NOT NULL REFERENCES recurrent_tasks(id) ON DELETE CASCADE,
            asset_id INTEGER NOT NULL REFERENCES assets(id) ON DELETE CASCADE,
            PRIMARY KEY (recurrent_task_id, asset_id)
        );

        CREATE TABLE IF NOT EXISTS recurrent_task_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            recurrent_task_id INTEGER NOT NULL REFERENCES recurrent_tasks(id) ON DELETE CASCADE,
            previous_status TEXT NOT NULL,
            new_status TEXT NOT NULL,
            changed_by TEXT NOT NULL,
            reason TEXT NOT NULL,
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS preventive_tasks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            task_no TEXT NOT NULL UNIQUE,
            recurrent_task_id INTEGER NOT NULL REFERENCES recurrent_tasks(id),
            target_date TEXT NOT NULL,
            early_date TEXT NOT NULL,
            late_date TEXT NOT NULL,
            status TEXT NOT NULL CHECK (status IN ('planned', 'due', 'completed', 'overdue')),
            completed_at TEXT,
            completed_by TEXT,
            feedback TEXT,
            actual_man_hours REAL,
            created_at TEXT NOT NULL,
            UNIQUE(recurrent_task_id, target_date)
        );

        CREATE TABLE IF NOT EXISTS safety_permits (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            permit_no TEXT NOT NULL UNIQUE,
            work_order_id INTEGER REFERENCES work_orders(id),
            asset_id INTEGER NOT NULL REFERENCES assets(id),
            form_type TEXT NOT NULL CHECK (
                form_type IN (
                    'electrical_ptw', 'mechanical_ptw',
                    'electrical_loa', 'mechanical_loa',
                    'electrical_sft', 'mechanical_sft'
                )
            ),
            status TEXT NOT NULL CHECK (
                status IN ('prepared', 'issued', 'received', 'cleared', 'cancelled')
            ),
            work_description TEXT NOT NULL,
            location TEXT NOT NULL,
            issued_to TEXT NOT NULL,
            employer TEXT NOT NULL,
            electrical_isolations TEXT,
            mechanical_isolations TEXT,
            circuit_main_earths TEXT,
            additional_earths INTEGER NOT NULL DEFAULT 0,
            identity_wristlets INTEGER NOT NULL DEFAULT 0,
            limits_of_access TEXT,
            precautions_confirmed INTEGER NOT NULL DEFAULT 0,
            prepared_by TEXT NOT NULL,
            issued_by TEXT,
            controller_name TEXT,
            received_by TEXT,
            cleared_by TEXT,
            cancelled_by TEXT,
            issued_at TEXT,
            received_at TEXT,
            cleared_at TEXT,
            cancelled_at TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS permit_precautions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            permit_id INTEGER NOT NULL REFERENCES safety_permits(id) ON DELETE CASCADE,
            precaution_code TEXT NOT NULL,
            precaution_text TEXT NOT NULL,
            selected INTEGER NOT NULL DEFAULT 0,
            UNIQUE(permit_id, precaution_code)
        );

        CREATE TABLE IF NOT EXISTS permit_special_assessments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            permit_id INTEGER NOT NULL REFERENCES safety_permits(id) ON DELETE CASCADE,
            assessment_type TEXT NOT NULL CHECK (
                assessment_type IN ('hot_work', 'height_work', 'confined_space')
            ),
            answer TEXT NOT NULL CHECK (answer IN ('yes', 'no', 'na')),
            remarks TEXT,
            UNIQUE(permit_id, assessment_type)
        );

        CREATE TABLE IF NOT EXISTS permit_transition_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            permit_id INTEGER NOT NULL REFERENCES safety_permits(id) ON DELETE CASCADE,
            previous_status TEXT NOT NULL,
            new_status TEXT NOT NULL,
            action TEXT NOT NULL,
            performed_by TEXT NOT NULL,
            controller_name TEXT,
            remarks TEXT NOT NULL,
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            employee_no TEXT NOT NULL UNIQUE,
            full_name TEXT NOT NULL,
            initials TEXT NOT NULL,
            department TEXT NOT NULL,
            role_name TEXT NOT NULL,
            password_hash TEXT,
            status TEXT NOT NULL DEFAULT 'active'
                CHECK (status IN ('active', 'inactive'))
        );

        CREATE TABLE IF NOT EXISTS responsibility_groups (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            code TEXT NOT NULL UNIQUE,
            name TEXT NOT NULL UNIQUE
        );

        CREATE TABLE IF NOT EXISTS responsibility_group_members (
            group_id INTEGER NOT NULL REFERENCES responsibility_groups(id) ON DELETE CASCADE,
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            PRIMARY KEY (group_id, user_id)
        );

        CREATE TABLE IF NOT EXISTS inbox_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source_type TEXT NOT NULL,
            source_id INTEGER NOT NULL,
            action_code TEXT NOT NULL,
            title TEXT NOT NULL,
            description TEXT NOT NULL,
            priority TEXT NOT NULL CHECK (priority IN ('high', 'medium', 'normal')),
            base_priority TEXT NOT NULL DEFAULT 'normal',
            due_at TEXT,
            escalation_level INTEGER NOT NULL DEFAULT 0,
            escalated_at TEXT,
            responsible_group_id INTEGER NOT NULL REFERENCES responsibility_groups(id),
            status TEXT NOT NULL DEFAULT 'open'
                CHECK (status IN ('open', 'claimed', 'completed', 'cancelled')),
            claimed_by INTEGER REFERENCES users(id),
            claimed_at TEXT,
            completed_at TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            UNIQUE(source_type, source_id, action_code)
        );

        CREATE TABLE IF NOT EXISTS inbox_recipients (
            inbox_item_id INTEGER NOT NULL REFERENCES inbox_items(id) ON DELETE CASCADE,
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            PRIMARY KEY (inbox_item_id, user_id)
        );

        CREATE TABLE IF NOT EXISTS inbox_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            inbox_item_id INTEGER NOT NULL REFERENCES inbox_items(id) ON DELETE CASCADE,
            action TEXT NOT NULL CHECK (action IN ('assigned', 'claimed', 'released', 'completed')),
            user_id INTEGER REFERENCES users(id),
            details TEXT,
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS inbox_escalation_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            inbox_item_id INTEGER NOT NULL REFERENCES inbox_items(id) ON DELETE CASCADE,
            previous_level INTEGER NOT NULL,
            new_level INTEGER NOT NULL,
            reason TEXT NOT NULL,
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS audit_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER REFERENCES users(id),
            employee_no TEXT,
            user_name TEXT,
            role_name TEXT,
            action TEXT NOT NULL,
            target TEXT NOT NULL,
            method TEXT NOT NULL,
            status_code INTEGER NOT NULL,
            details TEXT,
            ip_address TEXT,
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS attachments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            entity_type TEXT NOT NULL,
            entity_id INTEGER NOT NULL,
            original_name TEXT NOT NULL,
            stored_name TEXT NOT NULL UNIQUE,
            content_type TEXT,
            file_size INTEGER NOT NULL,
            uploaded_by_id INTEGER NOT NULL REFERENCES users(id),
            uploaded_by_name TEXT NOT NULL,
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS backup_runs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            filename TEXT NOT NULL UNIQUE,
            created_by TEXT NOT NULL,
            created_at TEXT NOT NULL,
            database_bytes INTEGER NOT NULL,
            upload_files INTEGER NOT NULL,
            upload_bytes INTEGER NOT NULL,
            archive_bytes INTEGER NOT NULL,
            sha256 TEXT NOT NULL,
            integrity TEXT NOT NULL,
            last_verified_at TEXT,
            status TEXT NOT NULL DEFAULT 'available'
                CHECK (status IN ('available', 'deleted', 'failed'))
        );

        CREATE TABLE IF NOT EXISTS restore_runs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source_filename TEXT NOT NULL,
            safety_backup_filename TEXT NOT NULL,
            restored_by TEXT NOT NULL,
            restored_at TEXT NOT NULL,
            status TEXT NOT NULL,
            details TEXT
        );
        """
    )
    ensure_safety_permit_form_types(database)
    ensure_asset_columns(database)
    ensure_work_request_columns(database)
    ensure_work_order_columns(database)
    ensure_work_order_artisan_columns(database)
    ensure_preventive_task_columns(database)
    ensure_inbox_columns(database)
    database.executescript(
        """
        CREATE INDEX IF NOT EXISTS idx_assets_parent ON assets(parent_id);
        CREATE INDEX IF NOT EXISTS idx_assets_kks ON assets(kks_code);
        CREATE INDEX IF NOT EXISTS idx_assets_description ON assets(description);
        CREATE INDEX IF NOT EXISTS idx_assets_area ON assets(responsible_area);
        CREATE INDEX IF NOT EXISTS idx_assets_source ON assets(source_kind, is_reference);
        CREATE INDEX IF NOT EXISTS idx_audit_created ON audit_logs(created_at DESC);
        CREATE INDEX IF NOT EXISTS idx_audit_user ON audit_logs(user_id, created_at DESC);
        CREATE INDEX IF NOT EXISTS idx_audit_action ON audit_logs(action, created_at DESC);
        CREATE INDEX IF NOT EXISTS idx_attachments_entity
            ON attachments(entity_type, entity_id, created_at DESC);
        CREATE INDEX IF NOT EXISTS idx_inbox_history_item
            ON inbox_history(inbox_item_id, created_at DESC);
        CREATE INDEX IF NOT EXISTS idx_inbox_escalation_item
            ON inbox_escalation_history(inbox_item_id, created_at DESC);
        """
    )
    Path(app.config["DATABASE"]).parent.mkdir(parents=True, exist_ok=True)
    Path(app.config["UPLOAD_FOLDER"]).mkdir(parents=True, exist_ok=True)
    Path(app.config["KKS_STAGING_FOLDER"]).mkdir(parents=True, exist_ok=True)
    Path(app.config["BACKUP_FOLDER"]).mkdir(parents=True, exist_ok=True)
    if database.execute("SELECT COUNT(*) FROM assets").fetchone()[0] == 0:
        seed_assets(database)
    if database.execute("SELECT COUNT(*) FROM logbooks").fetchone()[0] == 0:
        seed_logbooks(database)
    if database.execute("SELECT COUNT(*) FROM event_entries").fetchone()[0] == 0:
        seed_events(database)
    if database.execute("SELECT COUNT(*) FROM work_requests").fetchone()[0] == 0:
        seed_corrective_maintenance(database)
    if database.execute("SELECT COUNT(*) FROM schedule_types").fetchone()[0] == 0:
        seed_preventive_maintenance(database)
    if database.execute("SELECT COUNT(*) FROM safety_permits").fetchone()[0] == 0:
        seed_safety_permits(database)
    if database.execute("SELECT COUNT(*) FROM users").fetchone()[0] == 0:
        seed_infobox_master(database)
    ensure_responsibility_groups(database)
    ensure_user_columns(database)
    sync_infobox(database)
    database.execute(
        """
        INSERT INTO inbox_history (
            inbox_item_id, action, user_id, details, created_at
        )
        SELECT i.id, 'assigned', NULL, 'Initial responsibility assignment', i.created_at
        FROM inbox_items i
        WHERE NOT EXISTS (
            SELECT 1 FROM inbox_history h WHERE h.inbox_item_id = i.id
        )
        """
    )
    database.commit()


def ensure_asset_columns(database: sqlite3.Connection) -> None:
    existing = {
        row["name"] for row in database.execute("PRAGMA table_info(assets)").fetchall()
    }
    additions = {
        "plant_code": "TEXT",
        "system_code": "TEXT",
        "equipment_code": "TEXT",
        "component_code": "TEXT",
        "responsible_area": "TEXT",
        "source_kind": "TEXT NOT NULL DEFAULT 'reference'",
        "source_row": "INTEGER",
        "is_reference": "INTEGER NOT NULL DEFAULT 0",
    }
    for name, declaration in additions.items():
        if name not in existing:
            database.execute(f"ALTER TABLE assets ADD COLUMN {name} {declaration}")
    database.execute(
        """
        UPDATE assets
        SET is_reference = 1
        WHERE kks_code IN (
            '10', '10E', '10ET', '10ETF', '10ETF10', '10ETF10AA217',
            '10ETF10AA217 KA01', '10ETF10AA217 MS01', '10ETF10AA217 -Y01'
        )
        """
    )


def ensure_work_order_columns(database: sqlite3.Connection) -> None:
    existing = {
        row["name"]
        for row in database.execute("PRAGMA table_info(work_orders)").fetchall()
    }
    additions = {
        "maintenance_code": "TEXT NOT NULL DEFAULT ''",
        "equipment_condition": "TEXT NOT NULL DEFAULT ''",
        "execution_started_at": "TEXT",
        "completion_summary": "TEXT",
        "actual_man_hours": "REAL",
        "failure_mode": "TEXT",
        "failure_cause": "TEXT",
        "downtime_started_at": "TEXT",
        "restored_at": "TEXT",
        "downtime_hours": "REAL",
        "execution_completed_by": "TEXT",
        "execution_completed_at": "TEXT",
        "acceptance_note": "TEXT",
        "acceptance_checked_by": "TEXT",
        "acceptance_checked_at": "TEXT",
    }
    for name, declaration in additions.items():
        if name not in existing:
            database.execute(
                f"ALTER TABLE work_orders ADD COLUMN {name} {declaration}"
            )


def ensure_work_request_columns(database: sqlite3.Connection) -> None:
    existing = {
        row["name"]
        for row in database.execute("PRAGMA table_info(work_requests)").fetchall()
    }
    additions = {
        "cmpt_primary": "TEXT",
        "cmpt_impacts": "TEXT NOT NULL DEFAULT '[]'",
        "cmpt_severity": "INTEGER",
        "cmpt_likelihood": "TEXT",
        "target_response_at": "TEXT",
    }
    for name, declaration in additions.items():
        if name not in existing:
            database.execute(
                f"ALTER TABLE work_requests ADD COLUMN {name} {declaration}"
            )
    database.execute(
        """
        UPDATE work_requests
        SET target_response_at = CASE priority
            WHEN 1 THEN datetime(created_at)
            WHEN 2 THEN datetime(created_at, '+2 days')
            WHEN 3 THEN datetime(created_at, '+14 days')
            WHEN 4 THEN datetime(created_at, '+56 days')
            WHEN 5 THEN datetime(created_at, '+183 days')
            ELSE NULL
        END
        WHERE target_response_at IS NULL AND priority BETWEEN 1 AND 5
        """
    )


def ensure_work_order_artisan_columns(database: sqlite3.Connection) -> None:
    existing = {
        row["name"]
        for row in database.execute("PRAGMA table_info(work_order_artisans)").fetchall()
    }
    if "actual_hours" not in existing:
        database.execute(
            "ALTER TABLE work_order_artisans ADD COLUMN actual_hours REAL"
        )


def ensure_inbox_columns(database: sqlite3.Connection) -> None:
    existing = {
        row["name"] for row in database.execute("PRAGMA table_info(inbox_items)").fetchall()
    }
    base_priority_added = "base_priority" not in existing
    additions = {
        "base_priority": "TEXT NOT NULL DEFAULT 'normal'",
        "escalation_level": "INTEGER NOT NULL DEFAULT 0",
        "escalated_at": "TEXT",
    }
    for name, declaration in additions.items():
        if name not in existing:
            database.execute(f"ALTER TABLE inbox_items ADD COLUMN {name} {declaration}")
    if base_priority_added:
        database.execute("UPDATE inbox_items SET base_priority = priority")


def ensure_preventive_task_columns(database: sqlite3.Connection) -> None:
    existing = {
        row["name"]
        for row in database.execute("PRAGMA table_info(preventive_tasks)").fetchall()
    }
    if "actual_man_hours" not in existing:
        database.execute(
            "ALTER TABLE preventive_tasks ADD COLUMN actual_man_hours REAL"
        )


def ensure_safety_permit_form_types(database: sqlite3.Connection) -> None:
    row = database.execute(
        """
        SELECT sql FROM sqlite_master
        WHERE type = 'table' AND name = 'safety_permits'
        """
    ).fetchone()
    if not row or "electrical_sft" in (row["sql"] or ""):
        return

    database.commit()
    database.execute("PRAGMA foreign_keys = OFF")
    try:
        database.executescript(
            """
            CREATE TABLE safety_permits_new (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                permit_no TEXT NOT NULL UNIQUE,
                work_order_id INTEGER REFERENCES work_orders(id),
                asset_id INTEGER NOT NULL REFERENCES assets(id),
                form_type TEXT NOT NULL CHECK (
                    form_type IN (
                        'electrical_ptw', 'mechanical_ptw',
                        'electrical_loa', 'mechanical_loa',
                        'electrical_sft', 'mechanical_sft'
                    )
                ),
                status TEXT NOT NULL CHECK (
                    status IN ('prepared', 'issued', 'received', 'cleared', 'cancelled')
                ),
                work_description TEXT NOT NULL,
                location TEXT NOT NULL,
                issued_to TEXT NOT NULL,
                employer TEXT NOT NULL,
                electrical_isolations TEXT,
                mechanical_isolations TEXT,
                circuit_main_earths TEXT,
                additional_earths INTEGER NOT NULL DEFAULT 0,
                identity_wristlets INTEGER NOT NULL DEFAULT 0,
                limits_of_access TEXT,
                precautions_confirmed INTEGER NOT NULL DEFAULT 0,
                prepared_by TEXT NOT NULL,
                issued_by TEXT,
                controller_name TEXT,
                received_by TEXT,
                cleared_by TEXT,
                cancelled_by TEXT,
                issued_at TEXT,
                received_at TEXT,
                cleared_at TEXT,
                cancelled_at TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            INSERT INTO safety_permits_new (
                id, permit_no, work_order_id, asset_id, form_type, status,
                work_description, location, issued_to, employer,
                electrical_isolations, mechanical_isolations, circuit_main_earths,
                additional_earths, identity_wristlets, limits_of_access,
                precautions_confirmed, prepared_by, issued_by, controller_name,
                received_by, cleared_by, cancelled_by, issued_at, received_at,
                cleared_at, cancelled_at, created_at, updated_at
            )
            SELECT
                id, permit_no, work_order_id, asset_id, form_type, status,
                work_description, location, issued_to, employer,
                electrical_isolations, mechanical_isolations, circuit_main_earths,
                additional_earths, identity_wristlets, limits_of_access,
                precautions_confirmed, prepared_by, issued_by, controller_name,
                received_by, cleared_by, cancelled_by, issued_at, received_at,
                cleared_at, cancelled_at, created_at, updated_at
            FROM safety_permits;

            DROP TABLE safety_permits;
            ALTER TABLE safety_permits_new RENAME TO safety_permits;
            """
        )
        database.commit()
    finally:
        database.execute("PRAGMA foreign_keys = ON")


def ensure_user_columns(database: sqlite3.Connection) -> None:
    existing = {
        row["name"] for row in database.execute("PRAGMA table_info(users)").fetchall()
    }
    if "password_hash" not in existing:
        database.execute("ALTER TABLE users ADD COLUMN password_hash TEXT")
    default_hash = generate_password_hash("SIPAM@2026")
    database.execute(
        """
        INSERT OR IGNORE INTO users (
            employee_no, full_name, initials, department, role_name,
            password_hash, status
        ) VALUES (
            'MBPS-ADMIN', 'SIPAM Administrator', 'SA', 'Information Systems',
            'System Administrator', ?, 'active'
        )
        """,
        (default_hash,),
    )
    database.execute(
        "UPDATE users SET password_hash = ? WHERE password_hash IS NULL OR password_hash = ''",
        (default_hash,),
    )


def ensure_responsibility_groups(database: sqlite3.Connection) -> None:
    database.executemany(
        "INSERT OR IGNORE INTO responsibility_groups (code, name) VALUES (?, ?)",
        [
            ("SHIFT_LEADERS", "Shift Leaders"),
            ("MAINT_APPROVERS", "Maintenance Approvers"),
            ("MAINT_PLANNERS", "Maintenance Planners"),
            ("CI_TEAM", "Control & Instrumentation Team"),
            ("MECH_TEAM", "Mechanical Maintenance Team"),
            ("ELEC_TEAM", "Electrical Maintenance Team"),
        ],
    )


def sync_user_groups(database: sqlite3.Connection, user_id: int, role_name: str) -> None:
    database.execute(
        "DELETE FROM responsibility_group_members WHERE user_id = ?",
        (user_id,),
    )
    for group_code in ROLE_GROUPS.get(role_name, ()):
        group = database.execute(
            "SELECT id FROM responsibility_groups WHERE code = ?",
            (group_code,),
        ).fetchone()
        if group:
            database.execute(
                """
                INSERT OR IGNORE INTO responsibility_group_members (group_id, user_id)
                VALUES (?, ?)
                """,
                (group["id"], user_id),
            )


def seed_assets(database: sqlite3.Connection) -> None:
    rows = [
        (None, "10", "U1", "Unit", 0),
        (1, "10E", "U1 Fuel Supply & Residues Disposal System", "Function", 1),
        (2, "10ET", "U1 Ash & Slag Removal System", "Function", 2),
        (3, "10ETF", "U1 BAS System (Ash Side)", "Function", 3),
        (4, "10ETF10", "U1 BAS System (Ash Side)", "System counter", 4),
        (5, "10ETF10AA217", "BAS A D Pump Outlet Dome Valve", "Equipment unit", 5),
        (6, "10ETF10AA217 KA01", "BAS A D Pump Outlet Dome Valve", "Equipment component", 6),
        (6, "10ETF10AA217 MS01", "BAS A D Pump Outlet Dome Valve Actuator", "Equipment component", 6),
        (6, "10ETF10AA217 -Y01", "BAS A D Pump Outlet Dome Valve Solenoid", "Equipment component", 6),
    ]
    database.executemany(
        """
        INSERT INTO assets
            (
                parent_id, kks_code, description, hierarchy_level, level_no,
                source_kind, is_reference
            )
        VALUES (?, ?, ?, ?, ?, 'reference', 1)
        """,
        rows,
    )


def seed_logbooks(database: sqlite3.Connection) -> None:
    database.executemany(
        """
        INSERT INTO logbooks
            (code, name, department, can_create_role, is_shift_leader)
        VALUES (?, ?, ?, ?, ?)
        """,
        [
            ("SHIFT", "Shift Leaders' Logbook", "Operations", "Shift Leader", 1),
            ("OPS", "Operations Logbook", "Operations", "Operations", 0),
            ("MECH", "Mechanical Maintenance Logbook", "Maintenance", "Mechanical Maintenance", 0),
            ("ELEC", "Electrical Maintenance Logbook", "Maintenance", "Electrical Maintenance", 0),
            ("CI", "Control & Instrumentation Logbook", "Maintenance", "Control & Instrumentation", 0),
        ],
    )


def seed_events(database: sqlite3.Connection) -> None:
    rows = [
        (
            None, 2, "EL-2026-0001", "Information",
            "Dome valve actuator response delayed", 8, "2026-06-09T06:35",
            "open", "Valve opening feedback arrived after 11 seconds during the ash handling sequence.",
            "Control Room Operator", "Kabelo Molefe", "2026-06-09T06:42", "2026-06-09T06:42",
        ),
        (
            1, 2, "EL-2026-0002", "Information",
            "Dome valve actuator response delayed", 8, "2026-06-09T07:05",
            "open", "C&I informed. Functional inspection requested for the day shift.",
            "Shift Leader", "Kabelo Molefe", "2026-06-09T07:08", "2026-06-09T07:08",
        ),
        (
            None, 3, "EL-2026-0003", "Information",
            "Visual inspection of solenoid assembly", 9, "2026-06-09T08:10",
            "closed", "No external damage found. Terminal tightness confirmed.",
            "Mechanical Technician", "Neo Dube", "2026-06-09T08:18", "2026-06-09T08:40",
        ),
    ]
    database.executemany(
        """
        INSERT INTO event_entries (
            parent_id, source_logbook_id, entry_no, entry_type, subject,
            asset_id, event_date, state, observation, informant, created_by,
            created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        rows,
    )
    database.executemany(
        """
        INSERT INTO event_entry_logbooks (entry_id, logbook_id, is_copy)
        VALUES (?, ?, ?)
        """,
        [
            (1, 2, 0), (1, 1, 1),
            (2, 2, 0), (2, 1, 1),
            (3, 3, 0), (3, 1, 1),
        ],
    )


def seed_corrective_maintenance(database: sqlite3.Connection) -> None:
    database.executemany(
        """
        INSERT INTO work_requests (
            request_no, source_event_id, asset_id, name, asset_type, type_of_work,
            main_department, priority, planned_start, planned_end, reminder_days,
            show_in_history, observation, author, status, decision_by,
            decision_reason, created_at, updated_at, target_response_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [
            (
                "WR-2026-0001", 1, 8, "Inspect delayed dome valve actuator",
                "Actuator", "Corrective inspection", "Control & Instrumentation",
                2, "2026-06-09T10:00", "2026-06-09T14:00", 0, 1,
                "Opening feedback is delayed during the ash handling sequence.",
                "Kabelo Molefe", "approved", "Thabo Ndlovu", None,
                "2026-06-09T07:20", "2026-06-09T07:45", "2026-06-11T07:20",
            ),
            (
                "WR-2026-0002", None, 9, "Replace damaged solenoid cable gland",
                "Solenoid valve", "Electrical repair", "Electrical Maintenance",
                3, "2026-06-10T08:00", "2026-06-10T12:00", 1, 1,
                "Cable gland shows cracking and should be replaced during the next available window.",
                "Neo Dube", "submitted", None, None,
                "2026-06-09T08:50", "2026-06-09T08:50", "2026-06-23T08:50",
            ),
            (
                "WR-2026-0003", None, 7, "Repaint instrument root valve tag",
                "Valve", "Housekeeping", "Mechanical Maintenance",
                3, None, None, 0, 0,
                "Tag is faded but remains readable.",
                "Neo Dube", "declined", "Thabo Ndlovu",
                "Include in the planned plant labelling campaign.",
                "2026-06-08T13:10", "2026-06-08T15:30", "2026-06-22T13:10",
            ),
        ],
    )
    database.execute(
        """
        INSERT INTO work_orders (
            order_no, work_request_id, workflow_step, description_of_work,
            workplace_requirements, expected_man_hours, permit_requirement,
            permit_status, plan_approved_by, execution_confirmed_by,
            acceptance_status, acceptance_reason, closed_by, created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            "WO-2026-0001", 1, "planning",
            "Inspect actuator linkage, command response and open-position feedback circuit.",
            "Coordinate with Unit 1 control room before functional testing.", 6,
            "undecided", "not_required", None, None, "pending", None, None,
            "2026-06-09T07:45", "2026-06-09T08:00",
        ),
    )
    database.executemany(
        """
        INSERT INTO work_order_supplies (
            work_order_id, supply_type, description, quantity, unit,
            ordered_at, order_number
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        [
            (1, "material", "Actuator seal and terminal kit", 1, "SET", None, None),
            (1, "material", "Electrical contact cleaner", 1, "CAN", None, None),
        ],
    )
    database.execute(
        """
        INSERT INTO work_order_artisans (
            work_order_id, person_name, trade, work_date, planned_hours, overtime_rate
        ) VALUES (?, ?, ?, ?, ?, ?)
        """,
        (1, "Boitumelo Kgosidintsi", "C&I Technician", "2026-06-09", 6, 0),
    )
    database.execute(
        """
        INSERT INTO work_order_history (
            work_order_id, workflow_step, action, performed_by, note, created_at
        ) VALUES (?, ?, ?, ?, ?, ?)
        """,
        (1, "planning", "Work request approved and work order created", "Thabo Ndlovu", None, "2026-06-09T07:45"),
    )


def seed_preventive_maintenance(database: sqlite3.Connection) -> None:
    database.executemany(
        """
        INSERT INTO schedule_types (
            name, meter_type, meter_interval, calendar_unit, interval_count,
            task_type, description, early_tolerance_days, late_tolerance_days,
            strategy, weekend_adjustment, status
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'active')
        """,
        [
            (
                "Monthly visual inspection", None, None, "month", 1,
                "Preventive work order",
                "Fixed monthly visual inspection with a short execution window.",
                3, 5, "fixed_schedule", "next_working_day",
            ),
            (
                "Quarterly actuator service", None, None, "month", 3,
                "Preventive work order",
                "Service interval follows the date of the last execution.",
                7, 14, "interval_followup", "next_working_day",
            ),
            (
                "Annual statutory inspection", None, None, "year", 1,
                "Preventive work order",
                "Official inspection with zero tolerance.",
                0, 0, "official_inspection", "next_working_day",
            ),
        ],
    )
    now = "2026-06-09T09:00"
    database.executemany(
        """
        INSERT INTO recurrent_tasks (
            recurrent_no, name, schedule_type_id, primary_asset_id,
            type_of_work, main_department, work_schedule, duration_hours,
            reminder_days, start_date, end_date, repetitions, generated_count,
            next_target_date, status, created_by, created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [
            (
                "RT-2026-0001", "Inspect dome valve actuator and linkage", 1, 8,
                "Visual inspection", "Control & Instrumentation",
                "Inspect actuator, linkage, feedback arm and local indication.",
                2, 5, "2026-06-10", None, None, 1, "2026-07-10",
                "active", "Maintenance Planner", now, now,
            ),
            (
                "RT-2026-0002", "Quarterly solenoid functional service", 2, 9,
                "Preventive service", "Control & Instrumentation",
                "Clean terminals, check coil resistance and perform operation test.",
                4, 10, "2026-04-15", None, 8, 1, "2026-07-15",
                "active", "Maintenance Planner", now, now,
            ),
            (
                "RT-2026-0003", "Annual BAS isolation inspection", 3, 6,
                "Official inspection", "Mechanical Maintenance",
                "Inspect isolation integrity and verify identification.",
                8, 14, "2026-08-03", None, None, 0, "2026-08-03",
                "active", "Maintenance Planner", now, now,
            ),
        ],
    )
    database.executemany(
        "INSERT INTO recurrent_task_assets (recurrent_task_id, asset_id) VALUES (?, ?)",
        [(1, 8), (1, 9), (2, 9), (3, 6), (3, 7)],
    )
    database.executemany(
        """
        INSERT INTO preventive_tasks (
            task_no, recurrent_task_id, target_date, early_date, late_date,
            status, completed_at, completed_by, feedback, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [
            (
                "PM-2026-0001", 1, "2026-06-10", "2026-06-07", "2026-06-15",
                "due", None, None, None, now,
            ),
            (
                "PM-2026-0002", 2, "2026-04-15", "2026-04-08", "2026-04-29",
                "completed", "2026-04-15T12:30", "Boitumelo Kgosidintsi",
                "Functional test satisfactory.", now,
            ),
        ],
    )


def seed_safety_permits(database: sqlite3.Connection) -> None:
    now = "2026-06-09T09:20"
    database.executemany(
        """
        INSERT INTO safety_permits (
            permit_no, work_order_id, asset_id, form_type, status,
            work_description, location, issued_to, employer,
            electrical_isolations, mechanical_isolations, circuit_main_earths,
            additional_earths, identity_wristlets, limits_of_access,
            precautions_confirmed, prepared_by, issued_by, controller_name,
            received_by, cleared_by, cancelled_by, issued_at, received_at,
            cleared_at, cancelled_at, created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [
            (
                "PTW-2026-0001", 1, 8, "electrical_ptw", "prepared",
                "Inspect actuator command and feedback circuit.",
                "Unit 1 BAS ash side, dome valve actuator",
                "Boitumelo Kgosidintsi", "Morupule B Power Station",
                "Isolate actuator 415 V supply and prove dead.",
                "Secure actuator linkage against movement.",
                "Apply local earth where required by switching instruction.",
                1, 2, None, 1, "Kabelo Molefe", None, None,
                None, None, None, None, None, None, None, now, now,
            ),
            (
                "LOA-2026-0001", None, 6, "mechanical_loa", "issued",
                "Visual inspection of dome valve body and identification.",
                "Unit 1 BAS ash side",
                "Neo Dube", "Morupule B Power Station",
                None, None, None, 0, 0,
                "Inspection limited to external valve surfaces and accessible nameplate.",
                1, "Kabelo Molefe", "Kabelo Molefe", "Thabo Ndlovu",
                None, None, None, "2026-06-09T08:30", None, None, None, now, now,
            ),
        ],
    )
    precautions = [
        ("isolate_energy", "All energy sources identified and isolated"),
        ("lock_tag", "Locks and caution tags applied"),
        ("prove_dead", "Dead condition proven before work"),
        ("drain_vent", "Pressure released, drained and vented"),
        ("barrier", "Work area barriers and warning notices installed"),
        ("ppe", "Required personal protective equipment confirmed"),
    ]
    database.executemany(
        """
        INSERT INTO permit_precautions
            (permit_id, precaution_code, precaution_text, selected)
        VALUES (?, ?, ?, ?)
        """,
        [
            (permit_id, code, text, 1 if code in selected else 0)
            for permit_id, selected in (
                (1, {"isolate_energy", "lock_tag", "prove_dead", "barrier", "ppe"}),
                (2, {"barrier", "ppe"}),
            )
            for code, text in precautions
        ],
    )
    database.executemany(
        """
        INSERT INTO permit_special_assessments
            (permit_id, assessment_type, answer, remarks)
        VALUES (?, ?, ?, ?)
        """,
        [
            (1, "hot_work", "no", None),
            (1, "height_work", "no", None),
            (1, "confined_space", "na", None),
            (2, "hot_work", "no", None),
            (2, "height_work", "no", None),
            (2, "confined_space", "na", None),
        ],
    )


def seed_infobox_master(database: sqlite3.Connection) -> None:
    database.executemany(
        """
        INSERT INTO users
            (employee_no, full_name, initials, department, role_name)
        VALUES (?, ?, ?, ?, ?)
        """,
        [
            ("MBPS-0104", "Kabelo Molefe", "KM", "Operations", "Shift Leader"),
            ("MBPS-0112", "Onalenna Modise", "OM", "Operations", "Shift Leader"),
            ("MBPS-0201", "Thabo Ndlovu", "TN", "Maintenance", "Maintenance Approver"),
            ("MBPS-0215", "Naledi Sechele", "NS", "Maintenance", "Maintenance Planner"),
            ("MBPS-0310", "Boitumelo Kgosidintsi", "BK", "Control & Instrumentation", "C&I Technician"),
            ("MBPS-0418", "Neo Dube", "ND", "Mechanical Maintenance", "Mechanical Technician"),
        ],
    )
    database.executemany(
        "INSERT INTO responsibility_groups (code, name) VALUES (?, ?)",
        [
            ("SHIFT_LEADERS", "Shift Leaders"),
            ("MAINT_APPROVERS", "Maintenance Approvers"),
            ("MAINT_PLANNERS", "Maintenance Planners"),
            ("CI_TEAM", "Control & Instrumentation Team"),
            ("MECH_TEAM", "Mechanical Maintenance Team"),
            ("ELEC_TEAM", "Electrical Maintenance Team"),
        ],
    )
    database.executemany(
        """
        INSERT INTO responsibility_group_members (group_id, user_id)
        VALUES (?, ?)
        """,
        [
            (1, 1), (1, 2),
            (2, 3),
            (3, 3), (3, 4),
            (4, 5),
            (5, 6),
        ],
    )


def sync_infobox(database: sqlite3.Connection | None = None) -> None:
    database = database or get_db()
    generate_reminder_preventive_tasks(database)
    now = datetime.now().isoformat(timespec="minutes")
    desired: list[dict] = []

    for row in database.execute(
        """
        SELECT id, request_no, name, priority, target_response_at
        FROM work_requests WHERE status = 'submitted'
        """
    ).fetchall():
        desired.append({
            "source_type": "work_request", "source_id": row["id"],
            "action_code": "decide_request",
            "title": f"Decide work request {row['request_no']}",
            "description": row["name"],
            "priority": (
                "high" if row["priority"] in (1, 2)
                else "medium" if row["priority"] in (3, 4)
                else "normal"
            ),
            "due_at": row["target_response_at"], "group_code": "MAINT_APPROVERS",
        })

    work_order_groups = {
        "planning": ("plan_work_order", "Plan work order", "MAINT_PLANNERS"),
        "plan_approval": ("approve_plan", "Approve execution plan", "MAINT_APPROVERS"),
        "permit_decision": ("coordinate_permit", "Coordinate PTW/LoA and execution", "SHIFT_LEADERS"),
        "work_check": ("check_work", "Check completed work", "MAINT_APPROVERS"),
        "rework": ("coordinate_rework", "Coordinate required rework", "MAINT_PLANNERS"),
    }
    for row in database.execute(
        """
        SELECT wo.id, wo.order_no, wo.workflow_step, wr.name, wr.planned_end,
            wr.main_department
        FROM work_orders wo
        JOIN work_requests wr ON wr.id = wo.work_request_id
        WHERE wo.workflow_step != 'closed'
        """
    ).fetchall():
        config = work_order_groups.get(row["workflow_step"])
        if row["workflow_step"] == "execution":
            group_code = {
                "Control & Instrumentation": "CI_TEAM",
                "Electrical Maintenance": "ELEC_TEAM",
                "Mechanical Maintenance": "MECH_TEAM",
                "Operations": "SHIFT_LEADERS",
            }.get(row["main_department"], "MAINT_PLANNERS")
            config = ("execute_work", "Execute work order", group_code)
        if config:
            desired.append({
                "source_type": "work_order", "source_id": row["id"],
                "action_code": config[0],
                "title": f"{config[1]} {row['order_no']}",
                "description": row["name"], "priority": "medium",
                "due_at": row["planned_end"], "group_code": config[2],
            })

    for row in database.execute(
        """
        SELECT pt.id, pt.task_no, pt.status, pt.target_date, rt.name, rt.main_department
        FROM preventive_tasks pt
        JOIN recurrent_tasks rt ON rt.id = pt.recurrent_task_id
        WHERE pt.status IN ('due', 'overdue')
           OR (
                pt.status = 'planned'
                AND date('now', 'localtime') >= date(
                    pt.target_date,
                    printf('-%d days', rt.reminder_days)
                )
           )
        """
    ).fetchall():
        group_code = {
            "Control & Instrumentation": "CI_TEAM",
            "Electrical Maintenance": "ELEC_TEAM",
            "Mechanical Maintenance": "MECH_TEAM",
            "Operations": "SHIFT_LEADERS",
        }.get(row["main_department"], "MAINT_PLANNERS")
        desired.append({
            "source_type": "preventive_task", "source_id": row["id"],
            "action_code": "execute_preventive",
            "title": f"Execute preventive task {row['task_no']}",
            "description": row["name"],
            "priority": "high" if row["status"] == "overdue" else "medium",
            "due_at": row["target_date"], "group_code": group_code,
        })

    permit_actions = {
        "prepared": ("issue_permit", "Issue safety permit"),
        "issued": ("confirm_receipt", "Confirm permit receipt"),
        "received": ("clear_location", "Confirm work clearance"),
        "cleared": ("cancel_permit", "Cancel safety permit"),
    }
    for row in database.execute(
        """
        SELECT id, permit_no, status, work_description
        FROM safety_permits WHERE status != 'cancelled'
        """
    ).fetchall():
        action_code, label = permit_actions[row["status"]]
        desired.append({
            "source_type": "permit", "source_id": row["id"],
            "action_code": action_code,
            "title": f"{label} {row['permit_no']}",
            "description": row["work_description"], "priority": "high",
            "due_at": None, "group_code": "SHIFT_LEADERS",
        })

    for row in database.execute(
        """
        SELECT id, handover_no, shift_date, shift_name, summary, outgoing_user_id
        FROM shift_handovers WHERE status = 'submitted'
        """
    ).fetchall():
        desired.append({
            "source_type": "shift_handover", "source_id": row["id"],
            "action_code": "accept_handover",
            "title": f"Accept shift handover {row['handover_no']}",
            "description": f"{row['shift_name']} / {row['summary']}",
            "priority": "high", "due_at": row["shift_date"],
            "group_code": "SHIFT_LEADERS",
            "exclude_user_id": row["outgoing_user_id"],
        })

    desired_keys = {
        (item["source_type"], item["source_id"], item["action_code"])
        for item in desired
    }
    open_rows = database.execute(
        "SELECT id, source_type, source_id, action_code FROM inbox_items WHERE status IN ('open', 'claimed')"
    ).fetchall()
    for row in open_rows:
        if (row["source_type"], row["source_id"], row["action_code"]) not in desired_keys:
            database.execute(
                "UPDATE inbox_items SET status = 'completed', completed_at = ?, updated_at = ? WHERE id = ?",
                (now, now, row["id"]),
            )
            add_infobox_history(
                database,
                row["id"],
                "completed",
                "Underlying workflow action completed",
            )

    for item in desired:
        group = database.execute(
            "SELECT id FROM responsibility_groups WHERE code = ?",
            (item["group_code"],),
        ).fetchone()
        if group is None:
            continue
        existing = database.execute(
            """
            SELECT id, status,
                (
                    SELECT h.details FROM inbox_history h
                    WHERE h.inbox_item_id = inbox_items.id
                      AND h.action = 'completed'
                    ORDER BY h.id DESC LIMIT 1
                ) AS completion_details
            FROM inbox_items
            WHERE source_type = ? AND source_id = ? AND action_code = ?
            """,
            (item["source_type"], item["source_id"], item["action_code"]),
        ).fetchone()
        if existing is None:
            cursor = database.execute(
                """
                INSERT INTO inbox_items (
                    source_type, source_id, action_code, title, description,
                    priority, base_priority, due_at, responsible_group_id, status,
                    created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'open', ?, ?)
                """,
                (
                    item["source_type"], item["source_id"], item["action_code"],
                    item["title"], item["description"], item["priority"],
                    item["priority"], item["due_at"], group["id"], now, now,
                ),
            )
            item_id = cursor.lastrowid
            members = database.execute(
                "SELECT user_id FROM responsibility_group_members WHERE group_id = ?",
                (group["id"],),
            ).fetchall()
            database.executemany(
                "INSERT INTO inbox_recipients (inbox_item_id, user_id) VALUES (?, ?)",
                [
                    (item_id, member["user_id"]) for member in members
                    if member["user_id"] != item.get("exclude_user_id")
                ],
            )
            add_infobox_history(
                database,
                item_id,
                "assigned",
                f"Assigned to {item['group_code']}",
                user_id=None,
            )
        elif (
            existing["status"] == "completed"
            and existing["completion_details"] == "Underlying workflow action completed"
        ):
            item_id = existing["id"]
            database.execute(
                """
                UPDATE inbox_items
                SET title = ?, description = ?, priority = ?, base_priority = ?, due_at = ?,
                    responsible_group_id = ?, status = 'open', claimed_by = NULL,
                    claimed_at = NULL, completed_at = NULL, escalation_level = 0,
                    escalated_at = NULL, updated_at = ?
                WHERE id = ?
                """,
                (
                    item["title"], item["description"], item["priority"],
                    item["priority"], item["due_at"], group["id"], now, item_id,
                ),
            )
            database.execute(
                "DELETE FROM inbox_recipients WHERE inbox_item_id = ?", (item_id,)
            )
            members = database.execute(
                "SELECT user_id FROM responsibility_group_members WHERE group_id = ?",
                (group["id"],),
            ).fetchall()
            database.executemany(
                "INSERT INTO inbox_recipients (inbox_item_id, user_id) VALUES (?, ?)",
                [
                    (item_id, member["user_id"]) for member in members
                    if member["user_id"] != item.get("exclude_user_id")
                ],
            )
            add_infobox_history(
                database,
                item_id,
                "assigned",
                f"Workflow returned; reassigned to {item['group_code']}",
                user_id=None,
            )
        elif existing["status"] in {"open", "claimed"}:
            database.execute(
                """
                UPDATE inbox_items
                SET title = ?, description = ?, base_priority = ?, due_at = ?,
                    responsible_group_id = ?, updated_at = ?
                WHERE id = ?
                """,
                (
                    item["title"], item["description"], item["priority"],
                    item["due_at"], group["id"], now, existing["id"],
                ),
            )
    apply_infobox_escalations(database, now)
    database.commit()


def apply_infobox_escalations(database: sqlite3.Connection, now: str) -> None:
    rows = database.execute(
        """
        SELECT id, escalation_level, base_priority, due_at,
            CASE
                WHEN due_at IS NULL OR datetime(due_at) >= datetime('now', 'localtime') THEN 0
                WHEN (julianday('now', 'localtime') - julianday(due_at)) * 24 >= 72 THEN 3
                WHEN (julianday('now', 'localtime') - julianday(due_at)) * 24 >= 24 THEN 2
                ELSE 1
            END AS required_level
        FROM inbox_items
        WHERE status IN ('open', 'claimed')
        """
    ).fetchall()
    for row in rows:
        required_level = row["required_level"]
        if required_level == row["escalation_level"]:
            continue
        reason = (
            "Due target revised; escalation reset"
            if required_level == 0
            else f"Assignment overdue; escalation level {required_level} applied"
        )
        database.execute(
            """
            UPDATE inbox_items
            SET escalation_level = ?, escalated_at = ?,
                priority = CASE WHEN ? > 0 THEN 'high' ELSE base_priority END,
                updated_at = ? WHERE id = ?
            """,
            (
                required_level, now if required_level else None,
                required_level, now, row["id"],
            ),
        )
        database.execute(
            """
            INSERT INTO inbox_escalation_history (
                inbox_item_id, previous_level, new_level, reason, created_at
            ) VALUES (?, ?, ?, ?, ?)
            """,
            (row["id"], row["escalation_level"], required_level, reason, now),
        )


def generate_reminder_preventive_tasks(
    database: sqlite3.Connection,
    as_of: date | None = None,
) -> list[dict]:
    release_date = (as_of or date.today()).isoformat()
    schedules = database.execute(
        """
        SELECT rt.*, st.early_tolerance_days, st.late_tolerance_days
        FROM recurrent_tasks rt
        JOIN schedule_types st ON st.id = rt.schedule_type_id
        WHERE rt.status = 'active'
          AND date(rt.next_target_date, printf('-%d days', rt.reminder_days)) <= date(?)
          AND NOT EXISTS (
              SELECT 1 FROM preventive_tasks pt
              WHERE pt.recurrent_task_id = rt.id
                AND pt.target_date = rt.next_target_date
          )
        ORDER BY rt.next_target_date, rt.id
        """,
        (release_date,),
    ).fetchall()
    generated: list[dict] = []
    for schedule in schedules:
        task, _reason = create_preventive_task_record(database, schedule)
        if task is not None:
            generated.append(task)
    return generated


def add_infobox_history(
    database: sqlite3.Connection,
    item_id: int,
    action: str,
    details: str | None = None,
    user_id: int | None = None,
) -> None:
    if user_id is None and getattr(g, "current_user", None) is not None:
        user_id = g.current_user["id"]
    database.execute(
        """
        INSERT INTO inbox_history (
            inbox_item_id, action, user_id, details, created_at
        ) VALUES (?, ?, ?, ?, ?)
        """,
        (
            item_id,
            action,
            user_id,
            details,
            datetime.now().isoformat(timespec="minutes"),
        ),
    )


@app.before_request
def load_signed_in_user():
    g.current_user = None
    user_id = session.get("user_id")
    if user_id:
        g.current_user = get_db().execute(
            """
            SELECT id, employee_no, full_name, initials, department, role_name
            FROM users WHERE id = ? AND status = 'active'
            """,
            (user_id,),
        ).fetchone()
        if g.current_user is None:
            session.clear()
    if (
        request.path.startswith("/api/")
        and request.endpoint != "health"
        and g.current_user is None
    ):
        return jsonify({"error": "Authentication required"}), 401


@app.after_request
def audit_successful_mutations(response):
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault("Referrer-Policy", "same-origin")
    response.headers.setdefault(
        "Permissions-Policy",
        "camera=(), microphone=(), geolocation=()",
    )
    response.headers.setdefault(
        "Content-Security-Policy",
        "default-src 'self'; "
        "script-src 'self' https://unpkg.com; "
        "style-src 'self' https://fonts.googleapis.com; "
        "font-src 'self' https://fonts.gstatic.com; "
        "img-src 'self' data:; "
        "connect-src 'self'; "
        "frame-ancestors 'none'; "
        "base-uri 'self'; "
        "form-action 'self'",
    )
    if (
        request.path.startswith("/api/")
        and request.method in {"POST", "PATCH", "DELETE"}
        and response.status_code < 400
        and getattr(g, "current_user", None) is not None
    ):
        record_audit(
            audit_action_name(request.method, request.path),
            request.path,
            request.method,
            response.status_code,
            sanitized_request_details(),
        )
    return response


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if g.current_user is None:
            if request.path.startswith("/api/"):
                return jsonify({"error": "Authentication required"}), 401
            return redirect(url_for("login"))
        return view(*args, **kwargs)
    return wrapped


def roles_required(*roles: str):
    def decorator(view):
        @wraps(view)
        @login_required
        def wrapped(*args, **kwargs):
            if (
                g.current_user["role_name"] != "System Administrator"
                and g.current_user["role_name"] not in roles
            ):
                return jsonify({"error": "Your role is not authorized for this action"}), 403
            return view(*args, **kwargs)
        return wrapped
    return decorator


def current_user_has_role(*roles: str) -> bool:
    role_name = g.current_user["role_name"]
    return role_name == "System Administrator" or role_name in roles


def execution_roles_for_department(department: str) -> tuple[str, ...]:
    return {
        "Control & Instrumentation": ("C&I Technician",),
        "Electrical Maintenance": ("Electrical Technician",),
        "Mechanical Maintenance": ("Mechanical Technician",),
        "Operations": ("Shift Leader",),
    }.get(department, ("Maintenance Planner",))


def required_roles_for_work_order_action(
    action: str, department: str
) -> tuple[str, ...]:
    if action in {"submit_plan", "resubmit_work"}:
        return ("Maintenance Planner",)
    if action in {
        "approve_plan", "return_plan", "accept_work", "deny_acceptance",
    }:
        return ("Maintenance Approver",)
    if action == "confirm_execution":
        return ("Shift Leader",)
    if action == "complete_work":
        return execution_roles_for_department(department)
    return ()


def can_create_logbook_entry(logbook: sqlite3.Row) -> bool:
    role_name = g.current_user["role_name"]
    return (
        role_name in {"System Administrator", "Shift Leader"}
        or role_name == logbook["can_create_role"]
        or g.current_user["department"] == logbook["can_create_role"]
    )


@app.route("/login", methods=["GET", "POST"])
def login():
    if g.current_user is not None:
        return redirect(url_for("index"))
    error = None
    if request.method == "POST":
        employee_no = str(request.form.get("employee_no") or "").strip().upper()
        password = str(request.form.get("password") or "")
        user = get_db().execute(
            """
            SELECT id, password_hash FROM users
            WHERE employee_no = ? AND status = 'active'
            """,
            (employee_no,),
        ).fetchone()
        if user and check_password_hash(user["password_hash"], password):
            session.clear()
            session["user_id"] = user["id"]
            actor = get_db().execute(
                """
                SELECT id, employee_no, full_name, role_name
                FROM users WHERE id = ?
                """,
                (user["id"],),
            ).fetchone()
            record_audit("Signed in", "/login", "POST", 302, user=actor)
            return redirect(url_for("index"))
        error = "Invalid employee number or password."
    return render_template("login.html", error=error)


@app.post("/logout")
def logout():
    if g.current_user is not None:
        record_audit("Signed out", "/logout", "POST", 302)
    session.clear()
    return redirect(url_for("login"))


@app.get("/")
@login_required
def index():
    return render_template("index.html", current_user=row_to_dict(g.current_user))


@app.get("/print/<entity_type>/<int:entity_id>")
@login_required
def print_document(entity_type: str, entity_id: int):
    database = get_db()
    attachment_entity = entity_type
    attachment_entity_id = entity_id
    if entity_type == "event":
        record = get_event(entity_id)
        record["comments"] = [
            row_to_dict(row) for row in database.execute(
                """
                SELECT entry_no, observation, created_by, created_at
                FROM event_entries WHERE parent_id = ?
                ORDER BY event_date, id
                """,
                (entity_id,),
            ).fetchall()
        ]
        title = "Event Log Record"
        document_no = record["entry_no"]
    elif entity_type == "corrective":
        record = get_work_request(entity_id)
        order_id = record.get("work_order_id")
        record["supplies"] = []
        record["artisans"] = []
        record["history"] = []
        if order_id:
            record["supplies"] = [
                row_to_dict(row) for row in database.execute(
                    "SELECT * FROM work_order_supplies WHERE work_order_id = ? ORDER BY id",
                    (order_id,),
                ).fetchall()
            ]
            record["artisans"] = [
                row_to_dict(row) for row in database.execute(
                    "SELECT * FROM work_order_artisans WHERE work_order_id = ? ORDER BY id",
                    (order_id,),
                ).fetchall()
            ]
            record["history"] = [
                row_to_dict(row) for row in database.execute(
                    "SELECT * FROM work_order_history WHERE work_order_id = ? ORDER BY id",
                    (order_id,),
                ).fetchall()
            ]
        title = "Corrective Maintenance Work Record"
        document_no = record.get("order_no") or record["request_no"]
    elif entity_type == "preventive_task":
        row = database.execute(
            """
            SELECT pt.*, rt.recurrent_no, rt.name, rt.type_of_work,
                rt.main_department, rt.work_schedule, rt.duration_hours,
                rt.id AS recurrent_task_id,
                st.name AS schedule_type_name, st.strategy,
                a.kks_code, a.description AS asset_description
            FROM preventive_tasks pt
            JOIN recurrent_tasks rt ON rt.id = pt.recurrent_task_id
            JOIN schedule_types st ON st.id = rt.schedule_type_id
            JOIN assets a ON a.id = rt.primary_asset_id
            WHERE pt.id = ?
            """,
            (entity_id,),
        ).fetchone()
        if row is None:
            abort(404)
        record = row_to_dict(row)
        record["assets"] = [
            row_to_dict(asset) for asset in database.execute(
                """
                SELECT a.kks_code, a.description
                FROM recurrent_task_assets ra
                JOIN assets a ON a.id = ra.asset_id
                WHERE ra.recurrent_task_id = ? ORDER BY a.kks_code
                """,
                (record["recurrent_task_id"],),
            ).fetchall()
        ]
        title = "Preventive Maintenance Task Record"
        document_no = record["task_no"]
        attachment_entity = "preventive"
        attachment_entity_id = record["recurrent_task_id"]
    elif entity_type == "preventive":
        record = get_recurrent_task(entity_id)
        record["assets"] = [
            row_to_dict(row) for row in database.execute(
                """
                SELECT a.kks_code, a.description
                FROM recurrent_task_assets ra
                JOIN assets a ON a.id = ra.asset_id
                WHERE ra.recurrent_task_id = ? ORDER BY a.kks_code
                """,
                (entity_id,),
            ).fetchall()
        ]
        record["generated_tasks"] = [
            row_to_dict(row) for row in database.execute(
                """
                SELECT * FROM preventive_tasks
                WHERE recurrent_task_id = ? ORDER BY target_date
                """,
                (entity_id,),
            ).fetchall()
        ]
        title = "Preventive Maintenance Schedule"
        document_no = record["recurrent_no"]
    elif entity_type == "permit":
        record = get_safety_permit(entity_id)
        record["precautions"] = [
            row_to_dict(row) for row in database.execute(
                """
                SELECT precaution_text, selected FROM permit_precautions
                WHERE permit_id = ? ORDER BY id
                """,
                (entity_id,),
            ).fetchall()
        ]
        record["assessments"] = [
            row_to_dict(row) for row in database.execute(
                """
                SELECT assessment_type, answer, remarks
                FROM permit_special_assessments WHERE permit_id = ? ORDER BY id
                """,
                (entity_id,),
            ).fetchall()
        ]
        if record["form_type"].endswith("sft"):
            title = "Sanction for Test"
        elif record["form_type"].endswith("ptw"):
            title = "Permit to Work"
        else:
            title = "Limitation of Access"
        document_no = record["permit_no"]
    elif entity_type == "asset":
        record = asset_detail(entity_id).get_json()
        title = "KKS Asset History Record"
        document_no = record["kks_code"]
        attachment_entity = None
    else:
        abort(404)

    record["attachments"] = (
        attachment_rows(attachment_entity, attachment_entity_id)
        if attachment_entity else []
    )
    return render_template(
        "print_document.html",
        entity_type=entity_type,
        record=record,
        title=title,
        document_no=document_no,
        printed_by=g.current_user["full_name"],
        printed_at=datetime.now().isoformat(timespec="minutes"),
    )


@app.get("/api/health")
def health():
    return jsonify({"status": "ok", "station": "Morupule B Power Station"})


@app.get("/api/me")
def current_user():
    return jsonify(row_to_dict(g.current_user))


@app.get("/api/dashboard")
@login_required
def dashboard():
    database = get_db()
    sync_infobox(database)
    row = database.execute(
        """
        SELECT
            (SELECT COUNT(*) FROM event_entries WHERE state = 'open') AS open_events,
            (SELECT COUNT(*) FROM event_entries WHERE date(event_date) = date('now')) AS events_today,
            (SELECT COUNT(*) FROM assets WHERE status = 'active') AS active_assets,
            (SELECT COUNT(*) FROM logbooks) AS logbooks,
            (SELECT COUNT(*) FROM work_requests WHERE status = 'submitted') AS pending_requests,
            (SELECT COUNT(*) FROM work_orders WHERE workflow_step != 'closed') AS active_work_orders,
            (SELECT COUNT(*) FROM preventive_tasks WHERE status IN ('due', 'overdue')) AS preventive_due,
            (SELECT COUNT(*) FROM safety_permits WHERE status NOT IN ('cancelled')) AS active_permits,
            (
                SELECT COUNT(*) FROM inbox_items i
                JOIN inbox_recipients r ON r.inbox_item_id = i.id
                WHERE r.user_id = ?
                  AND (i.status = 'open' OR (i.status = 'claimed' AND i.claimed_by = ?))
            ) AS my_infobox
        """,
        (g.current_user["id"], g.current_user["id"]),
    ).fetchone()
    return jsonify(row_to_dict(row))


@app.get("/api/reports/summary")
def reports_summary():
    start, end = report_date_range()
    database = get_db()
    counts = database.execute(
        """
        SELECT
            (SELECT COUNT(*) FROM event_entries
             WHERE date(event_date) BETWEEN date(?) AND date(?)) AS events,
            (SELECT COUNT(*) FROM event_entries
             WHERE state = 'open' AND date(event_date) BETWEEN date(?) AND date(?)) AS open_events,
            (SELECT COUNT(*) FROM work_requests
             WHERE date(created_at) BETWEEN date(?) AND date(?)) AS work_requests,
            (SELECT COUNT(*) FROM work_requests
             WHERE status = 'submitted' AND date(created_at) BETWEEN date(?) AND date(?)) AS pending_requests,
            (SELECT COUNT(*) FROM preventive_tasks
             WHERE date(target_date) BETWEEN date(?) AND date(?)) AS preventive_tasks,
            (SELECT COUNT(*) FROM preventive_tasks
             WHERE status = 'overdue' AND date(target_date) BETWEEN date(?) AND date(?)) AS overdue_preventive,
            (SELECT COUNT(*) FROM safety_permits
             WHERE date(created_at) BETWEEN date(?) AND date(?)) AS permits,
            (SELECT COUNT(*) FROM safety_permits
             WHERE status IN ('issued', 'received') AND date(created_at) BETWEEN date(?) AND date(?)) AS active_permits
        """,
        (start, end) * 8,
    ).fetchone()
    daily = database.execute(
        """
        SELECT activity_date,
            SUM(events) AS events,
            SUM(corrective) AS corrective,
            SUM(preventive) AS preventive,
            SUM(permits) AS permits
        FROM (
            SELECT date(event_date) AS activity_date, COUNT(*) AS events,
                0 AS corrective, 0 AS preventive, 0 AS permits
            FROM event_entries
            WHERE date(event_date) BETWEEN date(?) AND date(?)
            GROUP BY date(event_date)
            UNION ALL
            SELECT date(created_at), 0, COUNT(*), 0, 0
            FROM work_requests
            WHERE date(created_at) BETWEEN date(?) AND date(?)
            GROUP BY date(created_at)
            UNION ALL
            SELECT date(target_date), 0, 0, COUNT(*), 0
            FROM preventive_tasks
            WHERE date(target_date) BETWEEN date(?) AND date(?)
            GROUP BY date(target_date)
            UNION ALL
            SELECT date(created_at), 0, 0, 0, COUNT(*)
            FROM safety_permits
            WHERE date(created_at) BETWEEN date(?) AND date(?)
            GROUP BY date(created_at)
        )
        GROUP BY activity_date
        ORDER BY activity_date
        """,
        (start, end) * 4,
    ).fetchall()
    areas = database.execute(
        """
        SELECT responsible_area, COUNT(*) AS total
        FROM (
            SELECT COALESCE(a.responsible_area, 'Unassigned') AS responsible_area
            FROM event_entries e LEFT JOIN assets a ON a.id = e.asset_id
            WHERE date(e.event_date) BETWEEN date(?) AND date(?)
            UNION ALL
            SELECT COALESCE(a.responsible_area, 'Unassigned')
            FROM work_requests wr JOIN assets a ON a.id = wr.asset_id
            WHERE date(wr.created_at) BETWEEN date(?) AND date(?)
            UNION ALL
            SELECT COALESCE(a.responsible_area, 'Unassigned')
            FROM preventive_tasks pt
            JOIN recurrent_tasks rt ON rt.id = pt.recurrent_task_id
            JOIN assets a ON a.id = rt.primary_asset_id
            WHERE date(pt.target_date) BETWEEN date(?) AND date(?)
            UNION ALL
            SELECT COALESCE(a.responsible_area, 'Unassigned')
            FROM safety_permits p JOIN assets a ON a.id = p.asset_id
            WHERE date(p.created_at) BETWEEN date(?) AND date(?)
        )
        GROUP BY responsible_area
        ORDER BY total DESC, responsible_area
        LIMIT 12
        """,
        (start, end) * 4,
    ).fetchall()
    statuses = {
        "events": [
            row_to_dict(row) for row in database.execute(
                """
                SELECT state AS status, COUNT(*) AS total FROM event_entries
                WHERE date(event_date) BETWEEN date(?) AND date(?)
                GROUP BY state ORDER BY total DESC
                """,
                (start, end),
            ).fetchall()
        ],
        "corrective": [
            row_to_dict(row) for row in database.execute(
                """
                SELECT status, COUNT(*) AS total FROM work_requests
                WHERE date(created_at) BETWEEN date(?) AND date(?)
                GROUP BY status ORDER BY total DESC
                """,
                (start, end),
            ).fetchall()
        ],
        "preventive": [
            row_to_dict(row) for row in database.execute(
                """
                SELECT status, COUNT(*) AS total FROM preventive_tasks
                WHERE date(target_date) BETWEEN date(?) AND date(?)
                GROUP BY status ORDER BY total DESC
                """,
                (start, end),
            ).fetchall()
        ],
        "permits": [
            row_to_dict(row) for row in database.execute(
                """
                SELECT status, COUNT(*) AS total FROM safety_permits
                WHERE date(created_at) BETWEEN date(?) AND date(?)
                GROUP BY status ORDER BY total DESC
                """,
                (start, end),
            ).fetchall()
        ],
    }
    performance = database.execute(
        """
        SELECT
            (
                SELECT COUNT(*) FROM work_orders
                WHERE execution_completed_at IS NOT NULL
                  AND date(execution_completed_at) BETWEEN date(?) AND date(?)
            ) AS completed_corrective,
            (
                SELECT COALESCE(SUM(expected_man_hours), 0) FROM work_orders
                WHERE execution_completed_at IS NOT NULL
                  AND date(execution_completed_at) BETWEEN date(?) AND date(?)
            ) AS corrective_planned_hours,
            (
                SELECT COALESCE(SUM(actual_man_hours), 0) FROM work_orders
                WHERE execution_completed_at IS NOT NULL
                  AND date(execution_completed_at) BETWEEN date(?) AND date(?)
            ) AS corrective_actual_hours,
            (
                SELECT COUNT(*) FROM preventive_tasks
                WHERE completed_at IS NOT NULL
                  AND date(completed_at) BETWEEN date(?) AND date(?)
            ) AS completed_preventive,
            (
                SELECT COALESCE(SUM(rt.duration_hours), 0)
                FROM preventive_tasks pt
                JOIN recurrent_tasks rt ON rt.id = pt.recurrent_task_id
                WHERE pt.completed_at IS NOT NULL
                  AND date(pt.completed_at) BETWEEN date(?) AND date(?)
            ) AS preventive_planned_hours,
            (
                SELECT COALESCE(SUM(actual_man_hours), 0) FROM preventive_tasks
                WHERE completed_at IS NOT NULL
                  AND date(completed_at) BETWEEN date(?) AND date(?)
            ) AS preventive_actual_hours,
            (
                SELECT COUNT(*) FROM work_orders
                WHERE acceptance_status = 'accepted'
                  AND acceptance_checked_at IS NOT NULL
                  AND date(acceptance_checked_at) BETWEEN date(?) AND date(?)
            ) AS accepted_work,
            (
                SELECT COUNT(*) FROM work_orders
                WHERE acceptance_status = 'denied'
                  AND acceptance_checked_at IS NOT NULL
                  AND date(acceptance_checked_at) BETWEEN date(?) AND date(?)
            ) AS denied_work
        """,
        (start, end) * 8,
    ).fetchone()
    response_compliance = row_to_dict(database.execute(
        """
        SELECT
            COUNT(*) AS targeted,
            COALESCE(SUM(CASE
                WHEN wo.workflow_step = 'closed'
                  AND wo.acceptance_checked_at IS NOT NULL
                  AND datetime(wo.acceptance_checked_at) <= datetime(wr.target_response_at)
                THEN 1 ELSE 0 END), 0) AS met,
            COALESCE(SUM(CASE
                WHEN (
                    wo.workflow_step = 'closed'
                    AND wo.acceptance_checked_at IS NOT NULL
                    AND datetime(wo.acceptance_checked_at) > datetime(wr.target_response_at)
                ) OR (
                    COALESCE(wo.workflow_step, '') != 'closed'
                    AND datetime(wr.target_response_at) < datetime('now', 'localtime')
                )
                THEN 1 ELSE 0 END), 0) AS breached,
            COALESCE(SUM(CASE
                WHEN COALESCE(wo.workflow_step, '') != 'closed'
                  AND datetime(wr.target_response_at) >= datetime('now', 'localtime')
                THEN 1 ELSE 0 END), 0) AS pending
        FROM work_requests wr
        LEFT JOIN work_orders wo ON wo.work_request_id = wr.id
        WHERE wr.status != 'declined'
          AND wr.target_response_at IS NOT NULL
          AND date(wr.created_at) BETWEEN date(?) AND date(?)
        """,
        (start, end),
    ).fetchone())
    completed_targets = response_compliance["met"] + response_compliance["breached"]
    response_compliance["compliance_percent"] = (
        round(response_compliance["met"] * 100 / completed_targets, 1)
        if completed_targets else None
    )
    reliability = row_to_dict(database.execute(
        """
        SELECT
            COUNT(CASE WHEN NULLIF(TRIM(wo.failure_mode), '') IS NOT NULL THEN 1 END)
                AS classified_failures,
            COUNT(CASE WHEN wo.downtime_hours IS NOT NULL THEN 1 END)
                AS downtime_events,
            COALESCE(SUM(wo.downtime_hours), 0) AS total_downtime_hours,
            COALESCE(AVG(wo.downtime_hours), 0) AS mttr_hours,
            (
                SELECT COUNT(*) FROM (
                    SELECT wr2.asset_id
                    FROM work_orders wo2
                    JOIN work_requests wr2 ON wr2.id = wo2.work_request_id
                    WHERE NULLIF(TRIM(wo2.failure_mode), '') IS NOT NULL
                      AND wo2.execution_completed_at IS NOT NULL
                      AND date(wo2.execution_completed_at) BETWEEN date(?) AND date(?)
                    GROUP BY wr2.asset_id HAVING COUNT(*) >= 2
                )
            ) AS repeat_failure_assets
        FROM work_orders wo
        WHERE wo.execution_completed_at IS NOT NULL
          AND date(wo.execution_completed_at) BETWEEN date(?) AND date(?)
        """,
        (start, end, start, end),
    ).fetchone())
    reliability["total_downtime_hours"] = round(
        float(reliability["total_downtime_hours"] or 0), 2
    )
    reliability["mttr_hours"] = round(float(reliability["mttr_hours"] or 0), 2)
    reliability["top_failure_assets"] = [
        row_to_dict(row) for row in database.execute(
            """
            SELECT a.kks_code, a.description,
                COUNT(*) AS failures,
                ROUND(COALESCE(SUM(wo.downtime_hours), 0), 2) AS downtime_hours
            FROM work_orders wo
            JOIN work_requests wr ON wr.id = wo.work_request_id
            JOIN assets a ON a.id = wr.asset_id
            WHERE NULLIF(TRIM(wo.failure_mode), '') IS NOT NULL
              AND wo.execution_completed_at IS NOT NULL
              AND date(wo.execution_completed_at) BETWEEN date(?) AND date(?)
            GROUP BY a.id, a.kks_code, a.description
            ORDER BY downtime_hours DESC, failures DESC, a.kks_code
            LIMIT 8
            """,
            (start, end),
        ).fetchall()
    ]
    maintenance_kpis = row_to_dict(database.execute(
        """
        SELECT
            (SELECT COUNT(*) FROM preventive_tasks
             WHERE date(target_date) BETWEEN date(?) AND date(?)) AS pm_due,
            (SELECT COUNT(*) FROM preventive_tasks
             WHERE date(target_date) BETWEEN date(?) AND date(?)
               AND completed_at IS NOT NULL
               AND datetime(completed_at) <= datetime(late_date, '+1 day')) AS pm_completed_on_time,
            (SELECT COUNT(*) FROM work_orders wo
             JOIN work_requests wr ON wr.id = wo.work_request_id
             WHERE wo.execution_completed_at IS NOT NULL
               AND wr.planned_end IS NOT NULL
               AND date(wo.execution_completed_at) BETWEEN date(?) AND date(?)) AS corrective_scheduled_completed,
            (SELECT COUNT(*) FROM work_orders wo
             JOIN work_requests wr ON wr.id = wo.work_request_id
             WHERE wo.execution_completed_at IS NOT NULL
               AND wr.planned_end IS NOT NULL
               AND date(wo.execution_completed_at) BETWEEN date(?) AND date(?)
               AND datetime(wo.execution_completed_at) <= datetime(wr.planned_end)) AS corrective_on_schedule,
            (SELECT COUNT(*) FROM work_orders wo
             JOIN work_requests wr ON wr.id = wo.work_request_id
             WHERE wo.workflow_step != 'closed'
               AND date(wr.created_at) <= date(?)) AS corrective_backlog,
            (SELECT COUNT(*) FROM work_orders wo
             JOIN work_requests wr ON wr.id = wo.work_request_id
             WHERE wo.workflow_step != 'closed'
               AND date(wr.created_at) <= date(?)
               AND julianday(?) - julianday(wr.created_at) >= 30) AS backlog_over_30_days,
            (SELECT COALESCE(AVG(MAX(0, julianday(?) - julianday(wr.created_at))), 0)
             FROM work_orders wo
             JOIN work_requests wr ON wr.id = wo.work_request_id
             WHERE wo.workflow_step != 'closed'
               AND date(wr.created_at) <= date(?)) AS average_backlog_age_days
        """,
        (start, end, start, end, start, end, start, end, end, end, end, end, end),
    ).fetchone())
    maintenance_kpis["pm_compliance_percent"] = (
        round(maintenance_kpis["pm_completed_on_time"] * 100 / maintenance_kpis["pm_due"], 1)
        if maintenance_kpis["pm_due"] else None
    )
    maintenance_kpis["corrective_schedule_percent"] = (
        round(
            maintenance_kpis["corrective_on_schedule"] * 100
            / maintenance_kpis["corrective_scheduled_completed"],
            1,
        )
        if maintenance_kpis["corrective_scheduled_completed"] else None
    )
    maintenance_kpis["average_backlog_age_days"] = round(
        float(maintenance_kpis["average_backlog_age_days"] or 0), 1
    )
    return jsonify({
        "start": start,
        "end": end,
        "counts": row_to_dict(counts),
        "daily": [row_to_dict(row) for row in daily],
        "areas": [row_to_dict(row) for row in areas],
        "statuses": statuses,
        "performance": row_to_dict(performance),
        "response_compliance": response_compliance,
        "reliability": reliability,
        "maintenance_kpis": maintenance_kpis,
    })


@app.get("/print/management-report")
@login_required
def print_management_report():
    result = reports_summary()
    if isinstance(result, tuple):
        return result
    report = result.get_json()
    generated_at = datetime.now()
    for item in report["daily"]:
        item["display_date"] = date.fromisoformat(item["activity_date"]).strftime("%d %b %Y")
    return render_template(
        "management_report.html",
        report=report,
        period_start=date.fromisoformat(report["start"]).strftime("%d %b %Y"),
        period_end=date.fromisoformat(report["end"]).strftime("%d %b %Y"),
        generated_at=generated_at.strftime("%d %b %Y %H:%M"),
        generated_by=g.current_user["full_name"],
    )


@app.get("/api/reports/activity.csv")
def export_activity_report():
    start, end = report_date_range()
    rows = get_db().execute(
        """
        SELECT * FROM (
            SELECT e.event_date AS activity_date, 'Event Log' AS module,
                e.entry_no AS record_no, e.state AS status,
                COALESCE(a.kks_code, '') AS kks_code,
                e.subject AS description,
                COALESCE(a.responsible_area, '') AS responsible_area,
                e.created_by AS responsible_person,
                NULL AS planned_hours, NULL AS actual_hours,
                e.observation AS outcome
            FROM event_entries e LEFT JOIN assets a ON a.id = e.asset_id
            WHERE date(e.event_date) BETWEEN date(?) AND date(?)
            UNION ALL
            SELECT wr.created_at, 'Corrective Maintenance', wr.request_no,
                wr.status, a.kks_code, wr.name,
                COALESCE(a.responsible_area, ''), wr.author,
                wo.expected_man_hours, wo.actual_man_hours,
                COALESCE(wo.acceptance_note, wo.acceptance_reason, wo.completion_summary, wr.observation)
            FROM work_requests wr JOIN assets a ON a.id = wr.asset_id
            LEFT JOIN work_orders wo ON wo.work_request_id = wr.id
            WHERE date(wr.created_at) BETWEEN date(?) AND date(?)
            UNION ALL
            SELECT pt.target_date, 'Preventive Maintenance', pt.task_no,
                pt.status, a.kks_code, rt.name,
                COALESCE(a.responsible_area, ''), COALESCE(pt.completed_by, rt.created_by),
                rt.duration_hours, pt.actual_man_hours, COALESCE(pt.feedback, rt.work_schedule, '')
            FROM preventive_tasks pt
            JOIN recurrent_tasks rt ON rt.id = pt.recurrent_task_id
            JOIN assets a ON a.id = rt.primary_asset_id
            WHERE date(pt.target_date) BETWEEN date(?) AND date(?)
            UNION ALL
            SELECT p.created_at, 'PTW / LoA / SFT', p.permit_no,
                p.status, a.kks_code, p.work_description,
                COALESCE(a.responsible_area, ''), p.prepared_by,
                NULL, NULL, COALESCE(
                    (
                        SELECT remarks FROM permit_transition_history ph
                        WHERE ph.permit_id = p.id ORDER BY ph.id DESC LIMIT 1
                    ),
                    p.location
                )
            FROM safety_permits p JOIN assets a ON a.id = p.asset_id
            WHERE date(p.created_at) BETWEEN date(?) AND date(?)
        )
        ORDER BY activity_date DESC, module, record_no
        """,
        (start, end) * 4,
    ).fetchall()
    output = io.StringIO()
    writer = csv.writer(output, lineterminator="\n")
    writer.writerow([
        "Activity Date", "Module", "Record Number", "Status", "KKS Code",
        "Description", "Responsible Area", "Responsible Person",
        "Planned Hours", "Actual Hours", "Outcome / Remarks",
    ])
    writer.writerows([tuple(row) for row in rows])
    filename = f"morupule-b-sipam-activity-{start}-to-{end}.csv"
    return Response(
        "\ufeff" + output.getvalue(),
        mimetype="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@app.get("/api/attachments/<entity_type>/<int:entity_id>")
def list_attachments(entity_type: str, entity_id: int):
    validate_attachment_entity(entity_type, entity_id)
    return jsonify(attachment_rows(entity_type, entity_id))


@app.post("/api/attachments/<entity_type>/<int:entity_id>")
def upload_attachment(entity_type: str, entity_id: int):
    validate_attachment_entity(entity_type, entity_id)
    uploaded = request.files.get("file")
    if uploaded is None or not uploaded.filename:
        return jsonify({"error": "Select a file to upload"}), 400
    original_name = secure_filename(uploaded.filename)
    extension = original_name.rsplit(".", 1)[-1].lower() if "." in original_name else ""
    if extension not in ALLOWED_ATTACHMENT_EXTENSIONS:
        return jsonify({"error": "This file type is not permitted"}), 400
    stored_name = f"{uuid.uuid4().hex}.{extension}"
    target = Path(app.config["UPLOAD_FOLDER"]) / stored_name
    uploaded.save(target)
    file_size = target.stat().st_size
    cursor = get_db().execute(
        """
        INSERT INTO attachments (
            entity_type, entity_id, original_name, stored_name, content_type,
            file_size, uploaded_by_id, uploaded_by_name, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            entity_type,
            entity_id,
            original_name,
            stored_name,
            uploaded.mimetype,
            file_size,
            g.current_user["id"],
            g.current_user["full_name"],
            datetime.now().isoformat(timespec="seconds"),
        ),
    )
    get_db().commit()
    return jsonify({"id": cursor.lastrowid, "original_name": original_name}), 201


@app.get("/api/attachments/file/<int:attachment_id>")
def download_attachment(attachment_id: int):
    row = get_db().execute(
        "SELECT original_name, stored_name FROM attachments WHERE id = ?",
        (attachment_id,),
    ).fetchone()
    if row is None:
        abort(404)
    return send_from_directory(
        app.config["UPLOAD_FOLDER"],
        row["stored_name"],
        as_attachment=True,
        download_name=row["original_name"],
    )


@app.delete("/api/attachments/<int:attachment_id>")
@roles_required("System Administrator")
def delete_attachment(attachment_id: int):
    database = get_db()
    row = database.execute(
        "SELECT stored_name FROM attachments WHERE id = ?",
        (attachment_id,),
    ).fetchone()
    if row is None:
        abort(404)
    database.execute("DELETE FROM attachments WHERE id = ?", (attachment_id,))
    database.commit()
    target = Path(app.config["UPLOAD_FOLDER"]) / row["stored_name"]
    if target.exists():
        target.unlink()
    return jsonify({"status": "deleted", "attachment_id": attachment_id})


@app.get("/api/assets")
def list_assets():
    database = get_db()
    query = str(request.args.get("q") or "").strip()
    reference_only = request.args.get("reference") == "1"
    parent_value = request.args.get("parent_id")
    try:
        limit = min(max(int(request.args.get("limit", 200)), 1), 500)
    except ValueError:
        limit = 200

    where = []
    parameters: list[object] = []
    if reference_only:
        where.append("a.is_reference = 1")
    elif query:
        where.append(
            "(a.kks_code LIKE ? OR a.description LIKE ? OR COALESCE(a.responsible_area, '') LIKE ?)"
        )
        term = f"%{query}%"
        parameters.extend([term, term, term])
    elif parent_value is not None:
        try:
            parent_id = int(parent_value)
        except ValueError:
            return jsonify({"error": "parent_id must be an integer"}), 400
        where.append("a.parent_id = ?")
        parameters.append(parent_id)
    else:
        where.append("a.parent_id IS NULL")

    parameters.append(limit)
    rows = database.execute(
        f"""
        SELECT
            a.id, a.parent_id, a.kks_code, a.description,
            a.hierarchy_level, a.level_no, a.status,
            a.responsible_area, a.source_kind, a.is_reference,
            (SELECT COUNT(*) FROM assets c WHERE c.parent_id = a.id) AS child_count
        FROM assets a
        WHERE {' AND '.join(where)}
        ORDER BY a.level_no, a.kks_code
        LIMIT ?
        """,
        parameters,
    ).fetchall()
    return jsonify([row_to_dict(row) for row in rows])


@app.get("/api/assets/<int:asset_id>")
def asset_detail(asset_id: int):
    database = get_db()
    row = database.execute(
        """
        SELECT
            a.*,
            p.kks_code AS parent_kks_code,
            p.description AS parent_description
        FROM assets a
        LEFT JOIN assets p ON p.id = a.parent_id
        WHERE a.id = ?
        """,
        (asset_id,),
    ).fetchone()
    if row is None:
        abort(404)
    asset = row_to_dict(row)
    asset["children"] = [
        row_to_dict(item) for item in database.execute(
            """
            SELECT
                id, kks_code, description, hierarchy_level, status,
                responsible_area,
                (SELECT COUNT(*) FROM assets c WHERE c.parent_id = assets.id) AS child_count
            FROM assets WHERE parent_id = ? ORDER BY kks_code
            """,
            (asset_id,),
        ).fetchall()
    ]
    asset["events"] = [
        row_to_dict(item) for item in database.execute(
            """
            SELECT id, entry_no, subject, event_date, state, observation
            FROM event_entries WHERE asset_id = ?
            ORDER BY event_date DESC, id DESC
            """,
            (asset_id,),
        ).fetchall()
    ]
    asset["corrective"] = [
        row_to_dict(item) for item in database.execute(
            """
            SELECT
                wr.id, wr.request_no, wr.name, wr.priority, wr.status,
                wr.created_at, wo.order_no, wo.workflow_step
            FROM work_requests wr
            LEFT JOIN work_orders wo ON wo.work_request_id = wr.id
            WHERE wr.asset_id = ?
            ORDER BY wr.created_at DESC
            """,
            (asset_id,),
        ).fetchall()
    ]
    asset["recurrent"] = [
        row_to_dict(item) for item in database.execute(
            """
            SELECT DISTINCT
                rt.id, rt.recurrent_no, rt.name, rt.next_target_date,
                rt.status, st.name AS schedule_type_name
            FROM recurrent_tasks rt
            JOIN schedule_types st ON st.id = rt.schedule_type_id
            JOIN recurrent_task_assets ra ON ra.recurrent_task_id = rt.id
            WHERE ra.asset_id = ?
            ORDER BY rt.next_target_date
            """,
            (asset_id,),
        ).fetchall()
    ]
    asset["preventive"] = [
        row_to_dict(item) for item in database.execute(
            """
            SELECT DISTINCT
                pt.id, pt.task_no, pt.target_date, pt.status,
                pt.completed_at, rt.name AS recurrent_name
            FROM preventive_tasks pt
            JOIN recurrent_tasks rt ON rt.id = pt.recurrent_task_id
            JOIN recurrent_task_assets ra ON ra.recurrent_task_id = rt.id
            WHERE ra.asset_id = ?
            ORDER BY pt.target_date DESC
            """,
            (asset_id,),
        ).fetchall()
    ]
    asset["permits"] = [
        row_to_dict(item) for item in database.execute(
            """
            SELECT id, permit_no, form_type, status, work_description, created_at
            FROM safety_permits WHERE asset_id = ?
            ORDER BY created_at DESC
            """,
            (asset_id,),
        ).fetchall()
    ]
    asset["counts"] = {
        "events": len(asset["events"]),
        "corrective": len(asset["corrective"]),
        "recurrent": len(asset["recurrent"]),
        "preventive": len(asset["preventive"]),
        "permits": len(asset["permits"]),
    }
    return jsonify(asset)


@app.get("/api/logbooks")
def list_logbooks():
    rows = get_db().execute(
        """
        SELECT id, code, name, department, can_create_role, is_shift_leader
        FROM logbooks ORDER BY is_shift_leader DESC, name
        """
    ).fetchall()
    return jsonify([row_to_dict(row) for row in rows])


def normalize_logbook_payload(payload: dict, existing: sqlite3.Row | None = None) -> tuple[dict | None, tuple[object, int] | None]:
    data = {
        "code": str(payload.get("code", existing["code"] if existing else "") or "").strip().upper(),
        "name": str(payload.get("name", existing["name"] if existing else "") or "").strip(),
        "department": str(payload.get("department", existing["department"] if existing else "") or "").strip(),
        "can_create_role": str(payload.get("can_create_role", existing["can_create_role"] if existing else "") or "").strip(),
        "is_shift_leader": 1 if payload.get(
            "is_shift_leader", existing["is_shift_leader"] if existing else False
        ) in {True, 1, "1", "true", "True", "on", "yes"} else 0,
    }
    missing = [key for key in ("code", "name", "department", "can_create_role") if not data[key]]
    if missing:
        return None, ({"error": "Missing required fields", "fields": missing}, 400)
    if data["can_create_role"] not in USER_ROLES:
        return None, ({"error": "Invalid role for logbook entry creation"}, 400)
    return data, None


@app.get("/api/admin/logbooks")
@roles_required("System Administrator")
def list_admin_logbooks():
    rows = get_db().execute(
        """
        SELECT
            l.id, l.code, l.name, l.department, l.can_create_role, l.is_shift_leader,
            COUNT(DISTINCT e.id) AS entry_count,
            COUNT(DISTINCT v.entry_id) AS visible_entry_count,
            COALESCE(MAX(e.created_at), MAX(copied.created_at)) AS last_activity_at
        FROM logbooks l
        LEFT JOIN event_entries e ON e.source_logbook_id = l.id
        LEFT JOIN event_entry_logbooks v ON v.logbook_id = l.id
        LEFT JOIN event_entries copied ON copied.id = v.entry_id
        GROUP BY l.id
        ORDER BY l.is_shift_leader DESC, l.name
        """
    ).fetchall()
    return jsonify([row_to_dict(row) for row in rows])


@app.post("/api/admin/logbooks")
@roles_required("System Administrator")
def create_logbook():
    payload = request.get_json(silent=True) or {}
    data, error = normalize_logbook_payload(payload)
    if error:
        body, status = error
        return jsonify(body), status
    database = get_db()
    try:
        cursor = database.execute(
            """
            INSERT INTO logbooks (code, name, department, can_create_role, is_shift_leader)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                data["code"], data["name"], data["department"],
                data["can_create_role"], data["is_shift_leader"],
            ),
        )
    except sqlite3.IntegrityError:
        return jsonify({"error": "Logbook code or name already exists"}), 409
    database.commit()
    row = database.execute(
        """
        SELECT id, code, name, department, can_create_role, is_shift_leader
        FROM logbooks WHERE id = ?
        """,
        (cursor.lastrowid,),
    ).fetchone()
    return jsonify(row_to_dict(row)), 201


@app.patch("/api/admin/logbooks/<int:logbook_id>")
@roles_required("System Administrator")
def update_logbook(logbook_id: int):
    database = get_db()
    existing = database.execute(
        "SELECT id, code, name, department, can_create_role, is_shift_leader FROM logbooks WHERE id = ?",
        (logbook_id,),
    ).fetchone()
    if existing is None:
        abort(404)
    payload = request.get_json(silent=True) or {}
    data, error = normalize_logbook_payload(payload, existing)
    if error:
        body, status = error
        return jsonify(body), status
    try:
        database.execute(
            """
            UPDATE logbooks
            SET code = ?, name = ?, department = ?, can_create_role = ?, is_shift_leader = ?
            WHERE id = ?
            """,
            (
                data["code"], data["name"], data["department"],
                data["can_create_role"], data["is_shift_leader"], logbook_id,
            ),
        )
    except sqlite3.IntegrityError:
        return jsonify({"error": "Logbook code or name already exists"}), 409
    database.commit()
    return jsonify({"status": "updated", "logbook_id": logbook_id})


@app.get("/api/events")
def list_events():
    filters = []
    parameters: list[object] = []
    logbook_id = request.args.get("logbook_id", "").strip()
    logbook_ids_value = request.args.get("logbook_ids", "").strip()
    start = request.args.get("start", "").strip()
    end = request.args.get("end", "").strip()
    state = request.args.get("state", "").strip().lower()
    search = request.args.get("q", "").strip().lower()

    start_date = None
    end_date = None
    if start:
        try:
            start_date = date.fromisoformat(start)
        except ValueError:
            return jsonify({"error": "Start date is invalid"}), 400
    if end:
        try:
            end_date = date.fromisoformat(end)
        except ValueError:
            return jsonify({"error": "End date is invalid"}), 400
        if end_date > date.today():
            return jsonify({"error": "End date cannot be in the future"}), 400
    if start_date and end_date and start_date > end_date:
        return jsonify({"error": "Start date cannot be after end date"}), 400

    selected_logbook_ids: list[int] = []
    if logbook_ids_value:
        values = [value.strip() for value in logbook_ids_value.split(",") if value.strip()]
        if not values or any(not value.isdigit() for value in values):
            return jsonify({"error": "Logbook IDs must be comma-separated integers"}), 400
        selected_logbook_ids = sorted({int(value) for value in values})
        existing_ids = {
            row["id"] for row in get_db().execute(
                f"SELECT id FROM logbooks WHERE id IN ({','.join('?' for _ in selected_logbook_ids)})",
                tuple(selected_logbook_ids),
            ).fetchall()
        }
        if existing_ids != set(selected_logbook_ids):
            return jsonify({"error": "One or more logbooks were not found"}), 400
        filters.append(
            f"v.logbook_id IN ({','.join('?' for _ in selected_logbook_ids)})"
        )
        parameters.extend(selected_logbook_ids)
    elif logbook_id.isdigit():
        filters.append("v.logbook_id = ?")
        parameters.append(int(logbook_id))
    if start:
        filters.append("date(e.event_date) >= date(?)")
        parameters.append(start)
    if end:
        filters.append("date(e.event_date) <= date(?)")
        parameters.append(end)
    if state in {"open", "closed"}:
        filters.append("e.state = ?")
        parameters.append(state)
    if search:
        filters.append(
            "(lower(e.entry_no) LIKE ? OR lower(e.subject) LIKE ? "
            "OR lower(e.observation) LIKE ? OR lower(COALESCE(a.kks_code, '')) LIKE ?)"
        )
        pattern = f"%{search}%"
        parameters.extend([pattern, pattern, pattern, pattern])

    sql = """
        SELECT DISTINCT
            e.*, a.kks_code, a.description AS asset_description,
            l.name AS source_logbook_name,
            (SELECT COUNT(*) FROM event_entries c WHERE c.parent_id = e.id) AS comment_count
        FROM event_entries e
        JOIN event_entry_logbooks v ON v.entry_id = e.id
        JOIN logbooks l ON l.id = e.source_logbook_id
        LEFT JOIN assets a ON a.id = e.asset_id
    """
    if filters:
        sql += " WHERE " + " AND ".join(filters)
    sql += " ORDER BY e.event_date DESC, e.id DESC"
    rows = get_db().execute(sql, parameters).fetchall()
    return jsonify([row_to_dict(row) for row in rows])


@app.get("/api/events/<int:event_id>")
def event_detail(event_id: int):
    event = get_event(event_id)
    database = get_db()
    comments = database.execute(
        """
        SELECT e.*, a.kks_code, a.description AS asset_description
        FROM event_entries e
        LEFT JOIN assets a ON a.id = e.asset_id
        WHERE e.parent_id = ?
        ORDER BY e.event_date, e.id
        """,
        (event_id,),
    ).fetchall()
    event["comments"] = [row_to_dict(row) for row in comments]
    event["state_history"] = [
        row_to_dict(row) for row in database.execute(
            """
            SELECT previous_state, new_state, changed_by, reason, created_at
            FROM event_state_history
            WHERE event_id = ?
            ORDER BY id DESC
            """,
            (event_id,),
        ).fetchall()
    ]
    event["edit_history"] = []
    for row in database.execute(
        """
        SELECT changed_by, changes, created_at
        FROM event_edit_history
        WHERE event_id = ? ORDER BY id DESC
        """,
        (event_id,),
    ).fetchall():
        change = row_to_dict(row)
        change["changes"] = json.loads(change["changes"])
        event["edit_history"].append(change)
    event["work_requests"] = [
        row_to_dict(row) for row in database.execute(
            """
            SELECT id, request_no, name, status, main_department, priority
            FROM work_requests
            WHERE source_event_id = ?
            ORDER BY id
            """,
            (event_id,),
        ).fetchall()
    ]
    event["attachments"] = attachment_rows("event", event_id)
    return jsonify(event)


@app.get("/api/events.csv")
def export_events():
    result = list_events()
    if isinstance(result, tuple):
        return result
    events = result.get_json()
    output = io.StringIO()
    writer = csv.writer(output, lineterminator="\n")
    writer.writerow([
        "Entry Number", "Entry Type", "Event Date", "State", "Logbook",
        "KKS Code", "Asset Description", "Subject", "Observation",
        "Informant", "Created By", "Created At", "Updated At",
    ])
    for event in events:
        writer.writerow([
            event["entry_no"], event["entry_type"], event["event_date"],
            event["state"], event["source_logbook_name"],
            event.get("kks_code") or "", event.get("asset_description") or "",
            event["subject"], event["observation"], event.get("informant") or "",
            event["created_by"], event["created_at"], event["updated_at"],
        ])
    filename = f"morupule-b-event-log-{date.today().isoformat()}.csv"
    return Response(
        "\ufeff" + output.getvalue(),
        mimetype="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@app.get("/print/shift-handover")
@login_required
def print_shift_handover():
    result = list_events()
    if isinstance(result, tuple):
        return result
    database = get_db()
    events = result.get_json()
    for event in events:
        event["work_requests"] = [
            row_to_dict(row) for row in database.execute(
                """
                SELECT request_no, name, status, main_department, priority
                FROM work_requests WHERE source_event_id = ? ORDER BY id
                """,
                (event["id"],),
            ).fetchall()
        ]
    selected_ids = request.args.get("logbook_ids", "").strip()
    logbook_names = []
    if selected_ids:
        ids = [int(value) for value in selected_ids.split(",") if value.isdigit()]
        if ids:
            logbook_names = [
                row["name"] for row in database.execute(
                    f"SELECT name FROM logbooks WHERE id IN ({','.join('?' for _ in ids)}) ORDER BY name",
                    ids,
                ).fetchall()
            ]
    return render_template(
        "shift_handover.html",
        events=events,
        start=request.args.get("start") or "All available",
        end=request.args.get("end") or "Current",
        logbooks=logbook_names or ["All authorized logbooks"],
        generated_at=datetime.now().isoformat(timespec="minutes"),
        open_count=sum(1 for event in events if event["state"] == "open"),
        linked_request_count=sum(len(event["work_requests"]) for event in events),
    )


def get_shift_handover(handover_id: int) -> dict:
    database = get_db()
    row = database.execute(
        """
        SELECT sh.*, outgoing.full_name AS outgoing_name,
            incoming.full_name AS incoming_name
        FROM shift_handovers sh
        JOIN users outgoing ON outgoing.id = sh.outgoing_user_id
        LEFT JOIN users incoming ON incoming.id = sh.incoming_user_id
        WHERE sh.id = ?
        """,
        (handover_id,),
    ).fetchone()
    if row is None:
        abort(404)
    handover = row_to_dict(row)
    handover["events"] = [
        row_to_dict(event) for event in database.execute(
            """
            SELECT e.id, e.entry_no, e.subject, e.event_date,
                she.state_at_handover, e.state AS current_state,
                a.kks_code, a.description AS asset_description,
                l.name AS logbook_name,
                GROUP_CONCAT(wr.request_no, ', ') AS work_requests
            FROM shift_handover_events she
            JOIN event_entries e ON e.id = she.event_id
            JOIN logbooks l ON l.id = e.source_logbook_id
            LEFT JOIN assets a ON a.id = e.asset_id
            LEFT JOIN work_requests wr ON wr.source_event_id = e.id
            WHERE she.handover_id = ?
            GROUP BY e.id, she.state_at_handover
            ORDER BY e.event_date, e.id
            """,
            (handover_id,),
        ).fetchall()
    ]
    return handover


@app.get("/api/shift-handovers")
def list_shift_handovers():
    status = request.args.get("status", "").strip().lower()
    filters = []
    parameters: list[object] = []
    if status in {"draft", "submitted", "accepted"}:
        filters.append("sh.status = ?")
        parameters.append(status)
    sql = """
        SELECT sh.id, sh.handover_no, sh.shift_date, sh.shift_name, sh.status,
            sh.submitted_at, sh.accepted_at,
            outgoing.full_name AS outgoing_name,
            incoming.full_name AS incoming_name,
            COUNT(she.event_id) AS event_count
        FROM shift_handovers sh
        JOIN users outgoing ON outgoing.id = sh.outgoing_user_id
        LEFT JOIN users incoming ON incoming.id = sh.incoming_user_id
        LEFT JOIN shift_handover_events she ON she.handover_id = sh.id
    """
    if filters:
        sql += " WHERE " + " AND ".join(filters)
    sql += " GROUP BY sh.id ORDER BY sh.shift_date DESC, sh.id DESC"
    return jsonify([
        row_to_dict(row) for row in get_db().execute(sql, parameters).fetchall()
    ])


@app.get("/api/shift-handovers/<int:handover_id>")
def shift_handover_detail(handover_id: int):
    return jsonify(get_shift_handover(handover_id))


@app.post("/api/shift-handovers")
@roles_required("Shift Leader")
def create_shift_handover():
    payload = request.get_json(silent=True) or {}
    shift_date = str(payload.get("shift_date") or "").strip()
    shift_name = str(payload.get("shift_name") or "").strip()
    summary = str(payload.get("summary") or "").strip()
    if not shift_date or not shift_name or not summary:
        return jsonify({
            "error": "Shift date, shift name, and handover summary are required"
        }), 400
    try:
        parsed_date = date.fromisoformat(shift_date)
    except ValueError:
        return jsonify({"error": "Shift date is invalid"}), 400
    if parsed_date > date.today():
        return jsonify({"error": "Shift handover date cannot be in the future"}), 400
    event_ids = payload.get("event_ids")
    if event_ids is None:
        event_ids = []
    if not isinstance(event_ids, list):
        return jsonify({"error": "Event IDs must be a list"}), 400
    try:
        selected_ids = sorted({int(event_id) for event_id in event_ids})
    except (TypeError, ValueError):
        return jsonify({"error": "Event IDs must be integers"}), 400
    database = get_db()
    events = []
    if selected_ids:
        events = database.execute(
            f"""
            SELECT id, state FROM event_entries
            WHERE id IN ({','.join('?' for _ in selected_ids)})
              AND parent_id IS NULL
            """,
            selected_ids,
        ).fetchall()
        if len(events) != len(selected_ids):
            return jsonify({"error": "Select valid main Event Log entries"}), 400
    next_number = database.execute(
        "SELECT COUNT(*) + 1 AS value FROM shift_handovers WHERE substr(shift_date, 1, 4) = ?",
        (str(parsed_date.year),),
    ).fetchone()["value"]
    now = datetime.now().isoformat(timespec="minutes")
    cursor = database.execute(
        """
        INSERT INTO shift_handovers (
            handover_no, shift_date, shift_name, outgoing_user_id, status,
            summary, safety_notes, operational_notes, created_at, updated_at
        ) VALUES (?, ?, ?, ?, 'draft', ?, ?, ?, ?, ?)
        """,
        (
            f"SH-{parsed_date.year}-{next_number:04d}", shift_date, shift_name,
            g.current_user["id"], summary,
            str(payload.get("safety_notes") or "").strip() or None,
            str(payload.get("operational_notes") or "").strip() or None,
            now, now,
        ),
    )
    if events:
        database.executemany(
            """
            INSERT INTO shift_handover_events (handover_id, event_id, state_at_handover)
            VALUES (?, ?, ?)
            """,
            [(cursor.lastrowid, event["id"], event["state"]) for event in events],
        )
    database.commit()
    return jsonify(get_shift_handover(cursor.lastrowid)), 201


@app.patch("/api/shift-handovers/<int:handover_id>")
@roles_required("Shift Leader")
def update_shift_handover(handover_id: int):
    payload = request.get_json(silent=True) or {}
    action = str(payload.get("action") or "").strip().lower()
    database = get_db()
    handover = database.execute(
        "SELECT * FROM shift_handovers WHERE id = ?", (handover_id,)
    ).fetchone()
    if handover is None:
        abort(404)
    now = datetime.now().isoformat(timespec="minutes")
    if action == "submit":
        if handover["status"] != "draft":
            return jsonify({"error": "Only a draft handover can be submitted"}), 409
        if handover["outgoing_user_id"] != g.current_user["id"]:
            return jsonify({"error": "Only the outgoing Shift Leader can submit"}), 403
        database.execute(
            """
            UPDATE shift_handovers SET status = 'submitted', submitted_at = ?, updated_at = ?
            WHERE id = ?
            """,
            (now, now, handover_id),
        )
    elif action == "accept":
        if handover["status"] != "submitted":
            return jsonify({"error": "Only a submitted handover can be accepted"}), 409
        if handover["outgoing_user_id"] == g.current_user["id"]:
            return jsonify({"error": "Outgoing Shift Leader cannot accept their own handover"}), 409
        acceptance_notes = str(payload.get("acceptance_notes") or "").strip()
        if not acceptance_notes:
            return jsonify({"error": "Acceptance notes are required"}), 400
        database.execute(
            """
            UPDATE shift_handovers SET status = 'accepted', incoming_user_id = ?,
                acceptance_notes = ?, accepted_at = ?, updated_at = ? WHERE id = ?
            """,
            (g.current_user["id"], acceptance_notes, now, now, handover_id),
        )
    else:
        return jsonify({"error": "Action must be submit or accept"}), 400
    database.commit()
    return jsonify(get_shift_handover(handover_id))


@app.get("/print/shift-handover/<int:handover_id>")
@login_required
def print_formal_shift_handover(handover_id: int):
    return render_template(
        "formal_shift_handover.html",
        handover=get_shift_handover(handover_id),
        printed_by=g.current_user["full_name"],
        printed_at=datetime.now().isoformat(timespec="minutes"),
    )


@app.post("/api/events")
def create_event():
    payload = request.get_json(silent=True) or {}
    required = ("logbook_id", "subject", "event_date", "observation")
    missing = [field for field in required if not str(payload.get(field, "")).strip()]
    if missing:
        return jsonify({"error": "Missing required fields", "fields": missing}), 400

    database = get_db()
    logbook = database.execute(
        """
        SELECT id, name, department, can_create_role, is_shift_leader
        FROM logbooks WHERE id = ?
        """,
        (payload["logbook_id"],),
    ).fetchone()
    if logbook is None:
        return jsonify({"error": "Logbook not found"}), 400
    if not can_create_logbook_entry(logbook):
        return jsonify({
            "error": f"Your role cannot create entries in {logbook['name']}"
        }), 403

    state = str(payload.get("state") or "open").lower()
    if state not in {"open", "closed"}:
        return jsonify({"error": "Event state must be open or closed"}), 400

    parent_id = payload.get("parent_id")
    parent = None
    if parent_id:
        parent = database.execute(
            "SELECT id, subject, asset_id, event_date FROM event_entries WHERE id = ?",
            (parent_id,),
        ).fetchone()
        if parent is None:
            return jsonify({"error": "Parent entry not found"}), 400

    next_number = database.execute(
        "SELECT COALESCE(MAX(CAST(substr(entry_no, 9) AS INTEGER)), 0) + 1 FROM event_entries"
    ).fetchone()[0]
    now = datetime.now().isoformat(timespec="minutes")
    subject = parent["subject"] if parent else str(payload["subject"]).strip()
    asset_id = parent["asset_id"] if parent else payload.get("asset_id")
    event_date = parent["event_date"] if parent else str(payload["event_date"]).strip()
    cursor = database.execute(
        """
        INSERT INTO event_entries (
            parent_id, source_logbook_id, entry_no, entry_type, subject,
            asset_id, event_date, state, observation, informant, created_by,
            created_at, updated_at
        ) VALUES (?, ?, ?, 'Information', ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            parent_id,
            int(payload["logbook_id"]),
            f"EL-{datetime.now().year}-{next_number:04d}",
            subject,
            asset_id,
            event_date,
            state,
            str(payload["observation"]).strip(),
            str(payload.get("informant") or "").strip() or None,
            g.current_user["full_name"],
            now,
            now,
        ),
    )
    event_id = cursor.lastrowid
    database.execute(
        "INSERT INTO event_entry_logbooks (entry_id, logbook_id, is_copy) VALUES (?, ?, 0)",
        (event_id, int(payload["logbook_id"])),
    )
    shift_logbook = database.execute(
        "SELECT id FROM logbooks WHERE is_shift_leader = 1"
    ).fetchone()
    if shift_logbook and shift_logbook["id"] != int(payload["logbook_id"]):
        database.execute(
            "INSERT INTO event_entry_logbooks (entry_id, logbook_id, is_copy) VALUES (?, ?, 1)",
            (event_id, shift_logbook["id"]),
        )
    database.commit()
    return jsonify(get_event(event_id)), 201


@app.patch("/api/events/<int:event_id>")
def update_event(event_id: int):
    payload = request.get_json(silent=True) or {}
    observation = str(payload.get("observation") or "").strip()
    if not observation:
        return jsonify({"error": "Observation is required"}), 400
    database = get_db()
    event = database.execute(
        """
        SELECT e.*, l.name AS logbook_name, l.department,
            l.can_create_role, l.is_shift_leader
        FROM event_entries e
        JOIN logbooks l ON l.id = e.source_logbook_id
        WHERE e.id = ?
        """,
        (event_id,),
    ).fetchone()
    if event is None:
        abort(404)
    if not can_create_logbook_entry(event):
        return jsonify({
            "error": f"Your role cannot edit entries in {event['logbook_name']}"
        }), 403
    asset_id = event["asset_id"]
    event_date = event["event_date"]
    if event["parent_id"] is None:
        asset_value = payload.get("asset_id")
        try:
            asset_id = int(asset_value) if asset_value not in (None, "") else None
        except (TypeError, ValueError):
            return jsonify({"error": "Asset is invalid"}), 400
        if asset_id is not None and database.execute(
            "SELECT id FROM assets WHERE id = ?", (asset_id,)
        ).fetchone() is None:
            return jsonify({"error": "Asset not found"}), 400
        event_date = str(payload.get("event_date") or "").strip()
        try:
            datetime.fromisoformat(event_date)
        except ValueError:
            return jsonify({"error": "Event date is invalid"}), 400
    informant = str(payload.get("informant") or "").strip() or None
    changes: dict[str, dict[str, object]] = {}
    values = {
        "asset_id": asset_id,
        "event_date": event_date,
        "observation": observation,
        "informant": informant,
    }
    for field, new_value in values.items():
        if event[field] != new_value:
            changes[field] = {"from": event[field], "to": new_value}
    if not changes:
        return jsonify({"error": "No event changes were supplied"}), 409
    now = datetime.now().isoformat(timespec="minutes")
    database.execute(
        """
        UPDATE event_entries
        SET asset_id = ?, event_date = ?, observation = ?, informant = ?,
            updated_at = ?
        WHERE id = ?
        """,
        (asset_id, event_date, observation, informant, now, event_id),
    )
    database.execute(
        """
        INSERT INTO event_edit_history (
            event_id, changed_by, changes, created_at
        ) VALUES (?, ?, ?, ?)
        """,
        (
            event_id, g.current_user["full_name"],
            json.dumps(changes, ensure_ascii=True), now,
        ),
    )
    database.commit()
    return jsonify(event_detail(event_id).get_json())


@app.patch("/api/events/<int:event_id>/state")
def update_event_state(event_id: int):
    payload = request.get_json(silent=True) or {}
    new_state = str(payload.get("state") or "").lower()
    reason = str(payload.get("reason") or "").strip()
    if new_state not in {"open", "closed"}:
        return jsonify({"error": "Event state must be open or closed"}), 400
    if not reason:
        return jsonify({"error": "A reason is required for the state change"}), 400

    database = get_db()
    event = database.execute(
        """
        SELECT e.id, e.parent_id, e.state, e.source_logbook_id,
            l.name, l.department, l.can_create_role, l.is_shift_leader
        FROM event_entries e
        JOIN logbooks l ON l.id = e.source_logbook_id
        WHERE e.id = ?
        """,
        (event_id,),
    ).fetchone()
    if event is None:
        abort(404)
    if event["parent_id"] is not None:
        return jsonify({"error": "Only main entries can change state"}), 409
    if not can_create_logbook_entry(event):
        return jsonify({
            "error": f"Your role cannot change entries in {event['name']}"
        }), 403
    if event["state"] == new_state:
        return jsonify({"error": f"Event is already {new_state}"}), 409

    now = datetime.now().isoformat(timespec="minutes")
    database.execute(
        "UPDATE event_entries SET state = ?, updated_at = ? WHERE id = ?",
        (new_state, now, event_id),
    )
    database.execute(
        """
        INSERT INTO event_state_history (
            event_id, previous_state, new_state, changed_by, reason, created_at
        ) VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            event_id, event["state"], new_state,
            g.current_user["full_name"], reason, now,
        ),
    )
    database.commit()
    return jsonify(event_detail(event_id).get_json())


@app.delete("/api/events/<int:event_id>")
def delete_event(event_id: int):
    payload = request.get_json(silent=True) or {}
    reason = str(payload.get("reason") or "").strip()
    if not reason:
        return jsonify({"error": "A deletion reason is required"}), 400
    database = get_db()
    event = database.execute(
        """
        SELECT e.*, l.name AS logbook_name, l.department,
            l.can_create_role, l.is_shift_leader
        FROM event_entries e
        JOIN logbooks l ON l.id = e.source_logbook_id
        WHERE e.id = ?
        """,
        (event_id,),
    ).fetchone()
    if event is None:
        abort(404)
    if not can_create_logbook_entry(event):
        return jsonify({
            "error": f"Your role cannot delete entries from {event['logbook_name']}"
        }), 403
    dependencies = {
        "sub_entries": database.execute(
            "SELECT COUNT(*) FROM event_entries WHERE parent_id = ?", (event_id,)
        ).fetchone()[0],
        "work_requests": database.execute(
            "SELECT COUNT(*) FROM work_requests WHERE source_event_id = ?", (event_id,)
        ).fetchone()[0],
        "attachments": database.execute(
            "SELECT COUNT(*) FROM attachments WHERE entity_type = 'event' AND entity_id = ?",
            (event_id,),
        ).fetchone()[0],
    }
    if any(dependencies.values()):
        labels = [name.replace("_", " ") for name, count in dependencies.items() if count]
        return jsonify({
            "error": "Entry cannot be deleted while linked records exist",
            "dependencies": dependencies,
            "linked": labels,
        }), 409
    snapshot = row_to_dict(event)
    snapshot["visible_logbooks"] = [
        row["logbook_id"] for row in database.execute(
            "SELECT logbook_id FROM event_entry_logbooks WHERE entry_id = ? ORDER BY logbook_id",
            (event_id,),
        ).fetchall()
    ]
    snapshot["state_history"] = [
        row_to_dict(row) for row in database.execute(
            "SELECT * FROM event_state_history WHERE event_id = ? ORDER BY id",
            (event_id,),
        ).fetchall()
    ]
    snapshot["edit_history"] = [
        row_to_dict(row) for row in database.execute(
            "SELECT * FROM event_edit_history WHERE event_id = ? ORDER BY id",
            (event_id,),
        ).fetchall()
    ]
    now = datetime.now().isoformat(timespec="minutes")
    database.execute(
        """
        INSERT INTO event_deletion_log (
            entry_no, snapshot, deleted_by, reason, deleted_at
        ) VALUES (?, ?, ?, ?, ?)
        """,
        (
            event["entry_no"], json.dumps(snapshot, ensure_ascii=True),
            g.current_user["full_name"], reason, now,
        ),
    )
    database.execute("DELETE FROM event_entries WHERE id = ?", (event_id,))
    database.commit()
    return jsonify({
        "status": "deleted",
        "entry_no": event["entry_no"],
        "deleted_by": g.current_user["full_name"],
        "deleted_at": now,
    })


@app.get("/api/corrective")
def list_corrective_tasks():
    filters = []
    parameters: list[object] = []
    search = request.args.get("q", "").strip().lower()
    request_status = request.args.get("request_status", "").strip().lower()
    department = request.args.get("department", "").strip()
    if search:
        filters.append(
            "(lower(wr.request_no) LIKE ? OR lower(wr.name) LIKE ? "
            "OR lower(wr.observation) LIKE ? OR lower(a.kks_code) LIKE ?)"
        )
        pattern = f"%{search}%"
        parameters.extend([pattern, pattern, pattern, pattern])
    if request_status in {"submitted", "approved", "declined"}:
        filters.append("wr.status = ?")
        parameters.append(request_status)
    if department:
        filters.append("wr.main_department = ?")
        parameters.append(department)
    sql = """
        SELECT
            wr.*, a.kks_code, a.description AS asset_description,
            wo.id AS work_order_id, wo.order_no, wo.workflow_step,
            wo.permit_requirement, wo.permit_status, wo.acceptance_status,
            CASE
                WHEN wr.target_response_at IS NOT NULL
                 AND datetime(wr.target_response_at) < datetime('now', 'localtime')
                 AND wr.status != 'declined'
                 AND COALESCE(wo.workflow_step, '') != 'closed'
                THEN 1 ELSE 0
            END AS is_response_overdue
        FROM work_requests wr
        JOIN assets a ON a.id = wr.asset_id
        LEFT JOIN work_orders wo ON wo.work_request_id = wr.id
    """
    if filters:
        sql += " WHERE " + " AND ".join(filters)
    sql += """
        ORDER BY
            CASE wr.status WHEN 'submitted' THEN 1 WHEN 'approved' THEN 2 ELSE 3 END,
            wr.updated_at DESC
    """
    rows = get_db().execute(sql, parameters).fetchall()
    return jsonify([row_to_dict(row) for row in rows])


@app.get("/api/corrective.csv")
def export_corrective_tasks():
    result = list_corrective_tasks()
    if isinstance(result, tuple):
        return result
    records = [get_work_request(item["id"]) for item in result.get_json()]
    output = io.StringIO()
    writer = csv.writer(output, lineterminator="\n")
    writer.writerow([
        "Work Request", "Work Order", "Request Status", "Workflow Step",
        "KKS", "Description", "Department", "Type of Work", "Priority",
        "CMPT Primary", "CMPT Impacts", "CMPT Severity", "CMPT Likelihood",
        "Planned Start", "Planned End", "Maintenance Code",
        "Equipment Condition", "Permit Requirement", "Permit Status",
        "Expected Man-Hours", "Actual Man-Hours", "Acceptance Status",
        "Failure Mode", "Failure Cause", "Downtime Started",
        "Equipment Restored", "Downtime Hours",
        "Response Target", "Response Overdue", "Source Event",
        "Source Event State", "Created At", "Updated At",
    ])
    for record in records:
        writer.writerow([
            record["request_no"], record.get("order_no") or "", record["status"],
            record.get("workflow_step") or "", record["kks_code"], record["name"],
            record["main_department"], record["type_of_work"], record["priority"],
            record.get("cmpt_primary") or "", ", ".join(record.get("cmpt_impacts") or []),
            record.get("cmpt_severity") if record.get("cmpt_severity") is not None else "",
            record.get("cmpt_likelihood") or "", record.get("planned_start") or "",
            record.get("planned_end") or "", record.get("maintenance_code") or "",
            record.get("equipment_condition") or "", record.get("permit_requirement") or "",
            record.get("permit_status") or "", record.get("expected_man_hours") or 0,
            record.get("actual_man_hours") if record.get("actual_man_hours") is not None else "",
            record.get("acceptance_status") or "", record.get("failure_mode") or "",
            record.get("failure_cause") or "", record.get("downtime_started_at") or "",
            record.get("restored_at") or "",
            record.get("downtime_hours") if record.get("downtime_hours") is not None else "",
            record.get("target_response_at") or "",
            "Yes" if record.get("is_response_overdue") else "No",
            record.get("source_event_no") or "",
            record.get("source_event_state") or "", record["created_at"], record["updated_at"],
        ])
    filename = f"morupule-b-corrective-{date.today().isoformat()}.csv"
    return Response(
        "\ufeff" + output.getvalue(),
        mimetype="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@app.get("/api/corrective/summary")
def corrective_summary():
    row = get_db().execute(
        """
        SELECT
            (SELECT COUNT(*) FROM work_requests) AS total_requests,
            (SELECT COUNT(*) FROM work_requests WHERE status = 'submitted') AS pending_approval,
            (SELECT COUNT(*) FROM work_orders WHERE workflow_step != 'closed') AS active_orders,
            (SELECT COUNT(*) FROM work_orders WHERE workflow_step = 'work_check') AS awaiting_check
            ,(SELECT COUNT(*) FROM work_requests wr
              LEFT JOIN work_orders wo ON wo.work_request_id = wr.id
              WHERE wr.target_response_at IS NOT NULL
                AND datetime(wr.target_response_at) < datetime('now', 'localtime')
                AND wr.status != 'declined'
                AND COALESCE(wo.workflow_step, '') != 'closed') AS overdue_response
        """
    ).fetchone()
    return jsonify(row_to_dict(row))


@app.get("/api/corrective/<int:request_id>")
def corrective_detail(request_id: int):
    task = get_work_request(request_id)
    database = get_db()
    if task.get("work_order_id"):
        order_id = task["work_order_id"]
        task["linked_permits"] = [
            row_to_dict(row) for row in database.execute(
                """
                SELECT id, permit_no, form_type, status, created_at
                FROM safety_permits
                WHERE work_order_id = ? ORDER BY id DESC
                """,
                (order_id,),
            ).fetchall()
        ]
        task["supplies"] = [
            row_to_dict(row) for row in database.execute(
                """
                SELECT id, supply_type, description, quantity, unit, ordered_at, order_number
                FROM work_order_supplies WHERE work_order_id = ? ORDER BY id
                """,
                (order_id,),
            ).fetchall()
        ]
        task["artisans"] = [
            row_to_dict(row) for row in database.execute(
                """
                SELECT id, person_name, trade, work_date, planned_hours,
                    actual_hours, overtime_rate
                FROM work_order_artisans WHERE work_order_id = ? ORDER BY id
                """,
                (order_id,),
            ).fetchall()
        ]
        task["history"] = [
            row_to_dict(row) for row in database.execute(
                """
                SELECT workflow_step, action, performed_by, note, created_at
                FROM work_order_history WHERE work_order_id = ? ORDER BY id DESC
                """,
                (order_id,),
            ).fetchall()
        ]
    else:
        task["linked_permits"] = []
        task["supplies"] = []
        task["artisans"] = []
        task["history"] = []
    task["edit_history"] = [
        {
            **row_to_dict(row),
            "changes": json.loads(row["changes"]),
        }
        for row in database.execute(
            """
            SELECT changed_by, changes, created_at
            FROM work_request_edit_history
            WHERE work_request_id = ? ORDER BY id DESC
            """,
            (request_id,),
        ).fetchall()
    ]
    task["attachments"] = attachment_rows("corrective", request_id)
    return jsonify(task)


def editable_planning_order(order_id: int) -> sqlite3.Row | None:
    return get_db().execute(
        """
        SELECT id, work_request_id, workflow_step
        FROM work_orders
        WHERE id = ?
        """,
        (order_id,),
    ).fetchone()


def planning_order_response(order: sqlite3.Row):
    if order is None:
        abort(404)
    if order["workflow_step"] not in {"planning", "rework"}:
        return None, (
            jsonify({
                "error": "Planning resources can only change during planning or rework"
            }),
            409,
        )
    return order, None


@app.post("/api/work-orders/<int:order_id>/supplies")
@roles_required("Maintenance Planner")
def add_work_order_supply(order_id: int):
    order, error = planning_order_response(editable_planning_order(order_id))
    if error:
        return error
    payload = request.get_json(silent=True) or {}
    description = str(payload.get("description") or "").strip()
    supply_type = str(payload.get("supply_type") or "material").lower()
    if not description:
        return jsonify({"error": "Supply description is required"}), 400
    if supply_type not in {"material", "external_service"}:
        return jsonify({"error": "Invalid supply type"}), 400
    try:
        quantity = float(payload.get("quantity") or 0)
    except (TypeError, ValueError):
        return jsonify({"error": "Quantity must be numeric"}), 400
    if quantity < 0:
        return jsonify({"error": "Quantity cannot be negative"}), 400
    database = get_db()
    database.execute(
        """
        INSERT INTO work_order_supplies (
            work_order_id, supply_type, description, quantity, unit,
            ordered_at, order_number
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            order_id, supply_type, description, quantity,
            str(payload.get("unit") or "").strip() or None,
            str(payload.get("ordered_at") or "").strip() or None,
            str(payload.get("order_number") or "").strip() or None,
        ),
    )
    database.commit()
    return jsonify(corrective_detail(order["work_request_id"]).get_json()), 201


@app.delete("/api/work-orders/<int:order_id>/supplies/<int:supply_id>")
@roles_required("Maintenance Planner")
def delete_work_order_supply(order_id: int, supply_id: int):
    order, error = planning_order_response(editable_planning_order(order_id))
    if error:
        return error
    database = get_db()
    cursor = database.execute(
        "DELETE FROM work_order_supplies WHERE id = ? AND work_order_id = ?",
        (supply_id, order_id),
    )
    if cursor.rowcount == 0:
        abort(404)
    database.commit()
    return jsonify(corrective_detail(order["work_request_id"]).get_json())


@app.post("/api/work-orders/<int:order_id>/artisans")
@roles_required("Maintenance Planner")
def add_work_order_artisan(order_id: int):
    order, error = planning_order_response(editable_planning_order(order_id))
    if error:
        return error
    payload = request.get_json(silent=True) or {}
    person_name = str(payload.get("person_name") or "").strip()
    trade = str(payload.get("trade") or "").strip()
    if not person_name or not trade:
        return jsonify({"error": "Artisan name and trade are required"}), 400
    try:
        planned_hours = float(payload.get("planned_hours") or 0)
        overtime_rate = float(payload.get("overtime_rate") or 0)
    except (TypeError, ValueError):
        return jsonify({"error": "Hours and overtime rate must be numeric"}), 400
    if planned_hours < 0 or overtime_rate < 0:
        return jsonify({"error": "Hours and overtime rate cannot be negative"}), 400
    database = get_db()
    database.execute(
        """
        INSERT INTO work_order_artisans (
            work_order_id, person_name, trade, work_date,
            planned_hours, overtime_rate
        ) VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            order_id, person_name, trade,
            str(payload.get("work_date") or "").strip() or None,
            planned_hours, overtime_rate,
        ),
    )
    database.commit()
    return jsonify(corrective_detail(order["work_request_id"]).get_json()), 201


@app.delete("/api/work-orders/<int:order_id>/artisans/<int:artisan_id>")
@roles_required("Maintenance Planner")
def delete_work_order_artisan(order_id: int, artisan_id: int):
    order, error = planning_order_response(editable_planning_order(order_id))
    if error:
        return error
    database = get_db()
    cursor = database.execute(
        "DELETE FROM work_order_artisans WHERE id = ? AND work_order_id = ?",
        (artisan_id, order_id),
    )
    if cursor.rowcount == 0:
        abort(404)
    database.commit()
    return jsonify(corrective_detail(order["work_request_id"]).get_json())


@app.post("/api/corrective")
def create_work_request():
    payload = request.get_json(silent=True) or {}
    required = (
        "asset_id", "name", "type_of_work", "main_department",
        "observation",
    )
    missing = [field for field in required if not str(payload.get(field, "")).strip()]
    if missing:
        return jsonify({"error": "Missing required fields", "fields": missing}), 400
    cmpt_fields = ("cmpt_primary", "cmpt_impacts", "cmpt_severity", "cmpt_likelihood")
    has_cmpt = any(field in payload for field in cmpt_fields)
    cmpt_primary = None
    cmpt_impacts = []
    cmpt_severity = None
    cmpt_likelihood = None
    if has_cmpt:
        cmpt_primary = str(payload.get("cmpt_primary") or "").upper().strip()
        cmpt_likelihood = str(payload.get("cmpt_likelihood") or "").upper().strip()
        try:
            cmpt_severity = int(payload.get("cmpt_severity"))
        except (TypeError, ValueError):
            return jsonify({"error": "CMPT severity must be between 0 and 5"}), 400
        if cmpt_primary not in CMPT_CATEGORIES:
            return jsonify({"error": "Select a valid CMPT primary consequence"}), 400
        if cmpt_severity not in CMPT_MATRIX:
            return jsonify({"error": "CMPT severity must be between 0 and 5"}), 400
        if cmpt_likelihood not in {"A", "B", "C", "D", "E"}:
            return jsonify({"error": "Select a valid CMPT likelihood"}), 400
        impact_values = payload.get("cmpt_impacts") or []
        if not isinstance(impact_values, list):
            return jsonify({"error": "CMPT impacts must be a list"}), 400
        normalized_impacts = {str(value).upper().strip() for value in impact_values}
        if not normalized_impacts.issubset(CMPT_CATEGORIES):
            return jsonify({"error": "Select valid CMPT impacted areas"}), 400
        normalized_impacts.add(cmpt_primary)
        cmpt_impacts = [code for code in CMPT_CATEGORIES if code in normalized_impacts]
        priority = calculate_cmpt_priority(cmpt_severity, cmpt_likelihood)
    else:
        try:
            priority = int(payload.get("priority"))
        except (TypeError, ValueError):
            return jsonify({"error": "Priority must be between 1 and 6"}), 400
        if priority not in range(1, 7):
            return jsonify({"error": "Priority must be between 1 and 6"}), 400
    database = get_db()
    if database.execute("SELECT id FROM assets WHERE id = ?", (payload["asset_id"],)).fetchone() is None:
        return jsonify({"error": "Asset not found"}), 400
    source_event_id = payload.get("source_event_id")
    if source_event_id:
        source_event = database.execute(
            """
            SELECT id, parent_id, asset_id, state
            FROM event_entries WHERE id = ?
            """,
            (source_event_id,),
        ).fetchone()
        if source_event is None:
            return jsonify({"error": "Source event not found"}), 400
        if source_event["parent_id"] is not None:
            return jsonify({"error": "A sub-entry cannot originate a work request"}), 409
        if source_event["state"] != "open":
            return jsonify({"error": "Only an open event can originate a work request"}), 409
        if source_event["asset_id"] is None:
            return jsonify({"error": "Source event must have a KKS asset"}), 409
        if int(payload["asset_id"]) != source_event["asset_id"]:
            return jsonify({"error": "Work request asset must match the source event"}), 409
        existing = database.execute(
            """
            SELECT request_no FROM work_requests
            WHERE source_event_id = ?
            """,
            (source_event_id,),
        ).fetchone()
        if existing:
            return jsonify({
                "error": f"{existing['request_no']} already originates from this event"
            }), 409
    next_number = database.execute(
        "SELECT COALESCE(MAX(CAST(substr(request_no, 9) AS INTEGER)), 0) + 1 FROM work_requests"
    ).fetchone()[0]
    now = datetime.now().isoformat(timespec="minutes")
    cursor = database.execute(
        """
        INSERT INTO work_requests (
            request_no, source_event_id, asset_id, name, asset_type, type_of_work,
            main_department, priority, cmpt_primary, cmpt_impacts, cmpt_severity,
            cmpt_likelihood, target_response_at, planned_start, planned_end, reminder_days,
            show_in_history, observation, author, status, created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'submitted', ?, ?)
        """,
        (
            f"WR-{datetime.now().year}-{next_number:04d}",
            source_event_id,
            int(payload["asset_id"]),
            str(payload["name"]).strip(),
            str(payload.get("asset_type") or "").strip() or None,
            str(payload["type_of_work"]).strip(),
            str(payload["main_department"]).strip(),
            priority,
            cmpt_primary,
            json.dumps(cmpt_impacts),
            cmpt_severity,
            cmpt_likelihood,
            cmpt_response_target(now, priority),
            str(payload.get("planned_start") or "").strip() or None,
            str(payload.get("planned_end") or "").strip() or None,
            int(payload.get("reminder_days") or 0),
            1 if payload.get("show_in_history", True) else 0,
            str(payload["observation"]).strip(),
            g.current_user["full_name"],
            now,
            now,
        ),
    )
    database.commit()
    return jsonify(get_work_request(cursor.lastrowid)), 201


@app.patch("/api/corrective/<int:request_id>")
@roles_required("Maintenance Approver")
def update_work_request(request_id: int):
    payload = request.get_json(silent=True) or {}
    required = (
        "asset_id", "name", "type_of_work", "main_department", "observation",
        "cmpt_primary", "cmpt_severity", "cmpt_likelihood",
    )
    missing = [field for field in required if payload.get(field) in (None, "")]
    if missing:
        return jsonify({"error": "Missing required fields", "fields": missing}), 400

    database = get_db()
    existing = database.execute(
        "SELECT * FROM work_requests WHERE id = ?", (request_id,)
    ).fetchone()
    if existing is None:
        abort(404)
    if existing["status"] != "submitted":
        return jsonify({"error": "Only submitted work requests can be edited"}), 409

    try:
        asset_id = int(payload["asset_id"])
        severity = int(payload["cmpt_severity"])
        reminder_days = int(payload.get("reminder_days") or 0)
    except (TypeError, ValueError):
        return jsonify({"error": "Asset, severity, and reminder values must be numeric"}), 400
    if database.execute("SELECT id FROM assets WHERE id = ?", (asset_id,)).fetchone() is None:
        return jsonify({"error": "Asset not found"}), 400

    primary = str(payload["cmpt_primary"]).upper().strip()
    likelihood = str(payload["cmpt_likelihood"]).upper().strip()
    if primary not in CMPT_CATEGORIES:
        return jsonify({"error": "Select a valid CMPT primary consequence"}), 400
    if severity not in CMPT_MATRIX:
        return jsonify({"error": "CMPT severity must be between 0 and 5"}), 400
    if likelihood not in {"A", "B", "C", "D", "E"}:
        return jsonify({"error": "Select a valid CMPT likelihood"}), 400
    impact_values = payload.get("cmpt_impacts") or []
    if not isinstance(impact_values, list):
        return jsonify({"error": "CMPT impacts must be a list"}), 400
    impacts = {str(value).upper().strip() for value in impact_values}
    if not impacts.issubset(CMPT_CATEGORIES):
        return jsonify({"error": "Select valid CMPT impacted areas"}), 400
    impacts.add(primary)
    ordered_impacts = [code for code in CMPT_CATEGORIES if code in impacts]
    priority = calculate_cmpt_priority(severity, likelihood)

    values = {
        "asset_id": asset_id,
        "name": str(payload["name"]).strip(),
        "asset_type": str(payload.get("asset_type") or "").strip() or None,
        "type_of_work": str(payload["type_of_work"]).strip(),
        "main_department": str(payload["main_department"]).strip(),
        "priority": priority,
        "cmpt_primary": primary,
        "cmpt_impacts": json.dumps(ordered_impacts),
        "cmpt_severity": severity,
        "cmpt_likelihood": likelihood,
        "target_response_at": cmpt_response_target(existing["created_at"], priority),
        "planned_start": str(payload.get("planned_start") or "").strip() or None,
        "planned_end": str(payload.get("planned_end") or "").strip() or None,
        "reminder_days": max(0, reminder_days),
        "show_in_history": 1 if payload.get("show_in_history", True) else 0,
        "observation": str(payload["observation"]).strip(),
    }
    if not values["name"] or not values["type_of_work"] or not values["main_department"] or not values["observation"]:
        return jsonify({"error": "Required text fields cannot be blank"}), 400

    changes = {}
    for field, value in values.items():
        old_value = existing[field]
        if old_value != value:
            changes[field] = {"from": old_value, "to": value}
    if changes:
        now = datetime.now().isoformat(timespec="minutes")
        assignments = ", ".join(f"{field} = ?" for field in values)
        database.execute(
            f"UPDATE work_requests SET {assignments}, updated_at = ? WHERE id = ?",
            (*values.values(), now, request_id),
        )
        database.execute(
            """
            INSERT INTO work_request_edit_history (
                work_request_id, changed_by, changes, created_at
            ) VALUES (?, ?, ?, ?)
            """,
            (request_id, g.current_user["full_name"], json.dumps(changes), now),
        )
        database.commit()
    return corrective_detail(request_id)


@app.patch("/api/corrective/<int:request_id>/decision")
@roles_required("Maintenance Approver")
def decide_work_request(request_id: int):
    payload = request.get_json(silent=True) or {}
    decision = str(payload.get("decision") or "").lower()
    performed_by = g.current_user["full_name"]
    if decision not in {"approved", "declined"}:
        return jsonify({"error": "Decision is required"}), 400
    reason = str(payload.get("reason") or "").strip() or None
    if decision == "declined" and not reason:
        return jsonify({"error": "A decline reason is required"}), 400
    database = get_db()
    request_row = database.execute(
        "SELECT id, status FROM work_requests WHERE id = ?", (request_id,)
    ).fetchone()
    if request_row is None:
        abort(404)
    if request_row["status"] != "submitted":
        return jsonify({"error": "Work request has already been decided"}), 409
    now = datetime.now().isoformat(timespec="minutes")
    database.execute(
        """
        UPDATE work_requests
        SET status = ?, decision_by = ?, decision_reason = ?, updated_at = ?
        WHERE id = ?
        """,
        (decision, performed_by, reason, now, request_id),
    )
    if decision == "approved":
        next_number = database.execute(
            "SELECT COALESCE(MAX(CAST(substr(order_no, 9) AS INTEGER)), 0) + 1 FROM work_orders"
        ).fetchone()[0]
        cursor = database.execute(
            """
            INSERT INTO work_orders (
                order_no, work_request_id, workflow_step, created_at, updated_at
            ) VALUES (?, ?, 'planning', ?, ?)
            """,
            (f"WO-{datetime.now().year}-{next_number:04d}", request_id, now, now),
        )
        database.execute(
            """
            INSERT INTO work_order_history (
                work_order_id, workflow_step, action, performed_by, note, created_at
            ) VALUES (?, 'planning', 'Work request approved and work order created', ?, ?, ?)
            """,
            (cursor.lastrowid, performed_by, reason, now),
        )
    database.commit()
    return jsonify(get_work_request(request_id))


@app.patch("/api/work-orders/<int:order_id>")
@login_required
def update_work_order(order_id: int):
    payload = request.get_json(silent=True) or {}
    action = str(payload.get("action") or "").strip().lower()
    performed_by = g.current_user["full_name"]
    if not action:
        return jsonify({"error": "Action is required"}), 400
    database = get_db()
    order = database.execute(
        """
        SELECT wo.*, wr.main_department, wr.source_event_id
        FROM work_orders wo
        JOIN work_requests wr ON wr.id = wo.work_request_id
        WHERE wo.id = ?
        """,
        (order_id,),
    ).fetchone()
    if order is None:
        abort(404)
    required_roles = required_roles_for_work_order_action(
        action, order["main_department"]
    )
    if not required_roles:
        return jsonify({"error": "Unknown work order action"}), 400
    if not current_user_has_role(*required_roles):
        return jsonify({
            "error": (
                f"This action requires: {', '.join(required_roles)}"
            )
        }), 403
    current = order["workflow_step"]
    transitions = {
        ("planning", "submit_plan"): "plan_approval",
        ("plan_approval", "approve_plan"): "permit_decision",
        ("plan_approval", "return_plan"): "planning",
        ("permit_decision", "confirm_execution"): "execution",
        ("execution", "complete_work"): "work_check",
        ("work_check", "accept_work"): "closed",
        ("work_check", "deny_acceptance"): "rework",
        ("rework", "resubmit_work"): "plan_approval",
    }
    next_step = transitions.get((current, action))
    if next_step is None:
        return jsonify({"error": f"Action {action} is not valid during {current}"}), 409

    if action == "return_plan" and not str(payload.get("reason") or "").strip():
        return jsonify({"error": "A reason is required when returning a plan"}), 400
    if action == "resubmit_work" and not str(payload.get("reason") or "").strip():
        return jsonify({"error": "A revised-plan summary is required"}), 400

    permit_requirement = str(payload.get("permit_requirement") or order["permit_requirement"])
    permit_status = order["permit_status"]
    if action == "approve_plan":
        if permit_requirement not in {"none", "ptw", "loa"}:
            return jsonify({"error": "Select PTW, LoA, or no permit requirement"}), 400
        permit_status = "not_required" if permit_requirement == "none" else "required"
    if action == "confirm_execution" and order["permit_requirement"] in {"ptw", "loa"}:
        linked_permit = database.execute(
            """
            SELECT permit_no, status FROM safety_permits
            WHERE work_order_id = ? AND status != 'cancelled'
            ORDER BY id DESC LIMIT 1
            """,
            (order_id,),
        ).fetchone()
        if linked_permit is None:
            return jsonify({"error": "Prepare the required linked permit before execution"}), 409
        if linked_permit["status"] != "received":
            return jsonify({
                "error": f"{linked_permit['permit_no']} must be received before execution"
            }), 409
    if action == "accept_work" and permit_status == "issued":
        return jsonify({"error": "Issued PTW/LoA must be cancelled before closing"}), 409
    completion_summary = order["completion_summary"]
    actual_man_hours = order["actual_man_hours"]
    failure_mode = order["failure_mode"]
    failure_cause = order["failure_cause"]
    downtime_started_at = order["downtime_started_at"]
    restored_at = order["restored_at"]
    downtime_hours = order["downtime_hours"]
    artisan_actuals: list[tuple[float, int]] = []
    if action == "complete_work":
        completion_summary = str(
            payload.get("completion_summary") or ""
        ).strip()
        if not completion_summary:
            return jsonify({"error": "Work completion summary is required"}), 400
        try:
            actual_man_hours = float(payload.get("actual_man_hours"))
        except (TypeError, ValueError):
            return jsonify({"error": "Actual man-hours are required"}), 400
        if actual_man_hours < 0:
            return jsonify({"error": "Actual man-hours cannot be negative"}), 400
        if "failure_mode" in payload:
            failure_mode = str(payload.get("failure_mode") or "").strip() or None
        if "failure_cause" in payload:
            failure_cause = str(payload.get("failure_cause") or "").strip() or None
        if "downtime_started_at" in payload or "restored_at" in payload:
            downtime_started_at = str(payload.get("downtime_started_at") or "").strip() or None
            restored_at = str(payload.get("restored_at") or "").strip() or None
            if bool(downtime_started_at) != bool(restored_at):
                return jsonify({
                    "error": "Downtime start and equipment restoration time are both required"
                }), 400
            downtime_hours = None
            if downtime_started_at and restored_at:
                try:
                    downtime_start = datetime.fromisoformat(downtime_started_at)
                    restoration = datetime.fromisoformat(restored_at)
                except ValueError:
                    return jsonify({"error": "Downtime timestamps are invalid"}), 400
                if restoration < downtime_start:
                    return jsonify({
                        "error": "Equipment restoration cannot be before downtime start"
                    }), 400
                downtime_hours = round(
                    (restoration - downtime_start).total_seconds() / 3600, 2
                )
        submitted_artisans = payload.get("artisan_hours")
        if submitted_artisans is not None:
            if not isinstance(submitted_artisans, list):
                return jsonify({"error": "Artisan hours must be a list"}), 400
            valid_artisan_ids = {
                row["id"] for row in database.execute(
                    "SELECT id FROM work_order_artisans WHERE work_order_id = ?",
                    (order_id,),
                ).fetchall()
            }
            seen_ids = set()
            for entry in submitted_artisans:
                try:
                    artisan_id = int(entry.get("id"))
                    hours = float(entry.get("actual_hours"))
                except (AttributeError, TypeError, ValueError):
                    return jsonify({"error": "Each artisan requires valid actual hours"}), 400
                if artisan_id not in valid_artisan_ids or artisan_id in seen_ids:
                    return jsonify({"error": "Invalid or duplicate artisan record"}), 400
                if hours < 0:
                    return jsonify({"error": "Artisan hours cannot be negative"}), 400
                seen_ids.add(artisan_id)
                artisan_actuals.append((hours, artisan_id))
            if artisan_actuals:
                actual_man_hours = sum(hours for hours, _artisan_id in artisan_actuals)

    now = datetime.now().isoformat(timespec="minutes")
    description = str(payload.get("description_of_work") or order["description_of_work"]).strip()
    maintenance_code = str(
        payload.get("maintenance_code") or order["maintenance_code"]
    ).strip().upper()
    equipment_condition = str(
        payload.get("equipment_condition") or order["equipment_condition"]
    ).strip()
    workplace = str(payload.get("workplace_requirements") or order["workplace_requirements"])
    try:
        man_hours = float(payload.get("expected_man_hours") or order["expected_man_hours"])
    except (TypeError, ValueError):
        return jsonify({"error": "Expected man-hours must be numeric"}), 400
    if action in {"submit_plan", "resubmit_work"}:
        missing_plan = []
        if not description:
            missing_plan.append("description_of_work")
        if not maintenance_code:
            missing_plan.append("maintenance_code")
        if equipment_condition not in {"Operating", "Degraded", "Failed", "Out of service"}:
            missing_plan.append("equipment_condition")
        if man_hours <= 0:
            missing_plan.append("expected_man_hours")
        if missing_plan:
            return jsonify({
                "error": "Complete the required work order planning fields",
                "fields": missing_plan,
            }), 400
    acceptance_status = order["acceptance_status"]
    acceptance_reason = order["acceptance_reason"]
    acceptance_note = order["acceptance_note"]
    if action == "accept_work":
        acceptance_status = "accepted"
        acceptance_note = str(payload.get("acceptance_note") or "").strip()
        if not acceptance_note:
            return jsonify({"error": "Inspection remarks are required"}), 400
    elif action == "deny_acceptance":
        acceptance_status = "denied"
        acceptance_reason = str(payload.get("reason") or "").strip()
        acceptance_note = None
        if not acceptance_reason:
            return jsonify({"error": "A denial reason is required"}), 400
    elif action == "resubmit_work":
        acceptance_status = "pending"
        acceptance_reason = None
        acceptance_note = None
    database.execute(
        """
        UPDATE work_orders SET
            workflow_step = ?, description_of_work = ?, maintenance_code = ?,
            equipment_condition = ?, workplace_requirements = ?,
            expected_man_hours = ?, permit_requirement = ?, permit_status = ?,
            plan_approved_by = CASE WHEN ? = 'approve_plan' THEN ? ELSE plan_approved_by END,
            execution_confirmed_by = CASE WHEN ? = 'confirm_execution' THEN ? ELSE execution_confirmed_by END,
            execution_started_at = CASE WHEN ? = 'confirm_execution' THEN ? ELSE execution_started_at END,
            acceptance_status = ?, acceptance_reason = ?,
            closed_by = CASE WHEN ? = 'accept_work' THEN ? ELSE closed_by END,
            acceptance_note = ?,
            acceptance_checked_by = CASE
                WHEN ? IN ('accept_work', 'deny_acceptance') THEN ?
                WHEN ? = 'resubmit_work' THEN NULL
                ELSE acceptance_checked_by
            END,
            acceptance_checked_at = CASE
                WHEN ? IN ('accept_work', 'deny_acceptance') THEN ?
                WHEN ? = 'resubmit_work' THEN NULL
                ELSE acceptance_checked_at
            END,
            completion_summary = ?,
            actual_man_hours = ?,
            failure_mode = ?, failure_cause = ?,
            downtime_started_at = ?, restored_at = ?, downtime_hours = ?,
            execution_completed_by = CASE WHEN ? = 'complete_work' THEN ? ELSE execution_completed_by END,
            execution_completed_at = CASE WHEN ? = 'complete_work' THEN ? ELSE execution_completed_at END,
            updated_at = ?
        WHERE id = ?
        """,
        (
            next_step, description, maintenance_code, equipment_condition, workplace,
            man_hours, permit_requirement, permit_status,
            action, performed_by, action, performed_by, action, now,
            acceptance_status, acceptance_reason,
            action, performed_by, acceptance_note,
            action, performed_by, action,
            action, now, action,
            completion_summary, actual_man_hours,
            failure_mode, failure_cause,
            downtime_started_at, restored_at, downtime_hours,
            action, performed_by, action, now, now, order_id,
        ),
    )
    if action == "complete_work" and artisan_actuals:
        database.executemany(
            "UPDATE work_order_artisans SET actual_hours = ? WHERE id = ?",
            artisan_actuals,
        )
    if action == "return_plan":
        database.execute(
            """
            UPDATE work_orders
            SET plan_approved_by = NULL, permit_requirement = 'undecided',
                permit_status = 'not_required'
            WHERE id = ?
            """,
            (order_id,),
        )
    database.execute(
        """
        INSERT INTO work_order_history (
            work_order_id, workflow_step, action, performed_by, note, created_at
        ) VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            order_id, next_step, action.replace("_", " ").title(), performed_by,
            (
                completion_summary if action == "complete_work"
                else acceptance_note if action == "accept_work"
                else payload.get("reason")
            ),
            now,
        ),
    )
    if action == "accept_work" and order["source_event_id"]:
        source_event = database.execute(
            "SELECT state FROM event_entries WHERE id = ?",
            (order["source_event_id"],),
        ).fetchone()
        if source_event and source_event["state"] == "open":
            event_reason = (
                f"Closed automatically after {order['order_no']} was accepted: "
                f"{acceptance_note}"
            )
            database.execute(
                "UPDATE event_entries SET state = 'closed', updated_at = ? WHERE id = ?",
                (now, order["source_event_id"]),
            )
            database.execute(
                """
                INSERT INTO event_state_history (
                    event_id, previous_state, new_state, changed_by, reason, created_at
                ) VALUES (?, 'open', 'closed', ?, ?, ?)
                """,
                (order["source_event_id"], performed_by, event_reason, now),
            )
    sync_infobox(database)
    database.commit()
    request_id = database.execute(
        "SELECT work_request_id FROM work_orders WHERE id = ?", (order_id,)
    ).fetchone()[0]
    return jsonify(get_work_request(request_id))


@app.patch("/api/work-orders/<int:order_id>/permit")
@roles_required("Shift Leader")
def update_work_order_permit(order_id: int):
    payload = request.get_json(silent=True) or {}
    status = str(payload.get("status") or "").lower()
    performed_by = g.current_user["full_name"]
    if status not in {"issued", "cancelled"}:
        return jsonify({"error": "Valid status is required"}), 400
    database = get_db()
    order = database.execute(
        "SELECT work_request_id, permit_requirement, permit_status FROM work_orders WHERE id = ?",
        (order_id,),
    ).fetchone()
    if order is None:
        abort(404)
    if order["permit_requirement"] not in {"ptw", "loa"}:
        return jsonify({"error": "This work order does not require a permit"}), 409
    if status == "cancelled" and order["permit_status"] != "issued":
        return jsonify({"error": "Only an issued permit can be cancelled"}), 409
    now = datetime.now().isoformat(timespec="minutes")
    database.execute(
        "UPDATE work_orders SET permit_status = ?, updated_at = ? WHERE id = ?",
        (status, now, order_id),
    )
    database.execute(
        """
        INSERT INTO work_order_history (
            work_order_id, workflow_step, action, performed_by, note, created_at
        )
        SELECT id, workflow_step, ?, ?, NULL, ? FROM work_orders WHERE id = ?
        """,
        (f"{order['permit_requirement'].upper()} {status}", performed_by, now, order_id),
    )
    database.commit()
    return jsonify(get_work_request(order["work_request_id"]))


def get_work_request(request_id: int) -> dict:
    row = get_db().execute(
        """
        SELECT
            wr.*, a.kks_code, a.description AS asset_description,
            wo.id AS work_order_id, wo.order_no, wo.workflow_step,
            wo.description_of_work, wo.maintenance_code, wo.equipment_condition,
            wo.workplace_requirements,
            wo.expected_man_hours, wo.permit_requirement, wo.permit_status,
            wo.plan_approved_by, wo.execution_confirmed_by, wo.execution_started_at,
            wo.acceptance_status, wo.acceptance_reason, wo.closed_by,
            wo.acceptance_note, wo.acceptance_checked_by,
            wo.acceptance_checked_at,
            wo.completion_summary, wo.actual_man_hours,
            wo.failure_mode, wo.failure_cause, wo.downtime_started_at,
            wo.restored_at, wo.downtime_hours,
            wo.execution_completed_by, wo.execution_completed_at,
            CASE
                WHEN wr.target_response_at IS NOT NULL
                 AND datetime(wr.target_response_at) < datetime('now', 'localtime')
                 AND wr.status != 'declined'
                 AND COALESCE(wo.workflow_step, '') != 'closed'
                THEN 1 ELSE 0
            END AS is_response_overdue,
            se.entry_no AS source_event_no, se.subject AS source_event_subject,
            se.state AS source_event_state
        FROM work_requests wr
        JOIN assets a ON a.id = wr.asset_id
        LEFT JOIN work_orders wo ON wo.work_request_id = wr.id
        LEFT JOIN event_entries se ON se.id = wr.source_event_id
        WHERE wr.id = ?
        """,
        (request_id,),
    ).fetchone()
    if row is None:
        abort(404)
    result = row_to_dict(row)
    try:
        result["cmpt_impacts"] = json.loads(result.get("cmpt_impacts") or "[]")
    except (TypeError, json.JSONDecodeError):
        result["cmpt_impacts"] = []
    return result


@app.get("/api/preventive/schedule-types")
def list_schedule_types():
    rows = get_db().execute(
        """
        SELECT st.*, COUNT(rt.id) AS recurrent_count
        FROM schedule_types st
        LEFT JOIN recurrent_tasks rt ON rt.schedule_type_id = st.id
        GROUP BY st.id ORDER BY st.name
        """
    ).fetchall()
    return jsonify([row_to_dict(row) for row in rows])


@app.post("/api/preventive/schedule-types")
@roles_required("Maintenance Planner")
def create_schedule_type():
    payload = request.get_json(silent=True) or {}
    required = ("name", "calendar_unit", "interval_count", "strategy")
    missing = [field for field in required if not str(payload.get(field, "")).strip()]
    if missing:
        return jsonify({"error": "Missing required fields", "fields": missing}), 400
    calendar_unit = str(payload["calendar_unit"]).lower()
    strategy = str(payload["strategy"]).lower()
    adjustment = str(payload.get("weekend_adjustment") or "none").lower()
    if calendar_unit not in {"day", "week", "month", "year"}:
        return jsonify({"error": "Invalid calendar unit"}), 400
    if strategy not in {"interval_followup", "fixed_schedule", "official_inspection"}:
        return jsonify({"error": "Invalid scheduling strategy"}), 400
    if adjustment not in {"none", "next_working_day", "previous_working_day"}:
        return jsonify({"error": "Invalid weekend adjustment"}), 400
    meter_type = str(payload.get("meter_type") or "").strip()
    meter_interval_value = payload.get("meter_interval")
    has_meter_interval = meter_interval_value not in (None, "")
    if bool(meter_type) != has_meter_interval:
        return jsonify({
            "error": "Meter type and meter interval must be provided together"
        }), 400
    try:
        interval_count = int(payload["interval_count"])
        early_tolerance = int(payload.get("early_tolerance_days") or 0)
        late_tolerance = int(payload.get("late_tolerance_days") or 0)
        meter_interval = (
            float(meter_interval_value) if has_meter_interval else None
        )
    except (TypeError, ValueError):
        return jsonify({"error": "Schedule intervals must be numeric"}), 400
    if interval_count < 1:
        return jsonify({"error": "Calendar interval must be at least 1"}), 400
    if early_tolerance < 0 or late_tolerance < 0:
        return jsonify({"error": "Tolerance days cannot be negative"}), 400
    if meter_interval is not None and meter_interval <= 0:
        return jsonify({"error": "Meter interval must be greater than zero"}), 400
    database = get_db()
    try:
        cursor = database.execute(
            """
            INSERT INTO schedule_types (
                name, meter_type, meter_interval, calendar_unit, interval_count,
                task_type, description, early_tolerance_days, late_tolerance_days,
                strategy, weekend_adjustment, status
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'active')
            """,
            (
                str(payload["name"]).strip(),
                meter_type or None,
                meter_interval,
                calendar_unit,
                interval_count,
                str(payload.get("task_type") or "Preventive work order").strip(),
                str(payload.get("description") or "").strip(),
                early_tolerance,
                late_tolerance,
                strategy,
                adjustment,
            ),
        )
    except sqlite3.IntegrityError:
        return jsonify({"error": "Schedule type name already exists"}), 409
    database.commit()
    row = database.execute("SELECT * FROM schedule_types WHERE id = ?", (cursor.lastrowid,)).fetchone()
    return jsonify(row_to_dict(row)), 201


@app.get("/api/preventive")
def list_recurrent_tasks():
    filters = []
    parameters: list[object] = []
    search = request.args.get("q", "").strip().lower()
    status = request.args.get("status", "").strip().lower()
    if search:
        filters.append(
            "(lower(rt.recurrent_no) LIKE ? OR lower(rt.name) LIKE ? "
            "OR lower(a.kks_code) LIKE ? OR lower(rt.main_department) LIKE ?)"
        )
        pattern = f"%{search}%"
        parameters.extend([pattern, pattern, pattern, pattern])
    if status in {"active", "completed", "suspended"}:
        filters.append("rt.status = ?")
        parameters.append(status)
    sql = """
        SELECT
            rt.*, st.name AS schedule_type_name, st.calendar_unit,
            st.interval_count, st.strategy, st.early_tolerance_days,
            st.late_tolerance_days, a.kks_code,
            a.description AS asset_description,
            (SELECT COUNT(*) FROM recurrent_task_assets ra WHERE ra.recurrent_task_id = rt.id) AS asset_count,
            (SELECT COUNT(*) FROM preventive_tasks pt WHERE pt.recurrent_task_id = rt.id AND pt.status IN ('due', 'overdue')) AS due_count
        FROM recurrent_tasks rt
        JOIN schedule_types st ON st.id = rt.schedule_type_id
        JOIN assets a ON a.id = rt.primary_asset_id
    """
    if filters:
        sql += " WHERE " + " AND ".join(filters)
    sql += " ORDER BY rt.next_target_date, rt.id"
    rows = get_db().execute(sql, parameters).fetchall()
    return jsonify([row_to_dict(row) for row in rows])


@app.get("/api/preventive/summary")
def preventive_summary():
    refresh_preventive_statuses()
    row = get_db().execute(
        """
        SELECT
            (SELECT COUNT(*) FROM recurrent_tasks WHERE status = 'active') AS active_schedules,
            (SELECT COUNT(*) FROM preventive_tasks WHERE status = 'due') AS due,
            (SELECT COUNT(*) FROM preventive_tasks WHERE status = 'overdue') AS overdue,
            (SELECT COUNT(*) FROM preventive_tasks WHERE status = 'completed') AS completed
        """
    ).fetchone()
    return jsonify(row_to_dict(row))


@app.get("/api/preventive/calendar")
def preventive_calendar():
    month = request.args.get("month", "").strip()
    try:
        month_start = date.fromisoformat(f"{month}-01")
    except ValueError:
        return jsonify({"error": "Month must use YYYY-MM format"}), 400
    if month_start.month == 12:
        next_month = date(month_start.year + 1, 1, 1)
    else:
        next_month = date(month_start.year, month_start.month + 1, 1)
    refresh_preventive_statuses()
    filters = [
        "date(pt.target_date) >= date(?)",
        "date(pt.target_date) < date(?)",
    ]
    parameters: list[object] = [month_start.isoformat(), next_month.isoformat()]
    department = request.args.get("department", "").strip()
    status = request.args.get("status", "").strip().lower()
    if department:
        filters.append("rt.main_department = ?")
        parameters.append(department)
    if status in {"planned", "due", "overdue", "completed"}:
        filters.append("pt.status = ?")
        parameters.append(status)
    rows = get_db().execute(
        f"""
        SELECT pt.id, pt.task_no, pt.recurrent_task_id, pt.target_date,
            pt.early_date, pt.late_date, pt.status, pt.completed_at,
            rt.recurrent_no, rt.name, rt.main_department,
            a.kks_code, a.description AS asset_description
        FROM preventive_tasks pt
        JOIN recurrent_tasks rt ON rt.id = pt.recurrent_task_id
        JOIN assets a ON a.id = rt.primary_asset_id
        WHERE {' AND '.join(filters)}
        ORDER BY pt.target_date, pt.task_no
        """,
        parameters,
    ).fetchall()
    tasks = [row_to_dict(row) for row in rows]
    summary = {
        key: sum(1 for task in tasks if task["status"] == key)
        for key in ("planned", "due", "overdue", "completed")
    }
    summary["total"] = len(tasks)
    return jsonify({
        "month": month,
        "days": (next_month - month_start).days,
        "summary": summary,
        "tasks": tasks,
    })


@app.get("/api/preventive/calendar.csv")
def export_preventive_calendar():
    result = preventive_calendar()
    if isinstance(result, tuple):
        return result
    data = result.get_json()
    output = io.StringIO()
    writer = csv.writer(output, lineterminator="\n")
    writer.writerow([
        "Target Date", "Task Number", "Status", "Recurrent Schedule",
        "Work Description", "KKS Code", "Asset Description", "Department",
        "Early Date", "Late Date", "Completed At",
    ])
    for task in data["tasks"]:
        writer.writerow([
            task["target_date"], task["task_no"], task["status"],
            task["recurrent_no"], task["name"], task["kks_code"],
            task["asset_description"], task["main_department"],
            task["early_date"], task["late_date"], task["completed_at"],
        ])
    filename = f"morupule-b-preventive-calendar-{data['month']}.csv"
    return Response(
        "\ufeff" + output.getvalue(),
        mimetype="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@app.get("/api/preventive/<int:recurrent_id>")
def preventive_detail(recurrent_id: int):
    task = get_recurrent_task(recurrent_id)
    database = get_db()
    task["assets"] = [
        row_to_dict(row) for row in database.execute(
            """
            SELECT a.id, a.kks_code, a.description
            FROM recurrent_task_assets ra
            JOIN assets a ON a.id = ra.asset_id
            WHERE ra.recurrent_task_id = ? ORDER BY a.kks_code
            """,
            (recurrent_id,),
        ).fetchall()
    ]
    task["generated_tasks"] = [
        row_to_dict(row) for row in database.execute(
            """
            SELECT * FROM preventive_tasks
            WHERE recurrent_task_id = ? ORDER BY target_date DESC
            """,
            (recurrent_id,),
        ).fetchall()
    ]
    task["status_history"] = [
        row_to_dict(row) for row in database.execute(
            """
            SELECT previous_status, new_status, changed_by, reason, created_at
            FROM recurrent_task_history
            WHERE recurrent_task_id = ?
            ORDER BY id DESC
            """,
            (recurrent_id,),
        ).fetchall()
    ]
    task["attachments"] = attachment_rows("preventive", recurrent_id)
    return jsonify(task)


@app.post("/api/preventive")
@roles_required("Maintenance Planner")
def create_recurrent_task():
    payload = request.get_json(silent=True) or {}
    required = (
        "name", "schedule_type_id", "primary_asset_id", "type_of_work",
        "main_department", "start_date",
    )
    missing = [field for field in required if not str(payload.get(field, "")).strip()]
    if missing:
        return jsonify({"error": "Missing required fields", "fields": missing}), 400
    database = get_db()
    schedule = database.execute(
        "SELECT * FROM schedule_types WHERE id = ? AND status = 'active'",
        (payload["schedule_type_id"],),
    ).fetchone()
    if schedule is None:
        return jsonify({"error": "Schedule type not found"}), 400
    if database.execute(
        "SELECT id FROM assets WHERE id = ?", (payload["primary_asset_id"],)
    ).fetchone() is None:
        return jsonify({"error": "Primary asset not found"}), 400
    start_date = date.fromisoformat(str(payload["start_date"]))
    target_date = adjust_weekend(start_date, schedule["weekend_adjustment"])
    next_number = database.execute(
        "SELECT COALESCE(MAX(CAST(substr(recurrent_no, 9) AS INTEGER)), 0) + 1 FROM recurrent_tasks"
    ).fetchone()[0]
    now = datetime.now().isoformat(timespec="minutes")
    cursor = database.execute(
        """
        INSERT INTO recurrent_tasks (
            recurrent_no, name, schedule_type_id, primary_asset_id,
            type_of_work, main_department, work_schedule, duration_hours,
            reminder_days, start_date, end_date, repetitions, generated_count,
            next_target_date, status, created_by, created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, ?, 'active', ?, ?, ?)
        """,
        (
            f"RT-{datetime.now().year}-{next_number:04d}",
            str(payload["name"]).strip(),
            int(payload["schedule_type_id"]),
            int(payload["primary_asset_id"]),
            str(payload["type_of_work"]).strip(),
            str(payload["main_department"]).strip(),
            str(payload.get("work_schedule") or "").strip() or None,
            float(payload.get("duration_hours") or 0),
            int(payload.get("reminder_days") or 0),
            start_date.isoformat(),
            str(payload.get("end_date") or "").strip() or None,
            int(payload["repetitions"]) if payload.get("repetitions") else None,
            target_date.isoformat(),
            g.current_user["full_name"],
            now,
            now,
        ),
    )
    recurrent_id = cursor.lastrowid
    asset_ids = payload.get("asset_ids") or [int(payload["primary_asset_id"])]
    if int(payload["primary_asset_id"]) not in asset_ids:
        asset_ids.append(int(payload["primary_asset_id"]))
    for asset_id in set(int(value) for value in asset_ids):
        if database.execute("SELECT id FROM assets WHERE id = ?", (asset_id,)).fetchone():
            database.execute(
                "INSERT INTO recurrent_task_assets (recurrent_task_id, asset_id) VALUES (?, ?)",
                (recurrent_id, asset_id),
            )
    database.commit()
    return jsonify(get_recurrent_task(recurrent_id)), 201


@app.patch("/api/preventive/<int:recurrent_id>")
@roles_required("Maintenance Planner")
def update_recurrent_task(recurrent_id: int):
    payload = request.get_json(silent=True) or {}
    required = ("name", "type_of_work", "main_department")
    missing = [field for field in required if not str(payload.get(field, "")).strip()]
    if missing:
        return jsonify({"error": "Missing required fields", "fields": missing}), 400
    database = get_db()
    current = database.execute(
        "SELECT * FROM recurrent_tasks WHERE id = ?",
        (recurrent_id,),
    ).fetchone()
    if current is None:
        abort(404)
    if current["status"] == "completed":
        return jsonify({"error": "A completed schedule cannot be edited"}), 409
    try:
        duration_hours = float(payload.get("duration_hours") or 0)
        reminder_days = int(payload.get("reminder_days") or 0)
        repetitions = (
            int(payload["repetitions"])
            if payload.get("repetitions") not in (None, "")
            else None
        )
    except (TypeError, ValueError):
        return jsonify({"error": "Duration, reminder, and repetitions must be numeric"}), 400
    if duration_hours < 0 or reminder_days < 0:
        return jsonify({"error": "Duration and reminder cannot be negative"}), 400
    if repetitions is not None and repetitions < max(1, current["generated_count"]):
        return jsonify({
            "error": "Repetitions cannot be lower than tasks already generated"
        }), 400
    end_date_value = str(payload.get("end_date") or "").strip() or None
    if end_date_value:
        try:
            end_date = date.fromisoformat(end_date_value)
        except ValueError:
            return jsonify({"error": "End date is invalid"}), 400
        if end_date < date.fromisoformat(current["start_date"]):
            return jsonify({"error": "End date cannot be before start date"}), 400
    asset_ids = payload.get("asset_ids") or []
    try:
        selected_asset_ids = {int(asset_id) for asset_id in asset_ids}
    except (TypeError, ValueError):
        return jsonify({"error": "Asset group contains an invalid asset"}), 400
    selected_asset_ids.add(current["primary_asset_id"])
    existing_asset_ids = {
        row["id"] for row in database.execute(
            f"SELECT id FROM assets WHERE id IN ({','.join('?' for _ in selected_asset_ids)})",
            tuple(selected_asset_ids),
        ).fetchall()
    }
    if existing_asset_ids != selected_asset_ids:
        return jsonify({"error": "One or more asset group records were not found"}), 400
    now = datetime.now().isoformat(timespec="minutes")
    database.execute(
        """
        UPDATE recurrent_tasks
        SET name = ?, type_of_work = ?, main_department = ?,
            work_schedule = ?, duration_hours = ?, reminder_days = ?,
            end_date = ?, repetitions = ?, updated_at = ?
        WHERE id = ?
        """,
        (
            str(payload["name"]).strip(),
            str(payload["type_of_work"]).strip(),
            str(payload["main_department"]).strip(),
            str(payload.get("work_schedule") or "").strip() or None,
            duration_hours, reminder_days, end_date_value, repetitions,
            now, recurrent_id,
        ),
    )
    database.execute(
        "DELETE FROM recurrent_task_assets WHERE recurrent_task_id = ?",
        (recurrent_id,),
    )
    database.executemany(
        "INSERT INTO recurrent_task_assets (recurrent_task_id, asset_id) VALUES (?, ?)",
        [(recurrent_id, asset_id) for asset_id in sorted(selected_asset_ids)],
    )
    database.commit()
    return jsonify(preventive_detail(recurrent_id).get_json())


@app.patch("/api/preventive/<int:recurrent_id>/status")
@roles_required("Maintenance Planner")
def update_recurrent_task_status(recurrent_id: int):
    payload = request.get_json(silent=True) or {}
    new_status = str(payload.get("status") or "").lower()
    reason = str(payload.get("reason") or "").strip()
    if new_status not in {"active", "suspended"}:
        return jsonify({"error": "Status must be active or suspended"}), 400
    if not reason:
        return jsonify({"error": "A reason is required for the status change"}), 400

    database = get_db()
    task = database.execute(
        "SELECT id, status FROM recurrent_tasks WHERE id = ?",
        (recurrent_id,),
    ).fetchone()
    if task is None:
        abort(404)
    if task["status"] == "completed":
        return jsonify({"error": "A completed schedule cannot be reactivated"}), 409
    if task["status"] == new_status:
        return jsonify({"error": f"Schedule is already {new_status}"}), 409

    now = datetime.now().isoformat(timespec="minutes")
    database.execute(
        "UPDATE recurrent_tasks SET status = ?, updated_at = ? WHERE id = ?",
        (new_status, now, recurrent_id),
    )
    database.execute(
        """
        INSERT INTO recurrent_task_history (
            recurrent_task_id, previous_status, new_status,
            changed_by, reason, created_at
        ) VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            recurrent_id, task["status"], new_status,
            g.current_user["full_name"], reason, now,
        ),
    )
    database.commit()
    return jsonify(preventive_detail(recurrent_id).get_json())


@app.post("/api/preventive/<int:recurrent_id>/generate")
@roles_required("Maintenance Planner")
def generate_preventive_task(recurrent_id: int):
    database = get_db()
    task = database.execute(
        """
        SELECT rt.*, st.early_tolerance_days, st.late_tolerance_days
        FROM recurrent_tasks rt
        JOIN schedule_types st ON st.id = rt.schedule_type_id
        WHERE rt.id = ? AND rt.status = 'active'
        """,
        (recurrent_id,),
    ).fetchone()
    if task is None:
        return jsonify({"error": "Active recurrent task not found"}), 404
    generated, reason = create_preventive_task_record(database, task)
    if generated is None:
        return jsonify({"error": reason}), 409
    database.commit()
    return jsonify(generated), 201


def create_preventive_task_record(
    database: sqlite3.Connection,
    task: sqlite3.Row,
) -> tuple[dict | None, str | None]:
    if task["repetitions"] is not None and task["generated_count"] >= task["repetitions"]:
        return None, "Configured number of repetitions has been reached"
    target = date.fromisoformat(task["next_target_date"])
    if task["end_date"] and target > date.fromisoformat(task["end_date"]):
        return None, "Recurrent task end date has been reached"
    existing = database.execute(
        "SELECT id FROM preventive_tasks WHERE recurrent_task_id = ? AND target_date = ?",
        (task["id"], target.isoformat()),
    ).fetchone()
    if existing:
        return None, "Task for this target date already exists"
    next_number = database.execute(
        "SELECT COALESCE(MAX(CAST(substr(task_no, 9) AS INTEGER)), 0) + 1 FROM preventive_tasks"
    ).fetchone()[0]
    today = date.today()
    late = target + timedelta(days=task["late_tolerance_days"])
    status = "overdue" if today > late else "due" if today >= target - timedelta(days=task["early_tolerance_days"]) else "planned"
    now = datetime.now().isoformat(timespec="minutes")
    cursor = database.execute(
        """
        INSERT INTO preventive_tasks (
            task_no, recurrent_task_id, target_date, early_date, late_date,
            status, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            f"PM-{datetime.now().year}-{next_number:04d}", task["id"],
            target.isoformat(),
            (target - timedelta(days=task["early_tolerance_days"])).isoformat(),
            late.isoformat(), status, now,
        ),
    )
    database.execute(
        "UPDATE recurrent_tasks SET generated_count = generated_count + 1, updated_at = ? WHERE id = ?",
        (now, task["id"]),
    )
    row = database.execute("SELECT * FROM preventive_tasks WHERE id = ?", (cursor.lastrowid,)).fetchone()
    return row_to_dict(row), None


def preventive_generation_scope(
    database: sqlite3.Connection,
    month: str,
    department: str,
) -> tuple[list[dict], str | None]:
    try:
        month_start = date.fromisoformat(f"{month}-01")
    except ValueError:
        return [], "Month must use YYYY-MM format"
    if month_start.month == 12:
        next_month = date(month_start.year + 1, 1, 1)
    else:
        next_month = date(month_start.year, month_start.month + 1, 1)
    filters = [
        "date(rt.next_target_date) >= date(?)",
        "date(rt.next_target_date) < date(?)",
    ]
    parameters: list[object] = [month_start.isoformat(), next_month.isoformat()]
    if department:
        filters.append("rt.main_department = ?")
        parameters.append(department)
    schedules = database.execute(
        f"""
        SELECT rt.*, st.early_tolerance_days, st.late_tolerance_days
        FROM recurrent_tasks rt
        JOIN schedule_types st ON st.id = rt.schedule_type_id
        WHERE {' AND '.join(filters)}
        ORDER BY rt.next_target_date, rt.id
        """,
        parameters,
    ).fetchall()
    preview: list[dict] = []
    for schedule in schedules:
        target = date.fromisoformat(schedule["next_target_date"])
        reason = None
        if schedule["status"] != "active":
            reason = f"Schedule is {schedule['status']}"
        elif (
            schedule["repetitions"] is not None
            and schedule["generated_count"] >= schedule["repetitions"]
        ):
            reason = "Configured number of repetitions has been reached"
        elif schedule["end_date"] and target > date.fromisoformat(schedule["end_date"]):
            reason = "Recurrent task end date has been reached"
        elif database.execute(
            """
            SELECT 1 FROM preventive_tasks
            WHERE recurrent_task_id = ? AND target_date = ?
            """,
            (schedule["id"], schedule["next_target_date"]),
        ).fetchone():
            reason = "Task for this target date already exists"
        preview.append({
            "recurrent_id": schedule["id"],
            "recurrent_no": schedule["recurrent_no"],
            "name": schedule["name"],
            "department": schedule["main_department"],
            "target_date": schedule["next_target_date"],
            "ready": reason is None,
            "reason": reason,
            "_schedule": schedule,
        })
    return preview, None


@app.get("/api/preventive/calendar/generate-preview")
@roles_required("Maintenance Planner")
def preview_preventive_calendar_generation():
    month = request.args.get("month", "").strip()
    department = request.args.get("department", "").strip()
    preview, error = preventive_generation_scope(get_db(), month, department)
    if error:
        return jsonify({"error": error}), 400
    items = [
        {key: value for key, value in item.items() if key != "_schedule"}
        for item in preview
    ]
    return jsonify({
        "month": month,
        "department": department or None,
        "total": len(items),
        "ready_count": sum(1 for item in items if item["ready"]),
        "blocked_count": sum(1 for item in items if not item["ready"]),
        "items": items,
    })


@app.post("/api/preventive/calendar/generate")
@roles_required("Maintenance Planner")
def generate_preventive_calendar_month():
    payload = request.get_json(silent=True) or {}
    month = str(payload.get("month") or "").strip()
    department = str(payload.get("department") or "").strip()
    database = get_db()
    preview, error = preventive_generation_scope(database, month, department)
    if error:
        return jsonify({"error": error}), 400
    generated: list[dict] = []
    skipped: list[dict] = []
    for item in preview:
        schedule = item["_schedule"]
        if not item["ready"]:
            skipped.append({
                "recurrent_id": item["recurrent_id"],
                "recurrent_no": item["recurrent_no"],
                "reason": item["reason"],
            })
            continue
        task, reason = create_preventive_task_record(database, schedule)
        if task is None:
            skipped.append({
                "recurrent_id": schedule["id"],
                "recurrent_no": schedule["recurrent_no"],
                "reason": reason,
            })
        else:
            generated.append(task)
    database.commit()
    return jsonify({
        "month": month,
        "department": department or None,
        "eligible": len(preview),
        "generated_count": len(generated),
        "skipped_count": len(skipped),
        "generated": generated,
        "skipped": skipped,
    })


@app.patch("/api/preventive/tasks/<int:task_id>/complete")
@login_required
def complete_preventive_task(task_id: int):
    payload = request.get_json(silent=True) or {}
    completed_by = g.current_user["full_name"]
    database = get_db()
    task = database.execute(
        """
        SELECT pt.*, rt.schedule_type_id, rt.start_date, rt.repetitions,
            rt.generated_count, rt.main_department,
            st.calendar_unit, st.interval_count,
            st.strategy, st.weekend_adjustment
        FROM preventive_tasks pt
        JOIN recurrent_tasks rt ON rt.id = pt.recurrent_task_id
        JOIN schedule_types st ON st.id = rt.schedule_type_id
        WHERE pt.id = ?
        """,
        (task_id,),
    ).fetchone()
    if task is None:
        abort(404)
    required_roles = execution_roles_for_department(task["main_department"])
    if not current_user_has_role(*required_roles):
        return jsonify({
            "error": (
                f"Completion requires: {', '.join(required_roles)}"
            )
        }), 403
    if task["status"] == "completed":
        return jsonify({"error": "Preventive task is already completed"}), 409
    feedback = str(payload.get("feedback") or "").strip()
    if not feedback:
        return jsonify({"error": "Completion feedback is required"}), 400
    try:
        actual_man_hours = float(payload.get("actual_man_hours"))
    except (TypeError, ValueError):
        return jsonify({"error": "Actual man-hours are required"}), 400
    if actual_man_hours < 0:
        return jsonify({"error": "Actual man-hours cannot be negative"}), 400
    completed_at = str(payload.get("completed_at") or datetime.now().isoformat(timespec="minutes"))
    try:
        completed_date = date.fromisoformat(completed_at[:10])
    except ValueError:
        return jsonify({"error": "Completion date is invalid"}), 400
    target_date = date.fromisoformat(task["target_date"])
    if task["strategy"] == "interval_followup":
        base_date = completed_date
    elif task["strategy"] == "official_inspection" and completed_date < target_date:
        base_date = completed_date
    else:
        base_date = target_date
    next_target = adjust_weekend(
        add_interval(base_date, task["calendar_unit"], task["interval_count"]),
        task["weekend_adjustment"],
    )
    now = datetime.now().isoformat(timespec="minutes")
    database.execute(
        """
        UPDATE preventive_tasks
        SET status = 'completed', completed_at = ?, completed_by = ?,
            feedback = ?, actual_man_hours = ?
        WHERE id = ?
        """,
        (
            completed_at, completed_by, feedback,
            actual_man_hours, task_id,
        ),
    )
    status = "completed" if task["repetitions"] is not None and task["generated_count"] >= task["repetitions"] else "active"
    database.execute(
        """
        UPDATE recurrent_tasks
        SET next_target_date = ?, status = ?, updated_at = ?
        WHERE id = ?
        """,
        (next_target.isoformat(), status, now, task["recurrent_task_id"]),
    )
    database.commit()
    return jsonify(preventive_detail(task["recurrent_task_id"]).get_json())


def add_interval(base: date, unit: str, count: int) -> date:
    if unit == "day":
        return base + timedelta(days=count)
    if unit == "week":
        return base + timedelta(weeks=count)
    months = count if unit == "month" else count * 12
    month_index = base.month - 1 + months
    year = base.year + month_index // 12
    month = month_index % 12 + 1
    day = min(base.day, calendar.monthrange(year, month)[1])
    return date(year, month, day)


def adjust_weekend(value: date, adjustment: str) -> date:
    if adjustment == "next_working_day":
        while value.weekday() >= 5:
            value += timedelta(days=1)
    elif adjustment == "previous_working_day":
        while value.weekday() >= 5:
            value -= timedelta(days=1)
    return value


def refresh_preventive_statuses() -> None:
    today = date.today().isoformat()
    database = get_db()
    database.execute(
        """
        UPDATE preventive_tasks
        SET status = CASE
            WHEN date(?) > date(late_date) THEN 'overdue'
            WHEN date(?) >= date(early_date) THEN 'due'
            ELSE 'planned'
        END
        WHERE status != 'completed'
        """,
        (today, today),
    )
    database.commit()


def get_recurrent_task(recurrent_id: int) -> dict:
    row = get_db().execute(
        """
        SELECT
            rt.*, st.name AS schedule_type_name, st.calendar_unit,
            st.interval_count, st.description AS schedule_description,
            st.early_tolerance_days, st.late_tolerance_days,
            st.strategy, st.weekend_adjustment, st.meter_type,
            st.meter_interval, st.task_type,
            a.kks_code, a.description AS asset_description
        FROM recurrent_tasks rt
        JOIN schedule_types st ON st.id = rt.schedule_type_id
        JOIN assets a ON a.id = rt.primary_asset_id
        WHERE rt.id = ?
        """,
        (recurrent_id,),
    ).fetchone()
    if row is None:
        abort(404)
    return row_to_dict(row)


@app.get("/api/permits")
def list_safety_permits():
    filters = []
    parameters: list[object] = []
    search = request.args.get("q", "").strip().lower()
    status = request.args.get("status", "").strip().lower()
    form_type = request.args.get("form_type", "").strip().lower()
    if search:
        filters.append(
            "(lower(p.permit_no) LIKE ? OR lower(p.work_description) LIKE ? "
            "OR lower(p.location) LIKE ? OR lower(a.kks_code) LIKE ?)"
        )
        pattern = f"%{search}%"
        parameters.extend([pattern, pattern, pattern, pattern])
    if status in {"prepared", "issued", "received", "cleared", "cancelled"}:
        filters.append("p.status = ?")
        parameters.append(status)
    if form_type in SAFETY_FORM_TYPES:
        filters.append("p.form_type = ?")
        parameters.append(form_type)
    sql = """
        SELECT
            p.*, a.kks_code, a.description AS asset_description,
            wo.order_no
        FROM safety_permits p
        JOIN assets a ON a.id = p.asset_id
        LEFT JOIN work_orders wo ON wo.id = p.work_order_id
    """
    if filters:
        sql += " WHERE " + " AND ".join(filters)
    sql += """
        ORDER BY
            CASE p.status
                WHEN 'prepared' THEN 1 WHEN 'issued' THEN 2
                WHEN 'received' THEN 3 WHEN 'cleared' THEN 4 ELSE 5
            END,
            p.updated_at DESC
    """
    rows = get_db().execute(sql, parameters).fetchall()
    return jsonify([row_to_dict(row) for row in rows])


@app.get("/api/permits/summary")
def safety_permits_summary():
    row = get_db().execute(
        """
        SELECT
            COUNT(*) AS total,
            SUM(CASE WHEN status = 'prepared' THEN 1 ELSE 0 END) AS prepared,
            SUM(CASE WHEN status IN ('issued', 'received') THEN 1 ELSE 0 END) AS active,
            SUM(CASE WHEN status = 'cleared' THEN 1 ELSE 0 END) AS awaiting_cancellation
        FROM safety_permits
        """
    ).fetchone()
    return jsonify(row_to_dict(row))


@app.get("/api/permits/<int:permit_id>")
def safety_permit_detail(permit_id: int):
    permit = get_safety_permit(permit_id)
    database = get_db()
    permit["precautions"] = [
        row_to_dict(row) for row in database.execute(
            """
            SELECT precaution_code, precaution_text, selected
            FROM permit_precautions WHERE permit_id = ? ORDER BY id
            """,
            (permit_id,),
        ).fetchall()
    ]
    permit["assessments"] = [
        row_to_dict(row) for row in database.execute(
            """
            SELECT assessment_type, answer, remarks
            FROM permit_special_assessments WHERE permit_id = ? ORDER BY id
            """,
            (permit_id,),
        ).fetchall()
    ]
    permit["transition_history"] = [
        row_to_dict(row) for row in database.execute(
            """
            SELECT previous_status, new_status, action, performed_by,
                controller_name, remarks, created_at
            FROM permit_transition_history
            WHERE permit_id = ?
            ORDER BY id DESC
            """,
            (permit_id,),
        ).fetchall()
    ]
    permit["attachments"] = attachment_rows("permit", permit_id)
    return jsonify(permit)


@app.post("/api/permits")
@roles_required("Shift Leader")
def create_safety_permit():
    payload = request.get_json(silent=True) or {}
    required = (
        "asset_id", "form_type", "work_description", "location",
        "issued_to", "employer",
    )
    missing = [field for field in required if not str(payload.get(field, "")).strip()]
    if missing:
        return jsonify({"error": "Missing required fields", "fields": missing}), 400
    form_type = str(payload["form_type"]).lower()
    if form_type not in SAFETY_FORM_TYPES:
        return jsonify({"error": "Invalid permit form type"}), 400
    database = get_db()
    if database.execute("SELECT id FROM assets WHERE id = ?", (payload["asset_id"],)).fetchone() is None:
        return jsonify({"error": "Asset not found"}), 400
    work_order_id = payload.get("work_order_id")
    if work_order_id:
        linked_order = database.execute(
            """
            SELECT wo.id, wo.workflow_step, wo.permit_requirement, wr.asset_id
            FROM work_orders wo
            JOIN work_requests wr ON wr.id = wo.work_request_id
            WHERE wo.id = ?
            """,
            (work_order_id,),
        ).fetchone()
        if linked_order is None:
            return jsonify({"error": "Work order not found"}), 400
        if linked_order["workflow_step"] != "permit_decision":
            return jsonify({
                "error": "A linked permit can only be prepared after plan approval"
            }), 409
        form_requirement = "loa" if form_type.endswith("loa") else ("sft" if form_type.endswith("sft") else "ptw")
        if linked_order["permit_requirement"] != form_requirement:
            return jsonify({
                "error": f"This work order requires {linked_order['permit_requirement'].upper()}"
            }), 409
        if int(payload["asset_id"]) != linked_order["asset_id"]:
            return jsonify({"error": "Permit asset must match the work order KKS"}), 409
        active_permit = database.execute(
            """
            SELECT permit_no FROM safety_permits
            WHERE work_order_id = ? AND status != 'cancelled'
            ORDER BY id DESC LIMIT 1
            """,
            (work_order_id,),
        ).fetchone()
        if active_permit:
            return jsonify({
                "error": f"{active_permit['permit_no']} is already active for this work order"
            }), 409
    prefix = "LOA" if form_type.endswith("loa") else ("SFT" if form_type.endswith("sft") else "PTW")
    next_number = database.execute(
        "SELECT COALESCE(MAX(CAST(substr(permit_no, 10) AS INTEGER)), 0) + 1 FROM safety_permits WHERE permit_no LIKE ?",
        (f"{prefix}-%",),
    ).fetchone()[0]
    now = datetime.now().isoformat(timespec="minutes")
    cursor = database.execute(
        """
        INSERT INTO safety_permits (
            permit_no, work_order_id, asset_id, form_type, status,
            work_description, location, issued_to, employer,
            electrical_isolations, mechanical_isolations, circuit_main_earths,
            additional_earths, identity_wristlets, limits_of_access,
            precautions_confirmed, prepared_by, created_at, updated_at
        ) VALUES (?, ?, ?, ?, 'prepared', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            f"{prefix}-{datetime.now().year}-{next_number:04d}",
            work_order_id,
            int(payload["asset_id"]),
            form_type,
            str(payload["work_description"]).strip(),
            str(payload["location"]).strip(),
            str(payload["issued_to"]).strip(),
            str(payload["employer"]).strip(),
            str(payload.get("electrical_isolations") or "").strip() or None,
            str(payload.get("mechanical_isolations") or "").strip() or None,
            str(payload.get("circuit_main_earths") or "").strip() or None,
            int(payload.get("additional_earths") or 0),
            int(payload.get("identity_wristlets") or 0),
            str(payload.get("limits_of_access") or "").strip() or None,
            1 if payload.get("precautions_confirmed") else 0,
            g.current_user["full_name"],
            now,
            now,
        ),
    )
    permit_id = cursor.lastrowid
    selected_precautions = set(payload.get("precautions") or [])
    for code, text in default_precautions():
        database.execute(
            """
            INSERT INTO permit_precautions
                (permit_id, precaution_code, precaution_text, selected)
            VALUES (?, ?, ?, ?)
            """,
            (permit_id, code, text, 1 if code in selected_precautions else 0),
        )
    assessments = payload.get("assessments") or {}
    for assessment_type in ("hot_work", "height_work", "confined_space"):
        assessment = assessments.get(assessment_type) or {}
        database.execute(
            """
            INSERT INTO permit_special_assessments
                (permit_id, assessment_type, answer, remarks)
            VALUES (?, ?, ?, ?)
            """,
            (
                permit_id, assessment_type,
                assessment.get("answer", "na"),
                str(assessment.get("remarks") or "").strip() or None,
            ),
        )
    database.commit()
    return jsonify(get_safety_permit(permit_id)), 201


@app.patch("/api/permits/<int:permit_id>/transition")
@roles_required("Shift Leader")
def transition_safety_permit(permit_id: int):
    payload = request.get_json(silent=True) or {}
    action = str(payload.get("action") or "").lower()
    performed_by = g.current_user["full_name"]
    if not action:
        return jsonify({"error": "Action is required"}), 400
    remarks = str(payload.get("remarks") or "").strip()
    if not remarks:
        return jsonify({"error": "Transition remarks are required"}), 400
    database = get_db()
    permit = database.execute("SELECT * FROM safety_permits WHERE id = ?", (permit_id,)).fetchone()
    if permit is None:
        abort(404)
    transitions = {
        ("prepared", "issue"): "issued",
        ("issued", "receive"): "received",
        ("received", "clear"): "cleared",
        ("cleared", "cancel"): "cancelled",
    }
    next_status = transitions.get((permit["status"], action))
    if next_status is None:
        return jsonify({"error": f"Action {action} is not valid during {permit['status']}"}), 409
    if action == "issue":
        if not permit["precautions_confirmed"]:
            return jsonify({"error": "Safety precautions must be confirmed before issue"}), 409
        if not str(payload.get("controller_name") or "").strip():
            return jsonify({"error": "Controller name is required for issue"}), 400
        selected_count = database.execute(
            "SELECT COUNT(*) FROM permit_precautions WHERE permit_id = ? AND selected = 1",
            (permit_id,),
        ).fetchone()[0]
        if selected_count == 0:
            return jsonify({"error": "At least one safety precaution must be selected"}), 409
    now = datetime.now().isoformat(timespec="minutes")
    field_updates = {
        "issue": ("issued_by", "issued_at"),
        "receive": ("received_by", "received_at"),
        "clear": ("cleared_by", "cleared_at"),
        "cancel": ("cancelled_by", "cancelled_at"),
    }
    person_field, time_field = field_updates[action]
    controller_name = str(payload.get("controller_name") or permit["controller_name"] or "").strip() or None
    database.execute(
        f"""
        UPDATE safety_permits
        SET status = ?, {person_field} = ?, {time_field} = ?,
            controller_name = ?, updated_at = ?
        WHERE id = ?
        """,
        (next_status, performed_by, now, controller_name, now, permit_id),
    )
    database.execute(
        """
        INSERT INTO permit_transition_history (
            permit_id, previous_status, new_status, action,
            performed_by, controller_name, remarks, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            permit_id, permit["status"], next_status, action,
            performed_by, controller_name, remarks, now,
        ),
    )
    if permit["work_order_id"]:
        permit_status = "issued" if action == "issue" else "cancelled" if action == "cancel" else None
        if permit_status:
            database.execute(
                "UPDATE work_orders SET permit_status = ?, updated_at = ? WHERE id = ?",
                (permit_status, now, permit["work_order_id"]),
            )
    database.commit()
    return jsonify(safety_permit_detail(permit_id).get_json())


def default_precautions() -> list[tuple[str, str]]:
    return [
        ("isolate_energy", "All energy sources identified and isolated"),
        ("lock_tag", "Locks and caution tags applied"),
        ("prove_dead", "Dead condition proven before work"),
        ("drain_vent", "Pressure released, drained and vented"),
        ("barrier", "Work area barriers and warning notices installed"),
        ("ppe", "Required personal protective equipment confirmed"),
    ]


def get_safety_permit(permit_id: int) -> dict:
    row = get_db().execute(
        """
        SELECT
            p.*, a.kks_code, a.description AS asset_description,
            wo.order_no, wr.request_no
        FROM safety_permits p
        JOIN assets a ON a.id = p.asset_id
        LEFT JOIN work_orders wo ON wo.id = p.work_order_id
        LEFT JOIN work_requests wr ON wr.id = wo.work_request_id
        WHERE p.id = ?
        """,
        (permit_id,),
    ).fetchone()
    if row is None:
        abort(404)
    return row_to_dict(row)


@app.get("/api/users")
@roles_required("System Administrator")
def list_users():
    rows = get_db().execute(
        """
        SELECT id, employee_no, full_name, initials, department, role_name, status
        FROM users ORDER BY status DESC, full_name
        """
    ).fetchall()
    return jsonify([row_to_dict(row) for row in rows])


@app.post("/api/users")
@roles_required("System Administrator")
def create_user():
    payload = request.get_json(silent=True) or {}
    required = ("employee_no", "full_name", "initials", "department", "role_name", "password")
    missing = [field for field in required if not str(payload.get(field) or "").strip()]
    if missing:
        return jsonify({"error": "Missing required fields", "fields": missing}), 400
    role_name = str(payload["role_name"]).strip()
    if role_name not in USER_ROLES:
        return jsonify({"error": "Invalid role"}), 400
    password = str(payload["password"])
    if len(password) < 8:
        return jsonify({"error": "Password must contain at least 8 characters"}), 400
    database = get_db()
    try:
        cursor = database.execute(
            """
            INSERT INTO users (
                employee_no, full_name, initials, department, role_name,
                password_hash, status
            ) VALUES (?, ?, ?, ?, ?, ?, 'active')
            """,
            (
                str(payload["employee_no"]).strip().upper(),
                str(payload["full_name"]).strip(),
                str(payload["initials"]).strip().upper()[:4],
                str(payload["department"]).strip(),
                role_name,
                generate_password_hash(password),
            ),
        )
    except sqlite3.IntegrityError:
        return jsonify({"error": "Employee number already exists"}), 409
    sync_user_groups(database, cursor.lastrowid, role_name)
    database.commit()
    row = database.execute(
        """
        SELECT id, employee_no, full_name, initials, department, role_name, status
        FROM users WHERE id = ?
        """,
        (cursor.lastrowid,),
    ).fetchone()
    return jsonify(row_to_dict(row)), 201


@app.patch("/api/users/<int:user_id>")
@roles_required("System Administrator")
def update_user(user_id: int):
    payload = request.get_json(silent=True) or {}
    database = get_db()
    user = database.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    if user is None:
        abort(404)
    role_name = str(payload.get("role_name") or user["role_name"]).strip()
    status = str(payload.get("status") or user["status"]).strip()
    if role_name not in USER_ROLES:
        return jsonify({"error": "Invalid role"}), 400
    if status not in {"active", "inactive"}:
        return jsonify({"error": "Invalid account status"}), 400
    if user_id == g.current_user["id"] and status == "inactive":
        return jsonify({"error": "You cannot deactivate your own account"}), 409
    database.execute(
        """
        UPDATE users SET full_name = ?, initials = ?, department = ?,
            role_name = ?, status = ?
        WHERE id = ?
        """,
        (
            str(payload.get("full_name") or user["full_name"]).strip(),
            str(payload.get("initials") or user["initials"]).strip().upper()[:4],
            str(payload.get("department") or user["department"]).strip(),
            role_name,
            status,
            user_id,
        ),
    )
    sync_user_groups(database, user_id, role_name)
    database.commit()
    return jsonify({"status": "updated", "user_id": user_id})


@app.post("/api/users/<int:user_id>/reset-password")
@roles_required("System Administrator")
def reset_user_password(user_id: int):
    payload = request.get_json(silent=True) or {}
    password = str(payload.get("password") or "")
    if len(password) < 8:
        return jsonify({"error": "Password must contain at least 8 characters"}), 400
    cursor = get_db().execute(
        "UPDATE users SET password_hash = ? WHERE id = ?",
        (generate_password_hash(password), user_id),
    )
    if cursor.rowcount == 0:
        abort(404)
    get_db().commit()
    return jsonify({"status": "password_reset", "user_id": user_id})


@app.get("/api/audit-logs")
@roles_required("System Administrator")
def list_audit_logs():
    filters = []
    parameters: list[object] = []
    query = str(request.args.get("q") or "").strip()
    action = str(request.args.get("action") or "").strip()
    start = str(request.args.get("start") or "").strip()
    end = str(request.args.get("end") or "").strip()
    if query:
        pattern = f"%{query}%"
        filters.append(
            "(employee_no LIKE ? OR user_name LIKE ? OR target LIKE ? OR details LIKE ?)"
        )
        parameters.extend([pattern, pattern, pattern, pattern])
    if action:
        filters.append("action = ?")
        parameters.append(action)
    if start:
        filters.append("date(created_at) >= date(?)")
        parameters.append(start)
    if end:
        filters.append("date(created_at) <= date(?)")
        parameters.append(end)
    try:
        limit = min(max(int(request.args.get("limit", 250)), 1), 1000)
    except ValueError:
        limit = 250
    sql = """
        SELECT
            id, employee_no, user_name, role_name, action, target,
            method, status_code, details, ip_address, created_at
        FROM audit_logs
    """
    if filters:
        sql += " WHERE " + " AND ".join(filters)
    sql += " ORDER BY created_at DESC, id DESC LIMIT ?"
    parameters.append(limit)
    rows = get_db().execute(sql, parameters).fetchall()
    return jsonify([row_to_dict(row) for row in rows])


@app.get("/api/audit-logs/actions")
@roles_required("System Administrator")
def list_audit_actions():
    rows = get_db().execute(
        "SELECT DISTINCT action FROM audit_logs ORDER BY action"
    ).fetchall()
    return jsonify([row["action"] for row in rows])


@app.get("/api/system/status")
@roles_required("System Administrator")
def system_status():
    database = get_db()
    database_path = Path(app.config["DATABASE"])
    upload_path = Path(app.config["UPLOAD_FOLDER"])
    upload_files = [path for path in upload_path.rglob("*") if path.is_file()]
    integrity = database.execute("PRAGMA integrity_check").fetchone()[0]
    foreign_key_issues = database.execute("PRAGMA foreign_key_check").fetchall()
    counts = database.execute(
        """
        SELECT
            (SELECT COUNT(*) FROM assets) AS assets,
            (SELECT COUNT(*) FROM event_entries) AS events,
            (SELECT COUNT(*) FROM work_requests) AS work_requests,
            (SELECT COUNT(*) FROM recurrent_tasks) AS recurrent_tasks,
            (SELECT COUNT(*) FROM preventive_tasks) AS preventive_tasks,
            (SELECT COUNT(*) FROM safety_permits) AS permits,
            (SELECT COUNT(*) FROM users WHERE status = 'active') AS active_users,
            (SELECT COUNT(*) FROM attachments) AS attachments,
            (SELECT COUNT(*) FROM audit_logs) AS audit_records
        """
    ).fetchone()
    import_runs = [
        row_to_dict(row) for row in database.execute(
            """
            SELECT id, source_file, imported_at, source_rows, unique_assets,
                duplicate_rows, inferred_parents
            FROM kks_import_runs ORDER BY imported_at DESC, id DESC LIMIT 10
            """
        ).fetchall()
    ]
    restore_runs = [
        row_to_dict(row) for row in database.execute(
            """
            SELECT id, source_filename, safety_backup_filename, restored_by,
                restored_at, status, details
            FROM restore_runs ORDER BY restored_at DESC, id DESC LIMIT 10
            """
        ).fetchall()
    ]
    return jsonify({
        "station": "Morupule B Power Station",
        "checked_at": datetime.now().isoformat(timespec="seconds"),
        "integrity": integrity,
        "foreign_key_issues": len(foreign_key_issues),
        "database_bytes": database_path.stat().st_size if database_path.exists() else 0,
        "upload_bytes": sum(path.stat().st_size for path in upload_files),
        "upload_files": len(upload_files),
        "counts": row_to_dict(counts),
        "kks_import_runs": import_runs,
        "restore_runs": restore_runs,
    })


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def create_retained_backup() -> dict:
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    filename = f"morupule-b-sipam-backup-{timestamp}-{uuid.uuid4().hex[:8]}.zip"
    backup_path = Path(app.config["BACKUP_FOLDER"]) / filename
    temporary_directory = Path(tempfile.mkdtemp(prefix="sipam-backup-"))
    snapshot_path = temporary_directory / "morupule_sipam.db"
    try:
        destination = sqlite3.connect(snapshot_path)
        try:
            get_db().backup(destination)
        finally:
            destination.close()
        database_hash = file_sha256(snapshot_path)
        upload_path = Path(app.config["UPLOAD_FOLDER"])
        upload_files = [path for path in upload_path.rglob("*") if path.is_file()]
        attachment_manifest = [
            {
                "path": path.relative_to(upload_path).as_posix(),
                "bytes": path.stat().st_size,
                "sha256": file_sha256(path),
            }
            for path in upload_files
        ]
        status = system_status().get_json()
        manifest = {
            **status,
            "backup_format": 2,
            "backup_created_by": g.current_user["full_name"],
            "backup_created_at": datetime.now().isoformat(timespec="seconds"),
            "database_sha256": database_hash,
            "attachments": attachment_manifest,
        }
        with zipfile.ZipFile(backup_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            archive.write(snapshot_path, "database/morupule_sipam.db")
            archive.writestr("manifest.json", json.dumps(manifest, indent=2, ensure_ascii=True))
            for path in upload_files:
                archive.write(path, Path("uploads") / path.relative_to(upload_path))
        archive_hash = file_sha256(backup_path)
        cursor = get_db().execute(
            """
            INSERT INTO backup_runs (
                filename, created_by, created_at, database_bytes,
                upload_files, upload_bytes, archive_bytes, sha256, integrity
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'not_verified')
            """,
            (
                filename, g.current_user["full_name"], manifest["backup_created_at"],
                snapshot_path.stat().st_size, len(upload_files),
                sum(item["bytes"] for item in attachment_manifest),
                backup_path.stat().st_size, archive_hash,
            ),
        )
        get_db().commit()
        row = get_db().execute("SELECT * FROM backup_runs WHERE id = ?", (cursor.lastrowid,)).fetchone()
        return row_to_dict(row)
    finally:
        shutil.rmtree(temporary_directory, ignore_errors=True)


def verify_backup_file(path: Path, expected_sha256: str | None = None) -> dict:
    archive_hash = file_sha256(path)
    errors: list[str] = []
    if expected_sha256 and archive_hash != expected_sha256:
        errors.append("Archive SHA-256 does not match the retained backup record")
    with zipfile.ZipFile(path) as archive:
        names = archive.namelist()
        unsafe = [name for name in names if Path(name).is_absolute() or ".." in Path(name).parts]
        if unsafe:
            errors.append("Archive contains unsafe paths")
        if "manifest.json" not in names or "database/morupule_sipam.db" not in names:
            errors.append("Archive is missing the manifest or database snapshot")
            return {"valid": False, "errors": errors, "sha256": archive_hash}
        manifest = json.loads(archive.read("manifest.json"))
        database_bytes = archive.read("database/morupule_sipam.db")
        database_hash = hashlib.sha256(database_bytes).hexdigest()
        if database_hash != manifest.get("database_sha256"):
            errors.append("Database snapshot hash does not match the manifest")
        temporary_directory = Path(tempfile.mkdtemp(prefix="sipam-verify-"))
        snapshot_path = temporary_directory / "verify.db"
        try:
            snapshot_path.write_bytes(database_bytes)
            connection = sqlite3.connect(snapshot_path)
            try:
                integrity = connection.execute("PRAGMA integrity_check").fetchone()[0]
                foreign_key_issues = len(connection.execute("PRAGMA foreign_key_check").fetchall())
                table_names = {
                    row[0] for row in connection.execute(
                        "SELECT name FROM sqlite_master WHERE type = 'table'"
                    ).fetchall()
                }
            finally:
                connection.close()
        finally:
            shutil.rmtree(temporary_directory, ignore_errors=True)
        if integrity != "ok":
            errors.append(f"Database integrity check returned {integrity}")
        if foreign_key_issues:
            errors.append(f"Database contains {foreign_key_issues} foreign-key issues")
        required_tables = {
            "assets", "event_entries", "work_requests", "work_orders", "users",
            "audit_logs", "backup_runs", "restore_runs",
        }
        missing_tables = sorted(required_tables - table_names)
        if manifest.get("backup_format") != 2:
            errors.append("Backup format is not supported for controlled restore")
        if missing_tables:
            errors.append(f"Database is missing required tables: {', '.join(missing_tables)}")
        for attachment in manifest.get("attachments", []):
            archive_name = f"uploads/{attachment['path']}"
            if archive_name not in names:
                errors.append(f"Missing attachment: {attachment['path']}")
                continue
            if hashlib.sha256(archive.read(archive_name)).hexdigest() != attachment.get("sha256"):
                errors.append(f"Attachment hash mismatch: {attachment['path']}")
    return {
        "valid": not errors, "errors": errors, "sha256": archive_hash,
        "integrity": integrity, "foreign_key_issues": foreign_key_issues,
        "manifest": manifest,
    }


@app.get("/api/system/backups")
@roles_required("System Administrator")
def list_system_backups():
    rows = get_db().execute(
        "SELECT * FROM backup_runs ORDER BY created_at DESC, id DESC"
    ).fetchall()
    return jsonify([row_to_dict(row) for row in rows])


@app.get("/api/system/backup")
@roles_required("System Administrator")
def download_system_backup():
    backup = create_retained_backup()
    path = Path(app.config["BACKUP_FOLDER"]) / backup["filename"]
    return send_file(path, as_attachment=True, download_name=path.name, mimetype="application/zip")


@app.get("/api/system/backups/<int:backup_id>/download")
@roles_required("System Administrator")
def download_retained_backup(backup_id: int):
    row = get_db().execute(
        "SELECT * FROM backup_runs WHERE id = ? AND status = 'available'", (backup_id,)
    ).fetchone()
    if row is None:
        abort(404)
    path = Path(app.config["BACKUP_FOLDER"]) / row["filename"]
    if not path.is_file():
        return jsonify({"error": "Retained backup file is missing"}), 410
    return send_file(path, as_attachment=True, download_name=path.name, mimetype="application/zip")


@app.post("/api/system/backups/<int:backup_id>/verify")
@roles_required("System Administrator")
def verify_retained_backup(backup_id: int):
    row = get_db().execute(
        "SELECT * FROM backup_runs WHERE id = ? AND status = 'available'", (backup_id,)
    ).fetchone()
    if row is None:
        abort(404)
    path = Path(app.config["BACKUP_FOLDER"]) / row["filename"]
    if not path.is_file():
        return jsonify({"error": "Retained backup file is missing"}), 410
    result = verify_backup_file(path, row["sha256"])
    verified_at = datetime.now().isoformat(timespec="seconds")
    get_db().execute(
        "UPDATE backup_runs SET integrity = ?, last_verified_at = ? WHERE id = ?",
        ("verified" if result["valid"] else "failed", verified_at, backup_id),
    )
    get_db().commit()
    return jsonify({**result, "backup_id": backup_id, "verified_at": verified_at}), (200 if result["valid"] else 409)


@app.post("/api/system/backups/<int:backup_id>/restore")
@roles_required("System Administrator")
def restore_retained_backup(backup_id: int):
    payload = request.get_json(silent=True) or {}
    if str(payload.get("confirmation") or "").strip() != "RESTORE MORUPULE B SIPAM":
        return jsonify({
            "error": "Type RESTORE MORUPULE B SIPAM to authorize recovery"
        }), 400
    database = get_db()
    source_row = database.execute(
        "SELECT * FROM backup_runs WHERE id = ? AND status = 'available'", (backup_id,)
    ).fetchone()
    if source_row is None:
        abort(404)
    source_backup = row_to_dict(source_row)
    backup_folder = Path(app.config["BACKUP_FOLDER"]).resolve()
    source_path = (backup_folder / source_backup["filename"]).resolve()
    if source_path.parent != backup_folder or not source_path.is_file():
        return jsonify({"error": "Recovery point file is unavailable"}), 410
    verification = verify_backup_file(source_path, source_backup["sha256"])
    if not verification["valid"]:
        return jsonify({"error": "Recovery point verification failed", **verification}), 409

    safety_backup = create_retained_backup()
    temporary_directory = Path(tempfile.mkdtemp(prefix="sipam-restore-"))
    prepared_database = temporary_directory / "restored.db"
    prepared_uploads = temporary_directory / "uploads-new"
    old_uploads = temporary_directory / "uploads-old"
    prepared_uploads.mkdir()
    try:
        with zipfile.ZipFile(source_path) as archive:
            prepared_database.write_bytes(archive.read("database/morupule_sipam.db"))
            for info in archive.infolist():
                if info.is_dir() or not info.filename.startswith("uploads/"):
                    continue
                relative = Path(info.filename).relative_to("uploads")
                target = (prepared_uploads / relative).resolve()
                if prepared_uploads.resolve() not in target.parents:
                    raise ValueError("Recovery archive contains an invalid attachment path")
                target.parent.mkdir(parents=True, exist_ok=True)
                with archive.open(info) as source, target.open("wb") as destination:
                    shutil.copyfileobj(source, destination)

        upload_folder = Path(app.config["UPLOAD_FOLDER"])
        if upload_folder.exists():
            shutil.move(str(upload_folder), str(old_uploads))
        shutil.move(str(prepared_uploads), str(upload_folder))

        database_path = Path(app.config["DATABASE"])
        replacement_path = database_path.with_suffix(database_path.suffix + ".restore")
        shutil.copy2(prepared_database, replacement_path)
        active_connection = g.pop("db", None)
        if active_connection is not None:
            active_connection.close()
        try:
            os.replace(replacement_path, database_path)
        except Exception:
            shutil.rmtree(upload_folder, ignore_errors=True)
            if old_uploads.exists():
                shutil.move(str(old_uploads), str(upload_folder))
            raise

        restored_database = get_db()
        for retained in (source_backup, safety_backup):
            restored_database.execute(
                """
                INSERT OR IGNORE INTO backup_runs (
                    filename, created_by, created_at, database_bytes, upload_files,
                    upload_bytes, archive_bytes, sha256, integrity,
                    last_verified_at, status
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'available')
                """,
                (
                    retained["filename"], retained["created_by"], retained["created_at"],
                    retained["database_bytes"], retained["upload_files"],
                    retained["upload_bytes"], retained["archive_bytes"],
                    retained["sha256"], retained["integrity"],
                    retained.get("last_verified_at"),
                ),
            )
        restored_at = datetime.now().isoformat(timespec="seconds")
        restored_database.execute(
            """
            INSERT INTO restore_runs (
                source_filename, safety_backup_filename, restored_by,
                restored_at, status, details
            ) VALUES (?, ?, ?, ?, 'completed', ?)
            """,
            (
                source_backup["filename"], safety_backup["filename"],
                g.current_user["full_name"], restored_at,
                "Database and uploaded attachments restored after full verification",
            ),
        )
        restored_database.commit()
        return jsonify({
            "status": "restored", "restored_at": restored_at,
            "source_filename": source_backup["filename"],
            "safety_backup_filename": safety_backup["filename"],
            "integrity": verification["integrity"],
            "foreign_key_issues": verification["foreign_key_issues"],
        })
    finally:
        shutil.rmtree(temporary_directory, ignore_errors=True)


@app.delete("/api/system/backups/<int:backup_id>")
@roles_required("System Administrator")
def delete_retained_backup(backup_id: int):
    row = get_db().execute(
        "SELECT * FROM backup_runs WHERE id = ? AND status = 'available'", (backup_id,)
    ).fetchone()
    if row is None:
        abort(404)
    backup_folder = Path(app.config["BACKUP_FOLDER"]).resolve()
    path = (backup_folder / row["filename"]).resolve()
    if path.parent != backup_folder:
        return jsonify({"error": "Backup path is invalid"}), 409
    path.unlink(missing_ok=True)
    get_db().execute(
        "UPDATE backup_runs SET status = 'deleted' WHERE id = ?", (backup_id,)
    )
    get_db().commit()
    return jsonify({"status": "deleted", "backup_id": backup_id})


@app.get("/api/kks-imports")
@roles_required("System Administrator")
def list_kks_imports():
    rows = get_db().execute(
        """
        SELECT id, original_name, source_rows, unique_assets, duplicate_rows,
            blank_kks_rows, inferred_parents, new_assets, matched_assets,
            status, validated_by, validated_at, imported_by, imported_at,
            error_message
        FROM kks_staged_imports
        ORDER BY validated_at DESC, id DESC
        LIMIT 25
        """
    ).fetchall()
    return jsonify([row_to_dict(row) for row in rows])


@app.post("/api/kks-imports/validate")
@roles_required("System Administrator")
def validate_kks_import():
    from import_kks import add_hierarchy_parents, read_workbook

    uploaded = request.files.get("file")
    if uploaded is None or not uploaded.filename:
        return jsonify({"error": "Select a KKS workbook"}), 400
    original_name = secure_filename(uploaded.filename)
    if not original_name.lower().endswith(".xlsx"):
        return jsonify({"error": "KKS register must be an .xlsx workbook"}), 400
    stored_name = f"{uuid.uuid4().hex}.xlsx"
    target = Path(app.config["KKS_STAGING_FOLDER"]) / stored_name
    uploaded.save(target)
    try:
        records, issues, source_rows = read_workbook(target)
        source_unique = sum(
            record["source_kind"] == "kks_workbook"
            for record in records.values()
        )
        source_codes = set(records)
        existing_codes = {
            row["kks_code"] for row in get_db().execute(
                "SELECT kks_code FROM assets WHERE is_reference = 0"
            ).fetchall()
        }
        inferred_count = add_hierarchy_parents(records)
        duplicate_rows = sum(
            issue["issue_type"] == "duplicate_kks" for issue in issues
        )
        blank_rows = sum(
            issue["issue_type"] == "blank_kks" for issue in issues
        )
        cursor = get_db().execute(
            """
            INSERT INTO kks_staged_imports (
                original_name, stored_name, source_rows, unique_assets,
                duplicate_rows, blank_kks_rows, inferred_parents,
                new_assets, matched_assets, status, validated_by, validated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'validated', ?, ?)
            """,
            (
                original_name,
                stored_name,
                source_rows,
                source_unique,
                duplicate_rows,
                blank_rows,
                inferred_count,
                len(source_codes - existing_codes),
                len(source_codes & existing_codes),
                g.current_user["full_name"],
                datetime.now().isoformat(timespec="seconds"),
            ),
        )
        get_db().commit()
    except Exception as error:
        target.unlink(missing_ok=True)
        return jsonify({"error": str(error)}), 400
    row = get_db().execute(
        "SELECT * FROM kks_staged_imports WHERE id = ?",
        (cursor.lastrowid,),
    ).fetchone()
    return jsonify(row_to_dict(row)), 201


@app.post("/api/kks-imports/<int:staged_id>/commit")
@roles_required("System Administrator")
def commit_kks_import(staged_id: int):
    from import_kks import add_hierarchy_parents, import_records, read_workbook

    database = get_db()
    staged = database.execute(
        "SELECT * FROM kks_staged_imports WHERE id = ?",
        (staged_id,),
    ).fetchone()
    if staged is None:
        abort(404)
    if staged["status"] != "validated":
        return jsonify({"error": "Only a validated workbook can be imported"}), 409
    source_path = Path(app.config["KKS_STAGING_FOLDER"]) / staged["stored_name"]
    if not source_path.exists():
        return jsonify({"error": "Staged workbook file is missing"}), 409
    try:
        records, issues, source_rows = read_workbook(source_path)
        inferred_count = add_hierarchy_parents(records)
        import_records(
            database,
            source_path,
            records,
            issues,
            source_rows,
            inferred_count,
        )
        database.execute(
            """
            UPDATE kks_staged_imports
            SET status = 'imported', imported_by = ?, imported_at = ?
            WHERE id = ?
            """,
            (
                g.current_user["full_name"],
                datetime.now().isoformat(timespec="seconds"),
                staged_id,
            ),
        )
        database.commit()
    except Exception as error:
        database.rollback()
        database.execute(
            """
            UPDATE kks_staged_imports
            SET status = 'failed', error_message = ?
            WHERE id = ?
            """,
            (str(error)[:1000], staged_id),
        )
        database.commit()
        return jsonify({"error": str(error)}), 500
    return jsonify({
        "status": "imported",
        "staged_id": staged_id,
        "source_rows": source_rows,
        "unique_assets": staged["unique_assets"],
        "duplicate_rows": staged["duplicate_rows"],
        "inferred_parents": inferred_count,
    })


def append_infobox_search(
    filters: list[str],
    parameters: list[object],
    query: str,
) -> None:
    if not query:
        return
    filters.append(
        """
        LOWER(
            COALESCE(i.title, '') || ' ' ||
            COALESCE(i.description, '') || ' ' ||
            COALESCE((
                SELECT search_group.name
                FROM responsibility_groups search_group
                WHERE search_group.id = i.responsible_group_id
            ), '') || ' ' ||
            COALESCE((
                SELECT search_user.full_name
                FROM users search_user
                WHERE search_user.id = i.claimed_by
            ), '') || ' ' ||
            COALESCE(CASE i.source_type
                WHEN 'work_request' THEN (
                    SELECT wr.request_no FROM work_requests wr WHERE wr.id = i.source_id
                )
                WHEN 'work_order' THEN (
                    SELECT wo.order_no FROM work_orders wo WHERE wo.id = i.source_id
                )
                WHEN 'preventive_task' THEN (
                    SELECT pt.task_no FROM preventive_tasks pt WHERE pt.id = i.source_id
                )
                WHEN 'permit' THEN (
                    SELECT p.permit_no FROM safety_permits p WHERE p.id = i.source_id
                )
                WHEN 'event' THEN (
                    SELECT e.entry_no FROM event_entries e WHERE e.id = i.source_id
                )
                WHEN 'shift_handover' THEN (
                    SELECT sh.handover_no FROM shift_handovers sh WHERE sh.id = i.source_id
                )
            END, '')
        ) LIKE ?
        """
    )
    parameters.append(f"%{query.lower()}%")


@app.get("/api/infobox")
def list_infobox():
    user_id = g.current_user["id"]
    database = get_db()
    sync_infobox(database)
    state = request.args.get("state", "active").strip().lower()
    scope = request.args.get("scope", "my").strip().lower()
    is_administrator = g.current_user["role_name"] == "System Administrator"
    filters: list[str] = []
    parameters: list[object] = []
    if scope != "team" or not is_administrator:
        filters.append(
            "EXISTS (SELECT 1 FROM inbox_recipients r "
            "WHERE r.inbox_item_id = i.id AND r.user_id = ?)"
        )
        parameters.append(user_id)
    if state == "completed":
        filters.append("i.status = 'completed'")
    elif scope == "team":
        filters.append("i.status IN ('open', 'claimed')")
    else:
        filters.append("(i.status = 'open' OR (i.status = 'claimed' AND i.claimed_by = ?))")
        parameters.append(user_id)
    priority = request.args.get("priority", "").strip().lower()
    source_type = request.args.get("source_type", "").strip().lower()
    timing = request.args.get("timing", "").strip().lower()
    query = request.args.get("q", "").strip()
    group_id = request.args.get("group_id", type=int)
    if priority in {"high", "medium", "normal"}:
        filters.append("i.priority = ?")
        parameters.append(priority)
    if source_type in {"work_request", "work_order", "preventive_task", "permit", "event", "shift_handover"}:
        filters.append("i.source_type = ?")
        parameters.append(source_type)
    if group_id:
        filters.append("i.responsible_group_id = ?")
        parameters.append(group_id)
    if timing == "overdue":
        filters.append("i.due_at IS NOT NULL AND date(i.due_at) < date('now', 'localtime')")
    elif timing == "due_today":
        filters.append("i.due_at IS NOT NULL AND date(i.due_at) = date('now', 'localtime')")
    elif timing == "upcoming":
        filters.append("i.due_at IS NOT NULL AND date(i.due_at) > date('now', 'localtime')")
    elif timing == "no_target":
        filters.append("i.due_at IS NULL")
    append_infobox_search(filters, parameters, query)
    rows = database.execute(
        f"""
        SELECT
            i.*, g.name AS responsible_group_name,
            u.full_name AS claimed_by_name,
            CASE i.source_type
                WHEN 'work_request' THEN 'corrective'
                WHEN 'work_order' THEN 'corrective'
                WHEN 'preventive_task' THEN 'preventive'
                WHEN 'permit' THEN 'permits'
                WHEN 'event' THEN 'events'
                WHEN 'shift_handover' THEN 'handovers'
            END AS target_view,
            CASE i.source_type
                WHEN 'work_request' THEN i.source_id
                WHEN 'work_order' THEN (
                    SELECT wo.work_request_id
                    FROM work_orders wo
                    WHERE wo.id = i.source_id
                )
                WHEN 'preventive_task' THEN (
                    SELECT pt.recurrent_task_id
                    FROM preventive_tasks pt
                    WHERE pt.id = i.source_id
                )
                WHEN 'permit' THEN i.source_id
                WHEN 'event' THEN i.source_id
                WHEN 'shift_handover' THEN i.source_id
            END AS target_id,
            CASE
                WHEN i.status = 'completed' THEN 'completed'
                WHEN i.due_at IS NULL THEN 'no_target'
                WHEN date(i.due_at) < date('now', 'localtime') THEN 'overdue'
                WHEN date(i.due_at) = date('now', 'localtime') THEN 'due_today'
                ELSE 'upcoming'
            END AS due_state,
            MAX(0, ROUND((julianday('now', 'localtime') - julianday(i.created_at)) * 24, 1)) AS age_hours
        FROM inbox_items i
        JOIN responsibility_groups g ON g.id = i.responsible_group_id
        LEFT JOIN users u ON u.id = i.claimed_by
        WHERE {' AND '.join(filters)}
        ORDER BY
            CASE WHEN i.status = 'completed' THEN i.completed_at END DESC,
            CASE i.priority WHEN 'high' THEN 1 WHEN 'medium' THEN 2 ELSE 3 END,
            CASE WHEN i.due_at IS NULL THEN 1 ELSE 0 END,
            i.due_at,
            i.created_at
        """,
        parameters,
    ).fetchall()
    return jsonify([row_to_dict(row) for row in rows])


@app.get("/api/infobox/summary")
def infobox_summary():
    user_id = g.current_user["id"]
    database = get_db()
    sync_infobox(database)
    scope = request.args.get("scope", "my").strip().lower()
    is_administrator = g.current_user["role_name"] == "System Administrator"
    visibility_filters: list[str] = []
    visibility_parameters: list[object] = []
    if scope != "team" or not is_administrator:
        visibility_filters.append(
            "EXISTS (SELECT 1 FROM inbox_recipients r "
            "WHERE r.inbox_item_id = i.id AND r.user_id = ?)"
        )
        visibility_parameters.append(user_id)
    active_filters = [*visibility_filters]
    active_parameters = [*visibility_parameters]
    if scope == "team":
        active_filters.append("i.status IN ('open', 'claimed')")
    else:
        active_filters.append(
            "(i.status = 'open' OR (i.status = 'claimed' AND i.claimed_by = ?))"
        )
        active_parameters.append(user_id)
    priority = request.args.get("priority", "").strip().lower()
    source_type = request.args.get("source_type", "").strip().lower()
    timing = request.args.get("timing", "").strip().lower()
    query = request.args.get("q", "").strip()
    group_id = request.args.get("group_id", type=int)
    common_filters: list[str] = []
    common_parameters: list[object] = []
    if priority in {"high", "medium", "normal"}:
        common_filters.append("i.priority = ?")
        common_parameters.append(priority)
    if source_type in {"work_request", "work_order", "preventive_task", "permit", "event", "shift_handover"}:
        common_filters.append("i.source_type = ?")
        common_parameters.append(source_type)
    if group_id:
        common_filters.append("i.responsible_group_id = ?")
        common_parameters.append(group_id)
    if timing == "overdue":
        common_filters.append("i.due_at IS NOT NULL AND date(i.due_at) < date('now', 'localtime')")
    elif timing == "due_today":
        common_filters.append("i.due_at IS NOT NULL AND date(i.due_at) = date('now', 'localtime')")
    elif timing == "upcoming":
        common_filters.append("i.due_at IS NOT NULL AND date(i.due_at) > date('now', 'localtime')")
    elif timing == "no_target":
        common_filters.append("i.due_at IS NULL")
    append_infobox_search(common_filters, common_parameters, query)
    active_filters.extend(common_filters)
    active_parameters.extend(common_parameters)
    row = database.execute(
        f"""
        SELECT
            COUNT(*) AS total,
            SUM(CASE WHEN i.priority = 'high' THEN 1 ELSE 0 END) AS high_priority,
            SUM(CASE WHEN i.status = 'claimed' THEN 1 ELSE 0 END) AS claimed,
            SUM(CASE WHEN i.due_at IS NOT NULL AND date(i.due_at) < date('now', 'localtime') THEN 1 ELSE 0 END) AS overdue,
            SUM(CASE WHEN i.escalation_level > 0 THEN 1 ELSE 0 END) AS escalated,
            SUM(CASE WHEN i.escalation_level = 3 THEN 1 ELSE 0 END) AS critical_escalations
        FROM inbox_items i
        WHERE {' AND '.join(active_filters)}
        """,
        active_parameters,
    ).fetchone()
    completed_filters = [
        *visibility_filters, "i.status = 'completed'", *common_filters,
    ]
    completed = database.execute(
        f"SELECT COUNT(*) FROM inbox_items i WHERE {' AND '.join(completed_filters)}",
        [*visibility_parameters, *common_parameters],
    ).fetchone()[0]
    summary = row_to_dict(row)
    summary["completed"] = completed
    return jsonify(summary)


@app.get("/api/infobox/workload")
def infobox_workload():
    user_id = g.current_user["id"]
    database = get_db()
    sync_infobox(database)
    is_administrator = g.current_user["role_name"] == "System Administrator"
    visibility = ""
    parameters: list[object] = []
    if not is_administrator:
        visibility = """
            AND EXISTS (
                SELECT 1 FROM inbox_recipients r
                WHERE r.inbox_item_id = i.id AND r.user_id = ?
            )
        """
        parameters.append(user_id)
    rows = database.execute(
        f"""
        SELECT g.id, g.code, g.name,
            SUM(CASE WHEN i.status IN ('open', 'claimed') THEN 1 ELSE 0 END) AS active,
            SUM(CASE WHEN i.status = 'open' THEN 1 ELSE 0 END) AS available,
            SUM(CASE WHEN i.status = 'claimed' THEN 1 ELSE 0 END) AS claimed,
            SUM(CASE
                WHEN i.status IN ('open', 'claimed')
                 AND i.due_at IS NOT NULL
                 AND date(i.due_at) < date('now', 'localtime')
                THEN 1 ELSE 0
            END) AS overdue,
            SUM(CASE WHEN i.status = 'completed' THEN 1 ELSE 0 END) AS completed
        FROM responsibility_groups g
        JOIN inbox_items i ON i.responsible_group_id = g.id
        WHERE 1 = 1 {visibility}
        GROUP BY g.id, g.code, g.name
        HAVING active > 0 OR completed > 0
        ORDER BY active DESC, g.name
        """,
        parameters,
    ).fetchall()
    return jsonify([row_to_dict(row) for row in rows])


@app.get("/api/infobox/history.csv")
def export_infobox_history():
    user_id = g.current_user["id"]
    database = get_db()
    sync_infobox(database)
    scope = request.args.get("scope", "my").strip().lower()
    is_administrator = g.current_user["role_name"] == "System Administrator"
    filters: list[str] = []
    parameters: list[object] = []
    if scope != "team" or not is_administrator:
        filters.append(
            "EXISTS (SELECT 1 FROM inbox_recipients r "
            "WHERE r.inbox_item_id = i.id AND r.user_id = ?)"
        )
        parameters.append(user_id)
    state = request.args.get("state", "active").strip().lower()
    if state == "completed":
        filters.append("i.status = 'completed'")
    elif state == "active":
        if scope == "team":
            filters.append("i.status IN ('open', 'claimed')")
        else:
            filters.append("(i.status = 'open' OR (i.status = 'claimed' AND i.claimed_by = ?))")
            parameters.append(user_id)
    priority = request.args.get("priority", "").strip().lower()
    source_type = request.args.get("source_type", "").strip().lower()
    timing = request.args.get("timing", "").strip().lower()
    query = request.args.get("q", "").strip()
    group_id = request.args.get("group_id", type=int)
    if priority in {"high", "medium", "normal"}:
        filters.append("i.priority = ?")
        parameters.append(priority)
    if source_type in {"work_request", "work_order", "preventive_task", "permit", "event", "shift_handover"}:
        filters.append("i.source_type = ?")
        parameters.append(source_type)
    if group_id:
        filters.append("i.responsible_group_id = ?")
        parameters.append(group_id)
    if timing == "overdue":
        filters.append("i.due_at IS NOT NULL AND date(i.due_at) < date('now', 'localtime')")
    elif timing == "due_today":
        filters.append("i.due_at IS NOT NULL AND date(i.due_at) = date('now', 'localtime')")
    elif timing == "upcoming":
        filters.append("i.due_at IS NOT NULL AND date(i.due_at) > date('now', 'localtime')")
    elif timing == "no_target":
        filters.append("i.due_at IS NULL")
    append_infobox_search(filters, parameters, query)
    rows = database.execute(
        f"""
        SELECT
            i.created_at AS assigned_at,
            i.claimed_at,
            i.completed_at,
            i.status,
            i.priority,
            i.base_priority,
            i.escalation_level,
            i.escalated_at,
            i.source_type,
            CASE i.source_type
                WHEN 'work_request' THEN (
                    SELECT wr.request_no FROM work_requests wr WHERE wr.id = i.source_id
                )
                WHEN 'work_order' THEN (
                    SELECT wo.order_no FROM work_orders wo WHERE wo.id = i.source_id
                )
                WHEN 'preventive_task' THEN (
                    SELECT pt.task_no FROM preventive_tasks pt WHERE pt.id = i.source_id
                )
                WHEN 'permit' THEN (
                    SELECT p.permit_no FROM safety_permits p WHERE p.id = i.source_id
                )
                WHEN 'event' THEN (
                    SELECT e.entry_no FROM event_entries e WHERE e.id = i.source_id
                )
                WHEN 'shift_handover' THEN (
                    SELECT sh.handover_no FROM shift_handovers sh WHERE sh.id = i.source_id
                )
            END AS record_no,
            i.title,
            i.description,
            g.name AS responsibility_group,
            COALESCE(
                u.full_name,
                (
                    SELECT history_user.full_name
                    FROM inbox_history h
                    JOIN users history_user ON history_user.id = h.user_id
                    WHERE h.inbox_item_id = i.id AND h.action = 'claimed'
                    ORDER BY h.id DESC LIMIT 1
                ),
                ''
            ) AS handled_by,
            i.due_at,
            CASE
                WHEN i.status = 'completed' THEN 'completed'
                WHEN i.due_at IS NULL THEN 'no_target'
                WHEN date(i.due_at) < date('now', 'localtime') THEN 'overdue'
                WHEN date(i.due_at) = date('now', 'localtime') THEN 'due_today'
                ELSE 'upcoming'
            END AS due_status,
            MAX(0, ROUND((julianday('now', 'localtime') - julianday(i.created_at)) * 24, 1)) AS age_hours,
            CASE
                WHEN i.completed_at IS NOT NULL
                THEN ROUND((julianday(i.completed_at) - julianday(i.created_at)) * 24, 2)
            END AS handling_hours
        FROM inbox_items i
        JOIN responsibility_groups g ON g.id = i.responsible_group_id
        LEFT JOIN users u ON u.id = i.claimed_by
        WHERE {' AND '.join(filters)}
        ORDER BY COALESCE(i.completed_at, i.updated_at) DESC, i.id DESC
        """,
        parameters,
    ).fetchall()
    output = io.StringIO()
    writer = csv.writer(output, lineterminator="\n")
    writer.writerow([
        "Assigned At", "Claimed At", "Completed At", "Status", "Priority",
        "Base Priority", "Escalation Level", "Escalated At",
        "Source Type", "Record Number", "Required Action", "Description",
        "Responsibility Group", "Handled By", "Due At", "Due Status",
        "Age Hours", "Handling Hours",
    ])
    writer.writerows([tuple(row) for row in rows])
    filename = f"morupule-b-infobox-{state}-{date.today().isoformat()}.csv"
    return Response(
        "\ufeff" + output.getvalue(),
        mimetype="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@app.get("/api/infobox/<int:item_id>/history")
def infobox_item_history(item_id: int):
    user_id = g.current_user["id"]
    database = get_db()
    recipient = database.execute(
        """
        SELECT 1 FROM inbox_recipients
        WHERE inbox_item_id = ? AND user_id = ?
        """,
        (item_id, user_id),
    ).fetchone()
    if recipient is None and g.current_user["role_name"] != "System Administrator":
        return jsonify({"error": "Infobox item is not assigned to this user"}), 403
    rows = database.execute(
        """
        SELECT * FROM (
            SELECT h.id AS sort_id, h.action, h.details, h.created_at,
                u.full_name AS user_name, u.employee_no
            FROM inbox_history h
            LEFT JOIN users u ON u.id = h.user_id
            WHERE h.inbox_item_id = ?
            UNION ALL
            SELECT eh.id AS sort_id,
                CASE WHEN eh.new_level = 0 THEN 'reset' ELSE 'escalated' END AS action,
                eh.reason || ' (' || eh.previous_level || ' to ' || eh.new_level || ')' AS details,
                eh.created_at, NULL AS user_name, NULL AS employee_no
            FROM inbox_escalation_history eh
            WHERE eh.inbox_item_id = ?
        ) ORDER BY created_at DESC, sort_id DESC
        """,
        (item_id, item_id),
    ).fetchall()
    return jsonify([row_to_dict(row) for row in rows])


@app.patch("/api/infobox/<int:item_id>/claim")
def claim_infobox_item(item_id: int):
    user_id = g.current_user["id"]
    database = get_db()
    recipient = database.execute(
        """
        SELECT i.status, i.claimed_by
        FROM inbox_items i
        JOIN inbox_recipients r ON r.inbox_item_id = i.id
        WHERE i.id = ? AND r.user_id = ?
        """,
        (item_id, user_id),
    ).fetchone()
    if recipient is None:
        return jsonify({"error": "Infobox item is not assigned to this user"}), 403
    if recipient["status"] != "open":
        return jsonify({"error": "Infobox item has already been taken"}), 409
    now = datetime.now().isoformat(timespec="minutes")
    cursor = database.execute(
        """
        UPDATE inbox_items
        SET status = 'claimed', claimed_by = ?, claimed_at = ?, updated_at = ?
        WHERE id = ? AND status = 'open'
        """,
        (user_id, now, now, item_id),
    )
    if cursor.rowcount == 0:
        return jsonify({"error": "Infobox item has already been taken"}), 409
    add_infobox_history(database, item_id, "claimed", "Responsibility accepted")
    database.commit()
    return jsonify({"status": "claimed", "item_id": item_id, "user_id": user_id})


@app.patch("/api/infobox/<int:item_id>/release")
def release_infobox_item(item_id: int):
    user_id = g.current_user["id"]
    database = get_db()
    cursor = database.execute(
        """
        UPDATE inbox_items
        SET status = 'open', claimed_by = NULL, claimed_at = NULL, updated_at = ?
        WHERE id = ? AND status = 'claimed' AND claimed_by = ?
        """,
        (datetime.now().isoformat(timespec="minutes"), item_id, user_id),
    )
    if cursor.rowcount == 0:
        return jsonify({"error": "Claimed item not found for this user"}), 409
    add_infobox_history(database, item_id, "released", "Returned to the responsibility group")
    database.commit()
    return jsonify({"status": "open", "item_id": item_id})


def get_event(event_id: int) -> dict:
    row = get_db().execute(
        """
        SELECT
            e.*, a.kks_code, a.description AS asset_description,
            l.name AS source_logbook_name
        FROM event_entries e
        JOIN logbooks l ON l.id = e.source_logbook_id
        LEFT JOIN assets a ON a.id = e.asset_id
        WHERE e.id = ?
        """,
        (event_id,),
    ).fetchone()
    if row is None:
        abort(404)
    return row_to_dict(row)


with app.app_context():
    init_db()


if __name__ == "__main__":
    app.run(
        host="127.0.0.1",
        port=int(os.environ.get("SIPAM_PORT", "5001")),
        debug=False,
        use_reloader=False,
    )
