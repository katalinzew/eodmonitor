from fastapi import APIRouter
from fastapi.responses import HTMLResponse

from app.repositories.store_repository import get_store_details

router = APIRouter()


@router.get("/api/store/{store_code}")
def store_details(store_code: str):
    return get_store_details(store_code)


@router.get("/store/{store_code}", response_class=HTMLResponse)
def store_page(store_code: str):
    with open("app/templates/store.html", "r", encoding="utf-8") as f:
        return f.read().replace("__STORE_CODE__", store_code)