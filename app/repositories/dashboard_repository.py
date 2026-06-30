from app.core.config import OFFLINE_AFTER_MINUTES, LATE_GRACE_MINUTES
from app.core.database import get_conn


DASHBOARD_SQL = """
    SELECT
        s.store_code,
        s.store_name,
        s.host,
        s.schedule_time,

        CASE
            WHEN cs.last_heartbeat IS NULL THEN 'NO_DATA'
            WHEN cs.last_heartbeat < NOW() - (%s * INTERVAL '1 minute') THEN 'OFFLINE'
            WHEN cs.status = 'OK' THEN 'OK'

            WHEN cs.status IN ('MISSING', 'PROBLEM')
                 AND cs.ok_valid_until > NOW()
            THEN 'OK'

            WHEN s.schedule_time ~ '^[0-2][0-9]:[0-5][0-9]$'
                 AND NOW() > (CURRENT_DATE + s.schedule_time::time + (%s * INTERVAL '1 minute'))
                 AND NOT (cs.ok_valid_until > NOW())
                 AND COALESCE(cs.status, 'MISSING') <> 'OK'
            THEN 'LATE'

            ELSE COALESCE(cs.status, 'NO_DATA')
        END AS status,

        CASE
            WHEN cs.status IN ('MISSING', 'PROBLEM')
                 AND cs.ok_valid_until > NOW()
            THEN cs.last_ok_eod_file
            ELSE cs.eod_file
        END AS eod_file,

        CASE
            WHEN cs.status IN ('MISSING', 'PROBLEM')
                 AND cs.ok_valid_until > NOW()
            THEN 'OK validat anterior - valabil 10 ore'
            ELSE cs.message
        END AS message,

        CASE
            WHEN cs.status IN ('MISSING', 'PROBLEM')
                 AND cs.ok_valid_until > NOW()
            THEN cs.last_ok_eod_date
            ELSE cs.eod_date
        END AS eod_date,

        cs.last_heartbeat,
        cs.updated_at,
        cs.ok_valid_until,
        cs.eod_file_created_at,
        COALESCE(cs.heartbeat_state, 'ONLINE') AS heartbeat_state,
        cs.services_status,

        EXTRACT(EPOCH FROM (NOW() - cs.last_heartbeat))::INT AS seconds_since_heartbeat,

        cs.hostname,
        cs.agent_version,
        cs.os_info,
        cs.uptime_seconds,
        cs.cpu_load_1m,
        cs.ram_total_mb,
        cs.ram_used_mb,
        cs.ram_percent,
        cs.disk_total_gb,
        cs.disk_used_gb,
        cs.disk_percent

    FROM stores s
    LEFT JOIN current_status cs
        ON s.store_code = cs.store_code

    WHERE s.active = true
"""


def rows_to_dicts(cols, rows):
    result = []

    for row in rows:
        item = {}

        for key, value in zip(cols, row):
            if hasattr(value, "isoformat"):
                item[key] = value.isoformat()
            else:
                item[key] = value

        result.append(item)

    return result


def get_dashboard_rows():
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                DASHBOARD_SQL + " ORDER BY s.store_code",
                (
                    OFFLINE_AFTER_MINUTES,
                    LATE_GRACE_MINUTES,
                ),
            )

            cols = [desc[0] for desc in cur.description]
            rows = cur.fetchall()

    return rows_to_dicts(cols, rows)