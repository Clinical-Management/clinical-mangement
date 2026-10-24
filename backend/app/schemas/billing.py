"""Bills, payments, refunds and receipts. Money is in paise (integer) everywhere in the API."""

from datetime import date, datetime
from typing import Annotated, Literal

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, model_validator

from app.billing.calc import GST_RATES_BP
from app.schemas.common import PyObjectId

ItemKind = Literal["consultation", "procedure", "injection", "dressing", "test", "medicine", "other"]
FeeKey = Literal["new", "follow_up", "returning", "emergency", "teleconsultation"]
PayMode = Literal["cash", "upi", "card", "other"]
MAX_PAISE = 100_000_000  # ₹10 lakh


def _gst(v: float) -> float:
    if round(v * 100) not in GST_RATES_BP:
        raise ValueError("Use a GST rate: 0, 0.25, 3, 5, 12, 18 or 28")
    return v


GstRate = Annotated[float, AfterValidator(_gst)]  # percent


class BillItem(BaseModel):
    id: str | None = None
    kind: ItemKind = "other"
    service_id: str | None = None  # from the price list
    description: str = Field(min_length=1, max_length=120)
    qty: int = Field(1, ge=1, le=1000)
    unit_price: int = Field(ge=0, le=MAX_PAISE)
    tax_rate: GstRate = 0


class FeeChoice(BaseModel):
    """The consultation line. 'auto' follows the detected visit type; anything else is an override
    that needs a reason and is written to the audit log."""

    basis: Literal["auto", "new", "follow_up", "returning", "emergency", "teleconsultation", "custom"] = "auto"
    amount: int | None = Field(None, ge=0, le=MAX_PAISE)  # only for 'custom'
    reason: str | None = Field(None, max_length=200)

    @model_validator(mode="after")
    def check(self):
        if self.basis != "auto" and len((self.reason or "").strip()) < 3:
            raise ValueError("Give a reason for changing the consultation fee")
        if self.basis == "custom" and self.amount is None:
            raise ValueError("Enter the custom fee")
        return self


class ConcessionIn(BaseModel):
    type: Literal["none", "senior", "staff", "waiver", "other"] = "none"
    percent: float | None = Field(None, ge=0, le=100)  # senior/staff default to the clinic's preset
    amount: int | None = Field(None, ge=0, le=MAX_PAISE)  # fixed amount instead of a percent ('other')
    reason: str | None = Field(None, max_length=200)

    @model_validator(mode="after")
    def check(self):
        if self.type in ("waiver", "other") and len((self.reason or "").strip()) < 3:
            raise ValueError("Give a reason for this concession")
        return self


class BillIn(BaseModel):
    items: list[BillItem] = Field(default_factory=list, max_length=50)  # extra lines; the consultation line comes from `fee`
    fee: FeeChoice = Field(default_factory=FeeChoice)
    concession: ConcessionIn = Field(default_factory=ConcessionIn)


class PaymentIn(BaseModel):
    mode: PayMode
    amount: int = Field(ge=0, le=MAX_PAISE)
    reference: str | None = Field(None, max_length=80)  # UPI ref / card slip number


class RefundIn(BaseModel):
    amount: int = Field(gt=0, le=MAX_PAISE)
    mode: PayMode
    reason: str = Field(min_length=3, max_length=200)


class ReasonIn(BaseModel):
    reason: str = Field(min_length=3, max_length=200)


class BillLineOut(BillItem):
    id: str
    auto: bool = False
    amount: int
    discount: int
    taxable: int
    tax: int


class Concession(BaseModel):
    type: str
    percent: float | None = None
    amount: int | None = None
    reason: str | None = None
    status: Literal["none", "approved", "pending", "rejected"]
    discount: int  # paise actually taken off
    approved_by_role: str | None = None


class Payment(BaseModel):
    id: str
    mode: str
    amount: int
    reference: str | None = None
    at: datetime
    by_role: str
    receipt_id: str | None = None
    receipt_number: str | None = None


class Refund(BaseModel):
    id: str
    amount: int
    mode: str
    reason: str
    status: Literal["requested", "approved", "rejected"]
    requested_at: datetime
    requested_by_role: str
    decided_at: datetime | None = None
    decided_by_role: str | None = None
    receipt_number: str | None = None


class TaxSlab(BaseModel):
    rate_bp: int
    taxable: int
    tax: int
    cgst: int
    sgst: int


class BillOut(BaseModel):
    id: str
    appointment_id: str
    patient_id: str
    visit_type: str
    fee: dict  # basis, key, amount, source, reason
    fee_missing: bool
    items: list[BillLineOut]
    concession: Concession
    subtotal: int
    discount: int
    taxable: int
    tax_by_rate: list[TaxSlab]
    tax: int
    round_off: int
    total: int
    paid: int
    refunded: int
    balance: int
    status: Literal["unpaid", "partial", "paid", "waived", "cancelled"]
    payments: list[Payment]
    refunds: list[Refund]
    cancel_reason: str | None = None
    currency: str = "INR"


class ReceiptOut(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: PyObjectId = Field(validation_alias="_id")
    number: str
    kind: Literal["payment", "refund"]
    appointment_id: PyObjectId
    patient_id: str
    amount: int
    mode: str
    issued_at: datetime
    issued_by_role: str
    total: int
    balance: int
    next_appointment: dict | None = None


class ReceiptDeliveryIn(BaseModel):
    channel: Literal["print", "whatsapp", "sms", "email", "patient_app"]
    to: str | None = Field(None, max_length=120)


class ServiceIn(BaseModel):
    """Price list entry: procedures, injections, dressings, in-clinic tests, dispensed medicines."""

    name: str = Field(min_length=1, max_length=120)
    kind: ItemKind = "procedure"
    price: int = Field(ge=0, le=MAX_PAISE)
    tax_rate: GstRate = 0
    active: bool = True


class ServiceOut(ServiceIn):
    model_config = ConfigDict(populate_by_name=True)

    id: PyObjectId = Field(validation_alias="_id")


class FeeSchedule(BaseModel):
    """Consultation fee (whole rupees) per kind of visit; None = not set."""

    new: int | None = Field(None, ge=0, le=100_000)
    follow_up: int | None = Field(None, ge=0, le=100_000)
    returning: int | None = Field(None, ge=0, le=100_000)
    emergency: int | None = Field(None, ge=0, le=100_000)
    teleconsultation: int | None = Field(None, ge=0, le=100_000)


class BillingSettings(BaseModel):
    round_to_rupee: bool = True
    consultation_tax_rate: GstRate = 0  # healthcare services are generally GST-exempt
    approval_discount_percent: float = Field(10, ge=0, le=100)  # bigger concessions need an admin
    senior_percent: float = Field(10, ge=0, le=100)
    staff_percent: float = Field(50, ge=0, le=100)
    # used when a doctor has no fee of their own for that kind of visit
    specialty_fees: dict[str, FeeSchedule] = Field(default_factory=dict)


class ReconciliationIn(BaseModel):
    date: date
    counted: dict[PayMode, int]  # paise counted / settled per mode
    note: str | None = Field(None, max_length=300)
