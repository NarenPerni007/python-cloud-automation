#!/usr/bin/env python3
"""Delete old EBS snapshots that nothing references.

Keeps snapshots that are:
  - newer than --days
  - attached to a registered AMI
  - shared with another account
  - tagged Keep=true

Everything else gets deleted (or listed with --dry-run).
"""

import argparse
import sys
from datetime import datetime, timedelta, timezone

import boto3


def ami_snapshot_ids(ec2):
    """Snapshot ids referenced by any registered AMI owned by us."""
    ids = set()
    for page in ec2.get_paginator("describe_images").paginate(Owners=["self"]):
        for img in page["Images"]:
            for dev in img.get("BlockDeviceMappings", []):
                snap = dev.get("Ebs", {}).get("SnapshotId")
                if snap:
                    ids.add(snap)
    return ids


def is_shared(ec2, snapshot_id):
    """True if the snapshot is shared with another account (or public)."""
    perms = ec2.describe_snapshot_attribute(
        Attribute="createVolumePermission",
        SnapshotId=snapshot_id,
    ).get("CreateVolumePermissions", [])
    return len(perms) > 0


def tagged_keep(ec2, snapshot_id):
    for tag in ec2.describe_tags(
        Filters=[{"Name": "resource-id", "Values": [snapshot_id]}]
    )["Tags"]:
        if tag["Key"] == "Keep" and tag["Value"].lower() == "true":
            return True
    return False


def main():
    p = argparse.ArgumentParser(
        description="Delete EBS snapshots older than N days that are not in use."
    )
    p.add_argument("--days", type=int, default=30,
                   help="delete snapshots older than this (default: 30)")
    p.add_argument("--region", default="us-east-1")
    p.add_argument("--dry-run", dest="dry_run", action="store_true", default=True,
                   help="only list what would be deleted (default)")
    p.add_argument("--no-dry-run", dest="dry_run", action="store_false",
                   help="actually delete the snapshots")
    args = p.parse_args()

    ec2 = boto3.client("ec2", region_name=args.region)
    cutoff = datetime.now(timezone.utc) - timedelta(days=args.days)
    in_use = ami_snapshot_ids(ec2)

    deleted, skipped, kept = 0, 0, 0
    paginator = ec2.get_paginator("describe_snapshots")
    for page in paginator.paginate(OwnerIds=["self"]):
        for snap in page["Snapshots"]:
            sid = snap["SnapshotId"]
            if snap["StartTime"] >= cutoff:
                skipped += 1
                continue
            if sid in in_use:
                kept += 1
                continue
            if is_shared(ec2, sid):
                kept += 1
                continue
            if tagged_keep(ec2, sid):
                kept += 1
                continue
            size = snap["VolumeSize"]
            print("%s %s %dGiB created %s" % (
                "would delete" if args.dry_run else "deleting",
                sid, size, snap["StartTime"].date()))
            if not args.dry_run:
                ec2.delete_snapshot(SnapshotId=sid)
            deleted += 1

    print("---")
    print("deleted: %d, kept (in use / shared / tagged): %d, skipped (too new): %d"
          % (deleted, kept, skipped))
    if args.dry_run:
        print("dry-run: nothing changed. use --no-dry-run to apply.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
