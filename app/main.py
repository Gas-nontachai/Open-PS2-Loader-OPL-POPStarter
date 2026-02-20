from __future__ import annotations

import os

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.api.routes import router

load_dotenv()

app = FastAPI(title="PS2 ISO Importer")
app.mount("/static", StaticFiles(directory="app/static"), name="static")
app.include_router(router)


if __name__ == "__main__":
    import uvicorn

    host = os.getenv("HOST", "127.0.0.1")
    port = int(os.getenv("PORT", "8000"))
    reload_enabled = os.getenv("RELOAD", "true").strip().lower() in {"1", "true", "yes", "on"}
    uvicorn.run("app.main:app", host=host, port=port, reload=reload_enabled)
