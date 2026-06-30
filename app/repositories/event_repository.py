def insert_event(cur, store_code, event_type, old_value, new_value, message, created_at):
    cur.execute(
        """
        INSERT INTO event_log (
            store_code,
            event_type,
            old_value,
            new_value,
            message,
            created_at
        )
        VALUES (%s, %s, %s, %s, %s, %s)
        """,
        (
            store_code,
            event_type,
            old_value,
            new_value,
            message,
            created_at,
        ),
    )