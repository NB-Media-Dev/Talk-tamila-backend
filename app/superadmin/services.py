class SuperadminService:
    @staticmethod
    def get_status() -> dict:
        return {"status": "active", "role": "superadmin"}
