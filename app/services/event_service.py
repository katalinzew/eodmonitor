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


def normalize_services(services):
    if not services:
        return {}

    if isinstance(services, dict):
        return services

    return {}


def build_service_events(old_services, new_services):
    old_services = normalize_services(old_services)
    new_services = normalize_services(new_services)

    events = []

    for service_name, new_status in new_services.items():
        old_status = old_services.get(service_name)

        if old_status == new_status:
            continue

        if new_status != "active":
            events.append(
                {
                    "event_type": "SERVICE_DOWN",
                    "old_value": old_status,
                    "new_value": new_status,
                    "message": f"Serviciu oprit: {service_name} ({old_status} -> {new_status})",
                }
            )

        elif old_status and old_status != "active" and new_status == "active":
            events.append(
                {
                    "event_type": "SERVICE_UP",
                    "old_value": old_status,
                    "new_value": new_status,
                    "message": f"Serviciu revenit: {service_name} ({old_status} -> {new_status})",
                }
            )

    return events