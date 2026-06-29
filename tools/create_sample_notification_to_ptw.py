from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app import app, clear_operational_data, get_db, init_db  # noqa: E402


def api(client, method: str, path: str, user_id: int, payload: dict | None = None):
    with client.session_transaction() as session:
        session["user_id"] = user_id
    response = client.open(path, method=method, json=payload)
    data = response.get_json(silent=True)
    if response.status_code >= 400:
        raise RuntimeError(f"{method} {path} failed {response.status_code}: {data}")
    return data


def first_asset_id() -> int:
    row = get_db().execute(
        """
        SELECT id FROM assets
        WHERE level_no IN (2, 3)
        ORDER BY id
        LIMIT 1
        """
    ).fetchone()
    if row is None:
        raise RuntimeError("No KKS assets found. Import KKS before creating the sample.")
    return int(row["id"])


def main() -> None:
    app.config["TESTING"] = True
    with app.app_context():
        init_db()
        clear_operational_data(get_db())
        asset_id = first_asset_id()

    client = app.test_client()

    event = api(
        client,
        "POST",
        "/api/events",
        1,
        {
            "logbook_id": 1,
            "asset_id": asset_id,
            "subject": "Sample notification for PTW workflow",
            "event_date": datetime.now().isoformat(timespec="minutes"),
            "observation": "Abnormal vibration observed. Maintenance notification raised from KKS asset.",
            "informant": "Operations sample",
            "state": "open",
        },
    )

    request = api(
        client,
        "POST",
        "/api/corrective",
        1,
        {
            "source_event_id": event["id"],
            "asset_id": asset_id,
            "name": "Sample corrective maintenance from notification",
            "asset_type": "KKS equipment",
            "type_of_work": "Mechanical repair",
            "main_department": "Mechanical Maintenance",
            "cmpt_primary": "A",
            "cmpt_impacts": ["A"],
            "cmpt_severity": 3,
            "cmpt_likelihood": "D",
            "observation": "Create work request from the event log notification.",
        },
    )

    approved_request = api(
        client,
        "PATCH",
        f"/api/corrective/{request['id']}/decision",
        3,
        {"decision": "approved", "performed_by": "Maintenance Approver"},
    )
    work_order_id = approved_request["work_order_id"]

    planned_order = api(
        client,
        "PATCH",
        f"/api/work-orders/{work_order_id}",
        4,
        {
            "action": "submit_plan",
            "performed_by": "Maintenance Planner",
            "description_of_work": "Inspect, isolate, repair, and test the equipment under PTW.",
            "maintenance_code": "COR-MECH",
            "equipment_condition": "Degraded",
            "expected_man_hours": 4,
        },
    )

    approved_plan = api(
        client,
        "PATCH",
        f"/api/work-orders/{work_order_id}",
        3,
        {
            "action": "approve_plan",
            "performed_by": "Maintenance Approver",
            "permit_requirement": "ptw",
        },
    )

    permit = api(
        client,
        "POST",
        "/api/permits",
        1,
        {
            "work_order_id": work_order_id,
            "asset_id": asset_id,
            "form_type": "mechanical_ptw",
            "work_description": "Sample PTW for corrective maintenance.",
            "location": "Plant area linked to selected KKS",
            "issued_to": "Mechanical Technician",
            "employer": "STEAG Energy Services",
            "mechanical_isolations": "Isolate, lock, tag, and prove zero energy before work.",
            "prepared_by": "Shift Leader",
            "precautions_confirmed": True,
            "precautions": ["isolate_energy", "lock_tag", "ppe"],
            "assessments": {
                "hot_work": {"answer": "no"},
                "height_work": {"answer": "no"},
                "confined_space": {"answer": "na"},
            },
        },
    )

    api(
        client,
        "PATCH",
        f"/api/permits/{permit['id']}/transition",
        1,
        {
            "action": "issue",
            "performed_by": "Shift Leader",
            "controller_name": "Operations Controller",
            "remarks": "Isolation and precautions verified before issue.",
        },
    )
    api(
        client,
        "PATCH",
        f"/api/permits/{permit['id']}/transition",
        1,
        {
            "action": "receive",
            "performed_by": "Mechanical Technician",
            "remarks": "Permit conditions accepted by work party.",
        },
    )
    api(
        client,
        "PATCH",
        f"/api/work-orders/{work_order_id}",
        1,
        {"action": "confirm_execution", "performed_by": "Shift Leader"},
    )
    api(
        client,
        "PATCH",
        f"/api/work-orders/{work_order_id}",
        6,
        {
            "action": "complete_work",
            "completion_summary": "Sample work completed and equipment checked.",
            "actual_man_hours": 4,
        },
    )
    api(
        client,
        "PATCH",
        f"/api/permits/{permit['id']}/transition",
        1,
        {
            "action": "clear",
            "performed_by": "Mechanical Technician",
            "remarks": "Work completed and area cleared.",
        },
    )
    api(
        client,
        "PATCH",
        f"/api/permits/{permit['id']}/transition",
        1,
        {
            "action": "cancel",
            "performed_by": "Operations Controller",
            "remarks": "Permit cancelled after restoration.",
        },
    )
    closed_order = api(
        client,
        "PATCH",
        f"/api/work-orders/{work_order_id}",
        3,
        {
            "action": "accept_work",
            "acceptance_note": "Sample workflow accepted after PTW cancellation.",
        },
    )

    summary = {
        "event_no": event["entry_no"],
        "work_request_no": request["request_no"],
        "work_order_no": planned_order["order_no"],
        "permit_no": permit["permit_no"],
        "permit_requirement": approved_plan["permit_requirement"],
        "permit_status": "cancelled",
        "work_order_status": closed_order["workflow_step"],
        "source_event_state": api(client, "GET", f"/api/events/{event['id']}", 1)["state"],
    }
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
