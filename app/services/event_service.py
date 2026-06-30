def should_log_status_change(old_status, new_status):
    if old_status == new_status:
        return False

    if old_status == "OK" and new_status == "MISSING":
        return False

    return True


def build_status_change_message(old_status, new_status):
    return f"Status EOD schimbat: {old_status} -> {new_status}"


def build_heartbeat_online_event(old_heartbeat_state):
    if old_heartbeat_state != "OFFLINE":
        return None

    return {
        "event_type": "HEARTBEAT_ONLINE",
        "old_value": "OFFLINE",
        "new_value": "ONLINE",
        "message": "Agentul a revenit online.",
    }