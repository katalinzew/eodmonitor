import asyncio

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.routers import agent_commands, agent_updates, alerts, dashboard, health, stores, status
from app.services.alert_dispatcher import alert_dispatcher_loop
from app.services.offline_service import offline_monitor_loop

app = FastAPI(title="EOD Monitor API")

app.mount("/static", StaticFiles(directory="app/static"), name="static")

app.include_router(dashboard.router)
app.include_router(health.router)
app.include_router(stores.router)
app.include_router(status.router)
app.include_router(alerts.router)
app.include_router(agent_updates.router)
app.include_router(agent_commands.router)

@app.on_event("startup")
async def startup_event():
    asyncio.create_task(offline_monitor_loop())
    asyncio.create_task(alert_dispatcher_loop())


@app.get("/")
def root():
    return {
        "service": "EOD Monitor API",
        "status": "running",
        "version": "refactor",
    }
