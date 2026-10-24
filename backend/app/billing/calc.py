"""Bill arithmetic. Deterministic integer maths in paise (1 rupee = 100 paise), no floats, no AI.

Order of operations (matches how Indian clinic invoices are usually drawn up):
1. line amount = quantity x unit price
2. the concession (percent or fixed) is taken off the subtotal and spread over the lines in proportion
   to their amounts (largest-remainder, so the parts add up exactly)
3. GST is charged per line on the amount after its share of the discount, rounded half-up to the paisa
4. the grand total is optionally rounded to the nearest rupee, with the difference shown as "round off"
"""

from dataclasses import dataclass

GST_RATES_BP = {0, 25, 300, 500, 1200, 1800, 2800}  # basis points: 0%, 0.25%, 3%, 5%, 12%, 18%, 28%


def rate_bp(percent: float) -> int:
    """18 -> 1800 basis points. Rates are entered as percent; only standard GST slabs are allowed."""
    bp = round(percent * 100)
    if bp not in GST_RATES_BP:
        raise ValueError(f"{percent}% is not a GST rate")
    return bp


def _pct(amount: int, bp: int) -> int:
    """amount x bp / 10000, rounded half-up (amount >= 0)."""
    return (amount * bp + 5000) // 10000


@dataclass
class Line:
    qty: int
    unit_price: int  # paise
    tax_bp: int = 0

    @property
    def amount(self) -> int:
        return self.qty * self.unit_price


def allocate(total: int, weights: list[int]) -> list[int]:
    """Split `total` in proportion to `weights` so the parts sum exactly to `total` (largest remainder)."""
    whole = sum(weights)
    if total == 0 or whole == 0:
        return [0] * len(weights)
    parts = [total * w // whole for w in weights]
    remainders = sorted(range(len(weights)), key=lambda i: (-(total * weights[i] % whole), i))
    for i in remainders[: total - sum(parts)]:
        parts[i] += 1
    return parts


def discount_for(subtotal: int, *, percent_bp: int = 0, fixed: int = 0) -> int:
    if percent_bp:
        return min(subtotal, _pct(subtotal, percent_bp))
    return min(subtotal, fixed)


def compute(lines: list[Line], *, discount: int = 0, round_to_rupee: bool = True) -> dict:
    if discount < 0:
        raise ValueError("Discount cannot be negative")
    subtotal = sum(l.amount for l in lines)
    discount = min(discount, subtotal)
    shares = allocate(discount, [l.amount for l in lines])
    out_lines = []
    tax_by_rate: dict[int, dict] = {}
    for line, share in zip(lines, shares):
        taxable = line.amount - share
        tax = _pct(taxable, line.tax_bp)
        out_lines.append({"amount": line.amount, "discount": share, "taxable": taxable, "tax": tax})
        if line.tax_bp:
            slab = tax_by_rate.setdefault(line.tax_bp, {"rate_bp": line.tax_bp, "taxable": 0, "tax": 0})
            slab["taxable"] += taxable
            slab["tax"] += tax
    taxable_total = subtotal - discount
    tax_total = sum(l["tax"] for l in out_lines)
    exact = taxable_total + tax_total
    total = (exact + 50) // 100 * 100 if round_to_rupee else exact
    return {
        "lines": out_lines,
        "subtotal": subtotal,
        "discount": discount,
        "taxable": taxable_total,
        # intra-state GST is split equally into CGST and SGST on the receipt
        "tax_by_rate": [
            {**s, "cgst": s["tax"] // 2, "sgst": s["tax"] - s["tax"] // 2} for s in sorted(tax_by_rate.values(), key=lambda s: s["rate_bp"])
        ],
        "tax": tax_total,
        "round_off": total - exact,
        "total": total,
    }


def rupees(paise: int) -> str:
    """12345 -> '123.45' (for receipts and CSV)."""
    sign = "-" if paise < 0 else ""
    paise = abs(paise)
    return f"{sign}{paise // 100}.{paise % 100:02d}"


def to_paise(rupee_amount: float | int | str) -> int:
    """'123.45' / 123.45 / 123 -> 12345, exactly (via string to avoid float error)."""
    text = f"{rupee_amount}".strip()
    whole, _, frac = text.partition(".")
    if len(frac) > 2:
        raise ValueError("At most two decimal places")
    sign = -1 if whole.startswith("-") else 1
    return sign * (abs(int(whole or "0")) * 100 + int((frac + "00")[:2]))
