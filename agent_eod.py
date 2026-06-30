# -*- coding: utf-8 -*-
# Agent EOD pentru fiecare magazin
# Ruleaza local pe serverul magazinului
# Verifica fisierul EOD, citeste schedule-ul si trimite health metrics catre API

import os
import re
import json
import time
import socket
import platform
import requests
import datetime as dt


# =========================
# CONFIGURARE AGENT
# =========================

# API-ul central unde agentul trimite datele
API_URL = "http://10.143.252.2:8000/api/status"

# Cheia simpla de autentificare catre API
API_KEY = "test123"

# Codul magazinului.
# IMPORTANT: pe fiecare magazin trebuie schimbat codul.
STORE_CODE = "5034"

# Versiunea agentului, ca sa stim ce versiune ruleaza pe fiecare magazin
AGENT_VERSION = "1.2"

# Folderul unde apar fisierele EOD
WATCH_DIR = "/home/NCR/webfront-endofday/eodstatus"

# Fisierul din care citim ora programata de EOD
CONF_FILE = "/home/NCR/webfront-endofday/conf/scheduled_eod.properties"

# Cheia din fisierul de configurare
SCHEDULE_KEY = "eod.scheduler.start.time"

# La cate secunde trimite agentul status catre API
CHECK_INTERVAL = 60

# Partitia pentru care calculam disk usage
DISK_PATH = "/"

# Formatul acceptat pentru fisierele EOD:
# eodstatusYYYYMMDDHHMMSS.json
REGEX = re.compile(r"^eodstatus(\d{14})\.json$")


# =========================
# DATA CURENTA
# =========================

def today_ymd():
    # Returneaza data de azi in format YYYYMMDD
    return dt.datetime.now().strftime("%Y%m%d")


# =========================
# CITIRE SCHEDULE EOD
# =========================

def read_schedule_time():
    # Citeste ora de EOD din fisierul scheduled_eod.properties
    try:
        if not os.path.exists(CONF_FILE):
            return None

        with open(CONF_FILE, "r") as f:
            for line in f:
                line = line.strip()

                # Ignoram linii goale, comentarii sau linii fara =
                if not line or line.startswith("#") or "=" not in line:
                    continue

                key, value = line.split("=", 1)
                key = key.strip()
                value = value.strip()

                # Cautam cheia corecta
                if key == SCHEDULE_KEY:
                    # Cautam ora in format HH:MM
                    m = re.search(r"([01][0-9]|2[0-3]):([0-5][0-9])", value)
                    if m:
                        return m.group(0)

        return None

    except Exception as e:
        print("SCHEDULE ERROR:", str(e))
        return None


# =========================
# GASIRE FISIER EOD
# =========================

def find_latest_today_file():
    # Cauta cel mai nou fisier EOD de azi
    ymd = today_ymd()
    best_name = None
    best_ts = None

    try:
        for name in os.listdir(WATCH_DIR):
            m = REGEX.match(name)

            # Ignoram orice fisier care nu respecta formatul
            if not m:
                continue

            ts = m.group(1)

            # Luam doar fisierele de azi
            if not ts.startswith(ymd):
                continue

            # Alegem cel mai nou fisier dupa timestamp
            if best_ts is None or ts > best_ts:
                best_ts = ts
                best_name = name

        return best_name

    except Exception as e:
        print("WATCH DIR ERROR:", str(e))
        return None


# =========================
# CLASIFICARE STATUS EOD
# =========================

def classify_eod(eod):
    # Citeste statusul din JSON-ul EOD si il transforma in OK / PROBLEM
    status = str(eod.get("status", "")).strip()

    if status in (
        "EOD_ENDED_OK",
        "EOD_ENDED_WITH_WARNINGS",
        "EOD_ENDED_SUCCESSFULLY",
    ):
        return "OK", status

    return "PROBLEM", status or "UNKNOWN"


# =========================
# INFORMATII SISTEM
# =========================

def get_os_info():
    # Citeste numele sistemului de operare
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
    # Citeste de cat timp este pornit serverul
    try:
        with open("/proc/uptime", "r") as f:
            return int(float(f.read().split()[0]))

    except Exception:
        return None


def get_cpu_usage_percent():
    # Calculeaza procentul real de utilizare CPU
    # Citim /proc/stat de doua ori, la diferenta de 1 secunda
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
    # Citeste RAM total, RAM folosit si procent RAM
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

        # Pe Linux mai vechi MemAvailable poate lipsi
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
    # Calculeaza disk total, disk folosit si procent disk pentru /
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


# =========================
# HEALTH METRICS
# =========================

def get_health_metrics():
    # Aduna toate informatiile de sistem intr-un dictionar
    ram_total_mb, ram_used_mb, ram_percent = get_ram_info()
    disk_total_gb, disk_used_gb, disk_percent = get_disk_info()

    return {
        "hostname": socket.gethostname(),
        "agent_version": AGENT_VERSION,
        "os_info": get_os_info(),
        "uptime_seconds": get_uptime_seconds(),
        "cpu_load_1m": get_cpu_usage_percent(),  # aici trimitem CPU %
        "ram_total_mb": ram_total_mb,
        "ram_used_mb": ram_used_mb,
        "ram_percent": ram_percent,
        "disk_total_gb": disk_total_gb,
        "disk_used_gb": disk_used_gb,
        "disk_percent": disk_percent,
    }


# =========================
# CONSTRUIRE PAYLOAD
# =========================

def build_payload():
    # Construieste JSON-ul care va fi trimis catre API

    filename = find_latest_today_file()
    schedule_time = read_schedule_time()
    eod_date = dt.datetime.now().strftime("%Y-%m-%d")

    # Daca nu exista fisier EOD pentru ziua curenta
    if not filename:
        payload = {
            "store_code": STORE_CODE,
            "status": "MISSING",
            "eod_file": "",
            "message": "Nu exista fisier EOD",
            "eod_date": eod_date,
            "schedule_time": schedule_time,
        }

    else:
        path = os.path.join(WATCH_DIR, filename)

        try:
            # Citim JSON-ul EOD
            with open(path, "r") as f:
                eod = json.load(f)

            # Transformam statusul intern in OK / PROBLEM
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
            "schedule_time": schedule_time,
        }

    # Adaugam CPU / RAM / Disk / OS / hostname
    payload.update(get_health_metrics())

    return payload


# =========================
# TRIMITERE CATRE API
# =========================

def send_payload(payload):
    # Trimite informatia catre API-ul central
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
        print("PAYLOAD:", payload)
        print("===================================")
        print("")

    except Exception as e:
        print("API ERROR:", str(e))


# =========================
# LOOP PRINCIPAL
# =========================

def main_loop():
    # Ruleaza permanent
    while True:
        try:
            payload = build_payload()
            send_payload(payload)

        except Exception as e:
            print("GENERAL ERROR:", str(e))

        print("Sleeping {} seconds...".format(CHECK_INTERVAL))

        time.sleep(CHECK_INTERVAL)


# =========================
# START PROGRAM
# =========================

if __name__ == "__main__":
    main_loop()