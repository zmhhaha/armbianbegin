#!/usr/bin/env python3
"""Render PPT's public OAuth ConfigMaps without changing services or the template.

Requires Python 3.11+ and PyYAML. The separate ppt-owner ConfigMap is never read,
rendered or changed; manage its email list independently.
Client values are intentionally absent from normal output and error messages.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import sys
import tomllib

import yaml


TEMPLATE = Path(__file__).with_name("ppt-proxy-configmap.yaml")
OWNER_EMAILS_FILE = "/owner/emails"
CLIENT_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,255}\Z", re.ASCII)
CLIENT_LINE = re.compile(r"(?m)^[ \t]*client_id[ \t]*=[^\r\n]*$")


class ConfigurationError(ValueError):
    """Messages are fixed codes and must never contain configuration values."""


class PublicConfigDumper(yaml.SafeDumper):
    pass


def _public_string(dumper, value):
    return dumper.represent_scalar("tag:yaml.org,2002:str", value,
                                   style="|" if "\n" in value else None)


PublicConfigDumper.add_representer(str, _public_string)


def validate_client_id(client_id):
    if type(client_id) is not str or not CLIENT_ID.fullmatch(client_id):
        raise ConfigurationError("invalid_client_id")
    folded = client_id.casefold().replace("-", "_")
    if (any(marker in folded for marker in
            ("required", "placeholder", "change_me", "changeme", "your_", "todo",
             "replace_me", "replace_with"))
            or folded in {"xxx", "client_id", "client_id_here"}):
        raise ConfigurationError("placeholder_client_id")


def render_configuration(client_id, *, template=TEMPLATE):
    validate_client_id(client_id)
    try:
        documents = list(yaml.safe_load_all(Path(template).read_text(encoding="utf-8")))
        if (len(documents) != 2 or any(type(doc) is not dict for doc in documents)
                or any(doc.get("apiVersion") != "v1" or doc.get("kind") != "ConfigMap"
                       or doc.get("metadata", {}).get("namespace") != "ppt-service-test"
                       for doc in documents)):
            raise ConfigurationError("invalid_canonical_template")
        by_name = {doc["metadata"]["name"]: doc for doc in documents}
        if set(by_name) != {"ppt-auth", "ppt-oidc"}:
            raise ConfigurationError("invalid_canonical_template")
        auth, oidc = by_name["ppt-auth"]["data"], by_name["ppt-oidc"]["data"]
        proxy = oidc["oauth2-proxy.cfg"]
        parsed_proxy = tomllib.loads(proxy)
        if (not isinstance(auth.get("OIDC_AUDIENCE"), str)
                or parsed_proxy.get("client_id") != auth["OIDC_AUDIENCE"]
                or len(CLIENT_LINE.findall(proxy)) != 1
                or auth.get("INVITATION_EMAILS_FILE") != OWNER_EMAILS_FILE
                or parsed_proxy.get("authenticated_emails_file") != OWNER_EMAILS_FILE
                or "allowed-emails" in oidc or "INVITATION_SUBJECTS" in auth):
            raise ConfigurationError("invalid_canonical_template")
        auth["OIDC_AUDIENCE"] = client_id
        oidc["oauth2-proxy.cfg"] = CLIENT_LINE.sub(
            lambda _match: "client_id = " + json.dumps(client_id), proxy)
        return yaml.dump_all(documents, Dumper=PublicConfigDumper,
                             sort_keys=False, allow_unicode=True)
    except (OSError, KeyError, TypeError, AttributeError, yaml.YAMLError,
            tomllib.TOMLDecodeError):
        raise ConfigurationError("invalid_canonical_template") from None


def configure(client_id, output, *, template=TEMPLATE):
    content = render_configuration(client_id, template=template)
    # O_EXCL rejects existing files and symlinks. No source template is rewritten.
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(os.fspath(output), flags, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as target:
        target.write(content)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--client-id", required=True)
    parser.add_argument("--output", type=Path, required=True,
                        help="new output file; existing paths are rejected")
    args = parser.parse_args(argv)
    try:
        configure(args.client_id, args.output)
    except FileExistsError:
        print("error: output_exists", file=sys.stderr)
        return 2
    except ConfigurationError as error:
        print("error: " + str(error), file=sys.stderr)
        return 2
    except OSError:
        print("error: configuration_file_io_failed", file=sys.stderr)
        return 2
    print("PPT public configuration rendered; no deployment performed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
