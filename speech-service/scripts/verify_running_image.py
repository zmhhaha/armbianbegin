"""Verify one ready workload's actual image digest against its release record."""
import argparse
import json
import re
import sys


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--container", required=True)
    parser.add_argument("--image-digest", required=True)
    parser.add_argument("--source-revision", required=True)
    args = parser.parse_args()
    if not re.fullmatch(r"sha256:[0-9a-f]{64}", args.image_digest):
        parser.error("a concrete sha256 registry digest is required")
    pods = [p for p in json.load(sys.stdin)["items"]
            if not p["metadata"].get("deletionTimestamp")
            and p.get("status", {}).get("phase") == "Running"]
    if len(pods) != 1:
        raise SystemExit("expected exactly one running workload pod")
    pod = pods[0]
    if pod["metadata"].get("annotations", {}).get("speech.panghuer.top/source-revision") != args.source_revision:
        raise SystemExit("running pod source annotation differs from release")
    states = [c for c in pod["status"].get("containerStatuses", []) if c["name"] == args.container]
    if len(states) != 1 or states[0].get("ready") is not True:
        raise SystemExit("expected container is not ready")
    actual = states[0].get("imageID", "").rsplit("@", 1)[-1]
    if actual != args.image_digest:
        raise SystemExit("running image digest differs from release")
    print(json.dumps({"verified": True, "pod": pod["metadata"]["name"],
                      "uid": pod["metadata"]["uid"], "digest": actual}))


if __name__ == "__main__":
    main()
