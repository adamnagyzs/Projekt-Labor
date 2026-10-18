from uuid import UUID

from pydantic import BaseModel, Field


class RoomOut(BaseModel):
    id: UUID
    zone_code: str
    room_number: str
    name: str | None = None
    #: „I-217 · Labor"; a szerver állítja elő, a kliens változatlanul mutatja
    label: str


class RoomCreate(BaseModel):
    zone_code: str
    room_number: str = Field(min_length=1, max_length=30)
    name: str | None = Field(default=None, max_length=100)
