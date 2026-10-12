#!/usr/bin/env python3
"""Dump a CSV inventory of all S3 buckets.

Columns: bucket, region, size_bytes, versioning, default_encryption.

Size is summed from object listings, which is slow on huge buckets --
I cap it at --max-objects per bucket and mark truncated results.
For real fleet-wide size tracking, S3 Storage Lens is the right tool;
this is for quick audits.
"""

import argparse
import csv
import sys

import boto3
from botocore.exceptions import ClientError


def bucket_region(s3, name):
    loc = s3.get_bucket_location(Bucket=name)["LocationConstraint"]
    return loc or "us-east-1"


def bucket_size(s3, name, max_objects):
    total, count, truncated = 0, 0, False
    paginator = s3.get_paginator("list_objects_v2")
    try:
        for page in paginator.paginate(Bucket=name):
            for obj in page.get("Contents", []):
                total += obj["Size"]
                count += 1
                if count >= max_objects:
                    truncated = True
                    break
            if truncated:
                break
    except ClientError as e:
        return None, "error: %s" % e.response["Error"]["Code"]
    return total, "truncated at %d objects" % max_objects if truncated else "ok"


def versioning_status(s3, name):
    try:
        v = s3.get_bucket_versioning(Bucket=name).get("Status", "Suspended")
        return v
    except ClientError:
        return "unknown"


def encryption_status(s3, name):
    try:
        s3.get_bucket_encryption(Bucket=name)
        return "enabled"
    except ClientError as e:
        if e.response["Error"]["Code"] == "ServerSideEncryptionConfigurationNotFoundError":
            return "disabled"
        return "unknown"


def main():
    p = argparse.ArgumentParser(
        description="Write a CSV inventory of S3 buckets to --output."
    )
    p.add_argument("--output", default="report.csv",
                   help="csv file to write (default: report.csv)")
    p.add_argument("--max-objects", type=int, default=100000,
                   help="max objects to list per bucket when summing size "
                        "(default: 100000)")
    args = p.parse_args()

    s3 = boto3.client("s3")
    buckets = s3.list_buckets()["Buckets"]

    rows = []
    for b in buckets:
        name = b["Name"]
        print("scanning %s ..." % name)
        region = bucket_region(s3, name)
        # listing must happen against the bucket's region
        regional = boto3.client("s3", region_name=region)
        size, note = bucket_size(regional, name, args.max_objects)
        rows.append({
            "bucket": name,
            "region": region,
            "size_bytes": size if size is not None else "",
            "size_note": note,
            "versioning": versioning_status(regional, name),
            "default_encryption": encryption_status(regional, name),
        })

    with open(args.output, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["bucket", "region", "size_bytes",
                                          "size_note", "versioning",
                                          "default_encryption"])
        w.writeheader()
        w.writerows(rows)

    print("wrote %d bucket(s) to %s" % (len(rows), args.output))
    return 0


if __name__ == "__main__":
    sys.exit(main())
