# AWS proposal (not provisioned)

Status: proposal for review. No AWS resources exist, no AWS code is in the repository, and nothing here runs without Michael's approval. The local tool stays fully usable without AWS. Prices are on-demand list prices for ca-central-1 (Canada Central) from the AWS Price List API, offer files published between 2026-09-11 and 2026-11-05; free-tier allowances are ignored, so the estimates are upper bounds for these workloads. Taxes are excluded.

## Stage 1: private S3 storage for validated run artifacts

### Architecture

```
laptop / container                                   AWS account (ca-central-1)
------------------                                   --------------------------
workbench run ... ──► runs/<run_id>/                 S3 bucket  cl-workbench-artifacts-<account-id>
workbench verify runs/<run_id>      (must pass)        Block Public Access: all four on
workbench upload runs/<run_id> ───── HTTPS ────────►   Object Ownership: bucket owner enforced (no ACLs)
                                                       Default encryption: SSE-S3
workbench share  runs/<run_id> report.html             Versioning: on
   └─► presigned GET URL, 1 h default ──► recipient    Bucket policy: deny non-TLS requests
                                                       runs/<run_id>/...        complete runs
                                                       diagnostics/<run_id>/... incomplete/failed (opt-in)
```

All AWS code would live in a new module behind the `aws` optional dependency group (`pip install -e '.[aws]'`, adding `boto3`). The core never imports it.

### Commands (proposed)

- `workbench upload RUN_DIR [--bucket NAME] [--allow-incomplete]`: refuses unless `manifest.json` says `complete` and `workbench verify` passes. With `--allow-incomplete`, uploads under `diagnostics/` instead. Never runs automatically.
- `workbench share RUN_DIR FILE [--expires 1h]`: prints a presigned GET URL for one object. Default 1 hour; SigV4 caps presigned URLs at 7 days, and URLs made with temporary credentials stop working when those credentials expire. `recording.h5` is refused unless `--include-raw` is given, so raw recordings stay private by default.
- `workbench remote-verify RUN_ID`: re-checks the S3 copies against the manifest.

### Integrity

1. Run IDs are already unique (`<UTC time>-s<seed>-<6 random hex>`). Upload refuses to overwrite an existing `runs/<run_id>/` prefix.
2. Each file is sent as a single PUT with `ChecksumAlgorithm=SHA256` and the SHA-256 already recorded in the manifest, so S3 rejects a corrupted upload. Single PUT allows objects up to 5 GB; a 30 s recording is 97 MB.
3. After upload, `HeadObject` with checksum mode confirms each stored checksum matches the manifest.
4. An `_UPLOAD_COMPLETE.json` object (file list, checksums, uploader, time) is written last; a prefix without it counts as a partial upload.
5. A local `upload_receipt.json` in the run folder records bucket, keys, version IDs and checksums.

### Retention (decisions for Michael)

Proposed lifecycle rules: `diagnostics/` expires after 30 days; noncurrent object versions expire after 30 days; incomplete multipart uploads are aborted after 7 days. Open question: keep complete runs indefinitely, or expire them after 12 months?

### Required access

