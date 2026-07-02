from fastapi import APIRouter

from app.core.database import get_conn
from app.services.alert_mail_service import send_test_email
router = APIRouter()


@router.get("/api/health")
def health():
    try:
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT 1")
                cur.fetchone()

        return {
            "ok": True,
            "database": "connected",
        }

    except Exception as e:
        return {
            "ok": False,
            "database": "error",
            "error": str(e),
        }
    
@router.post("/api/test-mail")
def test_mail():
    send_test_email()
    return {"ok": True, "message": "Test mail sent"}