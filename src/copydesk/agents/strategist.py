"""Strategist: vague brief -> 3 different compliant angles, dropping non-compliant asks."""

from copydesk.config import model_for
from copydesk.rules import RuleBook
from copydesk.schemas import StrategyPlan

STRATEGIST_PROMPT = """You are the ad strategist for Acme Telehealth, an online service where \
adults see licensed clinicians by video and, when a clinician decides it is appropriate, get \
prescriptions.

Turn the client's brief into exactly 3 clearly different creative angles for Meta ads \
(e.g. convenience, cost, privacy, clinician quality). Each angle targets adults only.

Some asks in a brief may break the compliance rules below. Do not build any angle on them. \
List each one in dropped_asks with the rule_id it would break. If nothing must be dropped, \
return an empty list.

Compliance rules:
{rules}"""


def run(brief: str, rulebook: RuleBook) -> StrategyPlan:
    model = model_for("strategist").with_structured_output(StrategyPlan, method="json_schema")
    plan = model.invoke(
        [
            ("system", STRATEGIST_PROMPT.format(rules=rulebook.summary())),
            ("human", f"Brief: {brief}"),
        ]
    )
    if len(plan.angles) != 3:
        raise ValueError(f"Strategist returned {len(plan.angles)} angles, expected 3")
    for i, angle in enumerate(plan.angles, start=1):
        angle.index = i
    return plan
