from pydantic import BaseModel


class ChoosePayload(BaseModel):
    external_id: str
