# S-PULSE UAT Sign-Off Template

Use this template after completing `UAT_CHECKLIST.md`.

## Project

| Field | Value |
| --- | --- |
| Application | S-PULSE |
| Test environment URL | |
| Build / package name | |
| Test start date | |
| Test completion date | |
| Test coordinator | |

## Test Participants

| Name | Department | SIPAM Role | Signature / Confirmation | Date |
| --- | --- | --- | --- | --- |
| | Operations | Shift Leader | | |
| | Maintenance | Maintenance Approver | | |
| | Maintenance Planning | Maintenance Planner | | |
| | C&I Maintenance | C&I Technician | | |
| | Electrical Maintenance | Electrical Technician | | |
| | Mechanical Maintenance | Mechanical Technician | | |
| | IT / Application Owner | System Administrator | | |

## Module Acceptance

| Module | Tester | Result | Notes / Open Items |
| --- | --- | --- | --- |
| Login, roles, and security | | Pass / Fail / Conditional | |
| Operations Dashboard | | Pass / Fail / Conditional | |
| Event Log | | Pass / Fail / Conditional | |
| KKS Asset Directory | | Pass / Fail / Conditional | |
| Corrective Maintenance | | Pass / Fail / Conditional | |
| CMPT priority workflow | | Pass / Fail / Conditional | |
| Preventive Maintenance | | Pass / Fail / Conditional | |
| PTW / LoA | | Pass / Fail / Conditional | |
| Infobox | | Pass / Fail / Conditional | |
| Shift Handover | | Pass / Fail / Conditional | |
| Reports | | Pass / Fail / Conditional | |
| Users and Roles | | Pass / Fail / Conditional | |
| Logbook Administration | | Pass / Fail / Conditional | |
| Audit Trail | | Pass / Fail / Conditional | |
| KKS Import | | Pass / Fail / Conditional | |
| Backup and Restore | | Pass / Fail / Conditional | |
| Smoke check | | Pass / Fail / Conditional | |
| Data-quality check | | Pass / Fail / Conditional | |

## Verification Evidence

| Evidence | Result / Reference |
| --- | --- |
| `python -m py_compile ...` | |
| `node --check static\app.js` | |
| `python tools\data_quality_check.py` | |
| `python tools\smoke_check.py --base-url ...` | |
| Latest clean delivery ZIP | |
| Delivery ZIP SHA-256 | |

## Open Items

Track detailed items in `docs/OPEN_ITEMS_REGISTER.md` and summarize blocking items here.

| ID | Module | Description | Priority | Owner | Target Date | Status |
| --- | --- | --- | --- | --- | --- | --- |
| UAT-001 | | | High / Medium / Low | | | Open |
| UAT-002 | | | High / Medium / Low | | | Open |
| UAT-003 | | | High / Medium / Low | | | Open |

## Acceptance Decision

Select one:

- Accepted for pilot use.
- Accepted with listed open items.
- Not accepted; retest required.

Decision:

```text

```

## Final Approval

| Approver | Role / Department | Approval | Date |
| --- | --- | --- | --- |
| | Operations | Approved / Not approved | |
| | Maintenance | Approved / Not approved | |
| | IT / Application Owner | Approved / Not approved | |
| | Project Sponsor | Approved / Not approved | |

## Notes

```text

```
