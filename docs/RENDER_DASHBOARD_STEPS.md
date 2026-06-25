# Render Dashboard Deployment Steps

Use these steps from the Render dashboard.

## Important

Render does not deploy a Python web service directly from a local ZIP upload. The normal route is:

1. Put this folder in a GitHub/GitLab repository.
2. Connect that repository to Render.
3. Deploy as a Blueprint using `render.yaml`, or deploy as a Web Service using the manual settings below.

## Option A: Blueprint Deployment

Recommended because this project includes `render.yaml`.

1. Open Render dashboard.
2. Select **Blueprints** from the left menu.
3. Select **New Blueprint Instance** or **New > Blueprint**.
4. Connect the Git repository containing `morupule-b-sipam`.
5. Select the repository.
6. Confirm Render detects `render.yaml`.
7. Enter service name:

```text
morupule-b-sipam
```

8. Set secret environment variable:

```text
SIPAM_SECRET_KEY=<long random secret>
```

9. Confirm persistent disk:

```text
Name: sipam-data
Mount path: /var/data
Size: 5 GB or higher
```

10. Deploy.

## Option B: Manual Web Service

Use this if you do not use Blueprint.

From your screenshot:

1. Click **+ New**.
2. Select **Web Service**.
3. Connect the Git repository.
4. Select the repository containing this project.
5. Use these settings:

| Field | Value |
| --- | --- |
| Name | `morupule-b-sipam` |
| Runtime | Python |
| Region | Choose nearest/approved region |
| Branch | Main deployment branch |
| Root Directory | Leave blank if repo root is this folder. If repo contains parent folders, set `morupule-b-sipam`. |
| Build Command | `pip install -r requirements.txt` |
| Start Command | `gunicorn app:app --bind 0.0.0.0:$PORT --workers 2 --timeout 120` |
| Health Check Path | `/api/health` |

6. Add environment variables:

| Key | Value |
| --- | --- |
| `SIPAM_DATA_DIR` | `/var/data` |
| `SIPAM_COOKIE_SECURE` | `1` |
| `SIPAM_SECRET_KEY` | Long random secret |

7. Add persistent disk:

| Field | Value |
| --- | --- |
| Name | `sipam-data` |
| Mount Path | `/var/data` |
| Size | `5 GB` or higher |

8. Create Web Service.

## After Deploy

1. Open:

```text
https://<your-render-service>.onrender.com/api/health
```

Expected station:

```text
Morupule B Power Station
```

2. Open the application URL.
3. Sign in:

```text
MBPS-ADMIN / SIPAM@2026
```

4. Change seeded password before pilot.
5. Create named user accounts.
6. Import or validate Morupule B KKS register.
7. Create and verify first recovery point.

## Smoke Check

After deployment, from your local PC:

```powershell
python tools\smoke_check.py --base-url https://<your-render-service>.onrender.com
```

## If Render Build Fails

Check:

- `requirements.txt` includes `gunicorn`.
- Root Directory is correct.
- Start command uses `$PORT`.
- Persistent disk exists at `/var/data`.
- `SIPAM_SECRET_KEY` is set.

## If Data Disappears After Redeploy

Cause:

- App is not using persistent disk.

Fix:

- Confirm `SIPAM_DATA_DIR=/var/data`.
- Confirm disk mount path is `/var/data`.
- Confirm the service is not scaled to multiple instances while using SQLite.
