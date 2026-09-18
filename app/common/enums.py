import enum


class UserRoleEnum(str, enum.Enum):
    ADMIN = "admin"
    INFLUENCER = "influencer"
    FREELANCER = "freelancer"


class StoryAudienceEnum(str, enum.Enum):
    PUBLIC = "public"
    CLOSE_FRIENDS = "close_friends"
    FOLLOWERS = "followers"


class MediaTypeEnum(str, enum.Enum):
    IMAGE = "image"
    VIDEO = "video"