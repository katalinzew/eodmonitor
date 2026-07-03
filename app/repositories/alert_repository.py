def get_active_alert(cur, store_code, alert_type, target):
    cur.execute(
        """
        SELECT
            id,
            store_code,
            alert_type,
            target,
            first_seen_at,
            last_seen_at,
            email_sent,
            email_sent_at,
            resolved,
            resolved_at
        FROM alert_state
        WHERE store_code = %s
          AND alert_type = %s
          AND target = %s
          AND resolved = false
        ORDER BY id DESC
        LIMIT 1
        """,
        (
            store_code,
            alert_type,
            target,
        ),
    )

    return cur.fetchone()


def create_alert(cur, store_code, alert_type, target, seen_at):
    cur.execute(
        """
        INSERT INTO alert_state (
            store_code,
            alert_type,
            target,
            first_seen_at,
            last_seen_at,
            email_sent,
            email_sent_at,
            resolved,
            resolved_at
        )
        VALUES (%s, %s, %s, %s, %s, false, NULL, false, NULL)
        RETURNING id
        """,
        (
            store_code,
            alert_type,
            target,
            seen_at,
            seen_at,
        ),
    )

    row = cur.fetchone()
    return row[0] if row else None


def touch_alert(cur, alert_id, seen_at):
    cur.execute(
        """
        UPDATE alert_state
        SET last_seen_at = %s
        WHERE id = %s
        """,
        (
            seen_at,
            alert_id,
        ),
    )


def upsert_active_alert(cur, store_code, alert_type, target, seen_at):
    alert = get_active_alert(cur, store_code, alert_type, target)

    if alert:
        alert_id = alert[0]
        touch_alert(cur, alert_id, seen_at)
        return alert_id

    return create_alert(
        cur,
        store_code,
        alert_type,
        target,
        seen_at,
    )


def resolve_alert(cur, store_code, alert_type, target, resolved_at):
    cur.execute(
        """
        UPDATE alert_state
        SET resolved = true,
            resolved_at = %s,
            last_seen_at = %s
        WHERE store_code = %s
          AND alert_type = %s
          AND target = %s
          AND resolved = false
        """,
        (
            resolved_at,
            resolved_at,
            store_code,
            alert_type,
            target,
        ),
    )


def mark_email_sent(cur, alert_id, sent_at):
    cur.execute(
        """
        UPDATE alert_state
        SET email_sent = true,
            email_sent_at = %s
        WHERE id = %s
        """,
        (
            sent_at,
            alert_id,
        ),
    )


def get_pending_email_alerts(cur):
    cur.execute(
        """
        SELECT
            a.id,
            a.store_code,
            s.store_name,
            s.host,
            s.schedule_time,
            a.alert_type,
            a.target,
            a.first_seen_at,
            a.last_seen_at,
            a.email_sent
        FROM alert_state a
        LEFT JOIN stores s
            ON s.store_code = a.store_code
        WHERE a.resolved = false
          AND a.email_sent = false
        ORDER BY a.first_seen_at ASC
        """
    )

    return cur.fetchall()