#!/bin/bash
# Run on the Pi as fpp: bash deploy.sh
set -euo pipefail

# Load the steps before git pull can update this script.
deploy() {
    cd "$(dirname "${BASH_SOURCE[0]}")"
    if [[ "$EUID" -eq 0 ]]; then
        echo "Run as your normal Pi user: bash deploy.sh (without sudo)." >&2
        return 1
    fi
    if [[ "$(git symbolic-ref --quiet --short HEAD)" != main ]]; then
        echo "Switch to main before deploying: git switch main" >&2
        return 1
    fi
    if ! git diff --quiet || ! git diff --cached --quiet; then
        echo "Commit or stash tracked changes before deploying." >&2
        return 1
    fi
    sudo -v
    git pull
    # Refresh the unit as well as the code; preserve existing password/settings.
    sudo bash install_dashboard_service.sh
    echo "Deployed $(git rev-parse --short HEAD). The show starts automatically."
}

deploy "$@"
