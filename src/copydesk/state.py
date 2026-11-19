"""Graph state. `variants` is written by 3 parallel branches, so it needs a reducer."""

import operator
from typing import Annotated

from pydantic import BaseModel

from copydesk.schemas import AdDraft, Angle, StrategyPlan, VariantResult, Violation

Variants = Annotated[list[VariantResult], operator.add]


class GraphState(BaseModel):
    brief: str
    plan: StrategyPlan | None = None
    variants: Variants = []
    report_path: str | None = None


class VariantInput(BaseModel):
    brief: str
    angle: Angle


class VariantOutput(BaseModel):
    variants: Variants = []


class VariantState(BaseModel):
    brief: str
    angle: Angle
    draft: AdDraft | None = None
    violations: list[Violation] = []
    rewrites: int = 0
    variants: Variants = []
