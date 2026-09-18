import enum
class UserRole(str, enum.Enum):
    admin = "Admin"
    influencer = "Influencer"
    freelancer = "Freelancer"