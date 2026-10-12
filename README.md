# python-cloud-automation

Small scripts I use to keep AWS bills and clutter down. Nothing fancy --
they find idle resources and clean up old snapshots. Everything runs in
dry-run mode by default so you can see what would happen before it touches
anything.

## Setup

```bash
pip install -r requirements.txt
# uses your normal AWS credentials (env vars, ~/.aws/credentials, or IAM role)
```

## Scripts

**ec2_scheduler.py** -- start/stop instances by tag. I run this from
EventBridge to shut dev boxes down at night.

```bash
# see what it would stop
python ec2_scheduler.py --action stop
# actually stop them
python ec2_scheduler.py --action stop --no-dry-run
# target specific instances instead of tags
python ec2_scheduler.py --action start --ids i-0123456789abcdef0 --no-dry-run
```

**ebs_snapshot_cleanup.py** -- delete EBS snapshots older than 30 days,
unless they're attached to an AMI or tagged `Keep=true`.

```bash
python ebs_snapshot_cleanup.py --days 60 --no-dry-run
```

**rds_snapshot_cleanup.py** -- same idea for manual RDS snapshots
(never touches automated backups).

```bash
python rds_snapshot_cleanup.py --no-dry-run
```

**s3_inventory_report.py** -- CSV of every bucket: region, size,
versioning, encryption. Size comes from listing objects, so it's slow on
big buckets -- capped at 100k objects per bucket by default.

```bash
python s3_inventory_report.py --output buckets.csv
```

## IAM

The instance profile / user running these needs (scope the resources down
to your account):

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "ec2:DescribeInstances", "ec2:DescribeSnapshots", "ec2:DescribeImages",
        "ec2:DescribeTags", "ec2:StartInstances", "ec2:StopInstances",
        "ec2:DeleteSnapshot",
        "rds:DescribeDBSnapshots", "rds:DeleteDBSnapshot",
        "rds:ListTagsForResource",
        "s3:ListAllMyBuckets", "s3:ListBucket",
        "s3:GetBucketLocation", "s3:GetBucketVersioning", "s3:GetEncryptionConfiguration"
      ],
      "Resource": "*"
    }
  ]
}
```

## Scheduling

I run the scheduler and cleanups on EventBridge cron rules (or plain cron
on a bastion box). Example: stop dev instances at 19:00 on weekdays.

Tested with Python 3.11 on Amazon Linux 2023.