One-time setup by an account administrator: create the CloudFormation stack (bucket, bucket policy, lifecycle rules, one IAM policy). Day-to-day, the CLI uses a principal with only this policy, preferably through IAM Identity Center so credentials are short-lived; an IAM user's access keys would also work but must live in `~/.aws/credentials`, never in the repository or the manifest.

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {"Effect": "Allow", "Action": ["s3:ListBucket"], "Resource": "arn:aws:s3:::cl-workbench-artifacts-ACCOUNT_ID"},
    {"Effect": "Allow", "Action": ["s3:PutObject", "s3:GetObject", "s3:GetObjectAttributes"],
     "Resource": "arn:aws:s3:::cl-workbench-artifacts-ACCOUNT_ID/*"}
  ]
}
```

No `s3:DeleteObject`: the CLI cannot delete artifacts; cleanup is a deliberate admin step.

### Cost estimate

#### Assumptions

- Region: ca-central-1 (Canada Central). Prices: AWS Price List API offer files, S3 published 2026-11-04 and data transfer 2026-11-03. On-demand list prices in USD, before tax. AWS bills storage per GB-month where 1 GB = 2^30 bytes (GiB).
- Measured artifact sizes, from four 5 s wall-clock runs with seed 42 on 2026-11-06 (identical across the four):

| File | Bytes |
| --- | --- |
| recording.h5 | 16,604,411 |
| report.html | 165,444 |
| metrics.json | 13,109 |
| manifest.json | about 9,200 |
| channel_metrics.csv | 3,268 |
| worker_result.json, config.json, worker.log | about 1,290 together |
| Total per run | 16,796,723 (0.01564 GiB) |

- Workload A: 100 complete 5 s runs uploaded per month; each run's 8 files go up with 8 PUTs plus 1 PUT for `_UPLOAD_COMPLETE.json`; 8 HEAD requests per run to verify checksums; 1 LIST per upload (overwrite check); 50 presigned views of a report and 10 presigned downloads of a recording per month.
- Retention for this estimate: every complete run is kept, nothing expires, nothing is overwritten (so versioning creates no noncurrent versions), no `diagnostics/` uploads. The figure below is for month 12, when 1,200 runs (18.77 GiB) are stored; storage cost grows by about 0.04 USD each month while nothing is deleted.

#### Breakdown, month 12

| Item | Quantity | Unit price (USD) | Monthly cost (USD) |
| --- | --- | --- | --- |
| S3 Standard storage | 18.77 GiB-month | 0.025 per GB-month (first 50 TB) | 0.469 |
| PUT requests | 900 | 0.0055 per 1,000 | 0.005 |
| LIST requests | 100 | 0.0055 per 1,000 | 0.001 |
| GET and HEAD requests | 860 | 0.0044 per 10,000 | 0.0004 |
| Data transfer in (uploads) | 1.56 GiB | 0.00 | 0.000 |
| Data transfer out to internet | 0.162 GiB (8.3 MB reports, 166 MB recordings) | 0.09 per GB | 0.015 |
| Total | | | about 0.49 |

The earlier figure of 0.52 USD used decimal megabytes, an estimated 16.5 MB per run and 10 PUTs per run; the table above replaces it with measured sizes, binary GB as AWS bills, and the request counts the proposed commands would make. Averaged over the first 12 months, storage is about 0.25 USD per month.

Included services: S3 (storage, requests) and AWS data transfer. SSE-S3 encryption, Block Public Access, versioning, lifecycle rules and bucket policies have no separate charge.

Excluded from the estimate: taxes; the AWS free tier (it would lower the bill); AWS Support plans; CloudFormation (no charge for AWS-native resources); IAM and IAM Identity Center (no charge); CloudTrail data events, KMS customer-managed keys, S3 Replication, S3 Storage Lens advanced metrics, CloudWatch alarms (none of these are proposed); requests made from the AWS console by hand; stage 2 compute, below.

Workload B (heavier): 1,000 runs of 30 s per month, all kept. New data 97 GB per month; storage at month 12 is 1.17 TB, about 29 USD per month, which is why the retention decision matters. Request and transfer costs stay under 1 USD per month unless recordings are downloaded often (0.09 USD per GB).

Not used, to avoid cost: KMS customer keys (SSE-S3 is free), S3 replication, CloudTrail data events, CloudWatch alarms.

### Infrastructure and teardown

Infrastructure would be one CloudFormation template in `infra/s3-artifacts.yaml`, deployed with `aws cloudformation deploy`. Teardown:

1. List what will be lost: `aws s3 ls s3://BUCKET --recursive --summarize`.
2. Empty the bucket including old versions (`aws s3api delete-objects` over `list-object-versions` output, or the console's Empty bucket action). This is permanent.
3. `aws cloudformation delete-stack --stack-name cl-workbench-artifacts`.
4. Remove the local credential profile.

### Acceptance criteria for stage 1

1. With no AWS packages installed, every local command and test still works.
2. `upload` refuses incomplete or unverified runs (unless `--allow-incomplete`, which writes to `diagnostics/`) and refuses to overwrite an existing run prefix.
3. After upload, every object's S3 SHA-256 equals the manifest value, and `_UPLOAD_COMPLETE.json` exists.
4. Anonymous access to the bucket and to any object without a valid presigned URL returns 403.
5. A presigned URL works before expiry and returns 403 after it; `recording.h5` cannot be shared without `--include-raw`.
6. A test deliberately corrupts a byte before upload and the upload is rejected.
7. Teardown instructions run end to end on a test stack and leave no billable resources.
8. Measured cost for the first month is under 2 USD for workload A, checked in Cost Explorer.

## Stage 2 (later): on-demand containerised runs

Evaluation only, after stage 1 works. Measured in this container during a 30 s wall-clock run (4 CPUs): up to 8 Python processes (CLI, worker, simulator data producer, recording process and helpers), peak `/dev/shm` use 17 MB, summed resident memory about 450 MB (an overcount, since shared pages are counted per process), a 97 MB recording, and complete integrity checks. A 5 s run takes about 7.3 s of wall-clock time.

| Option | Fit | Concerns to test |
| --- | --- | --- |
| ECS Fargate `RunTask` | On-demand, nothing always on, per-second billing with a one-minute minimum (per AWS pricing page; verify) | `/dev/shm` size and multiprocessing behaviour on Fargate; whether 1 vCPU keeps the recording process up with the producer in wall-clock mode |
| AWS Batch on Fargate | Same runtime plus a job queue | More moving parts than one user needs |
| Lambda | Cheap for short jobs | The SDK uses multiple processes and shared memory; Lambda's environment is known to lack `/dev/shm`, so Python multiprocessing primitives may fail. Would need a test before considering it |
| EC2 on demand | Full control, matches local tests | Instance lifecycle to manage; easy to leave running |

Tentative choice: ECS Fargate `RunTask`, 2 vCPU and 4 GB, in a public subnet with a public IP to reach ECR and S3 (avoids a NAT gateway). The task runs `workbench run`, then `workbench upload`, then exits. Before recommending it firmly: measure `/dev/shm` and integrity on Fargate at 1 and 2 vCPU, measure image size and start time, and confirm accelerated-mode behaviour there.

Licensing: a container image that contains cl-sdk is Sharing under CC BY-NC 4.0. The image would stay in a private ECR repository, carry the cl-sdk license and attribution, and not be used commercially without permission (see licensing.md).

Cost for workload A run on Fargate (100 tasks per month, 2 minutes billed each, an assumption to be measured):

| Item | Quantity | Unit price (USD) | Monthly cost (USD) |
| --- | --- | --- | --- |
| Fargate vCPU | 2 vCPU x 3.33 h | 0.04456 per vCPU-hour | 0.30 |
| Fargate memory | 4 GB x 3.33 h | 0.004865 per GB-hour | 0.06 |
| Public IPv4 address while tasks run | 3.33 h | 0.005 per hour | 0.02 |
| ECR image storage | about 1 GB (estimate, to measure) | 0.10 per GB-month | 0.10 |
| CloudWatch Logs ingestion | about 1 MB | 0.55 per GB | < 0.01 |
| Total, on top of stage 1 | | | about 0.48 |

Out of scope at every stage until asked: dashboards, a public API, databases, always-on services.

## Before anything is provisioned

Michael reviews this document and decides: AWS account and region, retention policy, IAM Identity Center or IAM user, bucket name, and whether stage 1 goes ahead. Then the stage 1 code and template are written and tested against a throwaway stack, with teardown verified, before any long-lived bucket is created.
