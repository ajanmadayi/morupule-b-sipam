# S-PULSE Open Items Register

Use this register during UAT, pilot preparation, and handover meetings.

## Priority Definitions

| Priority | Meaning |
| --- | --- |
| Critical | Blocks UAT or pilot; no acceptable workaround. |
| High | Important workflow issue; workaround exists but should be fixed before go-live. |
| Medium | Does not block pilot; should be planned and tracked. |
| Low | Cosmetic, documentation, training, or future improvement. |

## Status Definitions

| Status | Meaning |
| --- | --- |
| Open | Item recorded and awaiting action. |
| In Progress | Owner is working on the item. |
| Ready For Retest | Fix or response is ready for user verification. |
| Closed | Verified and accepted. |
| Deferred | Approved for later phase. |
| Rejected | Not accepted as a defect or change. |

## Register

| ID | Date Raised | Module | Description | Priority | Blocks Pilot | Owner | Target Date | Status | Resolution / Notes |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| MB-SIPAM-001 | | | | Critical / High / Medium / Low | Yes / No | | | Open | |
| MB-SIPAM-002 | | | | Critical / High / Medium / Low | Yes / No | | | Open | |
| MB-SIPAM-003 | | | | Critical / High / Medium / Low | Yes / No | | | Open | |

## Review Routine

During UAT:

1. Review open Critical and High items daily.
2. Confirm whether each item blocks pilot.
3. Assign one owner per item.
4. Add target date for every open item.
5. Move fixed items to Ready For Retest.
6. Close only after user verification.

During pilot:

1. Review register at start and end of week.
2. Separate defects from enhancement requests.
3. Keep production data/recovery items as Critical until resolved.
4. Keep training/documentation items visible but do not mix them with blocking defects.

## Common Modules

Use these module names for consistency:

- Access / Login
- Dashboard
- Event Log
- KKS Asset Directory
- Corrective Maintenance
- CMPT
- Preventive Maintenance
- PTW / LoA
- Infobox
- Shift Handover
- Reports
- Users & Roles
- Logbooks
- Audit Trail
- KKS Import
- Backup / Restore
- Deployment
- Documentation / Training

## Sign-Off Rule

Before pilot approval:

- No Critical open items.
- High open items must have approved workaround and owner.
- Medium/Low items may be deferred with sponsor approval.
- The UAT sign-off template must reference this register.
