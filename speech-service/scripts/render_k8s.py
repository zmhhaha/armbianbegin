"""Attach concrete release identities while retaining latest image tags."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import re

import yaml


def render(root: Path, component: str, revision: str, digest: str) -> dict:
    if not re.fullmatch(r"[0-9a-f]{40}", revision):
        raise ValueError("a full source revision is required")
    if not re.fullmatch(r"sha256:[0-9a-f]{64}", digest):
        raise ValueError("an actual registry image digest is required")
    filename = "k8s-device-plugin.yaml" if component == "plugin" else "k8s.yaml"
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    annotations = {"speech.panghuer.top/source-revision": revision,
                   "speech.panghuer.top/image-digest": digest,
                   "speech.panghuer.top/released-at": stamp}
    items = list(yaml.safe_load_all((root / filename).read_text(encoding="utf-8")))
    for item in items:
        if item["kind"] == "Namespace":
            continue
        item["metadata"].setdefault("annotations", {}).update(annotations)
        if item["kind"] in {"Deployment", "DaemonSet"}:
            template = item["spec"]["template"]
            template["metadata"].setdefault("annotations", {}).update(annotations)
            for container in template["spec"]["containers"]:
                if not container["image"].endswith(":latest"):
                    raise ValueError("application images must use latest")
    return {"apiVersion": "v1", "kind": "List", "items": items}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--component", choices=("app", "plugin"), required=True)
    parser.add_argument("--source-revision", required=True)
    parser.add_argument("--image-digest", required=True)
    args = parser.parse_args()
    try:
        result = render(Path(__file__).resolve().parents[1], args.component,
                        args.source_revision, args.image_digest)
    except (ValueError, OSError) as exc:
        parser.error(str(exc))
    print(json.dumps(result))


if __name__ == "__main__":
    main()
