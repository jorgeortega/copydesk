import pytest

from copydesk.rules import check_draft, load_rules, locate_finding
from copydesk.schemas import AdDraft, LLMFinding

DISCLAIMER = "Rx required. Results vary."


def make_draft(
    primary="See a licensed clinician online today.",
    headline="Care from home",
    description="Acme Telehealth",
) -> AdDraft:
    return AdDraft(
        primary_text=f"{primary} {DISCLAIMER}",
        headline=headline,
        description=description,
        cta="Learn more",
    )


def rule_ids(draft: AdDraft) -> list[str]:
    return [v.rule_id for v in check_draft(draft)]


def test_clean_draft_passes():
    assert check_draft(make_draft()) == []


def test_rulebook_loads_disclaimer():
    assert load_rules().disclaimer == DISCLAIMER


@pytest.mark.parametrize(
    "rule_id, bad, ok",
    [
        ("no_cure_claims", "This cures anxiety.", "Talk to a clinician about anxiety."),
        ("no_fda_claims", "Our FDA-approved plan.", "Our clinician-led plan."),
        ("no_rx_promise", "Get your prescription today.", "A clinician decides if Rx fits."),
        ("price_qualifier", "Visits cost $29.", "Visits starting at $29."),
        ("price_qualifier", "Only $29 a visit.", "Visits from $29."),
        ("no_body_shaming", "Lose the muffin top.", "Support for your health goals."),
        ("no_body_shaming", "Feeling fat?", "Feeling ready for a check-in?"),
        ("no_children", "Care for your kids too.", "Care for adults, on your time."),
        ("no_children", "Pediatric visits now open.", "Visits now open."),
        ("no_false_promises", "Guaranteed results.", "Real clinicians, real answers."),
        ("no_false_promises", "Feel better overnight.", "Book a visit tonight."),
        ("no_false_promises", "100% effective.", "Clinician-reviewed care."),
        ("no_false_promises", "Results in 7 days.", "Follow-ups included."),
    ],
)
def test_regex_rule_fires_on_bad_and_not_on_ok(rule_id, bad, ok):
    assert rule_id in rule_ids(make_draft(primary=bad))
    assert rule_id not in rule_ids(make_draft(primary=ok))


def test_minor_is_left_to_the_llm():
    assert "no_children" not in rule_ids(make_draft(primary="Only minor side effects."))


def test_disclaimer_does_not_trip_rx_promise():
    assert "no_rx_promise" not in rule_ids(make_draft())


def test_regex_span_points_at_the_match():
    draft = make_draft(primary="Talk to us. Guaranteed.")
    [v] = check_draft(draft)
    assert v.rule_id == "no_false_promises"
    assert v.field == "primary_text"
    assert draft.primary_text[v.start : v.end] == "Guaranteed" == v.excerpt
    assert v.source == "rule"


def test_rule_checks_every_text_field():
    v_fields = {v.field for v in check_draft(make_draft(headline="Cure it", description="Cured"))}
    assert v_fields == {"headline", "description"}


def test_missing_disclaimer():
    draft = AdDraft(
        primary_text="See a clinician.", headline="Care", description="Acme", cta="Learn more"
    )
    [v] = check_draft(draft)
    assert v.rule_id == "required_disclaimer"
    assert (v.start, v.end) == (len(draft.primary_text), len(draft.primary_text))


def test_headline_max_40():
    assert "headline_length" not in rule_ids(make_draft(headline="x" * 40))
    [v] = [v for v in check_draft(make_draft(headline="x" * 41)) if v.rule_id == "headline_length"]
    assert (v.start, v.end) == (40, 41)


def test_primary_text_max_125_includes_disclaimer():
    body = "x" * (125 - len(DISCLAIMER) - 1)  # -1 for the joining space
    assert len(make_draft(primary=body).primary_text) == 125
    assert "primary_text_length" not in rule_ids(make_draft(primary=body))
    assert "primary_text_length" in rule_ids(make_draft(primary=body + "x"))


def test_locate_finding_computes_span_from_excerpt():
    draft = make_draft(primary="Fun for the whole family.")
    finding = LLMFinding(
        rule_id="no_children", field="primary_text", excerpt="whole family", fix_hint="Adults only."
    )
    v = locate_finding(finding, draft)
    assert draft.primary_text[v.start : v.end] == "whole family"
    assert v.source == "llm"


def test_locate_finding_falls_back_to_whole_field_when_excerpt_missing():
    draft = make_draft()
    finding = LLMFinding(rule_id="no_children", field="headline", excerpt="nope", fix_hint="x")
    v = locate_finding(finding, draft)
    assert (v.start, v.end) == (0, len(draft.headline))
