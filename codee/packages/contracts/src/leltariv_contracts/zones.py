from pydantic import BaseModel


class ZoneOut(BaseModel):
    id: int
    code: str
    name: str
