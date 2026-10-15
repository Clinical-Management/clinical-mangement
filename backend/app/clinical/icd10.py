"""ICD-10 code search over the bundled ICD-10-CM FY2026 list (CMS, public domain).

Kept in memory (~98k codes): no database seeding, and searches take a few ms.
"""

import gzip
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

DATA_FILE = Path(__file__).resolve().parent.parent / "data" / "icd10cm_2026.tsv.gz"

# Frequent outpatient codes, ranked first in text search (codes missing from the file are ignored)
COMMON = frozenset({
    "I10", "E11.9", "E78.5", "E03.9", "E66.9", "D64.9", "I25.10",
    "J06.9", "J02.9", "J20.9", "J18.9", "J45.909", "J30.9", "R05.9",
    "R50.9", "R51.9", "R10.9", "R11.2", "A09", "A90", "B54", "A01.00",
    "K29.70", "K21.9", "K59.00", "N39.0", "M54.50", "M19.90",
    "F41.9", "F32.A", "H10.9", "L30.9", "Z00.00",
})

_CODE_QUERY =re.compile(r"^[A-Z]\d{1,2}(\.?[0-9A-Z]{0,4})?$")


@dataclass(frozen=True)
class Icd10Code:
    code: str
    title: str
    billable: bool  # a complete code (not a category header)
    search_text: str


@lru_cache
def _codes() -> tuple[Icd10Code, ...]:
    codes = []
    with gzip.open(DATA_FILE, "rt", encoding="utf-8") as f:
        for line in f:
            if line.startswith("#"):
                continue
            code, billable, title = line.rstrip("\n").split("\t")
            codes.append(Icd10Code(code, title, billable == "1", title.lower()))
    return tuple(codes)


@lru_cache
def _by_code() -> dict[str, Icd10Code]:
    return {c.code: c for c in _codes()}


def lookup(code: str) -> Icd10Code | None:
    return _by_code().get(code.strip().upper())


def search(query: str, limit: int = 20) -> list[Icd10Code]:
    q = query.strip()
    if not q:
        return []
    upper = q.upper()
    if _CODE_QUERY.match(upper):
        # "E11", "E119" and "E11.9" all work
        prefix = upper if "." in upper or len(upper) <= 3 else f"{upper[:3]}.{upper[3:]}"
        return [c for c in _codes() if c.code.startswith(prefix)][:limit]

    words = re.findall(r"\w+", q.lower())
    matches = [c for c in _codes() if all(w in c.search_text for w in words)]

    phrase = " ".join(words)

    def rank(c: Icd10Code):
        whole = all(re.search(rf"\b{re.escape(w)}", c.search_text) for w in words)
        return (not whole, c.code not in COMMON, phrase not in c.search_text, not c.billable, len(c.title))

    return sorted(matches, key=rank)[:limit]
