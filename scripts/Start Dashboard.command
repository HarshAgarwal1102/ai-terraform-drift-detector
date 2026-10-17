#!/usr/bin/env bash
# Double-click in Finder (macOS) to start the drift dashboard in a Terminal window.
# Same as: scripts/run_dashboard.sh   (see that script for the options)
cd "$(dirname "$0")/.." && exec scripts/run_dashboard.sh "$@"
