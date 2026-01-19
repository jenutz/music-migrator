import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.api import router
from app.core.config import APP_DIR, DB_PATH
from app.core.db import init_db

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    logger.info("Database ready at %s", DB_PATH)
    yield


def create_app() -> FastAPI:
    application = FastAPI(title="Music Migrator", version="1.0.0", lifespan=lifespan)
    application.mount("/static", StaticFiles(directory=APP_DIR / "static"), name="static")
    application.include_router(router)
    return application


app = create_app()
