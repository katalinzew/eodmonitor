from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.routers import dashboard
from app.core.database import get_conn

app = FastAPI(title="EOD Monitor API")

app.mount("/static", StaticFiles(directory="app/static"), name="static")

app.include_router(dashboard.router)


@app.get("/")
def root():
    return {
        "service": "EOD Monitor API",
        "status": "running",
        "version": "refactor",
    }


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