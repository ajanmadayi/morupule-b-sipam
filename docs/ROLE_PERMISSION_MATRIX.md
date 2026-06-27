# S-PULSE Role And Permission Matrix

This matrix describes the intended operating permissions for each user role in the S-PULSE application.

## Roles

| Role | Main Responsibility |
| --- | --- |
| Shift Leader | Operations logbook control, plant event recording, shift handover, and permit initiation. |
| Maintenance Approver | Review Work Requests, approve/decline corrective work, accept completed work, and monitor performance. |
| Maintenance Planner | Plan corrective work orders, maintain PM schedules, generate PM tasks, and manage workload. |
| C&I Technician | Execute Control & Instrumentation work and update assigned tasks. |
| Electrical Technician | Execute Electrical work and update assigned tasks. |
| Mechanical Technician | Execute Mechanical work and update assigned tasks. |
| System Administrator | Manage users, logbooks, audit, KKS import, backup, restore, and all administrative control. |

## Module Access

| Module | Shift Leader | Approver | Planner | C&I Tech | Elec Tech | Mech Tech | Admin |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Dashboard | View | View | View | View | View | View | View |
| Infobox | Own/team queue | Own/team queue | Own/team queue | Own/team queue | Own/team queue | Own/team queue | All as assigned |
| Event Log | Create/update allowed logbooks | View | View | View dept logbooks | View dept logbooks | View dept logbooks | Full |
| Shift Handover | Create/submit/accept | View | View | View | View | View | Full |
| KKS Asset Directory | View | View | View | View | View | View | View/admin import |
| Corrective Maintenance | Raise request | Approve/accept | Plan/control | Execute C&I | Execute Electrical | Execute Mechanical | Full |
| Preventive Maintenance | View operations PM | View | Create/plan/generate | Execute C&I PM | Execute Electrical PM | Execute Mechanical PM | Full |
| PTW / LoA | Prepare/issue workflow | View/approve as assigned | Link to work plan | Receive/clear as assigned | Receive/clear as assigned | Receive/clear as assigned | Full |
| Reports | View | View/print | View/print | View own work | View own work | View own work | Full |
| Users & Roles | No | No | No | No | No | No | Full |
| Logbook Administration | No | No | No | No | No | No | Full |
| Audit Trail | No | No | No | No | No | No | Full |
| System Status / Backup | No | No | No | No | No | No | Full |
| KKS Import | No | No | No | No | No | No | Full |

## Corrective Workflow Permissions

| Workflow Step | Responsible Role |
| --- | --- |
| Create Work Request | Shift Leader, Maintenance roles, or Administrator |
| Calculate CMPT priority | Creator during Work Request creation |
| Approve or decline Work Request | Maintenance Approver or Administrator |
| Plan Work Order | Maintenance Planner or Administrator |
| Add supplies/artisans | Maintenance Planner or Administrator |
| Define permit requirement | Maintenance Planner or Administrator |
| Execute C&I work | C&I Technician or Administrator |
| Execute Electrical work | Electrical Technician or Administrator |
| Execute Mechanical work | Mechanical Technician or Administrator |
| Submit completion for acceptance | Assigned executing role or Administrator |
| Accept completed work | Maintenance Approver or Administrator |
| Return for rework | Maintenance Approver or Administrator |

## Preventive Workflow Permissions

| Workflow Step | Responsible Role |
| --- | --- |
| Create schedule type | Maintenance Planner or Administrator |
| Create recurrent task | Maintenance Planner or Administrator |
| Add asset group | Maintenance Planner or Administrator |
| Generate PM task | Maintenance Planner or Administrator |
| Complete generated PM task | Department technician or Administrator |
| Suspend/reactivate recurrent task | Maintenance Planner or Administrator |
| Review PM compliance | Planner, Approver, Administrator |

## PTW / LoA Workflow Permissions

| Workflow Step | Responsible Role |
| --- | --- |
| Prepare permit | Shift Leader or Administrator |
| Issue permit | Shift Leader or Administrator |
| Receive permit | Assigned work recipient or Administrator |
| Clear permit | Assigned work recipient or Administrator |
| Cancel permit | Shift Leader or Administrator |
| Link permit to work order | Maintenance Planner or Administrator |

## Infobox Rules

- Items are assigned to users or responsibility groups.
- Users may claim available group items to show ownership.
- Claimed items can be released back to the group queue.
- Completed workflow actions remain visible in history.
- Administrators can review wider workflow records through reports and audit trail.

## Administration Rules

System Administrator can:

- Create users.
- Change roles.
- Activate/deactivate accounts.
- Reset passwords.
- Maintain logbooks.
- View audit logs.
- Validate and commit KKS imports.
- Create and verify backups.
- Restore from verified backups with the exact confirmation phrase.

System Administrator should not:

- Share the administrator account for daily operations.
- Restore production data without approved outage and backup confirmation.
- Commit KKS imports without reviewing validation results.

## Recommended S-PULSE Role Assignment

| Function | Suggested SIPAM Role |
| --- | --- |
| Operations Shift Leader | Shift Leader |
| Maintenance Superintendent / Engineer approving work | Maintenance Approver |
| Maintenance Planning Office | Maintenance Planner |
| C&I Workshop | C&I Technician |
| Electrical Workshop | Electrical Technician |
| Mechanical Workshop | Mechanical Technician |
| IT / Application Owner | System Administrator |

## UAT Sign-Off Notes

During UAT, each role should sign in and confirm:

- Only relevant navigation is visible.
- Infobox items match their responsibility.
- Restricted admin pages are blocked for non-admin users.
- Workflows move to the next correct role.
- Audit trail records successful create/update/delete actions.
