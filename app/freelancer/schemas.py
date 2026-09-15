from pydantic import BaseModel


class FreelancerProfileStub(BaseModel):
    message: str = "Freelancer module active"
