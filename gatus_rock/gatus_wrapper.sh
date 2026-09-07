#!/bin/bash

# Copyright 2025 Canonical Ltd.
# See LICENSE file for licensing details.

set -euo pipefail

python3 /gatus/render_config.py

export GATUS_CONFIG_PATH=/config
exec /gatus/bin/gatus
