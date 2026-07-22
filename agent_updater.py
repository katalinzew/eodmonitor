# -*- coding: utf-8 -*-
from __future__ import print_function

import hashlib
import hmac
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time

import requests


BASE_DIR = "/SmartId/agent"
CONFIG_PATH = os.path.join(BASE_DIR, "agent_config.json")
STATE_PATH = os.path.join(BASE_DIR, "update_state.json")
BACKUP_DIR = os.path.join(BASE_DIR, "backup")
SERVICE_NAME = "eod-agent.service"
REQUEST_TIMEOUT = 30

ALLOWED_COMPONENTS = {
    "agent": os.path.join(BASE_DIR, "agent_eod.py"),
}


def load_json(path, default=None):
    try:
        with open(path, "r") as handle:
            return json.load(handle)
    except Exception:
        return default if default is not None else {}


def save_json_atomic(path, payload):
    parent = os.path.dirname(path)
    descriptor, temporary = tempfile.mkstemp(prefix=".update-", dir=parent)
    try:
        with os.fdopen(descriptor, "w") as handle:
            json.dump(payload, handle, sort_keys=True, indent=2)
            handle.flush()
            os.fsync(handle.fileno())
        os.rename(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def canonical_bytes(payload):
    value = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    if not isinstance(value, bytes):
        value = value.encode("utf-8")
    return value


def verify_manifest(payload, api_key):
    received = payload.get("signature") or ""
    unsigned = dict(payload)
    unsigned.pop("signature", None)
    key = api_key if isinstance(api_key, bytes) else api_key.encode("utf-8")
    expected = hmac.new(key, canonical_bytes(unsigned), hashlib.sha256).hexdigest()
    received_bytes = received if isinstance(received, bytes) else received.encode("ascii")
    expected_bytes = expected if isinstance(expected, bytes) else expected.encode("ascii")
    return hmac.compare_digest(received_bytes, expected_bytes) if hasattr(hmac, "compare_digest") else received_bytes == expected_bytes


def sha256_file(path):
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        while True:
            chunk = handle.read(1024 * 1024)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def report(config, release_id, status, version, message=""):
    try:
        requests.post(
            config["server_url"].rstrip("/") + "/api/agent-updates/report",
            data=json.dumps({
                "store_code": config["store_code"],
                "release_id": release_id,
                "status": status,
                "current_version": version,
                "message": message[:2000],
            }),
            headers={"X-API-Key": config["api_key"], "Content-Type": "application/json"},
            timeout=REQUEST_TIMEOUT,
        )
    except Exception as error:
        print("UPDATE REPORT ERROR:", str(error))


def download_component(config, release_id, file_entry):
    component = file_entry.get("component")
    if component not in ALLOWED_COMPONENTS:
        raise ValueError("Component is not allowed: {0}".format(component))

    response = requests.get(
        config["server_url"].rstrip("/") + "/api/agent-updates/files/{0}/{1}".format(release_id, component),
        headers={"X-API-Key": config["api_key"]},
        stream=True,
        timeout=REQUEST_TIMEOUT,
    )
    response.raise_for_status()

    descriptor, temporary = tempfile.mkstemp(prefix=".agent-download-", dir=BASE_DIR)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            for chunk in response.iter_content(64 * 1024):
                if chunk:
                    handle.write(chunk)
            handle.flush()
            os.fsync(handle.fileno())
        if sha256_file(temporary) != file_entry.get("sha256"):
            raise ValueError("SHA-256 verification failed for {0}".format(component))
        return temporary
    except Exception:
        if os.path.exists(temporary):
            os.unlink(temporary)
        raise


def validate_python(path):
    try:
        with open(path, "rb") as handle:
            compile(handle.read(), path, "exec")
    except Exception as error:
        raise ValueError("Python syntax validation failed: {0}".format(error))


def install_release(config, manifest):
    release_id = manifest["release_id"]
    version = manifest["version"]
    files = manifest.get("files") or []
    if not files:
        raise ValueError("Release contains no files")

    if not os.path.isdir(BACKUP_DIR):
        os.makedirs(BACKUP_DIR)

    downloaded = {}
    backups = {}
    try:
        report(config, release_id, "DOWNLOADING", version)
        for entry in files:
            component = entry.get("component")
            downloaded[component] = download_component(config, release_id, entry)
            if component == "agent":
                validate_python(downloaded[component])

        for component, temporary in list(downloaded.items()):
            destination = ALLOWED_COMPONENTS[component]
            if os.path.islink(destination):
                raise ValueError("Refusing to replace symbolic link: {0}".format(destination))
            backup = os.path.join(BACKUP_DIR, "{0}.{1}.bak".format(component, int(time.time())))
            if os.path.exists(destination):
                shutil.copy2(destination, backup)
                backups[component] = backup
                os.chmod(temporary, os.stat(destination).st_mode)
            os.rename(temporary, destination)
            downloaded[component] = None

        if subprocess.call(["systemctl", "restart", SERVICE_NAME]) != 0:
            raise RuntimeError("systemctl restart failed")
        time.sleep(3)
        if subprocess.call(["systemctl", "is-active", "--quiet", SERVICE_NAME]) != 0:
            raise RuntimeError("Agent service is not active after restart")

        save_json_atomic(STATE_PATH, {"version": version, "release_id": release_id, "installed_at": int(time.time())})
        report(config, release_id, "INSTALLED", version)
        print("Agent updated successfully to", version)
    except Exception as error:
        for component, backup in backups.items():
            if os.path.isfile(backup):
                shutil.copy2(backup, ALLOWED_COMPONENTS[component])
        if backups:
            subprocess.call(["systemctl", "restart", SERVICE_NAME])
            report(config, release_id, "ROLLED_BACK", config.get("agent_version", ""), str(error))
        else:
            report(config, release_id, "FAILED", config.get("agent_version", ""), str(error))
        raise
    finally:
        for temporary in downloaded.values():
            if temporary and os.path.exists(temporary):
                os.unlink(temporary)


def main():
    config = load_json(CONFIG_PATH)
    required = ("server_url", "api_key", "store_code")
    if any(not config.get(key) for key in required):
        raise ValueError("Missing updater configuration in {0}".format(CONFIG_PATH))
    if not config["server_url"].lower().startswith("https://") and not config.get("allow_insecure_http"):
        raise ValueError("HTTPS is required for root-level updates; set allow_insecure_http only on a trusted private network")

    state = load_json(STATE_PATH, {"version": config.get("agent_version", "1.5")})
    response = requests.get(
        config["server_url"].rstrip("/") + "/api/agent-updates/latest",
        params={"store_code": config["store_code"], "current_version": state.get("version", "")},
        headers={"X-API-Key": config["api_key"]},
        timeout=REQUEST_TIMEOUT,
    )
    response.raise_for_status()
    manifest = response.json()
    if not manifest.get("update_available"):
        print("Agent is up to date")
        return
    if not verify_manifest(manifest, config["api_key"]):
        raise ValueError("Manifest signature verification failed")
    install_release(config, manifest)


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print("AGENT UPDATE ERROR:", str(error))
        sys.exit(1)
