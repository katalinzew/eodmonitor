def ensure_store_exists(cur, store_code):
    cur.execute(
        """
        SELECT store_code
        FROM stores
        WHERE store_code = %s
        """,
        (store_code,),
    )

    return cur.fetchone() is not None


def update_store_schedule(cur, store_code, schedule_time, updated_at):
    if not schedule_time:
        return

    cur.execute(
        """
        UPDATE stores
        SET schedule_time = %s,
            updated_at = %s
        WHERE store_code = %s
        """,
        (
            schedule_time,
            updated_at,
            store_code,
        ),
    )