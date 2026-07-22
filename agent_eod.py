# -*- coding: utf-8 -*-

import os
import re
import json
import time
import socket
import platform
import subprocess
import zipfile
import requests
import datetime as dt

BASE_DIR = "/SmartId/agent"
CONFIG_PATH = os.path.join(BASE_DIR, "agent_config.json")
AGENT_VERSION = "1.8.0"


def load_agent_config():
    try:
        with open(CONFIG_PATH, "r") as handle:
            return json.load(handle)
    except Exception as error:
        print("AGENT CONFIG ERROR:", str(error))
        return {}


AGENT_CONFIG = load_agent_config()
API_URL = AGENT_CONFIG.get("server_url", "http://10.143.252.2:8000").rstrip("/") + "/api/status"
SERVER_URL = AGENT_CONFIG.get("server_url", "http://10.143.252.2:8000").rstrip("/")
API_KEY = AGENT_CONFIG.get("api_key", "test123")
STORE_CODE = AGENT_CONFIG.get("store_code", "5034")

WATCH_DIR = "/home/NCR/webfront-endofday/eodstatus"
CONF_FILE = "/home/NCR/webfront-endofday/conf/scheduled_eod.properties"
SCHEDULE_KEY = "eod.scheduler.start.time"

CHECK_INTERVAL = 60
DISK_PATH = "/"

SERVICES_TO_CHECK = [
    "sidMETIEXPORT.service",
    "sidStorePack.service",
    "sidTrezor.service",
    "idcreader.service"
]

LOG_FILES = {
    "meti_export": "/SmartId/METIEXPORT/logs/meti_export.log",
    "storepack": "/SmartId/STOREPACK/logs/storepack.log",
    "trezor": "/SmartId/TREZOR/logs/trezor.log",
    "srvdemon": "/home/server/tmp/srvdemon.log",
    "ars_daemon": "/home/NCR/ArsPluMnt/logs/daemon_ArsPluMnt.log",
    "ars_general": "/home/NCR/ArsPluMnt/logs/general.log",
}
MAX_LOG_ARCHIVE_BYTES = 20 * 1024 * 1024

REGEX = re.compile(r"^eodstatus(\d{14})\.json$")


def today_ymd():
    return dt.datetime.now().strftime("%Y%m%d")


def extract_eod_file_created_at(filename):
    try:
        m = REGEX.match(filename)
        if not m:
            return None

        ts = m.group(1)
        d = dt.datetime.strptime(ts, "%Y%m%d%H%M%S")

        return d.strftime("%Y-%m-%d %H:%M:%S")

    except Exception as e:
        print("EOD FILE DATE ERROR:", str(e))
        return None


def find_latest_eod_file():
    best_name = None
    best_ts = None

    try:
        for name in os.listdir(WATCH_DIR):
            m = REGEX.match(name)

            if not m:
                continue

            ts = m.group(1)

            if best_ts is None or ts > best_ts:
                best_ts = ts
                best_name = name

        return best_name, best_ts

    except Exception as e:
        print("WATCH DIR ERROR:", str(e))
        return None, None


def read_schedule_time():
    try:
        if not os.path.exists(CONF_FILE):
            return None

        with open(CONF_FILE, "r") as f:
            for line in f:
                line = line.strip()

                if not line or line.startswith("#") or "=" not in line:
                    continue

                key, value = line.split("=", 1)
                key = key.strip()
                value = value.strip()

                if key == SCHEDULE_KEY:
                    m = re.search(r"([01][0-9]|2[0-3]):([0-5][0-9])", value)
                    if m:
                        return m.group(0)

        return None

    except Exception as e:
        print("SCHEDULE ERROR:", str(e))
        return None


def classify_eod(eod):
    status = str(eod.get("status", "")).strip()

    if status in (
        "EOD_ENDED_OK",
        "EOD_ENDED_WITH_WARNINGS",
        "EOD_ENDED_SUCCESSFULLY",
    ):
        return "OK", status

    return "PROBLEM", status or "UNKNOWN"


