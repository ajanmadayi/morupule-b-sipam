# S-PULSE Training Plan

This plan is for training S-PULSE users before pilot or production use.

## Training Objectives

By the end of training, users should be able to:

- Sign in and navigate only the modules relevant to their role.
- Search and select KKS assets.
- Record Event Log entries and follow-ups.
- Raise corrective Work Requests using KKS and CMPT.
- Process Infobox tasks.
- Complete role-specific corrective, preventive, permit, and handover actions.
- Understand backup, audit, and administration responsibilities.

## Recommended Sessions

| Session | Audience | Duration | Focus |
| --- | --- | --- | --- |
| 1. System Overview | All users | 45 minutes | Navigation, KKS, Event Log, Infobox, reports. |
| 2. Operations | Shift Leaders | 90 minutes | Event Log, Work Request creation, PTW/LoA, Shift Handover. |
| 3. Corrective Maintenance | Approvers, Planners, Technicians | 120 minutes | Work Request, CMPT, approval, planning, execution, acceptance. |
| 4. Preventive Maintenance | Planners, Technicians, Approvers | 90 minutes | Schedule types, recurrent tasks, generated PM, completion, compliance. |
| 5. Administration | System Administrators | 90 minutes | Users, roles, logbooks, KKS import, audit, backup, restore. |
| 6. UAT Walkthrough | Key users and sponsor | 120 minutes | End-to-end UAT checklist and sign-off. |

## Session 1: System Overview

Audience:

- Shift Leaders
- Maintenance Approvers
- Maintenance Planners
- Technicians
- Administrators

Exercises:

1. Sign in.
2. Open Dashboard.
3. Search KKS Asset Directory.
4. Open My Infobox.
5. Open Reports.
6. Review role-based navigation differences.

Expected result:

- Users understand the main modules and how KKS connects records.

## Session 2: Operations

Audience:

- Shift Leaders
- Operations supervisors

Exercises:

1. Create Event Log main entry with KKS.
2. Add sub-entry update.
3. Filter Event Log by logbook and state.
4. Create Work Request from Event Log.
5. Prepare PTW/LoA record.
6. Create, submit, and accept Shift Handover.
7. Print handover record.

Expected result:

- Shift Leaders can record events, initiate maintenance notification, manage permits, and hand over open plant status.

## Session 3: Corrective Maintenance

Audience:

- Maintenance Approver
- Maintenance Planner
- C&I Technician
- Electrical Technician
- Mechanical Technician

Exercises:

1. Review submitted Work Request in Infobox.
2. Confirm CMPT priority.
3. Approve request.
4. Plan Work Order with dates, resources, supplies, and permit requirement.
5. Complete Work Order as technician.
6. Accept completed work as approver.
7. Review asset history and report impact.

Expected result:

- Maintenance users can move one defect from notification to accepted close-out.

## Session 4: Preventive Maintenance

Audience:

- Maintenance Planner
- Technicians
- Maintenance Approver

Exercises:

1. Create schedule type.
2. Create recurrent task with KKS asset group.
3. Generate PM task.
4. View calendar.
5. Complete PM task.
6. Review PM compliance in Reports.

Expected result:

- Users can plan, generate, complete, and report preventive work.

## Session 5: Administration

Audience:

- System Administrator
- IT/application owner

Exercises:

1. Create user.
2. Change role.
3. Deactivate/reactivate account.
4. Reset password.
5. Create/edit logbook.
6. Review Audit Trail.
7. Validate KKS import.
8. Create and verify backup.
9. Review restore controls.
10. Run data-quality check.

Expected result:

- Administrators can maintain access, master data, audit, KKS, and recovery controls.

## Session 6: UAT Walkthrough

Audience:

- Key users
- Project sponsor
- Application owner

Exercises:

1. Follow `UAT_CHECKLIST.md`.
2. Record pass/fail/conditional result.
3. Record open items.
4. Confirm package and verification evidence.
5. Complete `docs/UAT_SIGNOFF_TEMPLATE.md`.

Expected result:

- UAT decision is documented and ready for pilot/handover approval.

## Training Materials

Use these documents:

- `docs/QUICK_REFERENCE.md`
- `docs/SIPAM_OPERATIONS_GUIDE.md`
- `docs/ROLE_PERMISSION_MATRIX.md`
- `docs/DEMO_WALKTHROUGH.md`
- `UAT_CHECKLIST.md`
- `docs/UAT_SIGNOFF_TEMPLATE.md`

## Trainer Checklist

Before training:

- Confirm app starts.
- Confirm demo accounts are available.
- Confirm KKS data is loaded.
- Confirm backup exists and is verified.
- Prepare one sample Event Log and one sample Work Request.
- Prepare attendance list.

After training:

- Record attendees.
- Record questions and issues.
- Update open-item tracker.
- Confirm which users are ready for UAT.

## Attendance Template

| Name | Department | Role | Session | Signature / Confirmation | Notes |
| --- | --- | --- | --- | --- | --- |
| | | | | | |
| | | | | | |
| | | | | | |
