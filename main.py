from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.routers import dashboard, health, stores

app = FastAPI(title="EOD Monitor API")

app.mount("/static", StaticFiles(directory="app/static"), name="static")

app.include_router(dashboard.router)
app.include_router(health.router)
app.include_router(stores.router)


@app.get("/")
def root():
    return {
        "service": "EOD Monitor API",
        "status": "running",
        "version": "refactor",
    }