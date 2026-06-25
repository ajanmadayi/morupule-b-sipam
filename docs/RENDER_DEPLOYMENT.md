# Render Deployment Guide

This guide explains how to run Morupule B SIPAM on Render.

For click-by-click dashboard setup, use `docs/RENDER_DASHBOARD_STEPS.md`.

## Important Storage Note

Morupule B SIPAM currently uses SQLite plus local uploaded files. On Render, these must be stored on a persistent disk.

This project is configured to use:

```text
SIPAM_DATA_DIR=/var/data
```

Runtime files on Render:

```text
/var/data/morupule_sipam.db
/var/data/uploads
/var/data/kks_staging
/var/data/backups
```

Do not run multiple scaled instances with the same SQLite database. Keep the Render service at one web instance unless the database is migrated to PostgreSQL.

## Files Added For Render

| File | Purpose |
| --- | --- |
| `render.yaml` | Render Blueprint for web service, Gunicorn start command, environment variables, health check, and persistent disk. |
| `requirements.txt` | Includes Flask, openpyxl, and gunicorn. |
| `app.py` | Reads `SIPAM_DATA_DIR` and stores runtime data on persistent disk. |
| `import_kks.py` | Supports `--data-dir` and `--database` for server-side imports. |

## Render Blueprint

The `render.yaml` defines:

```yaml
buildCommand: pip install -r requirements.txt
startCommand: gunicorn app:app --bind 0.0.0.0:$PORT --workers 2 --timeout 120
healthCheckPath: /api/health
SIPAM_DATA_DIR: /var/data
SIPAM_COOKIE_SECURE: "1"
```

It also defines a persistent disk:

```yaml
mountPath: /var/data
sizeGB: 5
```

Adjust disk size if uploads/backups are expected to grow.

## Deployment Steps

1. Push the clean source package or repository to GitHub/GitLab.
2. In Render, create a new Blueprint or Web Service from the repo.
3. Confirm Render detects `render.yaml`.
4. Set secret environment variable:

```text
SIPAM_SECRET_KEY
```

Use a long random value. Do not use the development key.

5. Confirm persistent disk is attached at:

```text
/var/data
```

6. Deploy.
7. Confirm health check:

```text
https://<render-service-url>/api/health
```

8. Sign in as administrator and change seeded passwords.
9. Create named users and assign roles.
10. Load or validate the Morupule B KKS register.
11. Create and verify first recovery point.

## First Login

Development seeded credentials:

| Account | Value |
| --- | --- |
| Administrator | `MBPS-ADMIN` |
| Initial password | `SIPAM@2026` |

Change seeded passwords before pilot use.

## KKS Import On Render

Application method:

1. Sign in as System Administrator.
2. Open **Administration > KKS Import**.
3. Upload `.xlsx`.
4. Validate and commit.

Command-line method if using Render shell:

```bash
python import_kks.py "/path/to/List of KKS codes.xlsx" --data-dir /var/data
```

## Backup On Render

Use **Administration > System Status**:

1. Create full backup.
2. Verify backup.
3. Download backup.
4. Store a copy outside Render.

Backups inside `/var/data/backups` are persistent, but an external copy is still required for disaster recovery.

## Restore On Render

Restore only after approval.

Confirmation phrase:

```text
RESTORE MORUPULE B SIPAM
```

The app creates a safety backup before replacing the database and uploads.

## Render Environment Variables

| Variable | Required | Value |
| --- | --- | --- |
| `SIPAM_DATA_DIR` | Yes | `/var/data` |
| `SIPAM_SECRET_KEY` | Yes | Long random secret, set in Render dashboard |
| `SIPAM_COOKIE_SECURE` | Yes | `1` |
| `PORT` | Render provided | Do not set manually |

Optional advanced overrides:

| Variable | Purpose |
| --- | --- |
| `SIPAM_DATABASE` | Explicit SQLite database path. |
| `SIPAM_UPLOAD_FOLDER` | Explicit uploads folder path. |
| `SIPAM_KKS_STAGING_FOLDER` | Explicit KKS staging folder path. |
| `SIPAM_BACKUP_FOLDER` | Explicit backups folder path. |

## Post-Deploy Verification

Run locally against the Render URL:

```powershell
python tools\smoke_check.py --base-url https://<render-service-url>
```

Run from Render shell or server environment:

```bash
python tools/data_quality_check.py --database /var/data/morupule_sipam.db
```

Expected:

```text
Smoke check passed.
Data quality check passed.
```

## Operational Limits

- Keep one web instance when using SQLite.
- Monitor disk usage for uploads and backups.
- Download verified backups regularly.
- Do not commit KKS import until validation is reviewed.
- Use HTTPS only for pilot/production users.