def get_os_info():
    try:
        if os.path.exists("/etc/os-release"):
            with open("/etc/os-release", "r") as f:
                for line in f:
                    if line.startswith("PRETTY_NAME="):
                        return line.split("=", 1)[1].strip().replace('"', '')

        return platform.platform()

    except Exception:
        return None


def get_uptime_seconds():
    try:
        with open("/proc/uptime", "r") as f:
            return int(float(f.read().split()[0]))
    except Exception:
        return None


def get_cpu_usage_percent():
    try:
        with open("/proc/stat", "r") as f:
            line1 = f.readline()

        time.sleep(1)

        with open("/proc/stat", "r") as f:
            line2 = f.readline()

        cpu1 = [float(x) for x in line1.split()[1:]]
        cpu2 = [float(x) for x in line2.split()[1:]]

        idle1 = cpu1[3]
        idle2 = cpu2[3]

        total1 = sum(cpu1)
        total2 = sum(cpu2)

        total_delta = total2 - total1
        idle_delta = idle2 - idle1

        if total_delta <= 0:
            return 0.0

        usage = 100.0 * (1.0 - (idle_delta / total_delta))
        return round(usage, 1)

    except Exception as e:
        print("CPU ERROR:", str(e))
        return None


def get_ram_info():
    try:
        mem = {}

        with open("/proc/meminfo", "r") as f:
            for line in f:
                parts = line.split(":")

                if len(parts) != 2:
                    continue

                key = parts[0]
                value = parts[1].strip().split()[0]

                try:
                    mem[key] = int(value)
                except Exception:
                    pass

        total_kb = mem.get("MemTotal")
        available_kb = mem.get("MemAvailable")

        if available_kb is None:
            free_kb = mem.get("MemFree", 0)
            buffers_kb = mem.get("Buffers", 0)
            cached_kb = mem.get("Cached", 0)
            available_kb = free_kb + buffers_kb + cached_kb

        if not total_kb:
            return None, None, None

        used_kb = total_kb - available_kb

        total_mb = int(total_kb / 1024)
        used_mb = int(used_kb / 1024)
        percent = round((float(used_kb) / float(total_kb)) * 100.0, 1)

        return total_mb, used_mb, percent

    except Exception as e:
        print("RAM ERROR:", str(e))
        return None, None, None


def get_disk_info():
    try:
        st = os.statvfs(DISK_PATH)

        total = st.f_blocks * st.f_frsize
        free = st.f_bavail * st.f_frsize
        used = total - free

        total_gb = round(total / 1024.0 / 1024.0 / 1024.0, 1)
        used_gb = round(used / 1024.0 / 1024.0 / 1024.0, 1)
        percent = round((float(used) / float(total)) * 100.0, 1) if total else None

        return total_gb, used_gb, percent

    except Exception as e:
        print("DISK ERROR:", str(e))
        return None, None, None


def run_cmd_timeout(cmd, timeout_sec=3):
    try:
        p = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT
        )

        start = time.time()

        while True:
            if p.poll() is not None:
                out = p.stdout.read()

                if not isinstance(out, str):
                    out = out.decode("utf-8", "ignore")

                return out.strip()

            if time.time() - start > timeout_sec:
                try:
                    p.kill()
                except Exception:
                    pass

                return "timeout"

            time.sleep(0.1)

    except Exception:
        return "unknown"


def get_services_status():
    services = {}

    for service in SERVICES_TO_CHECK:
        status = run_cmd_timeout(
            ["systemctl", "is-active", service],
            timeout_sec=3
        )

        if not status:
            status = "unknown"

        services[service] = status

    return services


def get_health_metrics():
    ram_total_mb, ram_used_mb, ram_percent = get_ram_info()
    disk_total_gb, disk_used_gb, disk_percent = get_disk_info()

    return {
        "hostname": socket.gethostname(),
        "agent_version": AGENT_VERSION,
        "os_info": get_os_info(),
        "uptime_seconds": get_uptime_seconds(),
        "cpu_load_1m": get_cpu_usage_percent(),
        "ram_total_mb": ram_total_mb,
        "ram_used_mb": ram_used_mb,
        "ram_percent": ram_percent,
        "disk_total_gb": disk_total_gb,
        "disk_used_gb": disk_used_gb,
        "disk_percent": disk_percent,
        "services_status": get_services_status()
    }


