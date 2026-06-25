# Morupule B SIPAM

Fresh web implementation of the SI/PAM workflows for Morupule B Power Station.

Start with [docs/DELIVERY_INDEX.md](docs/DELIVERY_INDEX.md) when reviewing the handover package.

## Current Scope

- Operations dashboard, Event Log, sub-entries, copy visibility, print, CSV, and audit history
- KKS Asset Directory with asset history across Event Log, Corrective, Preventive, and PTW/LoA
- Corrective Maintenance from work request/notification through CMPT, approval, planning, execution, acceptance, and closure
- Preventive Maintenance schedule types, recurrent tasks, generated work, calendar view, and compliance reporting
- Permit to Work and Limitation of Access forms with issue, receipt, clearance, and cancellation workflow
- Infobox queues, team workload, claim/release, escalation, history, and filtered exports
- Shift Handover drafts, submission, acceptance, captured open events, and print record
- Management reports for activity, reliability, downtime, CMPT response, PM compliance, backlog, and workload
- Administration for users, roles, logbooks, audit trail, KKS imports, backups, verification, and controlled restore
- Browser security headers, safer session cookies, inactive-session clearing, and attachment size/type controls

## Run Locally

Install dependencies:

```powershell
python -m pip install -r requirements.txt
```

Start the development server:

```powershell
$env:SIPAM_PORT='5035'
python app.py
```

Windows helper:

```powershell
powershell -ExecutionPolicy Bypass -File .\run_dev.ps1 -Port 5035
```

Open:

```text
http://127.0.0.1:5035/
```

If `SIPAM_PORT` is not set, the app defaults to `5001`.

## Development Sign-In

- Shift Leader: `MBPS-0104`
- Administrator: `MBPS-ADMIN`
- Initial password: `SIPAM@2026`

Change seeded passwords before any real deployment.

## Environment

Set these for deployment:

```powershell
$env:SIPAM_SECRET_KEY='replace-with-a-long-random-secret'
$env:SIPAM_COOKIE_SECURE='1'
$env:SIPAM_PORT='5001'
```

`SIPAM_COOKIE_SECURE=1` should be used when serving through HTTPS.

Runtime folders are created automatically beside `app.py`:

- `morupule_sipam.db`
- `uploads`
- `kks_staging`
- `backups`

## KKS Register

Initial command-line import:

```powershell
python import_kks.py "E:\SI SYSTEM\List of KKS codes.xlsx"
```

Administrators can also validate and commit revised `.xlsx` registers from **Administration > KKS Import**. Validation is staged first and does not alter live assets until committed.

## Backup And Restore

Use **Administration > System Status** to create retained recovery points. A full backup contains:

- SQLite database snapshot
- Uploaded supporting documents
- Manifest with record counts and hashes

Restore requires a verified backup and the confirmation phrase:

```text
RESTORE MORUPULE B SIPAM
```

Before restore, the app creates a safety backup of the current state.

## Verification

Run syntax checks:

```powershell
python -m py_compile app.py
node --check static/app.js
```

Run the test suite:

```powershell
python -m unittest discover -s tests
```

Latest verified result during this build:

```text
Ran 77 tests in 146.844s
OK
```

Live smoke checks completed on:

```text
http://127.0.0.1:5035/
```

Verified: health endpoint, administrator login, main page, logbook admin endpoint, and security headers.

For a repeatable live smoke check, run:

```powershell
python tools\smoke_check.py --base-url http://127.0.0.1:5035
```

The smoke check needs the Flask dependencies installed in the Python environment that starts the app.

For an offline database quality check that does not need Flask:

```powershell
python tools\data_quality_check.py
```

To create a clean source delivery ZIP without runtime DB/uploads/backups:

```powershell
python tools\package_delivery.py
```

Use [UAT_CHECKLIST.md](UAT_CHECKLIST.md) for module-by-module acceptance before demo or handover.

Use [docs/UAT_SIGNOFF_TEMPLATE.md](docs/UAT_SIGNOFF_TEMPLATE.md) to record formal UAT approval and open items.

Use [docs/SIPAM_OPERATIONS_GUIDE.md](docs/SIPAM_OPERATIONS_GUIDE.md) for operator training and workflow explanation.

Use [docs/ROLE_PERMISSION_MATRIX.md](docs/ROLE_PERMISSION_MATRIX.md) to review role responsibilities and access control during UAT.

Use [docs/DEPLOYMENT_RUNBOOK.md](docs/DEPLOYMENT_RUNBOOK.md) for pilot or production-style setup.

Use [docs/RENDER_DEPLOYMENT.md](docs/RENDER_DEPLOYMENT.md) to deploy the application on Render with persistent disk storage.

Use [docs/RENDER_DASHBOARD_STEPS.md](docs/RENDER_DASHBOARD_STEPS.md) for the exact Render dashboard clicks/settings.

Use [docs/REQUIREMENTS_TRACEABILITY.md](docs/REQUIREMENTS_TRACEABILITY.md) to map delivered features to SI/PAM workflow expectations.

Use [docs/DEMO_WALKTHROUGH.md](docs/DEMO_WALKTHROUGH.md) to present the system screen by screen.

Use [docs/RELEASE_NOTES.md](docs/RELEASE_NOTES.md) for a concise summary of this delivery.

Use [docs/QUICK_REFERENCE.md](docs/QUICK_REFERENCE.md) for daily role-based operating steps.

Use [docs/TRAINING_PLAN.md](docs/TRAINING_PLAN.md) to organize role-based user training.

Use [docs/OPEN_ITEMS_REGISTER.md](docs/OPEN_ITEMS_REGISTER.md) to track UAT defects, decisions, and deferred items.

Use [docs/PILOT_READINESS_CHECKLIST.md](docs/PILOT_READINESS_CHECKLIST.md) before starting controlled pilot use.

Use [docs/BACKUP_RESTORE_DRILL.md](docs/BACKUP_RESTORE_DRILL.md) to test recovery before pilot or production approval.
