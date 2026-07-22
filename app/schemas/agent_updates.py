from typing import Optional

from pydantic import BaseModel


class DeploymentReport(BaseModel):
    store_code: str
    release_id: int
    status: str
    current_version: Optional[str] = None
    message: str = ""
