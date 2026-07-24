#!/bin/sh
set -eu

BASE_DIR="/SmartId/agent"
BACKUP_DIR="${BASE_DIR}/backup"
PYTHON="/usr/bin/python"
AGENT_SERVICE="eod-agent.service"
UPDATER_SERVICE="eod-agent-updater.service"
UPDATER_TIMER="eod-agent-updater.timer"
SERVER_URL="${EOD_SERVER_URL:-http://10.143.252.2:8000}"
API_KEY="${EOD_API_KEY:-test123}"
EXPECTED_AGENT_VERSION="${EOD_EXPECTED_AGENT_VERSION:-1.8.0}"

usage() {
    echo "Usage: sh install.sh STORE_CODE"
    echo "Example: sh install.sh 5002"
}

if [ "$(id -u)" -ne 0 ]; then
    echo "ERROR: Run this installer as root."
    exit 1
fi

if [ "$#" -ne 1 ]; then
    usage
    exit 1
fi

STORE_CODE="$1"
case "$STORE_CODE" in
    ""|*[!A-Za-z0-9_-]*)
        echo "ERROR: Invalid store code: $STORE_CODE"
        exit 1
        ;;
esac

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)

for required_file in \
    "${SCRIPT_DIR}/agent_updater.py" \
    "${SCRIPT_DIR}/${UPDATER_SERVICE}" \
    "${SCRIPT_DIR}/${UPDATER_TIMER}"
do
    if [ ! -f "$required_file" ]; then
        echo "ERROR: Missing bundle file: $required_file"
        exit 1
    fi
done

if [ ! -x "$PYTHON" ]; then
    echo "ERROR: ${PYTHON} is not available."
    exit 1
fi

if [ ! -f "${BASE_DIR}/agent_eod.py" ]; then
    echo "ERROR: Existing agent not found at ${BASE_DIR}/agent_eod.py"
    exit 1
fi

if ! systemctl cat "$AGENT_SERVICE" 2>/dev/null | grep -q "${BASE_DIR}/agent_eod.py"; then
    echo "ERROR: ${AGENT_SERVICE} does not run ${BASE_DIR}/agent_eod.py"
    exit 1
fi

if ! "$PYTHON" -c "import requests" >/dev/null 2>&1; then
    echo "ERROR: Python module 'requests' is not installed for ${PYTHON}."
    exit 1
fi

mkdir -p "$BASE_DIR" "$BACKUP_DIR" "${BASE_DIR}/tmp"
STAMP=$(date +%Y%m%d%H%M%S)

cp -p "${BASE_DIR}/agent_eod.py" "${BACKUP_DIR}/agent_eod.py.before-bootstrap.${STAMP}"

if [ -f "${BASE_DIR}/agent_updater.py" ]; then
    cp -p "${BASE_DIR}/agent_updater.py" "${BACKUP_DIR}/agent_updater.py.before-bootstrap.${STAMP}"
fi

if [ -f "${BASE_DIR}/agent_config.json" ]; then
    cp -p "${BASE_DIR}/agent_config.json" "${BACKUP_DIR}/agent_config.json.before-bootstrap.${STAMP}"
fi

if [ -f "${BASE_DIR}/update_state.json" ]; then
    mv "${BASE_DIR}/update_state.json" "${BACKUP_DIR}/update_state.json.before-bootstrap.${STAMP}"
fi

cp "${SCRIPT_DIR}/agent_updater.py" "${BASE_DIR}/agent_updater.py"
cp "${SCRIPT_DIR}/${UPDATER_SERVICE}" "/etc/systemd/system/${UPDATER_SERVICE}"
cp "${SCRIPT_DIR}/${UPDATER_TIMER}" "/etc/systemd/system/${UPDATER_TIMER}"

sed -i '/RandomizedDelaySec/d;/Persistent=true/d' "/etc/systemd/system/${UPDATER_TIMER}"

umask 077
cat > "${BASE_DIR}/agent_config.json" <<EOF
{
  "server_url": "${SERVER_URL}",
  "api_key": "${API_KEY}",
  "store_code": "${STORE_CODE}",
  "agent_version": "1.5",
  "allow_insecure_http": true
}
EOF

chown root:root \
    "${BASE_DIR}/agent_updater.py" \
    "${BASE_DIR}/agent_config.json" \
    "/etc/systemd/system/${UPDATER_SERVICE}" \
    "/etc/systemd/system/${UPDATER_TIMER}"
chmod 700 "${BASE_DIR}/agent_updater.py"
chmod 600 "${BASE_DIR}/agent_config.json"
chmod 644 \
    "/etc/systemd/system/${UPDATER_SERVICE}" \
    "/etc/systemd/system/${UPDATER_TIMER}"

"$PYTHON" -m py_compile "${BASE_DIR}/agent_updater.py"

echo ""
echo "Configuration:"
echo "  Store:  ${STORE_CODE}"
echo "  Server: ${SERVER_URL}"
echo ""
echo "Starting the first agent update..."

cd "$BASE_DIR"
"$PYTHON" -u "${BASE_DIR}/agent_updater.py"

if ! grep -Fq "AGENT_VERSION = \"${EXPECTED_AGENT_VERSION}\"" "${BASE_DIR}/agent_eod.py"; then
    echo "ERROR: Expected agent ${EXPECTED_AGENT_VERSION} was not installed."
    echo "Check that store ${STORE_CODE} exists and is ACTIVE in EOD Monitor."
    exit 1
fi

if ! systemctl is-active --quiet "$AGENT_SERVICE"; then
    echo "ERROR: ${AGENT_SERVICE} is not active after the update."
    exit 1
fi

systemctl daemon-reload
systemctl enable "$UPDATER_TIMER"
if systemctl is-active --quiet "$UPDATER_TIMER"; then
    systemctl restart "$UPDATER_TIMER"
else
    systemctl start "$UPDATER_TIMER"
fi

echo ""
echo "Installation completed successfully."
grep "AGENT_VERSION" "${BASE_DIR}/agent_eod.py" | head -1
systemctl is-active "$AGENT_SERVICE"
systemctl is-active "$UPDATER_TIMER"
echo ""
echo "Verify this store in EOD Monitor:"
echo "  ${SERVER_URL}/store/${STORE_CODE}"
