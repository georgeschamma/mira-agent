from typing import Literal

from pydantic import BaseModel

OrgRole = Literal["analyst", "admin"]


class CurrentUser(BaseModel):
    id: str
    email: str | None = None
    token: str
