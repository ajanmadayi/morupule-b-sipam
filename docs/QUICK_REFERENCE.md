# Morupule B SIPAM Quick Reference

Short daily-use guide for common SIPAM roles.

## Shift Leader

Daily start:

1. Open Dashboard.
2. Review open Event Log entries.
3. Review My Infobox.
4. Check active PTW/LoA records if relevant.

Create plant event:

1. Open Event Log.
2. Select **New main entry**.
3. Select correct logbook.
4. Search/select KKS asset.
5. Enter subject, informant, observation, and state.
6. Save.

Raise maintenance notification:

1. Open the Event Log entry.
2. Select create Work Request.
3. Confirm KKS asset.
4. Enter work name, department, observation, and CMPT fields.
5. Submit.

End of shift:

1. Open Shift Handover.
2. Create draft.
3. Add summary, operational notes, safety notes.
4. Include open Event Log entries.
5. Submit to incoming Shift Leader.

## Maintenance Approver

Daily routine:

1. Open My Infobox.
2. Filter source to Requests or Orders.
3. Review submitted Work Requests.
4. Approve or decline.
5. Review completed Work Orders.
6. Accept or return for rework.

Approval check:

- Correct KKS asset selected.
- CMPT priority is reasonable.
- Observation is clear.
- Department and work type are correct.
- Urgent work has clear target date.

## Maintenance Planner

Daily routine:

1. Open My Infobox.
2. Review approved corrective requests.
3. Plan work orders.
4. Add planned start/end.
5. Add supplies and artisans.
6. Set permit requirement.
7. Generate due Preventive Maintenance work.
8. Review backlog in Reports.

Corrective planning:

1. Open Corrective Maintenance.
2. Select approved request.
3. Update Work Order planning details.
4. Add materials/supplies if needed.
5. Add responsible artisans.
6. Confirm PTW/LoA requirement.

Preventive planning:

1. Open Preventive Maintenance.
2. Review schedule types.
3. Create or update recurrent tasks.
4. Generate PM tasks from recurrent task or calendar.

## Technician

Daily routine:

1. Open My Infobox.
2. Filter to assigned work.
3. Open Work Order or Preventive task.
4. Confirm KKS asset and work scope.
5. Confirm permit status if required.
6. Complete task with actual hours and work summary.

Corrective completion:

1. Open assigned Work Order.
2. Record completion summary.
3. Select failure mode if applicable.
4. Record failure cause.
5. Enter actual man-hours.
6. Enter downtime/restoration times if applicable.
7. Submit for acceptance.

Preventive completion:

1. Open generated PM task.
2. Enter completion notes.
3. Enter actual hours.
4. Save completion.

## System Administrator

Daily/weekly routine:

1. Review Audit Trail.
2. Check System Status.
3. Create full backup.
4. Verify recovery point.
5. Confirm latest KKS imports.
6. Maintain users and logbooks.

User management:

1. Open Users & Roles.
2. Create named account.
3. Assign role.
4. Deactivate accounts no longer required.
5. Reset password when approved.

KKS import:

1. Open KKS Import.
2. Select `.xlsx` register.
3. Validate.
4. Review duplicates and inferred parents.
5. Commit only after approval.

Restore:

- Restore only from verified backup.
- Restore only with approval.
- Use exact phrase:

```text
RESTORE MORUPULE B SIPAM
```

## Common Buttons

| Button / Action | Meaning |
| --- | --- |
| New main entry | Create a new Event Log record. |
| New sub-entry | Add follow-up to selected Event Log record. |
| Create work request | Start corrective maintenance notification. |
| Approve | Accept Work Request for planning. |
| Plan | Define dates, resources, supplies, and permit requirements. |
| Complete | Submit work execution result. |
| Accept | Close completed work after review. |
| Claim | Take responsibility for an Infobox item. |
| Release | Return claimed item to team queue. |
| Generate | Create PM task from recurrent schedule. |
| Verify backup | Check retained recovery point integrity. |

## Minimum Good Record

For any operational or maintenance record, include:

- Correct KKS asset.
- Clear subject/name.
- Clear observation or work description.
- Responsible department.
- Target or planned dates where applicable.
- Final completion notes before closure.