def build_payload():
    filename, file_ts = find_latest_eod_file()
    schedule_time = read_schedule_time()
    today = today_ymd()
    eod_date = dt.datetime.now().strftime("%Y-%m-%d")

    latest_file_created_at = extract_eod_file_created_at(filename) if filename else None
    is_today_file = file_ts is not None and file_ts.startswith(today)

    if not filename:
        payload = {
            "store_code": STORE_CODE,
            "status": "MISSING",
            "eod_file": "",
            "message": "Nu exista niciun fisier EOD",
            "eod_date": eod_date,
            "eod_file_created_at": None,
            "schedule_time": schedule_time,
        }

    elif not is_today_file:
        payload = {
            "store_code": STORE_CODE,
            "status": "MISSING",
            "eod_file": "",
            "message": "Nu exista fisier EOD pentru ziua curenta",
            "eod_date": eod_date,
            "eod_file_created_at": latest_file_created_at,
            "schedule_time": schedule_time,
        }

    else:
        path = os.path.join(WATCH_DIR, filename)

        try:
            with open(path, "r") as f:
                eod = json.load(f)

            status, message = classify_eod(eod)

        except Exception as e:
            status = "PROBLEM"
            message = "JSON invalid: {}".format(str(e))

        payload = {
            "store_code": STORE_CODE,
            "status": status,
            "eod_file": filename,
            "message": message,
            "eod_date": eod_date,
            "eod_file_created_at": latest_file_created_at,
            "schedule_time": schedule_time,
        }

    payload.update(get_health_metrics())
    return payload


def send_payload(payload):
    try:
        r = requests.post(
            API_URL,
            data=json.dumps(payload),
            headers={
                "Content-Type": "application/json",
                "X-API-Key": API_KEY
            },
            timeout=10
        )

        print("")
        print("===================================")
        print("STORE:", STORE_CODE)
        print("TIME:", dt.datetime.now())
        print("STATUS:", r.status_code)
        print("RESPONSE:", r.text)
        print("EOD_FILE:", payload.get("eod_file"))
        print("EOD_FILE_CREATED_AT:", payload.get("eod_file_created_at"))
        print("SERVICES:", payload.get("services_status"))
        print("PAYLOAD:", payload)
        print("===================================")
        print("")

    except Exception as e:
        print("API ERROR:", str(e))


def report_service_command(command_id, status, message):
    try:
        response = requests.post(
            SERVER_URL + "/api/agent-commands/report",
            data=json.dumps({
                "store_code": STORE_CODE,
                "command_id": command_id,
                "status": status,
                "message": message,
            }),
            headers={"Content-Type": "application/json", "X-API-Key": API_KEY},
            timeout=10,
        )
        if response.status_code != 200:
            print("SERVICE COMMAND REPORT ERROR:", response.status_code, response.text)
    except Exception as error:
        print("SERVICE COMMAND REPORT ERROR:", str(error))


def process_service_command():
    try:
        response = requests.get(
            SERVER_URL + "/api/agent-commands/next",
            params={"store_code": STORE_CODE},
            headers={"X-API-Key": API_KEY},
            timeout=10,
        )
        if response.status_code != 200:
            print("SERVICE COMMAND POLL ERROR:", response.status_code, response.text)
            return

        command = response.json().get("command")
        if not command:
            return

        service_name = command.get("service_name")
        action = str(command.get("action", "")).lower()
        command_id = command.get("id")
        if service_name not in SERVICES_TO_CHECK or action not in ("start", "stop", "restart"):
            report_service_command(command_id, "FAILED", "Command rejected by agent allowlist")
            return

        print("SERVICE COMMAND:", action, service_name)
        output = run_cmd_timeout(["systemctl", action, service_name], timeout_sec=30)
        state = run_cmd_timeout(["systemctl", "is-active", service_name], timeout_sec=5)
        succeeded = state == ("inactive" if action == "stop" else "active")
        message = "systemctl output: {}; final state: {}".format(output or "(empty)", state)
        report_service_command(command_id, "SUCCEEDED" if succeeded else "FAILED", message)
        print("SERVICE COMMAND RESULT:", message)
    except Exception as error:
        print("SERVICE COMMAND ERROR:", str(error))


