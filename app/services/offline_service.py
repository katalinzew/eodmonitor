import asyncio
import datetime as dt

from app.core.config import OFFLINE_AFTER_MINUTES, OFFLINE_CHECK_INTERVAL_SECONDS
from app.core.database import get_conn
from app.repositories.event_repository import insert_event
from app.services.alert_service import process_alerts


def check_offline_agents_once():
    now = dt.datetime.now()

    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT store_code
                FROM current_status
                WHERE COALESCE(heartbeat_state, 'ONLINE') <> 'OFFLINE'
                  AND last_heartbeat IS NOT NULL
                  AND last_heartbeat < NOW() - (%s * INTERVAL '1 minute')
                """,
                (OFFLINE_AFTER_MINUTES,),
            )

            rows = cur.fetchall()

            for row in rows:
                store_code = row[0]

                cur.execute(
                    """
                    UPDATE current_status
                    SET heartbeat_state = 'OFFLINE',
                        updated_at = %s
                    WHERE store_code = %s
                    """,
                    (
                        now,
                        store_code,
                    ),
                )

                insert_event(
                    cur,
                    store_code,
                    "HEARTBEAT_OFFLINE",
                    "ONLINE",
                    "OFFLINE",
                    f"Agentul nu a mai trimis heartbeat de peste {OFFLINE_AFTER_MINUTES} minute.",
                    now,
                )

                process_alerts(
                    cur,
                    store_code,
                    {},
                    {},
                    "OFFLINE",
                    "OK",
                    now,
                    ram_percent=None,
                    disk_percent=None,
                )

    return len(rows)


async def offline_monitor_loop():
    while True:
        try:
            await asyncio.to_thread(check_offline_agents_once)
        except Exception as e:
            print(f"[offline-monitor] error: {e}")

        await asyncio.sleep(OFFLINE_CHECK_INTERVAL_SECONDS)