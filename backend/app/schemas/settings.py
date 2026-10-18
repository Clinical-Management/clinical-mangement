from pydantic import BaseModel, Field


class ClinicSettings(BaseModel):
    """Letterhead details printed on prescriptions."""

    name: str = Field("Clinical Management", min_length=1, max_length=120)
    address: str | None = Field(None, max_length=300)
    phone: str | None = Field(None, max_length=40)
    email: str | None = Field(None, max_length=120)
    registration: str | None = Field(None, max_length=80)  # clinic establishment registration


class DoctorCredentials(BaseModel):
    registration_number: str | None = Field(None, max_length=60)
    registration_council: str | None = Field(None, max_length=120)  # e.g. Maharashtra Medical Council
    qualifications: str | None = Field(None, max_length=200)  # e.g. MBBS, MD (General Medicine)
