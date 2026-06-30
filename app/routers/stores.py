from fastapi import APIRouter

from app.repositories.store_repository import get_store_details

router = APIRouter()


@router.get("/api/store/{store_code}")
def store_details(store_code: str):
    return get_store_details(store_code)