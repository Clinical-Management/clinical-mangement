from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class BillItem(BaseModel):
    id: str | None = None
    description: str = Field(min_length=1, max_length=120)
    amount: int = Field(ge=0, le=1_000_000)  # whole rupees
    kind: Literal["consultation", "procedure", "medicine", "investigation", "other"] = "other"


class BillIn(BaseModel):
    items: list[BillItem] = Field(max_length=50)
    discount: int = Field(0, ge=0, le=1_000_000)


class PayIn(BaseModel):
    mode: Literal["cash", "upi", "card", "other"]


class WaiveIn(BaseModel):
    reason: str = Field(min_length=3, max_length=200)


class BillItemOut(BillItem):
    id: str
    auto: bool = False  # filled from the doctor's fee for this visit type


class BillOut(BaseModel):
    appointment_id: str
    patient_id: str
    visit_type: str
    items: list[BillItemOut]
    subtotal: int
    discount: int
    total: int
    currency: str = "INR"
    payment_status: Literal["unpaid", "paid", "waived"]
    payment_mode: str | None
    paid_at: datetime | None
    waive_reason: str | None
    fee_missing: bool  # the doctor has no fee set for this visit type
