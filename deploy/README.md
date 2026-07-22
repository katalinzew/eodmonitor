# EOD Agent automatic updates

The updater supports both Python 2.7 and Python 3 on store servers. It only installs
the allowlisted `agent` component at `/SmartId/agent/agent_eod.py`. Release files are
verified with SHA-256 and the manifest is authenticated with HMAC before installation.

## 1. Prepare the central server

Run the database migration:

```bash
psql -U postgres -d eod_monitor -f db/migrations/001_agent_deployments.sql
```

Create the package directory and make it readable by the EOD Monitor process:

```bash
mkdir -p agent_packages
```

The package directory can be overridden with `EOD_AGENT_PACKAGES_DIR`.

## 2. One-time bootstrap on each store

Copy `agent_updater.py`, `agent_config.json`, and the two systemd unit files to the
store. Preserve the store-specific code in `agent_config.json`:

```json
{
  "server_url": "http://10.143.252.2:8000",
  "api_key": "YOUR_AGENT_API_KEY",
  "store_code": "5034",
  "agent_version": "1.5",
  "allow_insecure_http": true
}
```

```bash
mkdir -p /SmartId/agent/backup
cp agent_updater.py /SmartId/agent/agent_updater.py
cp agent_config.json /SmartId/agent/agent_config.json
```

The current `http://` URL is acceptable only on a trusted isolated network or VPN.
For deployment outside that boundary, expose the API through HTTPS and set
`allow_insecure_http` to `false`. Because the updater runs as root, interception of
an unencrypted API key would compromise the update trust chain.

Install and start the timer:

```bash
cp eod-agent-updater.service /etc/systemd/system/
cp eod-agent-updater.timer /etc/systemd/system/
systemctl daemon-reload
systemctl enable --now eod-agent-updater.timer
systemctl list-timers eod-agent-updater.timer
```

Before enabling the timer fleet-wide, test one store manually:

```bash
/usr/bin/python -u /SmartId/agent/agent_updater.py
systemctl status eod-agent.service --no-pager
```

Protect the local configuration:

```bash
chown root:root /SmartId/agent/agent_config.json /SmartId/agent/agent_updater.py
chmod 600 /SmartId/agent/agent_config.json
chmod 700 /SmartId/agent/agent_updater.py
```

## 3. Publish and activate a global release

On the central server, from the repository root:

```bash
python tools/publish_agent_release.py --version 1.6.0 --agent agent_eod.py --activate
```

Stores check for updates every 24 hours. The updater backs up the current file,
validates Python syntax, installs the
new file atomically, restarts `eod-agent.service`, and rolls back if the service does
not remain active.

## 4. Inspect deployment status

```sql
SELECT r.version, d.store_code, d.status, d.current_version, d.message, d.updated_at
FROM agent_deployments d
JOIN agent_releases r ON r.id = d.release_id
ORDER BY d.updated_at DESC;
```

## Security boundaries

- The update API requires the agent API key.
- Manifests are HMAC authenticated.
- Files are SHA-256 verified.
- The updater rejects symbolic-link destinations.
- Only hardcoded components and destinations can be installed.
- No shell commands or arbitrary destination paths are accepted from the server.
