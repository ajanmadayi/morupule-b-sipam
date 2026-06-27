import tempfile
import unittest
import json
import csv
import zipfile
import hashlib
from io import BytesIO
from pathlib import Path

from datetime import date, timedelta
from openpyxl import Workbook

from app import (
    add_interval, adjust_weekend, app, calculate_cmpt_priority,
    cmpt_response_target, get_db, init_db,
)


class SpulseTestCase(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        app.config.update(
            TESTING=True,
            DATABASE=Path(self.temp_dir.name) / "test.db",
            UPLOAD_FOLDER=Path(self.temp_dir.name) / "uploads",
            KKS_STAGING_FOLDER=Path(self.temp_dir.name) / "kks_staging",
            BACKUP_FOLDER=Path(self.temp_dir.name) / "backups",
        )
        with app.app_context():
            init_db()
        self.client = app.test_client()
        with self.client.session_transaction() as session:
            session["user_id"] = 7

    def tearDown(self):
        self.temp_dir.cleanup()

    def login_as(self, user_id):
        with self.client.session_transaction() as session:
            session["user_id"] = user_id

    def make_kks_workbook(self):
        workbook = Workbook()
        sheet = workbook.active
        sheet.title = "kks"
        sheet.append([
            "PLANT CODE", "SYSTEM CODE", "EQUIPMENT CODE", "COMPONENT CODE",
            "DESCRIPTION", "KKS code", "RESPONSIBLE AREA",
        ])
        sheet.append(["A0", "TST01", "", "", "Test system", "A0 TST01", "I&C"])
        sheet.append(["A0", "TST01", "001A", "", "Test equipment", "A0 TST01001A", "I&C"])
        sheet.append(["A0", "TST01", "001A", "-Q01", "Test component", "A0 TST01001A -Q01", "I&C"])
        sheet.append(["A0", "TST01", "001A", "-Q01", "Duplicate component", "A0 TST01001A -Q01", "I&C"])
        stream = BytesIO()
        workbook.save(stream)
        stream.seek(0)
        return stream

    def test_health_and_dashboard(self):
        health = self.client.get("/api/health")
        self.assertEqual(health.status_code, 200)
        self.assertEqual(health.get_json()["station"], "STEAG Energy Services")

        dashboard = self.client.get("/api/dashboard")
        self.assertEqual(dashboard.status_code, 200)
        self.assertGreaterEqual(dashboard.get_json()["active_assets"], 9)

    def test_report_summary_and_csv_export(self):
        summary = self.client.get(
            "/api/reports/summary?start=2026-06-01&end=2026-06-30"
        )
        self.assertEqual(summary.status_code, 200)
        report = summary.get_json()
        self.assertGreaterEqual(report["counts"]["events"], 3)
        self.assertGreaterEqual(report["counts"]["work_requests"], 2)
        self.assertTrue(report["daily"])
        self.assertTrue(report["areas"])
        self.assertIn("corrective_actual_hours", report["performance"])
        self.assertIn("preventive_actual_hours", report["performance"])
        self.assertIn("accepted_work", report["performance"])
        response_compliance = report["response_compliance"]
        self.assertEqual(
            response_compliance["targeted"],
            response_compliance["met"]
            + response_compliance["breached"]
            + response_compliance["pending"],
        )
        self.assertGreaterEqual(response_compliance["breached"], 1)
        self.assertIn("compliance_percent", response_compliance)
        self.assertIn("reliability", report)
        self.assertIn("mttr_hours", report["reliability"])
        self.assertIn("top_failure_assets", report["reliability"])
        maintenance_kpis = report["maintenance_kpis"]
        self.assertGreaterEqual(maintenance_kpis["pm_due"], 1)
        self.assertIn("pm_compliance_percent", maintenance_kpis)
        self.assertGreaterEqual(maintenance_kpis["corrective_backlog"], 1)
        self.assertIn("average_backlog_age_days", maintenance_kpis)

        export = self.client.get(
            "/api/reports/activity.csv?start=2026-06-01&end=2026-06-30"
        )
        self.assertEqual(export.status_code, 200)
        self.assertIn("text/csv", export.content_type)
        self.assertIn("attachment", export.headers["Content-Disposition"])
        csv_text = export.get_data(as_text=True)
        self.assertIn("Activity Date,Module,Record Number", csv_text)
        self.assertIn("Planned Hours,Actual Hours,Outcome / Remarks", csv_text)
        self.assertIn("EL-2026-0001", csv_text)

    def test_report_rejects_reversed_date_range(self):
        response = self.client.get(
            "/api/reports/summary?start=2026-06-30&end=2026-06-01"
        )
        self.assertEqual(response.status_code, 400)

    def test_printable_management_report_uses_selected_period(self):
        response = self.client.get(
            "/print/management-report?start=2026-06-01&end=2026-06-30"
        )
        self.assertEqual(response.status_code, 200)
        html = response.get_data(as_text=True)
        self.assertIn("Monthly Maintenance Performance Report", html)
        self.assertIn("01 Jun 2026 to 30 Jun 2026", html)
        self.assertIn("CMPT Response Compliance", html)
        self.assertIn("Response breached", html)
        self.assertIn("Equipment Reliability", html)
        self.assertIn("Highest-Impact Failure Assets", html)
        self.assertIn("Maintenance Performance KPIs", html)

    def test_attachment_upload_download_and_delete(self):
        uploaded = self.client.post(
            "/api/attachments/event/1",
            data={"file": (BytesIO(b"inspection evidence"), "evidence.txt")},
            content_type="multipart/form-data",
        )
        self.assertEqual(uploaded.status_code, 201)
        attachment_id = uploaded.get_json()["id"]

        detail = self.client.get("/api/events/1").get_json()
        self.assertEqual(detail["attachments"][0]["original_name"], "evidence.txt")

        download = self.client.get(f"/api/attachments/file/{attachment_id}")
        self.assertEqual(download.status_code, 200)
        self.assertEqual(download.data, b"inspection evidence")
        self.assertIn("attachment", download.headers["Content-Disposition"])
        download.close()

        deleted = self.client.delete(f"/api/attachments/{attachment_id}")
        self.assertEqual(deleted.status_code, 200)
        self.assertEqual(self.client.get("/api/events/1").get_json()["attachments"], [])

    def test_attachment_rejects_disallowed_extension(self):
        response = self.client.post(
            "/api/attachments/permit/1",
            data={"file": (BytesIO(b"binary"), "unsafe.exe")},
            content_type="multipart/form-data",
        )
        self.assertEqual(response.status_code, 400)

    def test_printable_workflow_documents(self):
        cases = [
            ("/print/event/1", "EL-2026-0001", "Event Log Record"),
            ("/print/corrective/1", "WR-2026-0001", "Corrective Maintenance"),
            ("/print/preventive/1", "RT-2026-0001", "Preventive Maintenance"),
            ("/print/preventive_task/1", "PM-2026-0001", "Preventive Maintenance Task Record"),
            ("/print/permit/1", "PTW-2026-0001", "Permit to Work"),
            ("/print/asset/8", "10ETF10AA217 MS01", "KKS Asset History Record"),
        ]
        for url, record_number, title in cases:
            with self.subTest(url=url):
                response = self.client.get(url)
                self.assertEqual(response.status_code, 200)
                page = response.get_data(as_text=True)
                self.assertIn(record_number, page)
                self.assertIn(title, page)
                self.assertIn("Print / Save PDF", page)

    def test_filtered_shift_handover_report(self):
        report = self.client.get(
            "/print/shift-handover",
            query_string={
                "start": "2026-06-09",
                "end": "2026-06-09",
                "state": "open",
                "logbook_ids": "1,2",
            },
        )
        self.assertEqual(report.status_code, 200)
        html = report.get_data(as_text=True)
        self.assertIn("Operations Shift Handover", html)
        self.assertIn("EL-2026-0001", html)
        self.assertIn("WR-2026-0001", html)
        self.assertIn("2026-06-09 to 2026-06-09", html)
        self.assertNotIn("EL-2026-0003", html)

    def test_formal_shift_handover_requires_separate_acceptance(self):
        self.login_as(1)
        created = self.client.post(
            "/api/shift-handovers",
            json={
                "shift_date": "2026-06-09",
                "shift_name": "Day shift",
                "summary": "Ash handling equipment status handed over.",
                "operational_notes": "Monitor dome valve feedback response.",
                "safety_notes": "No outstanding safety isolation.",
                "event_ids": [1, 3],
            },
        )
        self.assertEqual(created.status_code, 201)
        handover = created.get_json()
        self.assertEqual(handover["handover_no"], "SH-2026-0001")
        self.assertEqual(handover["status"], "draft")
        self.assertEqual(len(handover["events"]), 2)
        self.assertEqual(handover["events"][0]["state_at_handover"], "open")

        submitted = self.client.patch(
            f"/api/shift-handovers/{handover['id']}", json={"action": "submit"}
        )
        self.assertEqual(submitted.status_code, 200)
        self.assertEqual(submitted.get_json()["status"], "submitted")
        outgoing_queue = self.client.get(
            "/api/infobox?source_type=shift_handover"
        ).get_json()
        self.assertFalse(any(item["source_id"] == handover["id"] for item in outgoing_queue))
        self_acceptance = self.client.patch(
            f"/api/shift-handovers/{handover['id']}",
            json={"action": "accept", "acceptance_notes": "Received."},
        )
        self.assertEqual(self_acceptance.status_code, 409)

        self.login_as(2)
        incoming_queue = self.client.get(
            "/api/infobox?source_type=shift_handover"
        ).get_json()
        handover_item = next(
            item for item in incoming_queue if item["source_id"] == handover["id"]
        )
        self.assertEqual(handover_item["target_view"], "handovers")
        self.assertEqual(handover_item["action_code"], "accept_handover")
        missing_notes = self.client.patch(
            f"/api/shift-handovers/{handover['id']}", json={"action": "accept"}
        )
        self.assertEqual(missing_notes.status_code, 400)
        accepted = self.client.patch(
            f"/api/shift-handovers/{handover['id']}",
            json={
                "action": "accept",
                "acceptance_notes": "Plant status and open events received.",
            },
        )
        self.assertEqual(accepted.status_code, 200)
        self.assertEqual(accepted.get_json()["status"], "accepted")
        self.assertEqual(accepted.get_json()["incoming_name"], "Onalenna Modise")
        completed_queue = self.client.get(
            "/api/infobox?source_type=shift_handover&state=completed"
        ).get_json()
        self.assertTrue(any(item["source_id"] == handover["id"] for item in completed_queue))

        printable = self.client.get(f"/print/shift-handover/{handover['id']}")
        self.assertEqual(printable.status_code, 200)
        html = printable.get_data(as_text=True)
        self.assertIn("Formal Shift Handover", html)
        self.assertIn("SH-2026-0001", html)
        self.assertIn("EL-2026-0001", html)

    def test_print_document_requires_login(self):
        with self.client.session_transaction() as session:
            session.clear()
        response = self.client.get("/print/event/1")
        self.assertEqual(response.status_code, 302)
        self.assertIn("/login", response.headers["Location"])

    def test_system_status_and_full_backup(self):
        self.client.post(
            "/api/attachments/event/1",
            data={"file": (BytesIO(b"backup evidence"), "backup-evidence.txt")},
            content_type="multipart/form-data",
        )
        status = self.client.get("/api/system/status")
        self.assertEqual(status.status_code, 200)
        system = status.get_json()
        self.assertEqual(system["integrity"], "ok")
        self.assertEqual(system["foreign_key_issues"], 0)
        self.assertGreaterEqual(system["counts"]["assets"], 9)
        self.assertEqual(system["upload_files"], 1)

        backup = self.client.get("/api/system/backup", buffered=True)
        self.assertEqual(backup.status_code, 200)
        self.assertIn("application/zip", backup.content_type)
        self.assertIn("attachment", backup.headers["Content-Disposition"])
        with zipfile.ZipFile(BytesIO(backup.data)) as archive:
            names = archive.namelist()
            self.assertIn("database/morupule_sipam.db", names)
            self.assertIn("manifest.json", names)
            self.assertTrue(any(name.startswith("uploads/") for name in names))
            manifest = json.loads(archive.read("manifest.json"))
            self.assertEqual(manifest["integrity"], "ok")
            self.assertEqual(manifest["backup_created_by"], "S-PULSE Administrator")
        backup.close()
        backups = self.client.get("/api/system/backups").get_json()
        self.assertEqual(len(backups), 1)
        retained = backups[0]
        self.assertEqual(len(retained["sha256"]), 64)
        self.assertEqual(retained["status"], "available")

        verified = self.client.post(
            f"/api/system/backups/{retained['id']}/verify"
        )
        self.assertEqual(verified.status_code, 200)
        verification = verified.get_json()
        self.assertTrue(verification["valid"])
        self.assertEqual(verification["integrity"], "ok")
        self.assertEqual(verification["foreign_key_issues"], 0)
        self.assertFalse(verification["errors"])

        retained_download = self.client.get(
            f"/api/system/backups/{retained['id']}/download", buffered=True
        )
        self.assertEqual(retained_download.status_code, 200)
        self.assertEqual(
            hashlib.sha256(retained_download.data).hexdigest(), retained["sha256"]
        )
        retained_download.close()

        deleted = self.client.delete(f"/api/system/backups/{retained['id']}")
        self.assertEqual(deleted.status_code, 200)
        self.assertEqual(
            self.client.get(f"/api/system/backups/{retained['id']}/download").status_code,
            404,
        )

    def test_non_administrator_cannot_access_system_status(self):
        self.login_as(1)
        self.assertEqual(self.client.get("/api/system/status").status_code, 403)
        self.assertEqual(self.client.get("/api/system/backup").status_code, 403)

    def test_verified_backup_can_restore_database_and_attachments(self):
        uploaded = self.client.post(
            "/api/attachments/event/1",
            data={"file": (BytesIO(b"original recovery evidence"), "restore.txt")},
            content_type="multipart/form-data",
        )
        self.assertEqual(uploaded.status_code, 201)
        original_subject = self.client.get("/api/events/1").get_json()["subject"]
        backup = self.client.get("/api/system/backup", buffered=True)
        self.assertEqual(backup.status_code, 200)
        backup.close()
        recovery_point = self.client.get("/api/system/backups").get_json()[0]

        with app.app_context():
            database = get_db()
            stored_name = database.execute(
                "SELECT stored_name FROM attachments WHERE entity_type = 'event' AND entity_id = 1"
            ).fetchone()["stored_name"]
            database.execute(
                "UPDATE event_entries SET subject = 'Changed after recovery point' WHERE id = 1"
            )
            database.commit()
            (Path(app.config["UPLOAD_FOLDER"]) / stored_name).write_bytes(b"changed evidence")

        rejected = self.client.post(
            f"/api/system/backups/{recovery_point['id']}/restore",
            json={"confirmation": "restore"},
        )
        self.assertEqual(rejected.status_code, 400)
        restored = self.client.post(
            f"/api/system/backups/{recovery_point['id']}/restore",
            json={"confirmation": "RESTORE S-PULSE"},
        )
        self.assertEqual(restored.status_code, 200)
        result = restored.get_json()
        self.assertEqual(result["status"], "restored")
        self.assertEqual(result["integrity"], "ok")
        self.assertNotEqual(result["source_filename"], result["safety_backup_filename"])
        self.assertEqual(
            self.client.get("/api/events/1").get_json()["subject"], original_subject
        )
        with app.app_context():
            database = get_db()
            restored_name = database.execute(
                "SELECT stored_name FROM attachments WHERE entity_type = 'event' AND entity_id = 1"
            ).fetchone()["stored_name"]
            self.assertEqual(
                (Path(app.config["UPLOAD_FOLDER"]) / restored_name).read_bytes(),
                b"original recovery evidence",
            )
            self.assertEqual(
                database.execute("SELECT COUNT(*) FROM restore_runs").fetchone()[0], 1
            )
            self.assertEqual(
                database.execute("SELECT COUNT(*) FROM backup_runs WHERE status = 'available'").fetchone()[0],
                2,
            )

    def test_kks_workbook_validation_and_commit(self):
        validated = self.client.post(
            "/api/kks-imports/validate",
            data={"file": (self.make_kks_workbook(), "test-kks.xlsx")},
            content_type="multipart/form-data",
        )
        self.assertEqual(validated.status_code, 201)
        result = validated.get_json()
        self.assertEqual(result["source_rows"], 4)
        self.assertEqual(result["unique_assets"], 3)
        self.assertEqual(result["duplicate_rows"], 1)
        self.assertEqual(result["inferred_parents"], 1)

        committed = self.client.post(
            f"/api/kks-imports/{result['id']}/commit"
        )
        self.assertEqual(committed.status_code, 200)
        assets = self.client.get("/api/assets?q=A0%20TST01001A%20-Q01").get_json()
        self.assertTrue(any(item["kks_code"] == "A0 TST01001A -Q01" for item in assets))
        history = self.client.get("/api/kks-imports").get_json()
        self.assertEqual(history[0]["status"], "imported")

    def test_non_administrator_cannot_import_kks(self):
        self.login_as(1)
        response = self.client.post(
            "/api/kks-imports/validate",
            data={"file": (self.make_kks_workbook(), "test-kks.xlsx")},
            content_type="multipart/form-data",
        )
        self.assertEqual(response.status_code, 403)

    def test_login_and_api_authentication(self):
        with self.client.session_transaction() as session:
            session.clear()
        self.assertEqual(self.client.get("/api/dashboard").status_code, 401)
        login = self.client.post(
            "/login",
            data={"employee_no": "MBPS-0104", "password": "SIPAM@2026"},
        )
        self.assertEqual(login.status_code, 302)
        self.assertEqual(self.client.get("/api/me").get_json()["role_name"], "Shift Leader")

    def test_security_headers_and_session_cookie_flags(self):
        with self.client.session_transaction() as session:
            session.clear()
        login = self.client.post(
            "/login",
            data={"employee_no": "MBPS-0104", "password": "SIPAM@2026"},
        )
        cookie = login.headers.get("Set-Cookie", "")
        self.assertIn("HttpOnly", cookie)
        self.assertIn("SameSite=Lax", cookie)

        response = self.client.get("/")
        self.assertEqual(response.headers["X-Content-Type-Options"], "nosniff")
        self.assertEqual(response.headers["X-Frame-Options"], "DENY")
        self.assertEqual(response.headers["Referrer-Policy"], "same-origin")
        self.assertIn("frame-ancestors 'none'", response.headers["Content-Security-Policy"])
        self.assertIn("camera=()", response.headers["Permissions-Policy"])

    def test_inactive_session_is_cleared(self):
        self.login_as(1)
        with app.app_context():
            database = get_db()
            database.execute("UPDATE users SET status = 'inactive' WHERE id = 1")
            database.commit()

        response = self.client.get("/api/me")
        self.assertEqual(response.status_code, 401)
        with self.client.session_transaction() as session:
            self.assertNotIn("user_id", session)

    def test_role_restriction_blocks_planning_for_shift_leader(self):
        self.login_as(1)
        response = self.client.post(
            "/api/preventive/schedule-types",
            json={
                "name": "Unauthorized schedule",
                "calendar_unit": "month",
                "interval_count": 1,
                "strategy": "fixed_schedule",
            },
        )
        self.assertEqual(response.status_code, 403)

    def test_administrator_can_create_update_and_reset_user(self):
        created = self.client.post(
            "/api/users",
            json={
                "employee_no": "MBPS-0999",
                "full_name": "Test Technician",
                "initials": "TT",
                "department": "Control & Instrumentation",
                "role_name": "C&I Technician",
                "password": "Initial123",
            },
        )
        self.assertEqual(created.status_code, 201)
        user_id = created.get_json()["id"]

        updated = self.client.patch(
            f"/api/users/{user_id}",
            json={"role_name": "Maintenance Planner", "status": "inactive"},
        )
        self.assertEqual(updated.status_code, 200)

        reset = self.client.post(
            f"/api/users/{user_id}/reset-password",
            json={"password": "Changed123"},
        )
        self.assertEqual(reset.status_code, 200)

        users = self.client.get("/api/users").get_json()
        user = next(item for item in users if item["id"] == user_id)
        self.assertEqual(user["role_name"], "Maintenance Planner")
        self.assertEqual(user["status"], "inactive")

    def test_non_administrator_cannot_manage_users(self):
        self.login_as(1)
        self.assertEqual(self.client.get("/api/users").status_code, 403)
        response = self.client.post(
            "/api/users",
            json={
                "employee_no": "MBPS-0998",
                "full_name": "Blocked User",
                "initials": "BU",
                "department": "Operations",
                "role_name": "Shift Leader",
                "password": "Initial123",
            },
        )
        self.assertEqual(response.status_code, 403)

    def test_administrator_can_manage_logbook_master_data(self):
        created = self.client.post(
            "/api/admin/logbooks",
            json={
                "code": "chem",
                "name": "Chemical Plant Log",
                "department": "Operations",
                "can_create_role": "Shift Leader",
                "is_shift_leader": True,
            },
        )
        self.assertEqual(created.status_code, 201)
        logbook_id = created.get_json()["id"]
        self.assertEqual(created.get_json()["code"], "CHEM")

        public_logbooks = self.client.get("/api/logbooks").get_json()
        self.assertTrue(any(item["id"] == logbook_id for item in public_logbooks))

        duplicate = self.client.post(
            "/api/admin/logbooks",
            json={
                "code": "CHEM",
                "name": "Duplicate Chemical Plant Log",
                "department": "Operations",
                "can_create_role": "Shift Leader",
            },
        )
        self.assertEqual(duplicate.status_code, 409)

        updated = self.client.patch(
            f"/api/admin/logbooks/{logbook_id}",
            json={
                "name": "Chemical Operations Log",
                "department": "Chemical Operations",
                "can_create_role": "Maintenance Planner",
                "is_shift_leader": False,
            },
        )
        self.assertEqual(updated.status_code, 200)

        admin_logbooks = self.client.get("/api/admin/logbooks").get_json()
        logbook = next(item for item in admin_logbooks if item["id"] == logbook_id)
        self.assertEqual(logbook["name"], "Chemical Operations Log")
        self.assertEqual(logbook["department"], "Chemical Operations")
        self.assertEqual(logbook["can_create_role"], "Maintenance Planner")
        self.assertEqual(logbook["is_shift_leader"], 0)
        self.assertEqual(logbook["entry_count"], 0)

    def test_logbook_master_data_validates_role_and_admin_access(self):
        self.login_as(1)
        self.assertEqual(self.client.get("/api/admin/logbooks").status_code, 403)
        forbidden = self.client.post(
            "/api/admin/logbooks",
            json={
                "code": "OPS2",
                "name": "Blocked Operations Log",
                "department": "Operations",
                "can_create_role": "Shift Leader",
            },
        )
        self.assertEqual(forbidden.status_code, 403)

        self.login_as(7)
        invalid = self.client.post(
            "/api/admin/logbooks",
            json={
                "code": "OPS2",
                "name": "Invalid Role Log",
                "department": "Operations",
                "can_create_role": "Engineer",
            },
        )
        self.assertEqual(invalid.status_code, 400)

    def test_administrator_cannot_deactivate_own_account(self):
        response = self.client.patch("/api/users/7", json={"status": "inactive"})
        self.assertEqual(response.status_code, 409)

    def test_successful_mutation_is_audited_without_password(self):
        created = self.client.post(
            "/api/users",
            json={
                "employee_no": "MBPS-0977",
                "full_name": "Audit Test User",
                "initials": "AT",
                "department": "Operations",
                "role_name": "Shift Leader",
                "password": "Secret123",
            },
        )
        self.assertEqual(created.status_code, 201)
        logs = self.client.get("/api/audit-logs?q=MBPS-0977").get_json()
        self.assertGreaterEqual(len(logs), 1)
        self.assertEqual(logs[0]["action"], "Created record")
        self.assertNotIn("Secret123", logs[0]["details"] or "")
        self.assertNotIn("password", (logs[0]["details"] or "").lower())

    def test_login_is_audited(self):
        with self.client.session_transaction() as session:
            session.clear()
        self.client.post(
            "/login",
            data={"employee_no": "MBPS-0104", "password": "SIPAM@2026"},
        )
        self.login_as(7)
        logs = self.client.get("/api/audit-logs?action=Signed%20in").get_json()
        self.assertTrue(any(item["employee_no"] == "MBPS-0104" for item in logs))

    def test_non_administrator_cannot_read_audit_logs(self):
        self.login_as(1)
        self.assertEqual(self.client.get("/api/audit-logs").status_code, 403)

    def test_kks_hierarchy(self):
        response = self.client.get("/api/assets?reference=1")
        self.assertEqual(response.status_code, 200)
        assets = response.get_json()
        self.assertEqual(assets[0]["kks_code"], "10")
        self.assertTrue(any(item["kks_code"] == "10ETF10AA217" for item in assets))

    def test_asset_list_defaults_to_root_nodes(self):
        response = self.client.get("/api/assets")
        self.assertEqual(response.status_code, 200)
        self.assertTrue(all(item["parent_id"] is None for item in response.get_json()))

    def test_asset_search_matches_description(self):
        response = self.client.get("/api/assets?q=actuator")
        self.assertEqual(response.status_code, 200)
        self.assertTrue(
            any("actuator" in item["description"].lower() for item in response.get_json())
        )

    def test_asset_workspace_combines_linked_records(self):
        response = self.client.get("/api/assets/8")
        self.assertEqual(response.status_code, 200)
        asset = response.get_json()
        self.assertEqual(asset["kks_code"], "10ETF10AA217 MS01")
        self.assertGreaterEqual(asset["counts"]["events"], 1)
        self.assertGreaterEqual(asset["counts"]["corrective"], 1)
        self.assertGreaterEqual(asset["counts"]["recurrent"], 1)
        self.assertGreaterEqual(asset["counts"]["permits"], 1)

    def test_parent_asset_workspace_lists_children(self):
        response = self.client.get("/api/assets/6")
        self.assertEqual(response.status_code, 200)
        asset = response.get_json()
        child_codes = {item["kks_code"] for item in asset["children"]}
        self.assertIn("10ETF10AA217 KA01", child_codes)
        self.assertIn("10ETF10AA217 MS01", child_codes)
        self.assertIn("10ETF10AA217 -Y01", child_codes)

    def test_asset_workspace_does_not_mix_other_asset_events(self):
        response = self.client.get("/api/assets/9")
        self.assertEqual(response.status_code, 200)
        events = response.get_json()["events"]
        self.assertTrue(all(item["entry_no"] != "EL-2026-0001" for item in events))

    def test_event_log_filter_and_detail(self):
        logbooks = self.client.get("/api/logbooks").get_json()
        shift = next(item for item in logbooks if item["is_shift_leader"])
        response = self.client.get(f"/api/events?logbook_id={shift['id']}")
        self.assertEqual(response.status_code, 200)
        self.assertGreaterEqual(len(response.get_json()), 3)

        combined = self.client.get(
            "/api/events", query_string={"logbook_ids": "4,5"}
        )
        self.assertEqual(combined.status_code, 200)
        combined_events = combined.get_json()
        self.assertEqual(
            len({item["id"] for item in combined_events}), len(combined_events)
        )
        self.assertTrue(all(
            item["source_logbook_id"] in {4, 5} for item in combined_events
        ))
        self.assertEqual(
            self.client.get(
                "/api/events", query_string={"logbook_ids": "4,unknown"}
            ).status_code,
            400,
        )
        self.assertEqual(
            self.client.get(
                "/api/events", query_string={"logbook_ids": "4,999"}
            ).status_code,
            400,
        )
        event_export = self.client.get(
            "/api/events.csv",
            query_string={"logbook_ids": "1,4", "state": "open"},
        )
        self.assertEqual(event_export.status_code, 200)
        self.assertIn("text/csv", event_export.content_type)
        self.assertIn("attachment", event_export.headers["Content-Disposition"])
        csv_text = event_export.get_data(as_text=True)
        self.assertIn("Entry Number,Entry Type,Event Date", csv_text)
        exported_rows = list(csv.DictReader(csv_text.lstrip("\ufeff").splitlines()))
        self.assertTrue(exported_rows)
        self.assertTrue(all(row["State"] == "open" for row in exported_rows))
        self.assertEqual(
            len({row["Entry Number"] for row in exported_rows}), len(exported_rows)
        )

        detail = self.client.get("/api/events/1")
        self.assertEqual(detail.status_code, 200)
        self.assertGreaterEqual(len(detail.get_json()["comments"]), 1)

        future = (date.today() + timedelta(days=1)).isoformat()
        future_range = self.client.get(
            "/api/events", query_string={"end": future}
        )
        self.assertEqual(future_range.status_code, 400)
        reversed_range = self.client.get(
            "/api/events", query_string={
                "start": "2026-06-10", "end": "2026-06-01"
            },
        )
        self.assertEqual(reversed_range.status_code, 400)
        invalid_range = self.client.get(
            "/api/events", query_string={"start": "10-June-2026"}
        )
        self.assertEqual(invalid_range.status_code, 400)

    def test_create_main_entry_and_shift_copy(self):
        response = self.client.post(
            "/api/events",
            json={
                "logbook_id": 4,
                "subject": "Test electrical event",
                "asset_id": 8,
                "event_date": "2026-06-09T11:00",
                "state": "open",
                "observation": "Created by automated test.",
                "informant": "Test operator",
                "created_by": "Test User",
            },
        )
        self.assertEqual(response.status_code, 201)
        event = response.get_json()
        self.assertTrue(event["entry_no"].startswith("EL-"))

        shift_entries = self.client.get("/api/events?logbook_id=1").get_json()
        self.assertTrue(any(item["id"] == event["id"] for item in shift_entries))

    def test_create_sub_entry_inherits_main_fields(self):
        response = self.client.post(
            "/api/events",
            json={
                "parent_id": 1,
                "logbook_id": 2,
                "subject": "Ignored subject",
                "event_date": "2026-06-10T00:00",
                "observation": "Follow-up comment.",
                "created_by": "Test User",
            },
        )
        self.assertEqual(response.status_code, 201)
        comment = response.get_json()
        self.assertEqual(comment["subject"], "Dome valve actuator response delayed")
        self.assertEqual(comment["asset_id"], 8)

    def test_event_creation_follows_logbook_responsibility(self):
        payload = {
            "subject": "Discipline authorization test",
            "asset_id": 8,
            "event_date": "2026-06-10T09:00",
            "state": "open",
            "observation": "Authorization test entry.",
        }

        self.login_as(5)
        allowed_ci = self.client.post(
            "/api/events",
            json={**payload, "logbook_id": 5},
        )
        self.assertEqual(allowed_ci.status_code, 201)
        forbidden_electrical = self.client.post(
            "/api/events",
            json={**payload, "logbook_id": 4},
        )
        self.assertEqual(forbidden_electrical.status_code, 403)

        self.login_as(4)
        forbidden_planner = self.client.post(
            "/api/events",
            json={**payload, "logbook_id": 3},
        )
        self.assertEqual(forbidden_planner.status_code, 403)

        self.login_as(1)
        shift_oversight = self.client.post(
            "/api/events",
            json={**payload, "logbook_id": 4},
        )
        self.assertEqual(shift_oversight.status_code, 201)

    def test_event_state_lifecycle_requires_responsibility_and_reason(self):
        self.login_as(4)
        forbidden = self.client.patch(
            "/api/events/1/state",
            json={"state": "closed", "reason": "Planner cannot close this event"},
        )
        self.assertEqual(forbidden.status_code, 403)

        self.login_as(1)
        missing_reason = self.client.patch(
            "/api/events/1/state",
            json={"state": "closed"},
        )
        self.assertEqual(missing_reason.status_code, 400)

        closed = self.client.patch(
            "/api/events/1/state",
            json={"state": "closed", "reason": "Plant condition restored"},
        )
        self.assertEqual(closed.status_code, 200)
        self.assertEqual(closed.get_json()["state"], "closed")
        self.assertEqual(
            closed.get_json()["state_history"][0]["reason"],
            "Plant condition restored",
        )

        reopened = self.client.patch(
            "/api/events/1/state",
            json={"state": "open", "reason": "Condition observed again"},
        )
        self.assertEqual(reopened.status_code, 200)
        self.assertEqual(reopened.get_json()["state"], "open")
        self.assertEqual(len(reopened.get_json()["state_history"]), 2)

        sub_entry = self.client.patch(
            "/api/events/2/state",
            json={"state": "closed", "reason": "Not allowed on sub-entry"},
        )
        self.assertEqual(sub_entry.status_code, 409)

    def test_authorized_user_can_edit_event_with_revision_history(self):
        original = self.client.get("/api/events/1").get_json()
        self.login_as(4)
        forbidden = self.client.patch(
            "/api/events/1",
            json={"observation": "Planner correction attempt"},
        )
        self.assertEqual(forbidden.status_code, 403)

        self.login_as(1)
        updated = self.client.patch(
            "/api/events/1",
            json={
                "subject": "Subject must remain unchanged",
                "asset_id": 9,
                "event_date": "2026-06-09T09:45",
                "observation": "Corrected operational observation.",
                "informant": "Incoming Shift Leader",
            },
        )
        self.assertEqual(updated.status_code, 200)
        result = updated.get_json()
        self.assertEqual(result["subject"], original["subject"])
        self.assertEqual(result["entry_no"], original["entry_no"])
        self.assertEqual(result["source_logbook_id"], original["source_logbook_id"])
        self.assertEqual(result["asset_id"], 9)
        self.assertEqual(result["observation"], "Corrected operational observation.")
        self.assertEqual(len(result["edit_history"]), 1)
        self.assertIn("observation", result["edit_history"][0]["changes"])
        self.assertEqual(result["edit_history"][0]["changed_by"], "Kabelo Molefe")

    def test_event_deletion_requires_authority_reason_and_no_dependencies(self):
        self.login_as(1)
        created = self.client.post(
            "/api/events",
            json={
                "logbook_id": 1,
                "subject": "Temporary duplicate shift entry",
                "asset_id": 8,
                "event_date": "2026-06-10T12:00",
                "state": "open",
                "observation": "Duplicate entered during handover.",
                "informant": "Shift desk",
            },
        ).get_json()
        event_id = created["id"]
        missing_reason = self.client.delete(
            f"/api/events/{event_id}", json={}
        )
        self.assertEqual(missing_reason.status_code, 400)

        self.login_as(4)
        forbidden = self.client.delete(
            f"/api/events/{event_id}",
            json={"reason": "Planner must not delete shift entries"},
        )
        self.assertEqual(forbidden.status_code, 403)

        self.login_as(1)
        protected = self.client.delete(
            "/api/events/1",
            json={"reason": "Attempt to delete entry with dependencies"},
        )
        self.assertEqual(protected.status_code, 409)
        self.assertGreater(protected.get_json()["dependencies"]["sub_entries"], 0)

        deleted = self.client.delete(
            f"/api/events/{event_id}",
            json={"reason": "Confirmed duplicate created during shift handover"},
        )
        self.assertEqual(deleted.status_code, 200)
        self.assertEqual(deleted.get_json()["entry_no"], created["entry_no"])
        self.assertEqual(self.client.get(f"/api/events/{event_id}").status_code, 404)
        with app.app_context():
            audit = get_db().execute(
                "SELECT * FROM event_deletion_log WHERE entry_no = ?",
                (created["entry_no"],),
            ).fetchone()
            self.assertIsNotNone(audit)
            self.assertEqual(audit["deleted_by"], "Kabelo Molefe")
            self.assertEqual(
                json.loads(audit["snapshot"])["subject"],
                "Temporary duplicate shift entry",
            )

    def test_open_event_can_originate_one_matching_work_request(self):
        event = self.client.post(
            "/api/events",
            json={
                "logbook_id": 5,
                "subject": "New C&I defect",
                "asset_id": 9,
                "event_date": "2026-06-10T10:00",
                "state": "open",
                "observation": "Intermittent feedback signal.",
            },
        ).get_json()
        payload = {
            "source_event_id": event["id"],
            "asset_id": 9,
            "name": event["subject"],
            "type_of_work": "Control & instrumentation repair",
            "main_department": "Control & Instrumentation",
            "priority": 2,
            "observation": event["observation"],
        }
        created = self.client.post("/api/corrective", json=payload)
        self.assertEqual(created.status_code, 201)
        self.assertEqual(created.get_json()["source_event_no"], event["entry_no"])

        detail = self.client.get(f"/api/events/{event['id']}").get_json()
        self.assertEqual(len(detail["work_requests"]), 1)
        self.assertEqual(
            detail["work_requests"][0]["request_no"],
            created.get_json()["request_no"],
        )

        duplicate = self.client.post("/api/corrective", json=payload)
        self.assertEqual(duplicate.status_code, 409)

        another_event = self.client.post(
            "/api/events",
            json={
                "logbook_id": 5,
                "subject": "Second C&I defect",
                "asset_id": 9,
                "event_date": "2026-06-10T11:00",
                "state": "open",
                "observation": "Second source event.",
            },
        ).get_json()
        mismatched = self.client.post(
            "/api/corrective",
            json={
                **payload,
                "source_event_id": another_event["id"],
                "asset_id": 8,
            },
        )
        self.assertEqual(mismatched.status_code, 409)
        closed_event = self.client.post(
            "/api/corrective",
            json={**payload, "source_event_id": 3},
        )
        self.assertEqual(closed_event.status_code, 409)

    def test_event_validation(self):
        response = self.client.post("/api/events", json={"subject": "Incomplete"})
        self.assertEqual(response.status_code, 400)

    def test_corrective_list_summary_and_detail(self):
        response = self.client.get("/api/corrective?request_status=submitted")
        self.assertEqual(response.status_code, 200)
        requests = response.get_json()
        self.assertGreaterEqual(len(requests), 1)
        self.assertTrue(all(item["status"] == "submitted" for item in requests))

        summary = self.client.get("/api/corrective/summary")
        self.assertEqual(summary.status_code, 200)
        self.assertGreaterEqual(summary.get_json()["total_requests"], 3)

        detail = self.client.get("/api/corrective/1")
        self.assertEqual(detail.status_code, 200)
        self.assertGreaterEqual(len(detail.get_json()["supplies"]), 1)

        export = self.client.get(
            "/api/corrective.csv",
            query_string={
                "request_status": "submitted",
                "department": "Electrical Maintenance",
            },
        )
        self.assertEqual(export.status_code, 200)
        self.assertIn("text/csv", export.content_type)
        self.assertIn("attachment", export.headers["Content-Disposition"])
        rows = list(csv.DictReader(
            export.get_data(as_text=True).lstrip("\ufeff").splitlines()
        ))
        self.assertEqual([row["Work Request"] for row in rows], ["WR-2026-0002"])
        self.assertEqual(rows[0]["Department"], "Electrical Maintenance")
        self.assertIn("Downtime Hours", rows[0])

    def test_create_and_approve_work_request_creates_order(self):
        created = self.client.post(
            "/api/corrective",
            json={
                "asset_id": 9,
                "name": "Test solenoid inspection",
                "asset_type": "Solenoid valve",
                "type_of_work": "Control & instrumentation repair",
                "main_department": "Control & Instrumentation",
                "priority": 2,
                "observation": "Created by automated test.",
                "author": "Test User",
            },
        )
        self.assertEqual(created.status_code, 201)
        request_id = created.get_json()["id"]

        approved = self.client.patch(
            f"/api/corrective/{request_id}/decision",
            json={"decision": "approved", "performed_by": "Maintenance Approver"},
        )
        self.assertEqual(approved.status_code, 200)
        result = approved.get_json()
        self.assertEqual(result["status"], "approved")
        self.assertTrue(result["order_no"].startswith("WO-"))
        self.assertEqual(result["workflow_step"], "planning")

    def test_cmpt_calculates_work_request_priority_server_side(self):
        self.assertEqual(calculate_cmpt_priority(0, "E"), 6)
        self.assertEqual(calculate_cmpt_priority(4, "D"), 1)
        self.assertEqual(calculate_cmpt_priority(5, "A"), 3)
        self.assertEqual(
            cmpt_response_target("2026-06-01T08:00", 2),
            "2026-06-03T08:00",
        )
        self.assertIsNone(cmpt_response_target("2026-06-01T08:00", 6))

        created = self.client.post(
            "/api/corrective",
            json={
                "asset_id": 8,
                "name": "CMPT matrix verification",
                "type_of_work": "Corrective inspection",
                "main_department": "Operations",
                "priority": 6,
                "cmpt_primary": "A",
                "cmpt_impacts": ["P"],
                "cmpt_severity": 4,
                "cmpt_likelihood": "D",
                "observation": "Verify that CMPT controls the priority.",
            },
        )
        self.assertEqual(created.status_code, 201)
        result = created.get_json()
        self.assertEqual(result["priority"], 1)
        self.assertEqual(result["cmpt_primary"], "A")
        self.assertEqual(result["cmpt_impacts"], ["P", "A"])
        self.assertEqual(result["cmpt_severity"], 4)
        self.assertEqual(result["cmpt_likelihood"], "D")
        self.assertEqual(result["target_response_at"], result["created_at"])

        self.login_as(3)
        inbox_item = next(
            item for item in self.client.get("/api/infobox").get_json()
            if item["source_type"] == "work_request"
            and item["source_id"] == result["id"]
        )
        self.assertEqual(inbox_item["priority"], "high")
        self.assertEqual(inbox_item["due_at"], result["target_response_at"])
        self.assertIn(inbox_item["due_state"], {"overdue", "due_today"})

        invalid = self.client.post(
            "/api/corrective",
            json={
                "asset_id": 8,
                "name": "Invalid CMPT",
                "type_of_work": "Corrective inspection",
                "main_department": "Operations",
                "cmpt_primary": "X",
                "cmpt_impacts": [],
                "cmpt_severity": 2,
                "cmpt_likelihood": "A",
                "observation": "Invalid category should be rejected.",
            },
        )
        self.assertEqual(invalid.status_code, 400)

    def test_approver_can_correct_submitted_work_request_with_history(self):
        created = self.client.post(
            "/api/corrective",
            json={
                "asset_id": 8,
                "name": "Submitted request for correction",
                "type_of_work": "Corrective inspection",
                "main_department": "Operations",
                "cmpt_primary": "A",
                "cmpt_impacts": ["A"],
                "cmpt_severity": 1,
                "cmpt_likelihood": "C",
                "observation": "Initial observation.",
            },
        )
        self.assertEqual(created.status_code, 201)
        request_id = created.get_json()["id"]
        update_payload = {
            "asset_id": 9,
            "name": "Corrected work request",
            "asset_type": "Solenoid valve",
            "type_of_work": "Control & instrumentation repair",
            "main_department": "Control & Instrumentation",
            "cmpt_primary": "P",
            "cmpt_impacts": ["A"],
            "cmpt_severity": 4,
            "cmpt_likelihood": "D",
            "planned_start": "2026-06-20T08:00",
            "planned_end": "2026-06-20T12:00",
            "reminder_days": 1,
            "show_in_history": True,
            "observation": "Corrected after maintenance review.",
        }

        self.login_as(1)
        forbidden = self.client.patch(
            f"/api/corrective/{request_id}", json=update_payload
        )
        self.assertEqual(forbidden.status_code, 403)

        self.login_as(3)
        updated = self.client.patch(
            f"/api/corrective/{request_id}", json=update_payload
        )
        self.assertEqual(updated.status_code, 200)
        result = updated.get_json()
        self.assertEqual(result["asset_id"], 9)
        self.assertEqual(result["kks_code"], "10ETF10AA217 -Y01")
        self.assertEqual(result["priority"], 1)
        self.assertEqual(result["cmpt_impacts"], ["P", "A"])
        self.assertEqual(len(result["edit_history"]), 1)
        self.assertIn("asset_id", result["edit_history"][0]["changes"])
        self.assertEqual(result["edit_history"][0]["changed_by"], "Thabo Ndlovu")

        approved = self.client.patch(
            f"/api/corrective/{request_id}/decision", json={"decision": "approved"}
        )
        self.assertEqual(approved.status_code, 200)
        locked = self.client.patch(
            f"/api/corrective/{request_id}", json=update_payload
        )
        self.assertEqual(locked.status_code, 409)

    def test_declining_work_request_requires_reason(self):
        response = self.client.patch(
            "/api/corrective/2/decision",
            json={"decision": "declined", "performed_by": "Maintenance Approver"},
        )
        self.assertEqual(response.status_code, 400)

    def test_work_order_permit_gate(self):
        incomplete = self.client.patch(
            "/api/work-orders/1",
            json={"action": "submit_plan", "description_of_work": "Incomplete plan"},
        )
        self.assertEqual(incomplete.status_code, 400)
        self.assertIn("maintenance_code", incomplete.get_json()["fields"])

        submitted = self.client.patch(
            "/api/work-orders/1",
            json={
                "action": "submit_plan",
                "performed_by": "Planner",
                "description_of_work": "Test plan",
                "maintenance_code": "COR-CI",
                "equipment_condition": "Degraded",
                "expected_man_hours": 4,
            },
        )
        self.assertEqual(submitted.status_code, 200)
        approved = self.client.patch(
            "/api/work-orders/1",
            json={
                "action": "approve_plan",
                "performed_by": "Approver",
                "permit_requirement": "ptw",
            },
        )
        self.assertEqual(approved.status_code, 200)

        blocked = self.client.patch(
            "/api/work-orders/1",
            json={"action": "confirm_execution", "performed_by": "Supervisor"},
        )
        self.assertEqual(blocked.status_code, 409)

        issued = self.client.patch(
            "/api/permits/1/transition",
            json={
                "action": "issue",
                "controller_name": "Test Controller",
                "remarks": "Isolation and precautions verified.",
            },
        )
        self.assertEqual(issued.status_code, 200)
        issued_only = self.client.patch(
            "/api/work-orders/1", json={"action": "confirm_execution"}
        )
        self.assertEqual(issued_only.status_code, 409)
        self.assertIn("must be received", issued_only.get_json()["error"])

        received = self.client.patch(
            "/api/permits/1/transition",
            json={"action": "receive", "remarks": "Work party accepted conditions."},
        )
        self.assertEqual(received.status_code, 200)
        execution = self.client.patch(
            "/api/work-orders/1",
            json={"action": "confirm_execution", "performed_by": "Supervisor"},
        )
        self.assertEqual(execution.status_code, 200)
        self.assertEqual(execution.get_json()["workflow_step"], "execution")
        self.assertIsNotNone(execution.get_json()["execution_started_at"])
        completed = self.client.patch(
            "/api/work-orders/1",
            json={
                "action": "complete_work",
                "completion_summary": "Permit-controlled repair completed.",
                "actual_man_hours": 4,
            },
        )
        self.assertEqual(completed.status_code, 200)
        blocked_close = self.client.patch(
            "/api/work-orders/1",
            json={
                "action": "accept_work",
                "acceptance_note": "Functional test passed.",
            },
        )
        self.assertEqual(blocked_close.status_code, 409)
        self.assertIn("Cancel the linked permit", blocked_close.get_json()["error"])

    def test_approver_can_return_plan_to_planner_with_reason(self):
        self.login_as(4)
        submitted = self.client.patch(
            "/api/work-orders/1",
            json={
                "action": "submit_plan",
                "description_of_work": "Plan requiring approver review",
                "maintenance_code": "COR-CI",
                "equipment_condition": "Degraded",
                "expected_man_hours": 4,
            },
        )
        self.assertEqual(submitted.status_code, 200)

        self.login_as(3)
        missing_reason = self.client.patch(
            "/api/work-orders/1", json={"action": "return_plan"}
        )
        self.assertEqual(missing_reason.status_code, 400)
        returned = self.client.patch(
            "/api/work-orders/1",
            json={
                "action": "return_plan",
                "reason": "Add isolation details and confirm material availability.",
            },
        )
        self.assertEqual(returned.status_code, 200)
        self.assertEqual(returned.get_json()["workflow_step"], "planning")

        detail = self.client.get("/api/corrective/1").get_json()
        self.assertEqual(detail["history"][0]["action"], "Return Plan")
        self.assertEqual(
            detail["history"][0]["note"],
            "Add isolation details and confirm material availability.",
        )

        self.login_as(4)
        planner_items = self.client.get("/api/infobox").get_json()
        self.assertTrue(any(
            item["source_type"] == "work_order"
            and item["source_id"] == 1
            and "Plan work order" in item["title"]
            for item in planner_items
        ))

    def test_rework_requires_revised_plan_and_new_approval(self):
        plan = {
            "description_of_work": "Replace feedback switch and function test.",
            "maintenance_code": "COR-CI",
            "equipment_condition": "Degraded",
            "expected_man_hours": 4,
        }
        self.client.patch("/api/work-orders/1", json={"action": "submit_plan", **plan})
        self.client.patch(
            "/api/work-orders/1",
            json={"action": "approve_plan", "permit_requirement": "none"},
        )
        self.client.patch("/api/work-orders/1", json={"action": "confirm_execution"})
        self.client.patch(
            "/api/work-orders/1",
            json={
                "action": "complete_work",
                "completion_summary": "Initial repair completed.",
                "actual_man_hours": 4,
            },
        )
        denied = self.client.patch(
            "/api/work-orders/1",
            json={"action": "deny_acceptance", "reason": "Feedback remains unstable."},
        )
        self.assertEqual(denied.status_code, 200)
        self.assertEqual(denied.get_json()["workflow_step"], "rework")

        self.login_as(4)
        missing_summary = self.client.patch(
            "/api/work-orders/1", json={"action": "resubmit_work", **plan}
        )
        self.assertEqual(missing_summary.status_code, 400)
        revised = self.client.patch(
            "/api/work-orders/1",
            json={
                "action": "resubmit_work",
                "reason": "Added cable inspection and full stroke test.",
                **plan,
            },
        )
        self.assertEqual(revised.status_code, 200)
        self.assertEqual(revised.get_json()["workflow_step"], "plan_approval")
        self.assertEqual(revised.get_json()["acceptance_status"], "pending")
        detail = self.client.get("/api/corrective/1").get_json()
        self.assertEqual(detail["history"][0]["action"], "Resubmit Work")
        self.assertEqual(
            detail["history"][0]["note"],
            "Added cable inspection and full stroke test.",
        )

        self.login_as(3)
        approver_items = self.client.get("/api/infobox").get_json()
        self.assertTrue(any(
            item["source_type"] == "work_order"
            and item["source_id"] == 1
            and "Approve execution plan" in item["title"]
            for item in approver_items
        ))

    def test_planner_manages_resources_only_during_planning(self):
        self.login_as(1)
        forbidden = self.client.post(
            "/api/work-orders/1/supplies",
            json={"description": "Unauthorized material", "quantity": 1},
        )
        self.assertEqual(forbidden.status_code, 403)

        self.login_as(4)
        supply = self.client.post(
            "/api/work-orders/1/supplies",
            json={
                "supply_type": "material",
                "description": "Replacement feedback switch",
                "quantity": 1,
                "unit": "EA",
            },
        )
        self.assertEqual(supply.status_code, 201)
        added_supply = next(
            item for item in supply.get_json()["supplies"]
            if item["description"] == "Replacement feedback switch"
        )

        artisan = self.client.post(
            "/api/work-orders/1/artisans",
            json={
                "person_name": "Test Artisan",
                "trade": "C&I Technician",
                "planned_hours": 3.5,
            },
        )
        self.assertEqual(artisan.status_code, 201)
        added_artisan = next(
            item for item in artisan.get_json()["artisans"]
            if item["person_name"] == "Test Artisan"
        )

        removed_supply = self.client.delete(
            f"/api/work-orders/1/supplies/{added_supply['id']}"
        )
        self.assertEqual(removed_supply.status_code, 200)
        removed_artisan = self.client.delete(
            f"/api/work-orders/1/artisans/{added_artisan['id']}"
        )
        self.assertEqual(removed_artisan.status_code, 200)

        submitted = self.client.patch(
            "/api/work-orders/1",
            json={
                "action": "submit_plan",
                "description_of_work": "Planning complete",
                "maintenance_code": "COR-CI",
                "equipment_condition": "Degraded",
            },
        )
        self.assertEqual(submitted.status_code, 200)
        blocked_after_submit = self.client.post(
            "/api/work-orders/1/supplies",
            json={"description": "Late material", "quantity": 1},
        )
        self.assertEqual(blocked_after_submit.status_code, 409)

    def test_work_order_actions_follow_responsible_roles(self):
        self.login_as(1)
        forbidden_plan = self.client.patch(
            "/api/work-orders/1",
            json={"action": "submit_plan"},
        )
        self.assertEqual(forbidden_plan.status_code, 403)

        self.login_as(4)
        planned = self.client.patch(
            "/api/work-orders/1",
            json={
                "action": "submit_plan",
                "description_of_work": "Role-controlled execution plan",
                "maintenance_code": "COR-CI",
                "equipment_condition": "Degraded",
                "expected_man_hours": 4,
            },
        )
        self.assertEqual(planned.status_code, 200)
        forbidden_approval = self.client.patch(
            "/api/work-orders/1",
            json={"action": "approve_plan", "permit_requirement": "none"},
        )
        self.assertEqual(forbidden_approval.status_code, 403)

        self.login_as(3)
        approved = self.client.patch(
            "/api/work-orders/1",
            json={"action": "approve_plan", "permit_requirement": "none"},
        )
        self.assertEqual(approved.status_code, 200)
        forbidden_release = self.client.patch(
            "/api/work-orders/1",
            json={"action": "confirm_execution"},
        )
        self.assertEqual(forbidden_release.status_code, 403)

        self.login_as(1)
        released = self.client.patch(
            "/api/work-orders/1",
            json={"action": "confirm_execution"},
        )
        self.assertEqual(released.status_code, 200)

        self.login_as(6)
        forbidden_completion = self.client.patch(
            "/api/work-orders/1",
            json={"action": "complete_work"},
        )
        self.assertEqual(forbidden_completion.status_code, 403)

        self.login_as(5)
        missing_report = self.client.patch(
            "/api/work-orders/1",
            json={"action": "complete_work"},
        )
        self.assertEqual(missing_report.status_code, 400)
        incomplete_downtime = self.client.patch(
            "/api/work-orders/1",
            json={
                "action": "complete_work",
                "completion_summary": "Repair completed.",
                "actual_man_hours": 4,
                "downtime_started_at": "2026-06-09T10:00",
            },
        )
        self.assertEqual(incomplete_downtime.status_code, 400)
        reversed_downtime = self.client.patch(
            "/api/work-orders/1",
            json={
                "action": "complete_work",
                "completion_summary": "Repair completed.",
                "actual_man_hours": 4,
                "downtime_started_at": "2026-06-09T12:30",
                "restored_at": "2026-06-09T10:00",
            },
        )
        self.assertEqual(reversed_downtime.status_code, 400)
        completed = self.client.patch(
            "/api/work-orders/1",
            json={
                "action": "complete_work",
                "completion_summary": "Actuator feedback switch replaced and tested.",
                "actual_man_hours": 99,
                "artisan_hours": [{"id": 1, "actual_hours": 5.5}],
                "failure_mode": "Instrumentation / control",
                "failure_cause": "Feedback switch contacts failed intermittently.",
                "downtime_started_at": "2026-06-09T10:00",
                "restored_at": "2026-06-09T12:30",
            },
        )
        self.assertEqual(completed.status_code, 200)
        self.assertEqual(
            completed.get_json()["completion_summary"],
            "Actuator feedback switch replaced and tested.",
        )
        self.assertEqual(completed.get_json()["actual_man_hours"], 5.5)
        self.assertEqual(completed.get_json()["downtime_hours"], 2.5)
        self.assertEqual(
            completed.get_json()["failure_mode"], "Instrumentation / control"
        )
        reliability = self.client.get(
            "/api/reports/summary?start=2026-06-01&end=2026-06-30"
        ).get_json()["reliability"]
        self.assertEqual(reliability["classified_failures"], 1)
        self.assertEqual(reliability["total_downtime_hours"], 2.5)
        self.assertEqual(reliability["mttr_hours"], 2.5)
        self.assertEqual(reliability["top_failure_assets"][0]["kks_code"], "10ETF10AA217 MS01")
        maintenance_kpis = self.client.get(
            "/api/reports/summary?start=2026-06-01&end=2026-06-30"
        ).get_json()["maintenance_kpis"]
        self.assertEqual(maintenance_kpis["corrective_scheduled_completed"], 1)
        self.assertEqual(maintenance_kpis["corrective_on_schedule"], 0)
        self.assertEqual(maintenance_kpis["corrective_schedule_percent"], 0.0)
        detail = self.client.get("/api/corrective/1").get_json()
        self.assertEqual(detail["artisans"][0]["actual_hours"], 5.5)
        self.assertEqual(
            completed.get_json()["execution_completed_by"],
            "Boitumelo Kgosidintsi",
        )
        forbidden_acceptance = self.client.patch(
            "/api/work-orders/1",
            json={"action": "accept_work"},
        )
        self.assertEqual(forbidden_acceptance.status_code, 403)

        self.login_as(3)
        missing_remarks = self.client.patch(
            "/api/work-orders/1",
            json={"action": "accept_work"},
        )
        self.assertEqual(missing_remarks.status_code, 400)
        accepted = self.client.patch(
            "/api/work-orders/1",
            json={
                "action": "accept_work",
                "acceptance_note": "Functional operation and feedback verified.",
            },
        )
        self.assertEqual(accepted.status_code, 200)
        self.assertEqual(accepted.get_json()["workflow_step"], "closed")
        self.assertEqual(
            accepted.get_json()["acceptance_note"],
            "Functional operation and feedback verified.",
        )
        self.assertEqual(
            accepted.get_json()["acceptance_checked_by"],
            "Thabo Ndlovu",
        )
        source_event = self.client.get("/api/events/1").get_json()
        self.assertEqual(source_event["state"], "closed")
        self.assertEqual(source_event["state_history"][0]["previous_state"], "open")
        self.assertEqual(source_event["state_history"][0]["new_state"], "closed")
        self.assertIn("WO-2026-0001 was accepted", source_event["state_history"][0]["reason"])

    def test_preventive_completion_requires_responsible_department(self):
        self.login_as(6)
        forbidden = self.client.patch(
            "/api/preventive/tasks/1/complete",
            json={"feedback": "Wrong maintenance department"},
        )
        self.assertEqual(forbidden.status_code, 403)

        self.login_as(5)
        missing_evidence = self.client.patch(
            "/api/preventive/tasks/1/complete",
            json={"feedback": "C&I inspection completed"},
        )
        self.assertEqual(missing_evidence.status_code, 400)
        completed = self.client.patch(
            "/api/preventive/tasks/1/complete",
            json={
                "feedback": "C&I inspection completed",
                "actual_man_hours": 2.5,
                "completed_at": "2026-06-12T14:30",
            },
        )
        self.assertEqual(completed.status_code, 200)
        completed_task = next(
            item for item in completed.get_json()["generated_tasks"]
            if item["id"] == 1
        )
        self.assertEqual(completed_task["actual_man_hours"], 2.5)
        self.assertEqual(
            completed_task["completed_by"],
            "Boitumelo Kgosidintsi",
        )
        self.assertEqual(completed_task["completed_at"], "2026-06-12T14:30")
        self.assertEqual(completed_task["feedback"], "C&I inspection completed")

    def test_approver_cannot_create_preventive_schedule(self):
        self.login_as(3)
        response = self.client.post(
            "/api/preventive/schedule-types",
            json={
                "name": "Approver-owned schedule",
                "calendar_unit": "month",
                "interval_count": 1,
                "strategy": "fixed_schedule",
            },
        )
        self.assertEqual(response.status_code, 403)

    def test_planner_can_suspend_and_reactivate_preventive_schedule(self):
        self.login_as(1)
        forbidden = self.client.patch(
            "/api/preventive/1/status",
            json={"status": "suspended", "reason": "Unauthorized suspension"},
        )
        self.assertEqual(forbidden.status_code, 403)

        self.login_as(4)
        missing_reason = self.client.patch(
            "/api/preventive/1/status",
            json={"status": "suspended"},
        )
        self.assertEqual(missing_reason.status_code, 400)

        suspended = self.client.patch(
            "/api/preventive/1/status",
            json={
                "status": "suspended",
                "reason": "Unit outage schedule under review",
            },
        )
        self.assertEqual(suspended.status_code, 200)
        self.assertEqual(suspended.get_json()["status"], "suspended")
        self.assertEqual(
            suspended.get_json()["status_history"][0]["reason"],
            "Unit outage schedule under review",
        )

        blocked_generation = self.client.post("/api/preventive/1/generate")
        self.assertEqual(blocked_generation.status_code, 404)

        reactivated = self.client.patch(
            "/api/preventive/1/status",
            json={
                "status": "active",
                "reason": "Outage plan confirmed",
            },
        )
        self.assertEqual(reactivated.status_code, 200)
        self.assertEqual(reactivated.get_json()["status"], "active")
        self.assertEqual(len(reactivated.get_json()["status_history"]), 2)

    def test_planner_can_edit_recurrent_schedule_without_changing_identity(self):
        self.login_as(4)
        original = self.client.get("/api/preventive/1").get_json()
        secondary_id = 8 if original["primary_asset_id"] != 8 else 9
        updated = self.client.patch(
            "/api/preventive/1",
            json={
                "name": "Updated feedwater transmitter inspection",
                "type_of_work": original["type_of_work"],
                "main_department": original["main_department"],
                "work_schedule": "Inspect, calibrate, and record as-found values.",
                "duration_hours": 3.5,
                "reminder_days": 10,
                "end_date": "2027-12-31",
                "repetitions": 12,
                "asset_ids": [secondary_id],
            },
        )
        self.assertEqual(updated.status_code, 200)
        result = updated.get_json()
        self.assertEqual(result["recurrent_no"], original["recurrent_no"])
        self.assertEqual(result["schedule_type_id"], original["schedule_type_id"])
        self.assertEqual(result["primary_asset_id"], original["primary_asset_id"])
        self.assertEqual(result["start_date"], original["start_date"])
        self.assertEqual(result["duration_hours"], 3.5)
        self.assertEqual(result["reminder_days"], 10)
        self.assertEqual(
            {asset["id"] for asset in result["assets"]},
            {original["primary_asset_id"], secondary_id},
        )

        self.login_as(1)
        forbidden = self.client.patch(
            "/api/preventive/1",
            json={"name": "Unauthorized update"},
        )
        self.assertEqual(forbidden.status_code, 403)

    def test_preventive_list_summary_and_detail(self):
        response = self.client.get("/api/preventive?status=active")
        self.assertEqual(response.status_code, 200)
        schedules = response.get_json()
        self.assertGreaterEqual(len(schedules), 3)

        summary = self.client.get("/api/preventive/summary")
        self.assertEqual(summary.status_code, 200)
        self.assertGreaterEqual(summary.get_json()["active_schedules"], 3)

        detail = self.client.get("/api/preventive/1")
        self.assertEqual(detail.status_code, 200)
        self.assertGreaterEqual(len(detail.get_json()["assets"]), 2)
        self.assertGreaterEqual(len(detail.get_json()["generated_tasks"]), 1)

        calendar_response = self.client.get("/api/preventive/calendar?month=2026-06")
        self.assertEqual(calendar_response.status_code, 200)
        calendar_data = calendar_response.get_json()
        self.assertEqual(calendar_data["month"], "2026-06")
        self.assertEqual(calendar_data["days"], 30)
        self.assertTrue(calendar_data["tasks"])
        self.assertEqual(
            calendar_data["summary"]["total"],
            len(calendar_data["tasks"]),
        )
        calendar_task = calendar_data["tasks"][0]
        self.assertIn("recurrent_task_id", calendar_task)
        self.assertIn("kks_code", calendar_task)
        self.assertIn(calendar_task["status"], {"planned", "due", "overdue", "completed"})

        invalid_calendar = self.client.get("/api/preventive/calendar?month=June-2026")
        self.assertEqual(invalid_calendar.status_code, 400)

        department = calendar_task["main_department"]
        filtered_calendar = self.client.get(
            "/api/preventive/calendar",
            query_string={"month": "2026-06", "department": department},
        ).get_json()
        self.assertTrue(filtered_calendar["tasks"])
        self.assertTrue(all(
            task["main_department"] == department
            for task in filtered_calendar["tasks"]
        ))

        status_calendar = self.client.get(
            f"/api/preventive/calendar?month=2026-06&status={calendar_task['status']}"
        ).get_json()
        self.assertTrue(all(
            task["status"] == calendar_task["status"]
            for task in status_calendar["tasks"]
        ))

        calendar_export = self.client.get(
            f"/api/preventive/calendar.csv?month=2026-06&status={calendar_task['status']}"
        )
        self.assertEqual(calendar_export.status_code, 200)
        self.assertIn("text/csv", calendar_export.content_type)
        self.assertIn("attachment", calendar_export.headers["Content-Disposition"])
        self.assertIn(calendar_task["task_no"], calendar_export.get_data(as_text=True))

    def test_create_schedule_type_and_recurrent_task(self):
        schedule = self.client.post(
            "/api/preventive/schedule-types",
            json={
                "name": "Test fortnightly inspection",
                "calendar_unit": "week",
                "interval_count": 2,
                "meter_type": "Running hours",
                "meter_interval": 500,
                "task_type": "Inspection task",
                "early_tolerance_days": 1,
                "late_tolerance_days": 2,
                "strategy": "fixed_schedule",
                "weekend_adjustment": "next_working_day",
            },
        )
        self.assertEqual(schedule.status_code, 201)
        schedule_data = schedule.get_json()
        schedule_id = schedule_data["id"]
        self.assertEqual(schedule_data["meter_type"], "Running hours")
        self.assertEqual(schedule_data["meter_interval"], 500)
        self.assertEqual(schedule_data["task_type"], "Inspection task")

        incomplete_meter = self.client.post(
            "/api/preventive/schedule-types",
            json={
                "name": "Invalid meter schedule",
                "calendar_unit": "month",
                "interval_count": 1,
                "meter_type": "Running hours",
                "strategy": "fixed_schedule",
            },
        )
        self.assertEqual(incomplete_meter.status_code, 400)

        recurrent = self.client.post(
            "/api/preventive",
            json={
                "name": "Test recurrent inspection",
                "schedule_type_id": schedule_id,
                "primary_asset_id": 8,
                "type_of_work": "Preventive inspection",
                "main_department": "Control & Instrumentation",
                "start_date": "2026-06-13",
                "asset_ids": [8, 9],
                "created_by": "Test Planner",
            },
        )
        self.assertEqual(recurrent.status_code, 201)
        result = recurrent.get_json()
        self.assertEqual(result["next_target_date"], "2026-06-15")
        detail = self.client.get(f"/api/preventive/{result['id']}").get_json()
        self.assertEqual({asset["id"] for asset in detail["assets"]}, {8, 9})
        secondary_asset = self.client.get("/api/assets/9").get_json()
        self.assertTrue(any(
            item["id"] == result["id"] for item in secondary_asset["recurrent"]
        ))

        generated = self.client.post(f"/api/preventive/{result['id']}/generate")
        self.assertEqual(generated.status_code, 201)
        self.assertEqual(generated.get_json()["target_date"], "2026-06-15")

    def test_planner_can_generate_missing_tasks_for_calendar_month(self):
        self.login_as(4)
        schedule = self.client.post(
            "/api/preventive/schedule-types",
            json={
                "name": "Bulk generation monthly test",
                "calendar_unit": "month",
                "interval_count": 1,
                "early_tolerance_days": 2,
                "late_tolerance_days": 3,
                "strategy": "fixed_schedule",
                "weekend_adjustment": "none",
            },
        ).get_json()
        recurrent = self.client.post(
            "/api/preventive",
            json={
                "name": "Bulk generation test inspection",
                "schedule_type_id": schedule["id"],
                "primary_asset_id": 8,
                "type_of_work": "Preventive inspection",
                "main_department": "Control & Instrumentation",
                "start_date": "2026-08-12",
                "created_by": "Test Planner",
            },
        )
        self.assertEqual(recurrent.status_code, 201)

        preview = self.client.get(
            "/api/preventive/calendar/generate-preview",
            query_string={
                "month": "2026-08",
                "department": "Control & Instrumentation",
            },
        )
        self.assertEqual(preview.status_code, 200)
        preview_data = preview.get_json()
        self.assertGreaterEqual(preview_data["ready_count"], 1)
        self.assertTrue(any(
            item["ready"] and item["name"] == "Bulk generation test inspection"
            for item in preview_data["items"]
        ))

        generated = self.client.post(
            "/api/preventive/calendar/generate",
            json={
                "month": "2026-08",
                "department": "Control & Instrumentation",
            },
        )
        self.assertEqual(generated.status_code, 200)
        result = generated.get_json()
        self.assertGreaterEqual(result["eligible"], 1)
        self.assertEqual(
            result["eligible"],
            result["generated_count"] + result["skipped_count"],
        )

        repeated = self.client.post(
            "/api/preventive/calendar/generate",
            json={
                "month": "2026-08",
                "department": "Control & Instrumentation",
            },
        )
        self.assertEqual(repeated.status_code, 200)
        self.assertEqual(repeated.get_json()["generated_count"], 0)
        self.assertGreaterEqual(repeated.get_json()["skipped_count"], 1)

        repeated_preview = self.client.get(
            "/api/preventive/calendar/generate-preview",
            query_string={
                "month": "2026-08",
                "department": "Control & Instrumentation",
            },
        ).get_json()
        self.assertEqual(repeated_preview["ready_count"], 0)
        self.assertGreaterEqual(repeated_preview["blocked_count"], 1)
        self.assertTrue(any(
            item["reason"] == "Task for this target date already exists"
            for item in repeated_preview["items"]
        ))

        calendar_data = self.client.get(
            "/api/preventive/calendar",
            query_string={
                "month": "2026-08",
                "department": "Control & Instrumentation",
            },
        ).get_json()
        self.assertTrue(calendar_data["tasks"])

    def test_reminder_automatically_generates_task_and_infobox_assignment(self):
        self.login_as(4)
        schedule = self.client.post(
            "/api/preventive/schedule-types",
            json={
                "name": "Automatic reminder release test",
                "calendar_unit": "month",
                "interval_count": 1,
                "early_tolerance_days": 2,
                "late_tolerance_days": 3,
                "strategy": "fixed_schedule",
                "weekend_adjustment": "none",
            },
        ).get_json()
        target = date.today() + timedelta(days=5)
        recurrent = self.client.post(
            "/api/preventive",
            json={
                "name": "Automatically released C&I inspection",
                "schedule_type_id": schedule["id"],
                "primary_asset_id": 8,
                "type_of_work": "Preventive inspection",
                "main_department": "Control & Instrumentation",
                "start_date": target.isoformat(),
                "reminder_days": 7,
                "created_by": "Test Planner",
            },
        ).get_json()

        self.login_as(5)
        first_box = self.client.get("/api/infobox")
        self.assertEqual(first_box.status_code, 200)
        matching = [
            item for item in first_box.get_json()
            if item["source_type"] == "preventive_task"
            and item["description"] == "Automatically released C&I inspection"
        ]
        self.assertEqual(len(matching), 1)
        self.assertEqual(matching[0]["due_at"], target.isoformat())

        second_box = self.client.get("/api/infobox")
        self.assertEqual(len([
            item for item in second_box.get_json()
            if item["source_type"] == "preventive_task"
            and item["description"] == "Automatically released C&I inspection"
        ]), 1)
        detail = self.client.get(f"/api/preventive/{recurrent['id']}").get_json()
        self.assertEqual(len(detail["generated_tasks"]), 1)
        self.assertEqual(detail["generated_tasks"][0]["status"], "planned")

    def test_non_planner_cannot_bulk_generate_preventive_tasks(self):
        self.login_as(1)
        response = self.client.post(
            "/api/preventive/calendar/generate",
            json={"month": "2026-06"},
        )
        self.assertEqual(response.status_code, 403)
        preview = self.client.get(
            "/api/preventive/calendar/generate-preview?month=2026-06"
        )
        self.assertEqual(preview.status_code, 403)

    def test_complete_interval_followup_uses_execution_date(self):
        generated = self.client.post("/api/preventive/2/generate")
        self.assertEqual(generated.status_code, 201)
        task_id = generated.get_json()["id"]
        completed = self.client.patch(
            f"/api/preventive/tasks/{task_id}/complete",
            json={
                "completed_by": "Test Technician",
                "completed_at": "2026-07-20T10:00",
                "feedback": "Completed late for calculation test.",
                "actual_man_hours": 4,
            },
        )
        self.assertEqual(completed.status_code, 200)
        self.assertEqual(completed.get_json()["next_target_date"], "2026-10-20")

    def test_calendar_helpers_handle_month_end_and_weekend(self):
        self.assertEqual(add_interval(date(2026, 1, 31), "month", 1), date(2026, 2, 28))
        self.assertEqual(
            adjust_weekend(date(2026, 6, 13), "next_working_day"),
            date(2026, 6, 15),
        )

    def test_permit_list_summary_and_detail(self):
        response = self.client.get("/api/permits?status=prepared")
        self.assertEqual(response.status_code, 200)
        permits = response.get_json()
        self.assertGreaterEqual(len(permits), 1)
        self.assertTrue(all(item["status"] == "prepared" for item in permits))

        summary = self.client.get("/api/permits/summary")
        self.assertEqual(summary.status_code, 200)
        self.assertGreaterEqual(summary.get_json()["total"], 2)

        detail = self.client.get("/api/permits/1")
        self.assertEqual(detail.status_code, 200)
        self.assertGreaterEqual(len(detail.get_json()["precautions"]), 6)
        self.assertEqual(len(detail.get_json()["assessments"]), 3)

    def test_create_permit_and_lifecycle_updates_work_order(self):
        request_record = self.client.post(
            "/api/corrective",
            json={
                "asset_id": 8,
                "name": "Permit integration test work",
                "type_of_work": "Mechanical repair",
                "main_department": "Mechanical Maintenance",
                "cmpt_primary": "A",
                "cmpt_impacts": ["A"],
                "cmpt_severity": 3,
                "cmpt_likelihood": "D",
                "observation": "Work requires a controlled mechanical isolation.",
            },
        ).get_json()
        approved_request = self.client.patch(
            f"/api/corrective/{request_record['id']}/decision",
            json={"decision": "approved"},
        ).get_json()
        work_order_id = approved_request["work_order_id"]
        self.client.patch(
            f"/api/work-orders/{work_order_id}",
            json={
                "action": "submit_plan",
                "description_of_work": "Test mechanical permit work.",
                "maintenance_code": "COR-MECH",
                "equipment_condition": "Failed",
                "expected_man_hours": 4,
            },
        )
        self.client.patch(
            f"/api/work-orders/{work_order_id}",
            json={"action": "approve_plan", "permit_requirement": "ptw"},
        )
        permit_payload = {
                "work_order_id": work_order_id,
                "asset_id": 8,
                "form_type": "mechanical_ptw",
                "work_description": "Test mechanical permit.",
                "location": "Unit 1 BAS ash side",
                "issued_to": "Test Technician",
                "employer": "STEAG Energy Services",
                "mechanical_isolations": "Secure linkage.",
                "prepared_by": "Test Shift Leader",
                "precautions_confirmed": True,
                "precautions": ["isolate_energy", "lock_tag", "ppe"],
                "assessments": {
                    "hot_work": {"answer": "no"},
                    "height_work": {"answer": "no"},
                    "confined_space": {"answer": "na"},
                },
            }
        created = self.client.post(
            "/api/permits",
            json=permit_payload,
        )
        self.assertEqual(created.status_code, 201)
        permit_id = created.get_json()["id"]
        duplicate = self.client.post("/api/permits", json=permit_payload)
        self.assertEqual(duplicate.status_code, 409)

        issued = self.client.patch(
            f"/api/permits/{permit_id}/transition",
            json={
                "action": "issue",
                "performed_by": "Test Shift Leader",
                "controller_name": "Test Controller",
                "remarks": "Isolation and precautions verified before issue.",
            },
        )
        self.assertEqual(issued.status_code, 200)
        self.assertEqual(issued.get_json()["status"], "issued")

        order = self.client.get(f"/api/corrective/{request_record['id']}").get_json()
        self.assertEqual(order["permit_status"], "issued")
        self.assertEqual(order["linked_permits"][0]["id"], permit_id)

        for action, person, remarks in (
            ("receive", "Test Technician", "Permit conditions acknowledged."),
            ("clear", "Test Technician", "Work completed and location cleared."),
            ("cancel", "Test Controller", "Permit cancelled after restoration."),
        ):
            transitioned = self.client.patch(
                f"/api/permits/{permit_id}/transition",
                json={
                    "action": action,
                    "performed_by": person,
                    "remarks": remarks,
                },
            )
            self.assertEqual(transitioned.status_code, 200)

        permit = self.client.get(f"/api/permits/{permit_id}").get_json()
        self.assertEqual(len(permit["transition_history"]), 4)
        self.assertEqual(
            permit["transition_history"][0]["remarks"],
            "Permit cancelled after restoration.",
        )
        self.assertEqual(
            permit["transition_history"][0]["performed_by"],
            "S-PULSE Administrator",
        )

        order = self.client.get(f"/api/corrective/{request_record['id']}").get_json()
        self.assertEqual(order["permit_status"], "cancelled")

    def test_work_order_can_require_sft_and_link_sft_permit(self):
        request_record = self.client.post(
            "/api/corrective",
            json={
                "asset_id": 8,
                "name": "SFT integration test work",
                "type_of_work": "Electrical test",
                "main_department": "Electrical Maintenance",
                "cmpt_primary": "A",
                "cmpt_impacts": ["A"],
                "cmpt_severity": 3,
                "cmpt_likelihood": "D",
                "observation": "Work requires controlled testing after isolation.",
            },
        ).get_json()
        approved_request = self.client.patch(
            f"/api/corrective/{request_record['id']}/decision",
            json={"decision": "approved"},
        ).get_json()
        work_order_id = approved_request["work_order_id"]
        self.client.patch(
            f"/api/work-orders/{work_order_id}",
            json={
                "action": "submit_plan",
                "description_of_work": "Carry out controlled electrical testing.",
                "maintenance_code": "COR-ELEC",
                "equipment_condition": "Degraded",
                "expected_man_hours": 3,
            },
        )
        approved_plan = self.client.patch(
            f"/api/work-orders/{work_order_id}",
            json={"action": "approve_plan", "permit_requirement": "sft"},
        )
        self.assertEqual(approved_plan.status_code, 200)
        self.assertEqual(approved_plan.get_json()["permit_requirement"], "sft")

        created = self.client.post(
            "/api/permits",
            json={
                "work_order_id": work_order_id,
                "asset_id": 8,
                "form_type": "electrical_sft",
                "work_description": "Controlled test after maintenance.",
                "location": "Unit 1 BAS ash side",
                "issued_to": "Electrical Tester",
                "employer": "STEAG Energy Services",
                "electrical_isolations": "Isolate and prove dead before test.",
                "prepared_by": "Test Shift Leader",
                "precautions_confirmed": True,
                "precautions": ["isolate_energy", "lock_tag", "prove_dead", "ppe"],
                "assessments": {
                    "hot_work": {"answer": "no"},
                    "height_work": {"answer": "no"},
                    "confined_space": {"answer": "na"},
                },
            },
        )
        self.assertEqual(created.status_code, 201)
        self.assertTrue(created.get_json()["permit_no"].startswith("SFT-"))
        detail = self.client.get(f"/api/corrective/{request_record['id']}").get_json()
        self.assertEqual(detail["linked_permits"][0]["form_type"], "electrical_sft")

    def test_permit_issue_requires_confirmed_precautions(self):
        created = self.client.post(
            "/api/permits",
            json={
                "asset_id": 6,
                "form_type": "mechanical_loa",
                "work_description": "Unconfirmed test access.",
                "location": "BAS ash side",
                "issued_to": "Test Person",
                "employer": "STEAG Energy Services",
                "prepared_by": "Test Shift Leader",
                "precautions_confirmed": False,
                "precautions": ["ppe"],
            },
        )
        self.assertEqual(created.status_code, 201)
        permit_id = created.get_json()["id"]
        issued = self.client.patch(
            f"/api/permits/{permit_id}/transition",
            json={
                "action": "issue",
                "performed_by": "Test Shift Leader",
                "controller_name": "Test Controller",
                "remarks": "Attempted issue without confirmed precautions.",
            },
        )
        self.assertEqual(issued.status_code, 409)
        cancelled = self.client.patch(
            f"/api/permits/{permit_id}/transition",
            json={
                "action": "cancel",
                "remarks": "Prepared permit cancelled after failed issue check.",
            },
        )
        self.assertEqual(cancelled.status_code, 200)
        self.assertEqual(cancelled.get_json()["status"], "cancelled")

    def test_infobox_is_generated_from_workflows(self):
        users = self.client.get("/api/users")
        self.assertEqual(users.status_code, 200)
        self.assertGreaterEqual(len(users.get_json()), 6)

        self.login_as(1)
        shift_box = self.client.get("/api/infobox")
        self.assertEqual(shift_box.status_code, 200)
        shift_items = shift_box.get_json()
        permit_item = next(item for item in shift_items if item["source_type"] == "permit")
        self.assertEqual(permit_item["target_view"], "permits")
        self.assertEqual(permit_item["target_id"], permit_item["source_id"])

        self.login_as(3)
        approver_box = self.client.get("/api/infobox")
        self.assertEqual(approver_box.status_code, 200)
        request_item = next(
            item for item in approver_box.get_json()
            if item["source_type"] == "work_request"
        )
        self.assertEqual(request_item["target_view"], "corrective")
        self.assertEqual(request_item["target_id"], request_item["source_id"])

        self.login_as(5)
        technician_box = self.client.get("/api/infobox")
        self.assertEqual(technician_box.status_code, 200)
        preventive_item = next(
            item for item in technician_box.get_json()
            if item["source_type"] == "preventive_task"
        )
        self.assertEqual(preventive_item["target_view"], "preventive")
        with app.app_context():
            recurrent_id = get_db().execute(
                "SELECT recurrent_task_id FROM preventive_tasks WHERE id = ?",
                (preventive_item["source_id"],),
            ).fetchone()["recurrent_task_id"]
        self.assertEqual(preventive_item["target_id"], recurrent_id)

    def test_claiming_shared_infobox_item_removes_it_from_other_user(self):
        self.login_as(1)
        first_user_items = self.client.get("/api/infobox").get_json()
        shared_item = next(item for item in first_user_items if item["source_type"] == "permit")

        self.login_as(2)
        second_user_before = self.client.get("/api/infobox").get_json()
        self.assertTrue(any(item["id"] == shared_item["id"] for item in second_user_before))

        self.login_as(1)
        claimed = self.client.patch(
            f"/api/infobox/{shared_item['id']}/claim",
            json={},
        )
        self.assertEqual(claimed.status_code, 200)

        first_user_after = self.client.get("/api/infobox").get_json()
        claimed_item = next(item for item in first_user_after if item["id"] == shared_item["id"])
        self.assertEqual(claimed_item["status"], "claimed")

        self.login_as(2)
        second_user_after = self.client.get("/api/infobox").get_json()
        self.assertFalse(any(item["id"] == shared_item["id"] for item in second_user_after))
        team_after = self.client.get("/api/infobox?scope=team").get_json()
        team_item = next(item for item in team_after if item["id"] == shared_item["id"])
        self.assertEqual(team_item["status"], "claimed")
        self.assertEqual(team_item["claimed_by"], 1)

        team_summary = self.client.get("/api/infobox/summary?scope=team").get_json()
        self.assertGreaterEqual(team_summary["claimed"], 1)

        team_export = self.client.get(
            "/api/infobox/history.csv?state=active&scope=team&source_type=permit"
        )
        self.assertEqual(team_export.status_code, 200)
        self.assertIn(shared_item["title"], team_export.get_data(as_text=True))

    def test_team_infobox_does_not_cross_responsibility_groups(self):
        self.login_as(1)
        shift_item = next(
            item for item in self.client.get("/api/infobox?scope=team").get_json()
            if item["source_type"] == "permit"
        )
        self.login_as(5)
        technician_team = self.client.get("/api/infobox?scope=team").get_json()
        self.assertFalse(any(item["id"] == shift_item["id"] for item in technician_team))

    def test_administrator_can_filter_team_workload_by_group(self):
        self.login_as(7)
        workload = self.client.get("/api/infobox/workload")
        self.assertEqual(workload.status_code, 200)
        groups = workload.get_json()
        shift_group = next(group for group in groups if group["code"] == "SHIFT_LEADERS")
        self.assertGreaterEqual(shift_group["active"], 1)
        self.assertIn("claimed", shift_group)
        self.assertIn("overdue", shift_group)
        team_items = self.client.get("/api/infobox?scope=team").get_json()
        self.assertEqual(
            sum(group["active"] for group in groups),
            len(team_items),
        )

        filtered = self.client.get(
            f"/api/infobox?scope=team&group_id={shift_group['id']}"
        )
        self.assertEqual(filtered.status_code, 200)
        self.assertTrue(filtered.get_json())
        self.assertTrue(all(
            item["responsible_group_id"] == shift_group["id"]
            for item in filtered.get_json()
        ))

        summary = self.client.get(
            f"/api/infobox/summary?scope=team&group_id={shift_group['id']}"
        ).get_json()
        self.assertEqual(summary["total"], len(filtered.get_json()))

        export = self.client.get(
            f"/api/infobox/history.csv?scope=team&state=active&group_id={shift_group['id']}"
        )
        self.assertEqual(export.status_code, 200)
        csv_text = export.get_data(as_text=True)
        self.assertIn("Shift Leaders", csv_text)
        self.assertNotIn("Maintenance Approvers", csv_text)

    def test_infobox_item_can_be_released_to_group(self):
        self.login_as(1)
        item = next(
            value for value in self.client.get("/api/infobox").get_json()
            if value["source_type"] == "permit"
        )
        self.client.patch(f"/api/infobox/{item['id']}/claim", json={})
        released = self.client.patch(
            f"/api/infobox/{item['id']}/release",
            json={},
        )
        self.assertEqual(released.status_code, 200)
        self.login_as(2)
        second_user = self.client.get("/api/infobox").get_json()
        self.assertTrue(any(value["id"] == item["id"] for value in second_user))

        history = self.client.get(f"/api/infobox/{item['id']}/history")
        self.assertEqual(history.status_code, 200)
        actions = [entry["action"] for entry in history.get_json()]
        self.assertIn("assigned", actions)
        self.assertIn("claimed", actions)
        self.assertIn("released", actions)

    def test_infobox_history_is_restricted_to_assigned_users(self):
        self.login_as(1)
        item = next(
            value for value in self.client.get("/api/infobox").get_json()
            if value["source_type"] == "permit"
        )
        self.login_as(5)
        history = self.client.get(f"/api/infobox/{item['id']}/history")
        self.assertEqual(history.status_code, 403)

    def test_completed_infobox_items_are_available_in_archive(self):
        self.login_as(1)
        item = next(
            value for value in self.client.get("/api/infobox").get_json()
            if value["source_type"] == "permit"
        )
        with app.app_context():
            database = get_db()
            database.execute(
                """
                UPDATE inbox_items
                SET status = 'completed', completed_at = '2026-06-11T10:00',
                    updated_at = '2026-06-11T10:00'
                WHERE id = ?
                """,
                (item["id"],),
            )
            database.commit()

        active = self.client.get("/api/infobox?state=active").get_json()
        self.assertFalse(any(value["id"] == item["id"] for value in active))

        archived = self.client.get("/api/infobox?state=completed")
        self.assertEqual(archived.status_code, 200)
        archived_item = next(
            value for value in archived.get_json() if value["id"] == item["id"]
        )
        self.assertEqual(archived_item["status"], "completed")
        self.assertEqual(archived_item["target_view"], "permits")

        summary = self.client.get("/api/infobox/summary").get_json()
        self.assertGreaterEqual(summary["completed"], 1)

        export = self.client.get("/api/infobox/history.csv?state=completed")
        self.assertEqual(export.status_code, 200)
        self.assertIn("text/csv", export.content_type)
        self.assertIn("attachment", export.headers["Content-Disposition"])
        csv_text = export.get_data(as_text=True)
        self.assertIn("Assigned At,Claimed At,Completed At", csv_text)
        self.assertIn(
            "Responsibility Group,Handled By,Due At,Due Status,Age Hours,Handling Hours",
            csv_text,
        )
        self.assertIn(item["title"], csv_text)

    def test_infobox_csv_respects_source_filter(self):
        self.login_as(1)
        export = self.client.get(
            "/api/infobox/history.csv?state=active&source_type=permit"
        )
        self.assertEqual(export.status_code, 200)
        csv_text = export.get_data(as_text=True)
        self.assertIn("permit", csv_text)
        self.assertNotIn("work_request", csv_text)

    def test_infobox_due_status_filters_match_summary_and_export(self):
        self.login_as(7)
        overdue = self.client.get(
            "/api/infobox?scope=team&timing=overdue"
        )
        self.assertEqual(overdue.status_code, 200)
        overdue_items = overdue.get_json()
        self.assertTrue(overdue_items)
        self.assertTrue(all(item["due_state"] == "overdue" for item in overdue_items))
        self.assertTrue(all("age_hours" in item for item in overdue_items))

        summary = self.client.get(
            "/api/infobox/summary?scope=team&timing=overdue"
        ).get_json()
        self.assertEqual(summary["total"], len(overdue_items))
        self.assertEqual(summary["overdue"], len(overdue_items))

        no_target = self.client.get(
            "/api/infobox?scope=team&timing=no_target"
        ).get_json()
        self.assertTrue(no_target)
        self.assertTrue(all(item["due_state"] == "no_target" for item in no_target))

        export = self.client.get(
            "/api/infobox/history.csv?scope=team&state=active&timing=overdue"
        )
        self.assertEqual(export.status_code, 200)
        csv_text = export.get_data(as_text=True)
        self.assertIn("Due At,Due Status,Age Hours,Handling Hours", csv_text)
        self.assertIn("overdue", csv_text)
        self.assertNotIn("no_target", csv_text)

    def test_infobox_escalation_and_due_target_reset_are_audited(self):
        self.login_as(7)
        items = self.client.get("/api/infobox?scope=team").get_json()
        planning_item = next(
            item
            for item in items
            if item["source_type"] == "work_order"
            and item["source_id"] == 1
            and item["action_code"] == "plan_work_order"
        )
        self.assertEqual(planning_item["escalation_level"], 3)
        self.assertEqual(planning_item["priority"], "high")
        self.assertEqual(planning_item["base_priority"], "medium")
        summary = self.client.get("/api/infobox/summary?scope=team").get_json()
        self.assertGreaterEqual(summary["escalated"], 1)
        self.assertGreaterEqual(summary["critical_escalations"], 1)
        history = self.client.get(
            f"/api/infobox/{planning_item['id']}/history"
        ).get_json()
        self.assertTrue(any(entry["action"] == "escalated" for entry in history))

        future_target = (date.today() + timedelta(days=10)).isoformat() + "T12:00"
        with app.app_context():
            database = get_db()
            database.execute(
                "UPDATE work_requests SET planned_end = ? WHERE id = 1",
                (future_target,),
            )
            database.commit()
        refreshed = self.client.get("/api/infobox?scope=team").get_json()
        planning_item = next(
            item for item in refreshed
            if item["source_type"] == "work_order" and item["source_id"] == 1
        )
        self.assertEqual(planning_item["escalation_level"], 0)
        self.assertEqual(planning_item["priority"], "medium")
        history = self.client.get(
            f"/api/infobox/{planning_item['id']}/history"
        ).get_json()
        self.assertTrue(any(entry["action"] == "reset" for entry in history))

    def test_infobox_search_matches_record_group_and_description(self):
        self.login_as(7)
        by_record = self.client.get(
            "/api/infobox?scope=team&q=PTW-2026-0001"
        )
        self.assertEqual(by_record.status_code, 200)
        record_items = by_record.get_json()
        self.assertEqual(len(record_items), 1)
        self.assertEqual(record_items[0]["source_type"], "permit")

        by_group = self.client.get(
            "/api/infobox?scope=team&q=Control%20%26%20Instrumentation"
        ).get_json()
        self.assertTrue(by_group)
        self.assertTrue(all(
            item["responsible_group_name"] == "Control & Instrumentation Team"
            for item in by_group
        ))

        phrase = record_items[0]["description"].split()[0]
        by_description = self.client.get(
            f"/api/infobox?scope=team&q={phrase}"
        ).get_json()
        self.assertTrue(any(item["id"] == record_items[0]["id"] for item in by_description))

        summary = self.client.get(
            "/api/infobox/summary?scope=team&q=PTW-2026-0001"
        ).get_json()
        self.assertEqual(summary["total"], 1)

        export = self.client.get(
            "/api/infobox/history.csv?scope=team&state=active&q=PTW-2026-0001"
        )
        self.assertEqual(export.status_code, 200)
        self.assertIn("PTW-2026-0001", export.get_data(as_text=True))
        self.assertNotIn("PTW-2026-0002", export.get_data(as_text=True))


if __name__ == "__main__":
    unittest.main()
