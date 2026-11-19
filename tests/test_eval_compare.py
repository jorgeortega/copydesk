"""Unit tests for eval scoring and the baseline gate (no model calls)."""

from evals.run import CaseResult, aggregate, compare, load_golden


def case(**overrides) -> CaseResult:
    base = dict(
        id="g01",
        variants=3,
        rule_passes=3,
        approved=3,
        judge_compliant=3,
        judge_on_brief=4.0,
        angles_distinct=True,
        banned_asks_honored=True,
        rewrites=2,
        tokens=10_000,
    )
    return CaseResult(**(base | overrides))


def test_golden_has_8_cases_3_with_banned_asks():
    golden = load_golden()
    assert len(golden) == 8
    assert sum(bool(c.banned_asks) for c in golden) == 3


def test_crashed_case_counts_as_failing():
    metrics = aggregate([case(), CaseResult(id="g02", error="boom")])
    assert metrics["rule_pass_rate"] == 0.5
    assert metrics["errors"] == 1


def test_banned_ask_recall():
    metrics = aggregate(
        [case(banned_expected=2, banned_dropped=1), case(banned_expected=1, banned_dropped=1)]
    )
    assert metrics["banned_ask_recall"] == 2 / 3


def test_identical_run_passes():
    m = aggregate([case()])
    assert compare(m, m) == []


def test_any_quality_drop_fails():
    baseline = aggregate([case()])
    current = aggregate([case(judge_compliant=2)])
    [failure] = compare(current, baseline)
    assert failure.startswith("judge_compliant_rate dropped")


def test_cost_growth_at_30_percent_passes_above_fails():
    baseline = aggregate([case(tokens=10_000, rewrites=10)])
    assert compare(aggregate([case(tokens=13_000, rewrites=13)]), baseline) == []
    failures = compare(aggregate([case(tokens=13_001, rewrites=14)]), baseline)
    assert [f.split()[0] for f in failures] == ["rewrites", "tokens"]


def test_more_errors_fails():
    baseline = aggregate([case(), case()])
    current = aggregate([case(), CaseResult(id="x", error="boom")])
    assert any(f.startswith("errors increased") for f in compare(current, baseline))


def verdict(compliant: list[bool], on_brief: list[int], distinct: bool, honored: bool = True):
    from evals.judge import AdVerdict, JudgeVerdict

    return JudgeVerdict(
        ads=[
            AdVerdict(angle_index=i, compliant=c, on_brief=s, reason="r")
            for i, (c, s) in enumerate(zip(compliant, on_brief, strict=True), start=1)
        ],
        angles_distinct=distinct,
        banned_asks_honored=honored,
    )


def test_majority_votes_booleans_and_takes_median_score():
    from evals.judge import majority

    combined = majority(
        [
            verdict([True, False, True], [5, 2, 4], distinct=True),
            verdict([True, False, False], [3, 2, 4], distinct=False),
            verdict([False, True, False], [4, 9, 1], distinct=True, honored=False),
        ]
    )
    assert [a.compliant for a in combined.ads] == [True, False, False]
    assert [a.on_brief for a in combined.ads] == [4, 2, 4]  # 9 is clamped to 5 before the median
    assert combined.angles_distinct is True
    assert combined.banned_asks_honored is True


def test_majority_counts_a_skipped_ad_as_non_compliant():
    from evals.judge import AdVerdict, JudgeVerdict, majority

    full = verdict([True], [4], distinct=True)
    skipped = JudgeVerdict(ads=[], angles_distinct=True, banned_asks_honored=True)
    assert majority([full, skipped, skipped]).ads == [
        AdVerdict(angle_index=1, compliant=False, on_brief=4, reason="r")
    ]