def report_log_collection(request_id, status, message):
    try:
        response = requests.post(
            SERVER_URL + "/api/agent-log-collections/report",
            data=json.dumps({
                "store_code": STORE_CODE,
                "request_id": request_id,
                "status": status,
                "message": message,
            }),
            headers={"Content-Type": "application/json", "X-API-Key": API_KEY},
            timeout=10,
        )
        if response.status_code != 200:
            print("LOG COLLECTION REPORT ERROR:", response.status_code, response.text)
    except Exception as error:
        print("LOG COLLECTION REPORT ERROR:", str(error))


def process_log_collection():
    archive_path = None
    request_id = None
    try:
        response = requests.get(
            SERVER_URL + "/api/agent-log-collections/next",
            params={"store_code": STORE_CODE},
            headers={"X-API-Key": API_KEY},
            timeout=10,
        )
        if response.status_code != 200:
            print("LOG COLLECTION POLL ERROR:", response.status_code, response.text)
            return

        collection = response.json().get("request")
        if not collection:
            return
        request_id = collection.get("id")
        keys = collection.get("log_keys") or []
        if not keys or any(key not in LOG_FILES for key in keys):
            report_log_collection(request_id, "FAILED", "Request contains an invalid log key")
            return

        paths = [LOG_FILES[key] for key in keys]
        missing = [path for path in paths if not os.path.isfile(path)]
        if missing:
            report_log_collection(request_id, "FAILED", "Missing log files: {}".format(", ".join(missing)))
            return
        total_size = sum(os.path.getsize(path) for path in paths)
        if total_size > MAX_LOG_ARCHIVE_BYTES:
            report_log_collection(request_id, "FAILED", "Selected logs exceed 20 MB")
            return

        temp_dir = os.path.join(BASE_DIR, "tmp")
        if not os.path.isdir(temp_dir):
            os.makedirs(temp_dir)
        archive_path = os.path.join(temp_dir, "logs_{}_{}.zip".format(STORE_CODE, request_id))
        with zipfile.ZipFile(archive_path, "w", zipfile.ZIP_DEFLATED) as archive:
            for path in paths:
                archive.write(path, os.path.basename(path))
        if os.path.getsize(archive_path) > MAX_LOG_ARCHIVE_BYTES:
            report_log_collection(request_id, "FAILED", "ZIP archive exceeds 20 MB")
            return

        print("LOG COLLECTION UPLOAD:", archive_path)
        with open(archive_path, "rb") as archive_file:
            upload = requests.post(
                SERVER_URL + "/api/agent-log-collections/{}/upload".format(request_id),
                params={"store_code": STORE_CODE},
                data=archive_file,
                headers={"Content-Type": "application/zip", "X-API-Key": API_KEY},
                timeout=120,
            )
        if upload.status_code != 200:
            report_log_collection(request_id, "FAILED", "Upload failed: {} {}".format(upload.status_code, upload.text[:500]))
            print("LOG COLLECTION UPLOAD ERROR:", upload.status_code, upload.text)
            return
        print("LOG COLLECTION RESULT: archive sent by email")
    except Exception as error:
        print("LOG COLLECTION ERROR:", str(error))
        if request_id is not None:
            report_log_collection(request_id, "FAILED", str(error))
    finally:
        if archive_path and os.path.exists(archive_path):
            try:
                os.remove(archive_path)
            except Exception as error:
                print("LOG COLLECTION CLEANUP ERROR:", str(error))


def main_loop():
    while True:
        try:
            payload = build_payload()
            send_payload(payload)
            process_service_command()
            process_log_collection()

        except Exception as e:
            print("GENERAL ERROR:", str(e))

        print("Sleeping {} seconds...".format(CHECK_INTERVAL))
        time.sleep(CHECK_INTERVAL)


if __name__ == "__main__":
    main_loop()
