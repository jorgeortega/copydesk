"""Deterministic compliance checks driven by rules.yaml."""

import re
from functools import cache
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel

from copydesk.schemas import AdDraft, AdField, LLMFinding, Violation

RULES_PATH = Path(__file__).with_name("rules.yaml")


class Rule(BaseModel):
    rule_id: str
    check: Literal["regex", "max_length", "contains", "llm"]
    description: str
    fix_hint: str
    fields: list[AdField] = []
    pattern: str | None = None
    max: int | None = None
    text: str | None = None


class RuleBook(BaseModel):
    disclaimer: str
    rules: list[Rule]

    @property
    def deterministic(self) -> list[Rule]:
        return [r for r in self.rules if r.check != "llm"]

    @property
    def llm(self) -> list[Rule]:
        return [r for r in self.rules if r.check == "llm"]

    def summary(self) -> str:
        """One line per rule_id (first description wins), for prompts."""
        first: dict[str, str] = {}
        for rule in self.rules:
            first.setdefault(rule.rule_id, rule.description)
        return "\n".join(f"- {rule_id}: {desc}" for rule_id, desc in first.items())


@cache
def load_rules(path: Path = RULES_PATH) -> RuleBook:
    return RuleBook.model_validate(yaml.safe_load(path.read_text()))


def _check_field(rule: Rule, field: AdField, text: str) -> list[Violation]:
    def violation(start: int, end: int) -> Violation:
        return Violation(
            rule_id=rule.rule_id,
            field=field,
            start=start,
            end=end,
            excerpt=text[start:end],
            fix_hint=rule.fix_hint,
            source="rule",
        )

    if rule.check == "regex":
        return [violation(*m.span()) for m in re.finditer(rule.pattern, text, re.IGNORECASE)]
    if rule.check == "max_length" and len(text) > rule.max:
        return [violation(rule.max, len(text))]
    if rule.check == "contains" and rule.text not in text:
        return [violation(len(text), len(text))]
    return []


def check_draft(draft: AdDraft, rulebook: RuleBook | None = None) -> list[Violation]:
    rulebook = rulebook or load_rules()
    return [
        v
        for rule in rulebook.deterministic
        for field in rule.fields
        for v in _check_field(rule, field, draft.field_text(field))
    ]


def locate_finding(finding: LLMFinding, draft: AdDraft) -> Violation:
    """Turn an LLM finding into a Violation, computing the span from the quoted excerpt."""
    text = draft.field_text(finding.field)
    start = text.lower().find(finding.excerpt.lower())
    start, end = (start, start + len(finding.excerpt)) if start >= 0 else (0, len(text))
    return Violation(
        rule_id=finding.rule_id,
        field=finding.field,
        start=start,
        end=end,
        excerpt=text[start:end],
        fix_hint=finding.fix_hint,
        source="llm",
    )
