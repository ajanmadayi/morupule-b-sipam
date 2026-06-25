# Morupule B SIPAM UAT Checklist

Use this checklist for functional acceptance before a demo, pilot run, or deployment handover.

## 1. Access And Security

- Sign in as Shift Leader `MBPS-0104`.
- Confirm unauthorized API access returns authentication required after sign-out.
- Sign in as Administrator `MBPS-ADMIN`.
- Confirm Administration navigation is visible only for administrator accounts.
- Confirm inactive users cannot continue using an old session.
- Confirm security headers are present using `tools/smoke_check.py`.
- Review [docs/ROLE_PERMISSION_MATRIX.md](docs/ROLE_PERMISSION_MATRIX.md) and confirm each UAT role sees only the expected workflow actions.

## 2. Operations Dashboard

- Confirm open entries, events today, active assets, and logbook counts load.
- Open latest event entries from dashboard.
- Create a new Event Log entry from dashboard and confirm it appears in Event Log.

## 3. Event Log

- Create a main entry with KKS asset, informant, observation, and open state.
- Create a sub-entry against that main entry.
- Filter by logbook, state, date, and search text.
- Print shift handover/Event Log extract.
- Export Event Log CSV.
- Close an entry and confirm audit/history behavior.

## 4. KKS Asset Directory

- Search by KKS code and description.
- Open an asset and confirm linked Event Log, Corrective, Preventive, and Permit records.
- Confirm asset history remains readable after linked workflows are created.

## 5. Corrective Maintenance

- Create a work request from an Event Log entry.
- Confirm CMPT priority and response target are calculated.
- Approve the request as Maintenance Approver.
- Plan the work order as Maintenance Planner.
- Add supplies and artisans.
- Link or prepare PTW/LoA when required.
- Complete execution as technician.
- Accept or return work after inspection.
- Confirm accepted corrective work closes the source event where applicable.
- Export Corrective CSV and print work record.

## 6. Preventive Maintenance

- Create or edit a schedule type.
- Create a recurrent task with primary KKS and asset group.
- Generate preventive work for one task.
- Use calendar preview and monthly generation.
- Complete a preventive task with hours and completion notes.
- Confirm PM compliance appears in Reports.

## 7. PTW And LoA

- Prepare permit for a KKS asset or work order.
- Issue, receive, clear, and cancel the permit.
- Confirm invalid duplicate active permits are blocked.
- Print the permit record.

## 8. Infobox

- Confirm personal queue shows assigned actions.
- Claim and release an item.
- Filter by team, source, due state, priority, and search text.
- Export Infobox history.
- Confirm escalated and overdue counts are visible.

## 9. Shift Handover

- Create a draft handover with open Event Log entries.
- Submit the handover.
- Confirm the incoming Shift Leader receives the Infobox assignment.
- Accept the handover.
- Print accepted handover record.

## 10. Reports

- Run report for the current month.
- Confirm activity, status distribution, responsible-area workload, reliability, CMPT response, PM compliance, and backlog metrics.
- Print management report.
- Download activity CSV.

## 11. Administration

- Create a user and assign role.
- Change user role and deactivate/reactivate account.
- Reset password.
- Create and edit a Logbook.
- Confirm duplicate Logbook code/name is rejected.
- Review Audit Trail filters and details.
- Validate and commit revised KKS workbook from KKS Import.

## 12. Backup And Restore

- Create a full recovery point.
- Verify the retained backup.
- Download the backup archive.
- Confirm restore is blocked without exact phrase:

```text
RESTORE MORUPULE B SIPAM
```

- Restore only in an approved test environment.
- Confirm restore history records source backup and safety backup.

## 13. Final Smoke Check

Start the server, then run:

```powershell
python tools\smoke_check.py --base-url http://127.0.0.1:5035
```

Acceptance target:

```text
Smoke check passed.
```

## 14. Sign-Off

- Record final acceptance in [docs/UAT_SIGNOFF_TEMPLATE.md](docs/UAT_SIGNOFF_TEMPLATE.md).
- Attach or reference smoke-check and data-quality-check results.
- List open items with owner, priority, and target date.
- Confirm whether the build is accepted for pilot use, accepted with open items, or requires retest.
