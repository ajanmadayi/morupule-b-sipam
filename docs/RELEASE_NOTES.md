# Morupule B SIPAM Release Notes

## Release

| Field | Value |
| --- | --- |
| Application | Morupule B SIPAM |
| Release type | UAT / pilot handover build |
| Release date | 2026-06-24 |
| Package | `morupule-b-sipam-delivery-*.zip` |

## Summary

This release delivers a Morupule B-focused SI/PAM web application covering operations logging, KKS asset history, corrective maintenance, preventive maintenance, PTW/LoA, Infobox workflow routing, shift handover, management reporting, administration, KKS import, audit, backup, and controlled restore.

## Delivered Modules

- Operations Dashboard
- Event Log with main entries, sub-entries, logbook filtering, print, CSV export, state control, and audit
- KKS Asset Directory with linked operational and maintenance history
- Corrective Maintenance Work Request and Work Order workflow
- CMPT priority and response target calculation
- Corrective planning with supplies, artisans, permit requirement, execution, acceptance, and rework handling
- Preventive Maintenance schedule types, recurrent tasks, asset groups, calendar generation, and task completion
- PTW / LoA permit workflow
- Infobox personal/team queues, claim/release, escalation, workload, history, and export
- Shift Handover draft, submit, accept, captured open entries, and print
- Reports for activity, workload, CMPT response, reliability, downtime, PM compliance, and backlog
- Users & Roles administration
- Logbook administration
- Audit Trail
- KKS Import validation and commit
- System Status, retained backup, backup verification, download, delete, controlled restore, and restore history

## Security And Control

- Role-based access control for workflow and administration screens
- Admin-only master data, audit, backup, restore, and KKS import functions
- Safer session cookie defaults
- Inactive-session clearing
- Browser security headers
- Attachment type and size controls
- Restore confirmation phrase:

```text
RESTORE MORUPULE B SIPAM
```

## Delivery Documents

- `README.md`
- `UAT_CHECKLIST.md`
- `docs/DELIVERY_INDEX.md`
- `docs/SIPAM_OPERATIONS_GUIDE.md`
- `docs/ROLE_PERMISSION_MATRIX.md`
- `docs/DEPLOYMENT_RUNBOOK.md`
- `docs/REQUIREMENTS_TRACEABILITY.md`
- `docs/UAT_SIGNOFF_TEMPLATE.md`
- `docs/DEMO_WALKTHROUGH.md`
- `docs/RELEASE_NOTES.md`

## Verification Tools

- `tools/smoke_check.py`
- `tools/data_quality_check.py`
- `tools/package_delivery.py`

## Latest Data Quality Evidence

The offline database quality check passed on the current local database:

```text
Integrity: ok
Foreign key issues: 0
KKS assets: 152,168
Assets without KKS code: 0
Active users without role: 0
Open Event Log entries without subject: 0
Corrective requests without KKS asset: 0
Active permit records without KKS asset: 0
Available recovery points not verified: 0
Data quality check passed.
```

## Known Deployment Notes

- The Flask development server is suitable for development, demo, and pilot review only.
- Production hosting should use approved HTTPS hosting with `SIPAM_COOKIE_SECURE=1`.
- `SIPAM_SECRET_KEY` must be set before real deployment.
- Seeded passwords must be changed before pilot or production use.
- The clean source package intentionally excludes runtime database, uploads, backups, KKS staging files, virtual environment, logs, and caches.
- Live smoke check requires Flask dependencies installed in the active Python environment.

## Recommended Next Actions

1. Install dependencies in a controlled environment.
2. Start the application and run `tools/smoke_check.py`.
3. Complete `UAT_CHECKLIST.md`.
4. Record approval using `docs/UAT_SIGNOFF_TEMPLATE.md`.
5. Review `docs/PILOT_READINESS_CHECKLIST.md`.
6. Create and verify the first recovery point.
7. Conduct a demo using `docs/DEMO_WALKTHROUGH.md`.
