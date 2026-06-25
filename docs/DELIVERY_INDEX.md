# Morupule B SIPAM Delivery Index

This is the starting point for reviewing the Morupule B SIPAM delivery package.

## Application

| Item | Location | Purpose |
| --- | --- | --- |
| Flask application | `app.py` | Main backend, APIs, database setup, workflow logic, reports, backup/restore, and route security. |
| Frontend script | `static/app.js` | Single-page application behavior, module views, forms, workflow actions, filters, and exports. |
| Stylesheet | `static/styles.css` | Responsive SIPAM interface styling. |
| Main template | `templates/index.html` | Authenticated application shell and module screens. |
| Login template | `templates/login.html` | Sign-in screen. |
| Print templates | `templates/print_document.html`, `templates/management_report.html`, `templates/shift_handover.html`, `templates/formal_shift_handover.html` | Print-ready operational records. |

## Operational Documents

| Document | Purpose |
| --- | --- |
| `README.md` | Setup, run, verification, backup, restore, KKS import, and package commands. |
| `UAT_CHECKLIST.md` | Module-by-module user acceptance checklist. |
| `docs/UAT_SIGNOFF_TEMPLATE.md` | Formal UAT acceptance/sign-off record template. |
| `docs/OPEN_ITEMS_REGISTER.md` | UAT/pilot issue, decision, and deferred item tracker. |
| `docs/PILOT_READINESS_CHECKLIST.md` | Final readiness checklist before controlled pilot use. |
| `docs/BACKUP_RESTORE_DRILL.md` | Recovery-point verification and restore drill checklist. |
| `docs/SIPAM_OPERATIONS_GUIDE.md` | Operator workflow guide and SI/PAM terminology. |
| `docs/ROLE_PERMISSION_MATRIX.md` | Role responsibilities and permission matrix. |
| `docs/DEPLOYMENT_RUNBOOK.md` | Pilot/production setup, backup, restore, and go-live checklist. |
| `docs/RENDER_DEPLOYMENT.md` | Render-specific deployment with Gunicorn and persistent disk storage. |
| `docs/RENDER_DASHBOARD_STEPS.md` | Exact Render dashboard fields and post-deploy checks. |
| `docs/REQUIREMENTS_TRACEABILITY.md` | Mapping from expected SI/PAM workflow areas to delivered modules and verification paths. |
| `docs/DEMO_WALKTHROUGH.md` | Suggested screen-by-screen stakeholder demo script. |
| `docs/RELEASE_NOTES.md` | Summary of delivered modules, controls, verification evidence, and next actions. |
| `docs/QUICK_REFERENCE.md` | Short daily-use instructions for each operating role. |
| `docs/TRAINING_PLAN.md` | Role-based training sessions, exercises, and attendance template. |
| `docs/DELIVERY_INDEX.md` | This delivery overview. |

## Verification Tools

| Tool | Command | Purpose |
| --- | --- | --- |
| Smoke check | `python tools\smoke_check.py --base-url http://127.0.0.1:5035` | Live route, login, admin, and browser security-header check. Requires Flask environment and running server. |
| Data quality check | `python tools\data_quality_check.py` | Offline SQLite integrity, foreign-key, record-count, and master-data sanity check. |
| Package builder | `python tools\package_delivery.py` | Creates a clean handover ZIP excluding runtime data. |
| Python syntax | `python -m py_compile app.py tools\smoke_check.py tools\data_quality_check.py tools\package_delivery.py` | Syntax validation. |
| JavaScript syntax | `node --check static\app.js` | Frontend syntax validation. |

## Current Functional Scope

- Operations Dashboard
- Event Log with main/sub entries, filters, print, CSV, and audit trail
- KKS Asset Directory and asset history
- Corrective Maintenance Work Request to Work Order workflow
- CMPT priority and response target
- Preventive Maintenance schedules, recurrent tasks, calendar, and compliance
- PTW / LoA safety permit workflow
- Infobox queues, escalation, workload, claim/release, and history
- Shift Handover draft, submit, accept, and print
- Management reports
- User and role administration
- Logbook administration
- Audit Trail
- KKS import validation and commit
- System Status, retained backup, verification, download, delete, and controlled restore
- Browser security headers and safer session controls

## Runtime Data Excluded From Source Package

The clean delivery ZIP intentionally excludes:

- `morupule_sipam.db`
- `uploads/`
- `backups/`
- `kks_staging/`
- `.venv/`
- `dist/`
- caches and logs

This prevents source delivery from exposing live database content, uploaded attachments, retained recovery points, or local environment files.

## Deployment Preparation

Before production or pilot:

1. Install dependencies in a controlled Python environment.
2. Set `SIPAM_SECRET_KEY`.
3. Use HTTPS and set `SIPAM_COOKIE_SECURE=1`.
4. Change seeded passwords.
5. Load the approved Morupule B KKS register.
6. Create named users and assign roles.
7. Verify logbooks and permissions.
8. Create and verify a first recovery point.
9. Run the UAT checklist.
10. Run smoke and data-quality checks.

## Latest Package Rule

The delivery package must pass these checks:

```text
has_db False
has_uploads False
has_backups False
has_dist_nested False
```

The package manifest inside `DELIVERY_MANIFEST.json` lists every included source file with SHA-256 hashes.
