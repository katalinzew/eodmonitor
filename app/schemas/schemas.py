from typing import Optional

from pydantic import BaseModel


class StatusPayload(BaseModel):
    store_code: str
    status: str
    eod_file: str = ""
    message: str = ""
    eod_date: str = None
    eod_file_created_at: Optional[str] = None
    schedule_time: str = None

    hostname: str = None
    agent_version: str = None
    os_info: str = None
    uptime_seconds: int = None
    cpu_load_1m: float = None
    ram_total_mb: int = None
    ram_used_mb: int = None
    ram_percent: float = None
    disk_total_gb: float = None
    disk_used_gb: float = None
    disk_percent: float = None
    services_status: dict = None