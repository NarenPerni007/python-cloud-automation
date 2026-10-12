#!/usr/bin/env python3
"""Start or stop EC2 instances on a schedule.

I tag non-prod instances with Schedule=office-hours and run this from
EventBridge: stop at 19:00, start at 08:00 on weekdays. Never ran it
against prod tags -- double check your filters first.
"""

import argparse
import sys

import boto3


def find_instances(ec2, ids, tag_key, tag_value):
    filters = []
    if ids:
        return ec2.describe_instances(InstanceIds=ids)["Reservations"]
    if tag_key and tag_value:
        filters.append({"Name": f"tag:{tag_key}", "Values": [tag_value]})
    return ec2.describe_instances(Filters=filters)["Reservations"]


def main():
    p = argparse.ArgumentParser(
        description="Start or stop EC2 instances by tag or instance ids."
    )
    p.add_argument("--action", choices=["start", "stop"], required=True,
                   help="what to do with the matched instances")
    p.add_argument("--ids", nargs="*", default=[],
                   help="instance ids; if given, tag filters are ignored")
    p.add_argument("--tag-key", default="Schedule",
                   help="tag key to filter on (default: Schedule)")
    p.add_argument("--tag-value", default="office-hours",
                   help="tag value to filter on (default: office-hours)")
    p.add_argument("--region", default="us-east-1")
    p.add_argument("--dry-run", dest="dry_run", action="store_true", default=True,
                   help="only print what would happen (default)")
    p.add_argument("--no-dry-run", dest="dry_run", action="store_false",
                   help="actually perform the action")
    args = p.parse_args()

    ec2 = boto3.client("ec2", region_name=args.region)
    reservations = find_instances(ec2, args.ids, args.tag_key, args.tag_value)

    targets = []
    for r in reservations:
        for inst in r["Instances"]:
            state = inst["State"]["Name"]
            name = next((t["Value"] for t in inst.get("Tags", [])
                         if t["Key"] == "Name"), "-")
            if args.action == "stop" and state == "running":
                targets.append((inst["InstanceId"], name))
            elif args.action == "start" and state == "stopped":
                targets.append((inst["InstanceId"], name))

    if not targets:
        print("no instances to %s" % args.action)
        return 0

    for iid, name in targets:
        print("%s %s (%s)" % (args.action, iid, name))

    if args.dry_run:
        print("dry-run: nothing changed. use --no-dry-run to apply.")
        return 0

    ids = [t[0] for t in targets]
    if args.action == "stop":
        ec2.stop_instances(InstanceIds=ids)
    else:
        ec2.start_instances(InstanceIds=ids)
    print("done: %d instance(s) %sed" % (len(ids), args.action.rstrip("p") + "pp" if args.action == "stop" else args.action + "ed"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
