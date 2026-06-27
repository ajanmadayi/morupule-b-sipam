# S-PULSE Deployment Runbook

This runbook is for preparing a pilot or production-style deployment of the S-PULSE web application.

## 1. Server Prerequisites

- Windows server or workstation approved for S-PULSE application hosting.
- Python 3.11 or newer.
- Network access for users who will open the web application.
- A controlled folder for the application source.
- A controlled folder or backup location for retained recovery ZIP files.
- HTTPS termination through IIS, reverse proxy, or another approved gateway for production use.

## 2. Source Placement

Recommended folder:

```text
D:\Applications\morupule-b-sipam
```

Copy the clean delivery package contents into the selected folder.

Do not copy development runtime data unless it has been specifically approved:

- `morupule_sipam.db`
- `uploads/`
- `backups/`
- `kks_staging/`
- `.venv/`
- `dist/`

## 3. Python Environment

Create a virtual environment:

```powershell
py -m venv .venv
```

Install dependencies:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

Verify imports:

```powershell
.\.venv\Scripts\python.exe -c "import flask, openpyxl; print('dependencies ok')"
```

## 4. Environment Variables

Set required environment variables for the service account or hosting process:

```powershell
$env:SIPAM_SECRET_KEY='replace-with-long-random-secret'
$env:SIPAM_COOKIE_SECURE='1'
$env:SIPAM_PORT='5001'
```

Rules:

- `SIPAM_SECRET_KEY` must be unique per deployment and kept secret.
- `SIPAM_COOKIE_SECURE=1` should be used when served through HTTPS.
- For local non-HTTPS testing, `SIPAM_COOKIE_SECURE` may be omitted.

## 5. First Startup

Start using the helper:

```powershell
powershell -ExecutionPolicy Bypass -File .\run_dev.ps1 -Port 5001
```

Or start directly:

```powershell
$env:SIPAM_PORT='5001'
.\.venv\Scripts\python.exe app.py
```

Open:

```text
http://127.0.0.1:5001/
```

The first startup creates:

- `morupule_sipam.db`
- `uploads/`
- `kks_staging/`
- `backups/`

## 6. Initial Configuration

After first sign-in as administrator:

1. Change seeded administrator password.
2. Create named user accounts.
3. Assign roles according to `docs/ROLE_PERMISSION_MATRIX.md`.
4. Review configured logbooks.
5. Import or validate the approved S-PULSE KKS register.
6. Confirm Dashboard and Asset Directory record counts.
7. Create a first recovery point.
8. Verify the recovery point.

## 7. KKS Register Load

Command-line import:

```powershell
.\.venv\Scripts\python.exe import_kks.py "E:\SI SYSTEM\List of KKS codes.xlsx"
```

Application import:

1. Sign in as System Administrator.
2. Open **Administration > KKS Import**.
3. Select `.xlsx` workbook.
4. Validate workbook.
5. Review duplicate rows, inferred parents, and validation status.
6. Commit only after review.

## 8. Backup Routine

Daily minimum:

1. Open **Administration > System Status**.
2. Create full backup.
3. Verify backup.
4. Download/store copy in approved secure location.

Weekly minimum:

1. Run data-quality check.
2. Confirm recent verified backup exists.
3. Confirm backup archive can be downloaded.
4. Review Audit Trail for unusual activity.

Command:

```powershell
.\.venv\Scripts\python.exe tools\data_quality_check.py
```

## 9. Restore Rules

Restore must only be performed in an approved maintenance window or test environment.

Use `docs/BACKUP_RESTORE_DRILL.md` to test recovery before pilot or production approval.

Before restore:

1. Notify affected users.
2. Create a fresh backup of the current state.
3. Verify the selected restore backup.
4. Confirm reason and approval.

Restore confirmation phrase:

```text
RESTORE MORUPULE B SIPAM
```

The application creates a safety backup before replacing the database and attachments.

## 10. Verification Before Handover

Run:

```powershell
.\.venv\Scripts\python.exe -m py_compile app.py tools\smoke_check.py tools\data_quality_check.py tools\package_delivery.py
node --check static\app.js
.\.venv\Scripts\python.exe tools\data_quality_check.py
```

With server running:

```powershell
.\.venv\Scripts\python.exe tools\smoke_check.py --base-url http://127.0.0.1:5001
```

Expected:

```text
Smoke check passed.
Data quality check passed.
```

## 11. Production Hosting Note

The built-in Flask server is suitable for local development and pilot review only.

For production use:

- Host behind an approved WSGI server or reverse proxy.
- Serve through HTTPS.
- Restrict server access to authorized S-PULSE users.
- Keep runtime folders backed up and access-controlled.
- Monitor disk growth for uploads and backups.

## 12. Go-Live Checklist

- Dependencies installed in `.venv`.
- `SIPAM_SECRET_KEY` set.
- HTTPS enabled and `SIPAM_COOKIE_SECURE=1`.
- Seeded passwords changed.
- Named users created.
- Roles verified.
- Logbooks verified.
- KKS register loaded and reviewed.
- First verified backup created.
- Smoke check passed.
- Data-quality check passed.
- UAT checklist signed off.
- Restore procedure tested in non-production environment.

## 13. Render Hosting

For Render deployment, use `render.yaml` and follow `docs/RENDER_DEPLOYMENT.md`.
