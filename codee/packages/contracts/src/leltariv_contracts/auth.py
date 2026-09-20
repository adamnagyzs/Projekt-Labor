from typing import Literal

from pydantic import BaseModel, ConfigDict

Role = Literal["ADMIN", "LELTAROZO", "OLVASO"]


class LoginRequest(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "examples": [{"email": "admin@leltariv.local", "password": "leltar2026"}]
        }
    )

    email: str
    password: str


class LoginResponse(BaseModel):
    access_token: str
    refresh_token: str
    role: Role
    display_name: str
