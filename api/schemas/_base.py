"""Base model and shared field types for every stage contract.

`Contract` forbids unknown keys, so an LLM that invents a field fails
validation and gets retried instead of being silently accepted
(CLAUDE.md hard rule 4).
"""

from typing import Annotated

from pydantic import AfterValidator, BaseModel, ConfigDict, StringConstraints


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid")


def _check_fiscal_year(value: str) -> str:
    start, end = value.split("/")
    if (int(start) + 1) % 100 != int(end):
        raise ValueError(f"fiscal year {value!r} is not two consecutive BS years")
    return value


# BS fiscal year as written in notices, e.g. "2080/81" (NEPAL_CONTEXT.md section 7).
FiscalYearBS = Annotated[
    str,
    StringConstraints(pattern=r"^\d{4}/\d{2}$"),
    AfterValidator(_check_fiscal_year),
]

# BS date normalised to YYYY-MM-DD (BS months have 29-32 days, so day <= 32).
# Not an AD date: never parse this with `date.fromisoformat`.
BSDateISO = Annotated[
    str,
    StringConstraints(pattern=r"^\d{4}-(0[1-9]|1[0-2])-(0[1-9]|[12]\d|3[0-2])$"),
]

NonEmptyStr = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
