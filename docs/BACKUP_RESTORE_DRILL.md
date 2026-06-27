# S-PULSE Backup And Restore Drill

Use this drill in a test environment before pilot or production approval.

## Purpose

Confirm that S-PULSE recovery points can be created, verified, downloaded, and restored safely.

Do not perform restore testing against production data unless an approved outage and rollback plan are in place.

## Roles

| Role | Responsibility |
| --- | --- |
| System Administrator | Runs backup, verification, and restore steps. |
| Application Owner | Approves restore drill and validates result. |
| Operations Representative | Confirms Event Log and handover data after restore. |
| Maintenance Representative | Confirms corrective/preventive/permit data after restore. |

## Pre-Drill Checklist

| Check | Status | Notes |
| --- | --- | --- |
| Test environment identified | Pending / Done | |
| Users notified | Pending / Done | |
| Current database location known | Pending / Done | |
| Upload folder location known | Pending / Done | |
| Backup folder location known | Pending / Done | |
| Administrator login available | Pending / Done | |
| No production users active | Pending / Done | |

## Drill Steps

### 1. Baseline Check

Run:

```powershell
python tools\data_quality_check.py
```

Record:

| Item | Value |
| --- | --- |
| Integrity | |
| Foreign key issues | |
| KKS asset count | |
| Event Log entry count | |
| Work Request count | |
| User count | |

### 2. Create Recovery Point

1. Sign in as System Administrator.
2. Open **Administration > System Status**.
3. Select **Create full backup**.
4. Confirm the recovery point appears in the list.

Record:

| Item | Value |
| --- | --- |
| Backup filename | |
| Created by | |
| Created at | |
| Archive size | |

### 3. Verify Recovery Point

1. Select verify action for the backup.
2. Confirm integrity becomes verified.
3. Confirm no foreign-key issues are reported.

Record:

| Item | Value |
| --- | --- |
| Verification result | |
| Verified at | |
| SHA-256 | |

### 4. Download Recovery Point

1. Download the verified backup.
2. Store in approved test location.
3. Confirm ZIP opens.
4. Confirm manifest exists.

Record:

| Item | Value |
| --- | --- |
| Download path | |
| ZIP opens | Yes / No |
| Manifest present | Yes / No |

### 5. Make Test Change

Make a small approved test change that can be checked after restore.

Recommended:

- Create a test Event Log entry with subject:

```text
RESTORE DRILL TEMP ENTRY
```

Record:

| Item | Value |
| --- | --- |
| Test record type | |
| Test record number / ID | |
| Test record subject | |

### 6. Restore Verified Backup

1. Open **Administration > System Status**.
2. Confirm selected backup is verified.
3. Select restore.
4. Enter exact phrase:

```text
RESTORE MORUPULE B SIPAM
```

5. Confirm restore completes.
6. Confirm safety backup is retained.

Record:

| Item | Value |
| --- | --- |
| Restore source filename | |
| Safety backup filename | |
| Restored by | |
| Restored at | |

### 7. Post-Restore Validation

Run:

```powershell
python tools\data_quality_check.py
```

Confirm:

| Check | Status | Notes |
| --- | --- | --- |
| Integrity is ok | Pending / Done | |
| Foreign key issues are 0 | Pending / Done | |
| Test change made after backup is gone | Pending / Done | |
| Event Log opens | Pending / Done | |
| Corrective Maintenance opens | Pending / Done | |
| Preventive Maintenance opens | Pending / Done | |
| PTW/LoA opens | Pending / Done | |
| KKS Asset Directory opens | Pending / Done | |
| Restore history shows completed restore | Pending / Done | |

## Acceptance Criteria

The drill passes when:

- Backup is created.
- Backup verifies successfully.
- Backup downloads successfully.
- Restore requires exact confirmation phrase.
- Restore creates safety backup.
- Database integrity is `ok` after restore.
- Foreign-key issues are `0` after restore.
- Test change made after backup is removed by restore.
- Key modules open after restore.
- Restore history is recorded.

## Drill Result

Select one:

- Passed.
- Passed with observations.
- Failed; corrective action required.

Result:

```text

```

## Observations

| ID | Observation | Owner | Target Date | Status |
| --- | --- | --- | --- | --- |
| BRD-001 | | | | Open |
| BRD-002 | | | | Open |

## Approval

| Name | Role | Approval | Date |
| --- | --- | --- | --- |
| | System Administrator | Approved / Not approved | |
| | Application Owner | Approved / Not approved | |
| | Operations Representative | Approved / Not approved | |
| | Maintenance Representative | Approved / Not approved | |
