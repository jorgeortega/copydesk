"""Copywriter: one angle -> one Meta ad; on a rewrite, fixes the listed violations."""

from copydesk.config import model_for
from copydesk.rules import RuleBook
from copydesk.schemas import AdDraft, CopyRequest

COPYWRITER_PROMPT = """You write Meta (Facebook/Instagram) ads for Acme Telehealth, an online \
service where adults see licensed clinicians by video.

Format:
- primary_text: at most 125 characters INCLUDING the disclaimer. It must end with \
exactly: "{disclaimer}"
- headline: at most 40 characters.
- description: one short line.
- cta: one of the allowed values.

Compliance rules (every one must hold):
{rules}

Write plainly and specifically. Count characters before you answer."""

FIRST_DRAFT_REQUEST = """Brief: {brief}

Angle: {angle_name}
Hook: {hook}
Audience: {audience}

Write the ad."""

REWRITE_REQUEST = """Brief: {brief}

Angle: {angle_name}
Hook: {hook}
Audience: {audience}

Your previous draft:
{draft}

It failed compliance with these violations:
{violations}

Rewrite the ad so it fixes every violation and keeps the angle."""


def _request_text(request: CopyRequest) -> str:
    angle = request.angle
    common = dict(
        brief=request.brief, angle_name=angle.name, hook=angle.hook, audience=angle.audience
    )
    if request.previous_draft is None:
        return FIRST_DRAFT_REQUEST.format(**common)
    violations = "\n".join(
        f'- [{v.rule_id}] {v.field}: "{v.excerpt}" -> {v.fix_hint}' for v in request.violations
    )
    return REWRITE_REQUEST.format(
        **common, draft=request.previous_draft.model_dump_json(indent=2), violations=violations
    )


def run(request: CopyRequest, rulebook: RuleBook) -> AdDraft:
    model = model_for("copywriter").with_structured_output(AdDraft, method="json_schema")
    system = COPYWRITER_PROMPT.format(disclaimer=rulebook.disclaimer, rules=rulebook.summary())
    return model.invoke([("system", system), ("human", _request_text(request))])
