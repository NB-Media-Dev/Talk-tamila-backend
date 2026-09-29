
from pydantic import BaseModel, Field, field_validator


class MessageCreate(BaseModel):
    body: str = Field(..., max_length=2000)

    @field_validator("body")
    @classmethod
    def not_blank(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("Message cannot be empty")
        return v


class ReactionRequest(BaseModel):
    emoji: str = Field(..., min_length=1, max_length=16)

    @field_validator("emoji")
    @classmethod
    def looks_like_emoji(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("Emoji cannot be empty")
        # Keeps reactions from being used as a second text channel.
        if any(c.isascii() and c.isalpha() for c in v):
            raise ValueError("Reaction must be an emoji")
        return v