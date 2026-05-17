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

echo "🔧 Patching systemd user service..."
mkdir -p "${HOME}/.config/systemd/user"
cp "${SCRIPT_DIR}/../uzi-robot.service" "${HOME}/.config/systemd/user/uzi-robot.service"
systemctl --user daemon-reload

if [[ "$1" == "enable" ]]; then
	# Allow the user service manager to run at boot without a login session.
	sudo loginctl enable-linger "$USER"
fi

systemctl --user "$1" --now uzi-robot.service
systemctl --user status uzi-robot.service --no-pager

echo "✅ Service patched!"
