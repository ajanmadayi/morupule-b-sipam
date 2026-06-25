# Morupule B SIPAM Demo Walkthrough

Use this walkthrough to present the application to Morupule B stakeholders.

## Demo Preparation

Before starting:

1. Confirm the app is running.
2. Confirm a System Administrator account is available.
3. Confirm at least one Shift Leader account is available.
4. Run the offline data-quality check.
5. Keep `docs/ROLE_PERMISSION_MATRIX.md` open for role questions.
6. Keep `docs/REQUIREMENTS_TRACEABILITY.md` open for scope questions.

Suggested browser URL:

```text
http://127.0.0.1:5035/
```

## Opening Message

Suggested introduction:

```text
This Morupule B SIPAM web application is built around KKS-based operations and maintenance workflows. The main working records are Event Log entries, Work Requests, Work Orders, Preventive Maintenance tasks, PTW/LoA permits, Infobox tasks, and Shift Handovers. The system also includes administration, audit, reports, backup, restore, and KKS import controls.
```

## 1. Login And Navigation

1. Sign in as Shift Leader.
2. Show the left navigation.
3. Point out Operations, Maintenance, Reports, and Administration sections.
4. Explain that Administration appears only for System Administrator.

Key point:

```text
The visible actions depend on the signed-in user's role and responsibilities.
```

## 2. Dashboard

Show:

- Open Event Log entries.
- Events today.
- Active KKS assets.
- Logbook count.
- Latest event entries.

Key point:

```text
The dashboard is the shift overview. It shows current operational attention points and gives quick access to new Event Log entry creation.
```

## 3. KKS Asset Directory

Show:

1. Search for a KKS code or description.
2. Open an asset.
3. Show linked history sections.

Key point:

```text
KKS is the anchor. Event Log, Corrective Maintenance, Preventive Maintenance, and PTW/LoA records can all be linked back to the asset.
```

## 4. Event Log

Show:

1. Create a main entry.
2. Select logbook.
3. Select KKS asset.
4. Add subject and observation.
5. Save.
6. Add a sub-entry.
7. Filter by logbook/state/date/search.
8. Export or print.

Key point:

```text
Operational observations start as Event Log records. Follow-up updates should be added as sub-entries so the history remains together.
```

## 5. Corrective Work Request

Show:

1. Open Event Log entry.
2. Create linked Work Request.
3. Confirm KKS asset is carried through.
4. Fill CMPT consequence, severity, and likelihood.
5. Show calculated priority and response target.
6. Submit request.

Key point:

```text
In this application, the practical SI/PAM notification start is the Work Request. It can be raised from an Event Log entry or directly against KKS.
```

## 6. Corrective Approval And Planning

Show as appropriate:

1. Maintenance Approver approves request.
2. Maintenance Planner plans work order.
3. Add planned dates, workplace requirements, supplies, artisans, and permit requirement.
4. Link or prepare permit when required.

Key point:

```text
Corrective work moves from request to approved work order, then through planning, permit control, execution, and acceptance.
```

## 7. PTW / LoA

Show:

1. Prepare permit.
2. Select form type.
3. Link KKS asset or work order.
4. Issue, receive, clear, and cancel.

Key point:

```text
Permit records are controlled safety documents and can be linked to corrective work requiring access or isolation.
```

## 8. Preventive Maintenance

Show:

1. Schedule type list.
2. Recurrent task list.
3. Create or open a recurrent task.
4. Show primary KKS and asset group.
5. Generate PM task.
6. Show calendar view.
7. Complete task.

Key point:

```text
Preventive Maintenance is schedule-driven. Recurrent tasks generate actual PM work, and completion feeds compliance reporting.
```

## 9. Infobox

Show:

1. My Queue.
2. Team Queue.
3. Claim item.
4. Release item.
5. Filter by source, due state, priority, group, and search.
6. Open history.

Key point:

```text
Infobox is the daily work queue. It routes workflow tasks to the responsible user or group.
```

## 10. Shift Handover

Show:

1. Create draft handover.
2. Include open Event Log entries.
3. Add operational and safety notes.
4. Submit handover.
5. Accept as incoming Shift Leader.
6. Print handover.

Key point:

```text
Shift Handover captures open operational state and creates a controlled transfer between shift leaders.
```

## 11. Reports

Show:

1. Select report date range.
2. Run report.
3. Show activity by day.
4. Show status distribution.
5. Show responsible-area workload.
6. Show CMPT response compliance.
7. Show reliability and downtime metrics.
8. Print management report.

Key point:

```text
Reports connect operational activity, corrective maintenance, preventive compliance, permits, reliability, and backlog into one management view.
```

## 12. Administration

Sign in as System Administrator and show:

- Users & Roles.
- Logbooks.
- Audit Trail.
- System Status.
- KKS Import.
- Recovery points and restore history.

Key point:

```text
Administration is separated from daily workflow. It controls master data, access, audit, KKS imports, and recovery.
```

## 13. Backup And Restore

Show:

1. Create full backup.
2. Verify backup.
3. Download backup.
4. Explain restore confirmation phrase.

Do not restore during a live demo unless using a disposable test database.

Key point:

```text
Restore is intentionally controlled. It requires a verified backup and exact confirmation phrase, and the system creates a safety backup before replacement.
```

## Closing Message

Suggested closing:

```text
The application now covers Morupule B operations logging, KKS asset history, corrective and preventive maintenance, permit control, shift handover, Infobox task routing, reporting, audit, KKS import, backup, and controlled restore. UAT can be completed using the checklist and sign-off template included in the delivery package.
```

## Questions To Expect

| Question | Suggested Answer |
| --- | --- |
| What is the notification called? | The starting maintenance notification is handled as a Work Request. |
| Why is KKS important? | It ties operational and maintenance history back to the exact plant asset. |
| Who receives workflow tasks? | Infobox routes tasks to the responsible user or responsibility group. |
| Can users change roles? | Only System Administrator can change user roles. |
| Can backups be restored? | Yes, only verified backups can be restored, using the exact confirmation phrase. |
| Does the source package include plant data? | No, clean delivery packages exclude database, uploads, backups, staging files, and virtual environments. |
