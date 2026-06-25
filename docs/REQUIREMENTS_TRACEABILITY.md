# Morupule B SIPAM Requirements Traceability

This matrix maps the delivered Morupule B SIPAM application features to the functional areas expected from the supplied SI/PAM and CMMS workflow references.

## Traceability Status

| Status | Meaning |
| --- | --- |
| Delivered | Implemented in the current web application. |
| Delivered - Admin Controlled | Implemented and restricted to System Administrator or defined responsible role. |
| Delivered - Reported | Implemented and visible through reports, audit, or exports. |
| Future Option | Not required for current handover, but can be expanded later. |

## Functional Matrix

| Requirement Area | Delivered Module / Feature | Status | Verification Path |
| --- | --- | --- | --- |
| User login and role-based access | Login screen, session handling, role permissions, admin-only pages | Delivered | Sign in as Shift Leader and Administrator; review `docs/ROLE_PERMISSION_MATRIX.md`. |
| Operations dashboard | Open events, events today, asset count, logbook count, latest entries | Delivered | Dashboard screen and `/api/dashboard`. |
| KKS-based record creation | Asset picker in Event Log, Corrective, PM, PTW/LoA | Delivered | Search KKS in each workflow form. |
| KKS asset hierarchy | Asset Directory, parent/child navigation, asset history | Delivered | KKS Asset Directory screen. |
| Event Log main entries | Create, list, filter, print, export, close | Delivered | Event Log screen, CSV export, print view. |
| Event Log sub-entries | Follow-up comments under main entries | Delivered | Select Event Log entry and create sub-entry. |
| Logbook visibility | Source logbook and Shift Leader copy visibility | Delivered | Event Log logbook filter and Logbook Admin. |
| Shift handover | Draft, submit, accept, captured open entries, print | Delivered | Shift Handover screen and print view. |
| Work Request / notification | Corrective Work Request created directly or from Event Log | Delivered | Corrective Maintenance screen. |
| CMPT prioritization | Severity, likelihood, consequence category, priority, target date | Delivered | Create Work Request and inspect calculated priority. |
| Work Request approval | Approve or decline submitted request | Delivered | Maintenance Approver role workflow. |
| Work Order planning | Planned dates, workplace requirements, expected hours, permit requirement | Delivered | Work Order detail after approval. |
| Supplies and artisan planning | Add/remove supplies and artisans | Delivered | Corrective work order planning panel. |
| PTW/LoA gate | Link permit requirement before execution where needed | Delivered | Work Order permit gate and PTW/LoA module. |
| Corrective execution | Technician completion, actual hours, failure mode, cause, downtime | Delivered | Complete work order as department technician. |
| Corrective acceptance | Accept completed work or return for rework | Delivered | Maintenance Approver acceptance action. |
| Preventive schedule types | Calendar interval, meter options, tolerance, strategy | Delivered | Preventive Maintenance schedule type panel. |
| Recurrent PM tasks | Create recurrent task with KKS and asset group | Delivered | Preventive Maintenance recurrent task form. |
| PM generation | Generate by task or monthly calendar | Delivered | PM task generate actions and calendar. |
| PM completion | Complete generated tasks with hours and summary | Delivered | PM task detail action. |
| Permit to Work | Prepare, issue, receive, clear, cancel | Delivered | Permits & LoA screen. |
| Limitation of Access | Electrical/mechanical LoA form workflow | Delivered | Permits & LoA form type selection. |
| Infobox | Assigned tasks, team queue, claim/release, filters, history | Delivered | My Infobox screen. |
| Escalations | Due/overdue/escalated indicators and history | Delivered - Reported | Infobox metrics and history. |
| Reports | Activity, status, workload, downtime, MTTR, CMPT, PM, backlog | Delivered - Reported | Reports screen and print management report. |
| Audit trail | Authenticated create/update/delete tracking | Delivered - Admin Controlled | Administration > Audit Trail. |
| User administration | Create user, change role/status, reset password | Delivered - Admin Controlled | Administration > Users & Roles. |
| Logbook administration | Create/edit logbook and entry role | Delivered - Admin Controlled | Administration > Logbooks. |
| KKS import | Validate and commit `.xlsx` KKS register | Delivered - Admin Controlled | Administration > KKS Import. |
| Backup | Full retained backup, manifest, download | Delivered - Admin Controlled | Administration > System Status. |
| Restore | Verify backup, confirmation phrase, safety backup, restore history | Delivered - Admin Controlled | Administration > System Status. |
| Data quality verification | Offline SQLite integrity and master-data checks | Delivered - Reported | `python tools\data_quality_check.py`. |
| Smoke verification | Live route/login/header checks | Delivered - Reported | `python tools\smoke_check.py --base-url ...`. |
| Clean source delivery | Package builder with manifest and runtime-data exclusion | Delivered - Reported | `python tools\package_delivery.py`. |

## Document-To-Module Mapping

| Source Reference Area | Application Coverage |
| --- | --- |
| KKS code instruction | KKS import, Asset Directory, KKS picker, asset history, KKS-linked workflows. |
| Event Log references | Event Log module, logbooks, sub-entries, Shift Leader copy visibility, exports, print. |
| Corrective Maintenance references | Work Request, CMPT, approval, planning, execution, acceptance, reports. |
| Preventive Maintenance references | Schedule types, recurrent tasks, generated tasks, calendar, completion, compliance. |
| CMMS workflow procedure | Infobox routing, approval steps, planning, permits, work execution, close-out, audit. |
| Work Request / CMPT selection | Corrective Work Request creation and CMPT priority calculation. |
| SI/PAM workflow | End-to-end module navigation, role tasks, administration, reporting, backup/restore. |

## Current Known Operational Constraints

- The development Flask server is for pilot/demo use; production should use approved hosting with HTTPS.
- Live smoke check requires Flask dependencies installed in the active Python environment.
- Source delivery ZIP excludes live database, uploads, backups, KKS staging files, and virtual environment.
- Restore should only be tested in an approved non-production environment unless a controlled outage is approved.

## Acceptance Evidence

Use these files together for final acceptance:

- `UAT_CHECKLIST.md`
- `docs/SIPAM_OPERATIONS_GUIDE.md`
- `docs/ROLE_PERMISSION_MATRIX.md`
- `docs/DEPLOYMENT_RUNBOOK.md`
- `docs/DELIVERY_INDEX.md`
- `tools\data_quality_check.py`
- `tools\smoke_check.py`
- `tools\package_delivery.py`
