def save_eod_history(cur, payload, received_at):
    if not payload.eod_date or not payload.eod_file:
        return

    cur.execute(
        """
        INSERT INTO eod_history (
            store_code,
            eod_date,
            status,
            eod_file,
            message,
            eod_file_created_at,
            received_at
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (store_code, eod_date, COALESCE(eod_file, ''))
        DO UPDATE SET
            status = EXCLUDED.status,
            message = EXCLUDED.message,
            eod_file_created_at = EXCLUDED.eod_file_created_at,
            received_at = EXCLUDED.received_at
        """,
        (
            payload.store_code,
            payload.eod_date,
            payload.status,
            payload.eod_file,
            payload.message,
            payload.eod_file_created_at,
            received_at,
        ),
    )