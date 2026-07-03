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

def get_alerts(cur, status_filter="ACTIVE", alert_type=None, search=None):
    query = """
        SELECT
            a.id,
            a.store_code,
            s.store_name,
            s.host,
            a.alert_type,
            a.target,
            a.first_seen_at,
            a.last_seen_at,
            a.email_sent,
            a.email_sent_at,
            a.resolved,
            a.resolved_at
        FROM alert_state a
        LEFT JOIN stores s
            ON s.store_code = a.store_code
        WHERE 1 = 1
    """

    params = []

    if status_filter == "ACTIVE":
        query += " AND a.resolved = false"
    elif status_filter == "RESOLVED":
        query += " AND a.resolved = true"

    if alert_type and alert_type != "ALL":
        query += " AND a.alert_type = %s"
        params.append(alert_type)

    if search:
        query += """
            AND (
                a.store_code ILIKE %s
                OR s.store_name ILIKE %s
                OR s.host ILIKE %s
                OR a.alert_type ILIKE %s
                OR a.target ILIKE %s
            )
        """
        like = f"%{search}%"
        params.extend([like, like, like, like, like])

    query += """
        ORDER BY
            a.resolved ASC,
            a.first_seen_at DESC
        LIMIT 500
    """

    cur.execute(query, params)
    return cur.fetchall()


def get_alert_summary(cur):
    cur.execute(
        """
        SELECT
            COUNT(*) FILTER (WHERE resolved = false) AS active_total,
            COUNT(*) FILTER (WHERE resolved = false AND alert_type = 'AGENT_OFFLINE') AS agent_offline,
            COUNT(*) FILTER (WHERE resolved = false AND alert_type = 'SERVICE_DOWN') AS service_down,
            COUNT(*) FILTER (WHERE resolved = false AND alert_type = 'EOD_MISSING') AS eod_missing,
            COUNT(*) FILTER (WHERE resolved = false AND alert_type = 'HEALTH_WARNING') AS health_warning
        FROM alert_state
        """
    )

    row = cur.fetchone()

    return {
        "active_total": row[0] or 0,
        "agent_offline": row[1] or 0,
        "service_down": row[2] or 0,
        "eod_missing": row[3] or 0,
        "health_warning": row[4] or 0,
    }