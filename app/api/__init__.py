from fastapi import APIRouter

from app.api.routers import (
    apply,
    auth,
    imports,
    matching,
    pages,
    playlists,
    services,
    system,
    tokens,
)

router = APIRouter()

for module in (system, pages, tokens, auth, imports, playlists, matching, apply, services):
    router.include_router(module.router)
