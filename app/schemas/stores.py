import re
from typing import Optional

from pydantic import BaseModel, field_validator


class StorePayload(BaseModel):
    store_code: str
    store_name: str = ""
    host: str
    schedule_time: Optional[str] = None
    active: bool = True

    @field_validator("store_code", "host")
    @classmethod
    def required_text(cls, value: str):
        value = value.strip()
        if not value:
            raise ValueError("Field is required")
        return value

    @field_validator("store_name")
    @classmethod
    def clean_name(cls, value: str):
        return value.strip()

    @field_validator("schedule_time")
    @classmethod
    def valid_schedule(cls, value: Optional[str]):
        if value is None or not value.strip():
            return None
        value = value.strip()
        if not re.fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\d", value):
            raise ValueError("Schedule must use HH:MM format")
        return value
