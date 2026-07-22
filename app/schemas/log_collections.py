from typing import List, Optional

from pydantic import BaseModel


class LogCollectionCreate(BaseModel):
    log_keys: List[str]


class LogCollectionReport(BaseModel):
    store_code: str
    request_id: int
    status: str
    message: Optional[str] = ""
