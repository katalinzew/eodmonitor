from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

from app.core.database import get_conn

app = FastAPI(title="EOD Monitor API")

app.mount("/static", StaticFiles(directory="app/static"), name="static")


@app.get("/")
def root():
    return {
        "service": "EOD Monitor API",
        "status": "running",
        "version": "refactor",
    }


@app.get("/dashboard", response_class=HTMLResponse)
def dashboard_page():
    with open("app/templates/dashboard.html", "r", encoding="utf-8") as f:
        return f.read()


@app.get("/api/health")
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


@app.get("/api/dashboard")
def dashboard_data():
    return []