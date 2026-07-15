from fastapi import APIRouter
from fastapi.responses import HTMLResponse

from app.repositories.store_repository import get_store_details
from app.repositories.stores_repository import (
    create_store,
    list_stores,
    set_store_active,
    update_store,
)
from app.schemas.stores import StorePayload

router = APIRouter()


@router.get("/stores", response_class=HTMLResponse)
def stores_page():
    with open("app/templates/stores.html", "r", encoding="utf-8") as file:
        return file.read()


@router.get("/api/stores")
def stores_list():
    return list_stores()


@router.post("/api/stores", status_code=201)
def stores_create(payload: StorePayload):
    return create_store(payload)


@router.put("/api/stores/{store_code}")
def stores_update(store_code: str, payload: StorePayload):
    return update_store(store_code, payload)


@router.patch("/api/stores/{store_code}/activate")
def stores_activate(store_code: str):
    return set_store_active(store_code, True)


@router.patch("/api/stores/{store_code}/deactivate")
def stores_deactivate(store_code: str):
    return set_store_active(store_code, False)


@router.get("/api/store/{store_code}")
def store_details(store_code: str):
    return get_store_details(store_code)


@router.get("/store/{store_code}", response_class=HTMLResponse)
def store_page(store_code: str):
    with open("app/templates/store.html", "r", encoding="utf-8") as file:
        return file.read().replace("__STORE_CODE__", store_code)
