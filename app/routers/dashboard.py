from fastapi import APIRouter
from fastapi.responses import HTMLResponse

from app.repositories.dashboard_repository import get_dashboard_rows

router = APIRouter()


@router.get("/dashboard", response_class=HTMLResponse)
def dashboard_page():
    with open("app/templates/dashboard.html", "r", encoding="utf-8") as f:
        return f.read()


@router.get("/api/dashboard")
def dashboard_data():
    return get_dashboard_rows()