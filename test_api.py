from fastapi import FastAPI, Request
import datetime as dt
import json

app = FastAPI()

@app.post("/test")
async def receive_test(request: Request):
    data = await request.json()

    line = {
        "received_at": dt.datetime.now().isoformat(timespec="seconds"),
        "data": data
    }

    with open("received_status.txt", "a", encoding="utf-8") as f:
        f.write(json.dumps(line, ensure_ascii=False) + "\n")

    return {"ok": True, "saved": True}