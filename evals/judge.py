"""LLM judge: independent read of the final ads, with its own prompt and model (judge node)."""

from collections import defaultdict
from statistics import median

from pydantic import BaseModel, Field

from copydesk.config import model_for
from copydesk.rules import RuleBook
from copydesk.schemas import VariantResult

JUDGE_PROMPT = """You are an independent compliance and quality judge for Acme Telehealth \
Meta ads. You did not write these ads and you owe the writers nothing. Be strict.

For each ad decide:
- compliant: true only if the ad breaks none of the rules below, explicitly or by implication.
- on_brief: 1-5, how well the ad serves the legitimate (compliant) goals of the brief.

For the set of ads decide:
- angles_distinct: true if the ads take clearly different angles, not rewordings of one idea.
- banned_asks_honored: true if no ad carries any non-compliant ask from the brief.

Rules:
{rules}"""

JUDGE_REQUEST = """Brief: {brief}

Ads:
{ads}"""


class AdVerdict(BaseModel):
    angle_index: int
    compliant: bool
    on_brief: int = Field(description="1 (off brief) to 5 (excellent)")
    reason: str = Field(description="One sentence")


class JudgeVerdict(BaseModel):
    ads: list[AdVerdict]
    angles_distinct: bool
    banned_asks_honored: bool


def run(
    brief: str, variants: list[VariantResult], rulebook: RuleBook, callbacks: list
) -> JudgeVerdict:
    ads = "\n\n".join(
        f"angle_index={v.angle.index}\n{v.draft.model_dump_json(indent=2)}" for v in variants
    )
    model = model_for("judge").with_structured_output(JudgeVerdict, method="json_schema")
    return model.invoke(
        [
            ("system", JUDGE_PROMPT.format(rules=rulebook.summary())),
            ("human", JUDGE_REQUEST.format(brief=brief, ads=ads)),
        ],
        config={"callbacks": callbacks},
    )


def majority(verdicts: list[JudgeVerdict]) -> JudgeVerdict:
    """Combine independent judge samples: majority vote on booleans, median on_brief.

    An ad missing from a sample counts as a vote for non-compliant, so the vote never
    gets more lenient because the judge skipped an ad.
    """
    n = len(verdicts)

    def wins(votes: list[bool]) -> bool:
        return sum(votes) * 2 > n

    by_angle: dict[int, list[AdVerdict]] = defaultdict(list)
    for verdict in verdicts:
        for ad in verdict.ads:
            by_angle[ad.angle_index].append(ad)
    ads = [
        AdVerdict(
            angle_index=index,
            compliant=wins([a.compliant for a in samples]),
            on_brief=round(median(min(max(a.on_brief, 1), 5) for a in samples)),
            reason=samples[0].reason,
        )
        for index, samples in sorted(by_angle.items())
    ]
    return JudgeVerdict(
        ads=ads,
        angles_distinct=wins([v.angles_distinct for v in verdicts]),
        banned_asks_honored=wins([v.banned_asks_honored for v in verdicts]),
    )
