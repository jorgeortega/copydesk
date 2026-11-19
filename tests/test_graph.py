"""Graph tests with fake agents. The deterministic rule check is the real one."""

from collections import defaultdict

from copydesk.graph import MAX_REWRITES, Agents, build_graph
from copydesk.rules import check_draft
from copydesk.schemas import AdDraft, Angle, CopyRequest, DroppedAsk, StrategyPlan, Violation

DISCLAIMER = "Rx required. Results vary."
CLEAN = AdDraft(
    primary_text=f"See a licensed clinician from home. {DISCLAIMER}",
    headline="Care on your schedule",
    description="Acme Telehealth",
    cta="Book now",
)
DIRTY = CLEAN.model_copy(update={"headline": "Guaranteed results"})  # no_false_promises


def plan() -> StrategyPlan:
    return StrategyPlan(
        angles=[
            Angle(index=i, name=f"Angle {i}", hook=f"Hook {i}", audience="Adults", rationale="r")
            for i in (1, 2, 3)
        ],
        dropped_asks=[DroppedAsk(ask="target kids", reason="minors", rule_id="no_children")],
    )


class FakeCopywriter:
    """Returns scripted drafts per angle; repeats the last one when the script runs out."""

    def __init__(self, scripts: dict[int, list[AdDraft]]):
        self.scripts = scripts
        self.requests: dict[int, list[CopyRequest]] = defaultdict(list)

    def __call__(self, request: CopyRequest) -> AdDraft:
        calls = self.requests[request.angle.index]
        calls.append(request)
        script = self.scripts.get(request.angle.index, [CLEAN])
        return script[min(len(calls), len(script)) - 1]


def agents(copywriter, reviewer=lambda draft, known: []) -> Agents:
    return Agents(
        strategist=lambda brief: plan(),
        copywriter=copywriter,
        reviewer=reviewer,
        rule_check=check_draft,
    )


def run(agents_: Agents, tmp_path):
    out = tmp_path / "report.html"
    final = build_graph(agents_, out_path=out).invoke({"brief": "make ads"})
    by_angle = {v.angle.index: v for v in final["variants"]}
    return final, by_angle, out


def test_three_clean_variants_are_approved_and_reported(tmp_path):
    writer = FakeCopywriter({})
    final, by_angle, out = run(agents(writer), tmp_path)

    assert sorted(by_angle) == [1, 2, 3]
    assert all(v.status == "approved" and v.rewrites == 0 for v in by_angle.values())
    assert all(len(reqs) == 1 for reqs in writer.requests.values())
    html = out.read_text()
    assert html.count('class="card"') == 3
    assert html.count('class="badge approved"') == 3
    assert "target kids" in html


def test_failing_draft_is_rewritten_with_its_violations(tmp_path):
    writer = FakeCopywriter({2: [DIRTY, CLEAN]})
    _, by_angle, _ = run(agents(writer), tmp_path)

    assert by_angle[2].status == "approved"
    assert by_angle[2].rewrites == 1
    first, rewrite = writer.requests[2]
    assert first.previous_draft is None and first.violations == []
    assert rewrite.previous_draft == DIRTY
    assert [v.rule_id for v in rewrite.violations] == ["no_false_promises"]
    assert rewrite.brief == "make ads" and rewrite.angle.index == 2


def test_still_failing_after_max_rewrites_is_flagged(tmp_path):
    writer = FakeCopywriter({3: [DIRTY]})
    _, by_angle, out = run(agents(writer), tmp_path)

    assert by_angle[3].status == "flagged"
    assert by_angle[3].rewrites == MAX_REWRITES == 2
    assert len(writer.requests[3]) == 3  # first draft + 2 rewrites
    assert [v.rule_id for v in by_angle[3].violations] == ["no_false_promises"]
    assert by_angle[1].status == by_angle[2].status == "approved"
    assert out.read_text().count('class="badge flagged"') == 1


def test_llm_finding_triggers_rewrite_and_sees_rule_findings(tmp_path):
    seen_known: list[list[str]] = []

    def reviewer(draft: AdDraft, known: list[Violation]) -> list[Violation]:
        seen_known.append([v.rule_id for v in known])
        if draft.description != "whole family":
            return []
        return [
            Violation(
                rule_id="no_children",
                field="description",
                start=0,
                end=12,
                excerpt="whole family",
                fix_hint="Adults only.",
                source="llm",
            )
        ]

    family = CLEAN.model_copy(update={"description": "whole family"})
    writer = FakeCopywriter({1: [family, CLEAN], 2: [DIRTY, CLEAN]})
    _, by_angle, _ = run(agents(writer, reviewer), tmp_path)

    assert by_angle[1].status == "approved" and by_angle[1].rewrites == 1
    assert [v.rule_id for v in writer.requests[1][1].violations] == ["no_children"]
    assert ["no_false_promises"] in seen_known  # reviewer is told what the rules already found


def test_report_escapes_model_text(tmp_path):
    evil = CLEAN.model_copy(update={"headline": "<script>x</script>"})
    _, _, out = run(agents(FakeCopywriter({1: [evil]})), tmp_path)
    html = out.read_text()
    assert "<script>x" not in html
    assert "&lt;script&gt;x" in html
