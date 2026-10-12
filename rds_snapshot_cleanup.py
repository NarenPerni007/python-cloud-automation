#!/usr/bin/env python3
"""Delete old manual RDS snapshots.

Only touches manual snapshots (never automated ones) older than --days.
Skips anything tagged Keep=true.
"""

import argparse
import sys
from datetime import datetime, timedelta, timezone

import boto3


def tagged_keep(rds, arn):
    try:
        tags = rds.list_tags_for_resource(ResourceName=arn)["TagList"]
    except rds.exceptions.ClientError:
        return False
    return any(t["Key"] == "Keep" and t["Value"].lower() == "true" for t in tags)


def main():
    p = argparse.ArgumentParser(
        description="Delete manual RDS snapshots older than N days."
    )
    p.add_argument("--days", type=int, default=30,
                   help="delete snapshots older than this (default: 30)")
    p.add_argument("--region", default="us-east-1")
    p.add_argument("--dry-run", dest="dry_run", action="store_true", default=True,
                   help="only list what would be deleted (default)")
    p.add_argument("--no-dry-run", dest="dry_run", action="store_false",
                   help="actually delete the snapshots")
    args = p.parse_args()

    rds = boto3.client("rds", region_name=args.region)
    cutoff = datetime.now(timezone.utc) - timedelta(days=args.days)

    deleted, kept, skipped = 0, 0, 0
    paginator = rds.get_paginator("describe_db_snapshots")
    for page in paginator.paginate(SnapshotType="manual"):
        for snap in page["DBSnapshots"]:
            name = snap["DBSnapshotIdentifier"]
            if snap["SnapshotCreateTime"] >= cutoff:
                skipped += 1
                continue
            if tagged_keep(rds, snap["DBSnapshotArn"]):
                kept += 1
                continue
            print("%s %s (%s) created %s" % (
                "would delete" if args.dry_run else "deleting",
                name, snap["DBInstanceIdentifier"],
                snap["SnapshotCreateTime"].date()))
            if not args.dry_run:
                rds.delete_db_snapshot(DBSnapshotIdentifier=name)
            deleted += 1

    print("---")
    print("deleted: %d, kept (tagged): %d, skipped (too new): %d"
          % (deleted, kept, skipped))
    if args.dry_run:
        print("dry-run: nothing changed. use --no-dry-run to apply.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
