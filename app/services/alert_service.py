from app.repositories.alert_repository import (
    resolve_alert,
    upsert_active_alert,
)
from app.services.status_service import is_eod_alert_due

AGENT_OFFLINE = "AGENT_OFFLINE"
EOD_MISSING = "EOD_MISSING"
SERVICE_DOWN = "SERVICE_DOWN"
HEALTH_WARNING = "HEALTH_WARNING"

TARGET_HEARTBEAT = "HEARTBEAT"
TARGET_EOD = "EOD"
TARGET_RAM = "RAM"
TARGET_DISK = "DISK"

HEALTH_LIMIT_PERCENT = 90


def register_alert(cur, store_code, alert_type, target, seen_at):
    return upsert_active_alert(
        cur,
        store_code,
        alert_type,
        target,
        seen_at,
    )


def resolve_existing_alert(cur, store_code, alert_type, target, resolved_at):
    resolve_alert(
        cur,
        store_code,
        alert_type,
        target,
        resolved_at,
    )


def process_service_alerts(cur, store_code, old_services, new_services, now):
    old_services = old_services or {}
    new_services = new_services or {}

    for service_name, new_state in new_services.items():
        old_state = old_services.get(service_name)

        if new_state != "active":
            register_alert(
                cur,
                store_code,
                SERVICE_DOWN,
                service_name,
                now,
            )

        elif old_state and old_state != "active" and new_state == "active":
            resolve_existing_alert(
                cur,
                store_code,
                SERVICE_DOWN,
                service_name,
                now,
            )


def process_agent_alerts(cur, store_code, heartbeat_state, now):
    if heartbeat_state == "OFFLINE":
        register_alert(
            cur,
            store_code,
            AGENT_OFFLINE,
            TARGET_HEARTBEAT,
            now,
        )

    elif heartbeat_state == "ONLINE":
        resolve_existing_alert(
            cur,
            store_code,
            AGENT_OFFLINE,
            TARGET_HEARTBEAT,
            now,
        )


def process_eod_alerts(cur, store_code, effective_status, now, schedule_time=None):
    if effective_status in ("MISSING", "LATE", "PROBLEM"):
        if not is_eod_alert_due(schedule_time, now):
            return

        register_alert(
            cur,
            store_code,
            EOD_MISSING,
            TARGET_EOD,
            now,
        )

    elif effective_status == "OK":
        resolve_existing_alert(
            cur,
            store_code,
            EOD_MISSING,
            TARGET_EOD,
            now,
        )


def process_health_alerts(cur, store_code, ram_percent, disk_percent, now):
    if ram_percent is not None and float(ram_percent) >= HEALTH_LIMIT_PERCENT:
        register_alert(
            cur,
            store_code,
            HEALTH_WARNING,
            TARGET_RAM,
            now,
        )
    else:
        resolve_existing_alert(
            cur,
            store_code,
            HEALTH_WARNING,
            TARGET_RAM,
            now,
        )

    if disk_percent is not None and float(disk_percent) >= HEALTH_LIMIT_PERCENT:
        register_alert(
            cur,
            store_code,
            HEALTH_WARNING,
            TARGET_DISK,
            now,
        )
    else:
        resolve_existing_alert(
            cur,
            store_code,
            HEALTH_WARNING,
            TARGET_DISK,
            now,
        )


def process_alerts(
    cur,
    store_code,
    old_services,
    new_services,
    heartbeat_state,
    effective_status,
    now,
    ram_percent=None,
    disk_percent=None,
    schedule_time=None,
):
    process_service_alerts(
        cur,
        store_code,
        old_services,
        new_services,
        now,
    )

    process_agent_alerts(
        cur,
        store_code,
        heartbeat_state,
        now,
    )

    process_eod_alerts(
        cur,
        store_code,
        effective_status,
        now,
        schedule_time,
    )

    process_health_alerts(
        cur,
        store_code,
        ram_percent,
        disk_percent,
        now,
    )
