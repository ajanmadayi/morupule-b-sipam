# Morupule B SIPAM Operations Guide

This guide explains the working language and day-to-day flow of the Morupule B SIPAM web application.

## Key Terms

| Term | Meaning In This Application |
| --- | --- |
| KKS | Plant asset identification code. Every operational or maintenance record should be linked to the correct KKS asset where possible. |
| Event Log | Operations record for plant events, observations, shift information, and follow-up items. |
| Main Entry | Primary Event Log record. Use this for a new observation or plant event. |
| Sub-Entry | Follow-up comment or update under an existing Event Log main entry. |
| Work Request | Corrective maintenance notification raised from an Event Log or directly against a KKS asset. This is the SI/PAM equivalent of starting a maintenance notification. |
| CMPT | Corrective Maintenance Prioritization Tool. It calculates priority and response target from consequence and likelihood. |
| Work Order | Approved and planned corrective maintenance job created from a Work Request. |
| Infobox | User or team task inbox. Workflow actions appear here for the responsible role or person. |
| Recurrent Task | Preventive maintenance plan that generates scheduled PM work. |
| PTW / LoA | Permit to Work / Limitation of Access safety control records linked to work or KKS assets. |
| Shift Handover | Controlled transfer of current plant status, open events, and operational notes between shift leaders. |

## Starting A Corrective Notification

In SI/PAM language, the practical starting point is a **Work Request**.

Recommended Morupule B flow:

1. Search and select the correct KKS asset.
2. Create an Event Log main entry if the issue was observed by Operations.
3. From that Event Log entry, create a Work Request.
4. Complete CMPT fields so the priority and response target are calculated.
5. Submit the request to Maintenance Approver.
6. Track the next action in Infobox.

Direct Work Request creation is also available when Maintenance identifies the defect without a preceding operational log entry.

## Operations Workflow

1. **Dashboard**
   - Review open events, events today, active assets, and logbook counts.
   - Start a new Event Log entry for current plant information.

2. **Event Log**
   - Record the event subject, observation, informant, date, state, and KKS asset.
   - Add sub-entries for updates instead of creating unrelated duplicate entries.
   - Use filters for date, logbook, state, and search.
   - Close entries only when no further follow-up is required.

3. **Shift Handover**
   - Create a draft handover near the end of shift.
   - Include relevant open Event Log entries.
   - Submit the handover to the incoming Shift Leader.
   - Incoming Shift Leader accepts after review.

## Corrective Maintenance Workflow

1. **Work Request**
   - Raised from Event Log or directly against KKS.
   - Includes type of work, department, observation, CMPT consequence, severity, likelihood, and priority.

2. **Approval**
   - Maintenance Approver accepts or declines the Work Request.
   - Declined requests remain visible for audit and history.

3. **Planning**
   - Maintenance Planner confirms work scope, planned dates, workplace requirements, expected hours, supplies, artisans, and permit requirement.

4. **Permit Gate**
   - If work requires PTW/LoA, prepare and link the safety permit before execution.

5. **Execution**
   - Assigned technician completes the work and records actual hours, completion summary, failure mode, cause, and downtime/restoration where applicable.

6. **Acceptance**
   - Maintenance Approver accepts completed work or returns it for rework.
   - Accepted work can close the linked Event Log follow-up.

## Preventive Maintenance Workflow

1. Administrator or Planner maintains schedule types.
2. Planner creates recurrent tasks with primary KKS, asset group, interval, tolerance, department, and work schedule.
3. Planner generates PM tasks by recurrent task or calendar month.
4. Technician completes generated tasks with notes and hours.
5. Reports show PM compliance and overdue workload.

## PTW / LoA Workflow

1. Prepare permit with form type, KKS asset, work description, location, isolations, precautions, and recipient.
2. Issue permit.
3. Receive permit at worksite.
4. Clear permit after work completion.
5. Cancel permit for final closure.

The application blocks unsafe duplicate active permits for the same work where applicable.

## Infobox Working Rules

- **My Queue** shows actions assigned or available to the signed-in user.
- **Team Queue** shows shared responsibility-group work.
- Claiming an item removes it from shared handling until released or completed.
- Use source, due status, priority, group, and search filters for daily follow-up.
- Completed history remains available for audit and export.

## Administration Workflow

Administrator tasks:

- Create and deactivate users.
- Reset passwords.
- Assign roles.
- Maintain logbooks and entry permissions.
- Review Audit Trail.
- Validate and commit KKS register imports.
- Create, verify, download, delete, and restore recovery points.

Do not delete or rename KKS assets manually in production. Use controlled KKS import validation.

## Reports

Use Reports for:

- Event and work activity by date.
- Status distribution.
- Responsible-area workload.
- CMPT response compliance.
- Equipment downtime and MTTR.
- Repeat-failure assets.
- PM compliance.
- Corrective backlog and backlog age.

Print the management report for weekly or monthly review.

## Minimum Daily Routine

Shift Leader:

1. Review Dashboard and Infobox at start of shift.
2. Check open Event Log entries.
3. Record new plant events with KKS where possible.
4. Raise Work Requests for defects requiring Maintenance.
5. Prepare and submit Shift Handover before shift end.

Maintenance Planner:

1. Review Infobox team queue.
2. Plan approved corrective work.
3. Review permit requirements.
4. Generate due PM work.
5. Monitor backlog and overdue tasks.

Maintenance Approver:

1. Review submitted Work Requests.
2. Approve or decline based on scope and priority.
3. Accept completed work or return for rework.
4. Review CMPT response compliance.

System Administrator:

1. Check Audit Trail for unusual changes.
2. Create and verify recovery points.
3. Keep user access current.
4. Validate KKS imports before committing changes.
