#!/usr/bin/env python3

# Copyright 2025 Canonical Ltd.
# See LICENSE file for licensing details.

"""Add an announcement to a gatus-k8s-operator charm."""

import argparse
import logging
import os
import sys
from datetime import datetime
from pathlib import Path

import yaml

logger = logging.getLogger(__name__)

def main(type: str, message: str, archived: bool, config_file: Path) -> None:
    """Add an announcement to a gatus-k8s-operator charm."""
    data = {}
    if os.path.exists(config_file):
        try:
            with open(config_file, "r") as f:
                data = yaml.safe_load(f) or {}
        except Exception as e:
            print(f"Error reading YAML: {e}")
            sys.exit(1)

    if 'announcements' not in data or data['announcements'] is None:
        data['announcements'] = []

    # create the new announcement
    new_announcement = {
        "timestamp": datetime.now().isoformat(),
        "type": type,
        "message": message,
        "archived": archived,
    }
    data['announcements'].append(new_announcement)

    try:
        with open(config_file, "w") as f:
            yaml.dump(data, f, default_flow_style=False, sort_keys=False)
            print(f"Announcement added and maintenance performed on {config_file}")
    except Exception as e:
        print(f"Error writing to file: {e}")
        sys.exit(1)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--type",
        type=str,
        help="The type of announcement.",
        required=True,
    )
    parser.add_argument(
        "--message",
        type=str,
        help="The message to display to users.",
        required=True,
    )
    parser.add_argument(
        "--archived",
        type=bool,
        help="Whether to archive the announcement.",
        default=False,
    )
    parser.add_argument(
        "--config-file",
        type=str,
        help="The path to the announcement config file.",
        default="/config/announcements.yaml",
    )
    args = parser.parse_args()
    config_file = Path(args.config_file)

    main(type=args.type, message=args.message, archived=args.archived, config_file=config_file)
