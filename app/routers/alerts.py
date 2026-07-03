from fastapi import APIRouter, Query
from fastapi.responses import HTMLResponse

from app.core.database import get_conn
from app.repositories.alert_repository import get_alerts, get_alert_summary

router = APIRouter()


def row_to_alert(row):
    return {
        "id": row[0],
        "store_code": row[1],
        "store_name": row[2],
        "host": row[3],
        "alert_type": row[4],
        "target": row[5],
        "first_seen_at": row[6],
        "last_seen_at": row[7],
        "email_sent": row[8],
        "email_sent_at": row[9],
        "resolved": row[10],
        "resolved_at": row[11],
    }


@router.get("/api/alerts")
def alerts_api(
    status: str = Query(default="ACTIVE"),
    alert_type: str = Query(default="ALL"),
    search: str = Query(default=""),
):
    with get_conn() as conn:
        with conn.cursor() as cur:
            rows = get_alerts(
                cur,
                status_filter=status,
                alert_type=alert_type,
                search=search.strip() or None,
            )

            summary = get_alert_summary(cur)

    return {
        "summary": summary,
        "alerts": [row_to_alert(row) for row in rows],
    }


@router.get("/alerts", response_class=HTMLResponse)
def alerts_page():
    with open("app/templates/alerts.html", "r", encoding="utf-8") as f:
        return f.read()