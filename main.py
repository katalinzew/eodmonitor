from fastapi import FastAPI

app = FastAPI()


@app.get("/")
def root():
    return {
        "service": "EOD Monitor API",
        "status": "running",
        "version": "refactor",
    }