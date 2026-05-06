#!/bin/bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

usage() {
	echo "📋 Usage: $0 enable|disable" >&2
	exit 1
}

[[ $# -eq 1 ]] || usage
case "$1" in
	enable | disable) ;;
	*) usage ;;
esac

echo "🔧 Patching systemd service..."
sudo cp "${SCRIPT_DIR}/../uzi-robot.service" /etc/systemd/system/uzi-robot.service
sudo systemctl daemon-reload
sudo systemctl "$1" --now uzi-robot.service
sudo systemctl status uzi-robot.service

echo "✅ Service patched!"
