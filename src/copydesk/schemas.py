"""Pydantic models for every handoff between nodes."""

from typing import Literal

from pydantic import BaseModel, Field

AdField = Literal["primary_text", "headline", "description"]
CallToAction = Literal["Learn more", "Book now", "Sign up", "Contact us", "Subscribe"]
VariantStatus = Literal["approved", "flagged"]


class Angle(BaseModel):
    index: int = Field(description="1, 2 or 3")
    name: str = Field(description="Short label for the angle, e.g. 'Convenience'")
    hook: str = Field(description="The core idea the ad leads with")
    audience: str = Field(description="Who the ad speaks to (adults only)")
    rationale: str = Field(description="Why this angle fits the brief")


class DroppedAsk(BaseModel):
    ask: str = Field(description="The part of the brief that was dropped, quoted or paraphrased")
    reason: str
    rule_id: str = Field(description="The rule_id from the rules list that the ask would break")


class StrategyPlan(BaseModel):
    angles: list[Angle] = Field(description="Exactly 3 clearly different angles")
    dropped_asks: list[DroppedAsk] = Field(
        default_factory=list, description="Non-compliant asks removed from the brief"
    )


class AdDraft(BaseModel):
    primary_text: str = Field(description="Main ad text above the image")
    headline: str = Field(description="Bold line below the image")
    description: str = Field(description="Smaller line under the headline")
    cta: CallToAction

    def field_text(self, field: AdField) -> str:
        return getattr(self, field)


class Violation(BaseModel):
    rule_id: str
    field: AdField
    start: int = Field(description="Start offset of the offending span in the field")
    end: int = Field(description="End offset (exclusive) of the offending span")
    excerpt: str
    fix_hint: str
    source: Literal["rule", "llm"]


class LLMFinding(BaseModel):
    """What the LLM reviewer returns; offsets are computed in code from the excerpt."""

    rule_id: str
    field: AdField
    excerpt: str = Field(description="The exact offending text, copied verbatim from the field")
    fix_hint: str


class LLMReview(BaseModel):
    findings: list[LLMFinding] = Field(
        default_factory=list, description="Empty if the ad breaks none of the rules"
    )


class CopyRequest(BaseModel):
    """Everything the copywriter sees. On a rewrite: brief, angle, its draft, the violations."""

    brief: str
    angle: Angle
    previous_draft: AdDraft | None = None
    violations: list[Violation] = Field(default_factory=list)


class VariantResult(BaseModel):
    angle: Angle
    draft: AdDraft
    status: VariantStatus
    rewrites: int
    violations: list[Violation] = Field(default_factory=list)
