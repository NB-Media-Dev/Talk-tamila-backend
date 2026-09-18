from pydantic import BaseModel


class SuperadminInfo(BaseModel):
    message: str = "Superadmin module active"
