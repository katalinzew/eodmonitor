from app.repositories.alert_repository import (
    resolve_alert,
    upsert_active_alert,
)


AGENT_OFFLINE = "AGENT_OFFLINE"
EOD_MISSING = "EOD_MISSING"
SERVICE_DOWN = "SERVICE_DOWN"

TARGET_HEARTBEAT = "HEARTBEAT"
TARGET_EOD = "EOD"


def register_agent_offline(cur, store_code, seen_at):
    return upsert_active_alert(
        cur,
        store_code,
        AGENT_OFFLINE,
        TARGET_HEARTBEAT,
        seen_at,
    )


def resolve_agent_offline(cur, store_code, resolved_at):
    resolve_alert(
        cur,
        store_code,
        AGENT_OFFLINE,
        TARGET_HEARTBEAT,
        resolved_at,
    )


def register_eod_missing(cur, store_code, seen_at):
    return upsert_active_alert(
        cur,
        store_code,
        EOD_MISSING,
        TARGET_EOD,
        seen_at,
    )


def resolve_eod_missing(cur, store_code, resolved_at):
    resolve_alert(
        cur,
        store_code,
        EOD_MISSING,
        TARGET_EOD,
        resolved_at,
    )


def register_service_down(cur, store_code, service_name, seen_at):
    return upsert_active_alert(
        cur,
        store_code,
        SERVICE_DOWN,
        service_name,
        seen_at,
    )


def resolve_service_down(cur, store_code, service_name, resolved_at):
    resolve_alert(
        cur,
        store_code,
        SERVICE_DOWN,
        service_name,
        resolved_at,
    )