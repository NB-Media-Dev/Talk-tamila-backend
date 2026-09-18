from pydantic import BaseModel


class AdminOverview(BaseModel):
    total_users: int = 0
    total_stories: int = 0
