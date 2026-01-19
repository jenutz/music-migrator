from pydantic import BaseModel


class TokenPayload(BaseModel):
    value: str
