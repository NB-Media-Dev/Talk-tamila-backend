import enum


class StoryAudienceEnum(str, enum.Enum):
    PUBLIC = "PUBLIC"
    FOLLOWERS = "FOLLOWERS"
    CLOSE_FRIENDS = "CLOSE_FRIENDS"

    @classmethod
    def _missing_(cls, value: object):
        if isinstance(value, str):
            clean = value.strip().upper()
            for member in cls:
                if member.value == clean or member.name == clean:
                    return member
        return None
