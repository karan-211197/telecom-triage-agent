from typing import Literal
from pydantic import BaseModel, Field

RootCause = Literal[
    "coverage_edge",
    "missing_neighbor",
    "late_trigger",
    "target_overload",
    "xn_transport",
    "ul_power_control",
]


class Diagnosis(BaseModel):
    root_cause: RootCause
    evidence: list[str] = Field(
        min_length=1,
        description="Observed KPI values and log lines that support the root cause",
    )
    recommended_fix: str
    confidence: Literal["low", "medium", "high"]