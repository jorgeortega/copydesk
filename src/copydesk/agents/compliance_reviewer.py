"""Compliance reviewer: LLM judgment on the rules that regexes cannot catch."""

from copydesk.config import model_for
from copydesk.rules import RuleBook, locate_finding
from copydesk.schemas import AdDraft, LLMReview, Violation

REVIEWER_PROMPT = """You are the compliance reviewer for Acme Telehealth Meta ads.

Check the ad ONLY against these rules:
{rules}

Report a finding only for a real breach of one of these rules. Use the exact rule_id, \
copy the offending text verbatim into excerpt, and give a concrete fix_hint. \
Issues already found by automated checks are listed; do not report them again. \
If the ad breaks none of the rules, return no findings."""

REVIEW_REQUEST = """Ad:
{draft}

Already found by automated checks:
{known}"""


def run(draft: AdDraft, rulebook: RuleBook, known: list[Violation]) -> list[Violation]:
    rules = "\n".join(f"- {r.rule_id}: {r.description}" for r in rulebook.llm)
    known_text = "\n".join(f'- [{v.rule_id}] "{v.excerpt}"' for v in known) or "(none)"
    model = model_for("compliance").with_structured_output(LLMReview, method="json_schema")
    review = model.invoke(
        [
            ("system", REVIEWER_PROMPT.format(rules=rules)),
            (
                "human",
                REVIEW_REQUEST.format(draft=draft.model_dump_json(indent=2), known=known_text),
            ),
        ]
    )
    return [locate_finding(f, draft) for f in review.findings]
