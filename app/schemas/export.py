from pydantic import BaseModel


class ExportPayload(BaseModel):
    dst_service: str
    delivery: str = "playlist"
    name: str | None = None
