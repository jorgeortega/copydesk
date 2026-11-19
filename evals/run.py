"""Eval harness: real model, golden briefs, scored with copydesk.rules plus an LLM judge.

uv run python -m evals.run [--save-baseline | --compare results/baseline.json]
"""

import argparse
import json
import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from pathlib import Path

import yaml
from langchain_core.callbacks import UsageMetadataCallbackHandler
from pydantic import BaseModel

from copydesk.graph import build_graph
from copydesk.rules import check_draft, load_rules
from copydesk.schemas import StrategyPlan, VariantResult
from evals import judge

GOLDEN_PATH = Path(__file__).with_name("golden.yaml")
RESULTS_DIR = Path("results")
BASELINE_PATH = RESULTS_DIR / "baseline.json"
LATEST_PATH = RESULTS_DIR / "latest.json"
CONCURRENCY = 8
JUDGE_SAMPLES = 3  # judge each case 3 times and take the majority, to damp judge noise
COST_GROWTH_LIMIT = 0.30

# Higher is better; any drop vs baseline fails --compare.
QUALITY_METRICS = [
    "rule_pass_rate",
    "approved_rate",
    "judge_compliant_rate",
    "judge_on_brief",
    "angles_distinct_rate",
    "banned_asks_honored_rate",
    "banned_ask_recall",
]
# Lower is better; more than +30% vs baseline fails --compare. Judge tokens are excluded:
# they measure the eval, not the pipeline.
COST_METRICS = ["rewrites", "tokens"]


class GoldenCase(BaseModel):
    id: str
    brief: str
    banned_asks: list[str] = []


class CaseResult(BaseModel):
    id: str
    variants: int = 0
    rule_passes: int = 0
    approved: int = 0
    judge_compliant: int = 0
    judge_on_brief: float = 0.0
    angles_distinct: bool = False
    banned_asks_honored: bool = False
    banned_expected: int = 0
    banned_dropped: int = 0
    rewrites: int = 0
    tokens: int = 0
    judge_tokens: int = 0
    error: str | None = None


def load_golden(path: Path = GOLDEN_PATH) -> list[GoldenCase]:
    return [GoldenCase.model_validate(c) for c in yaml.safe_load(path.read_text())]


def _total_tokens(handler: UsageMetadataCallbackHandler) -> int:
    return sum(u["total_tokens"] for u in handler.usage_metadata.values())


def run_case(case: GoldenCase) -> CaseResult:
    result = CaseResult(id=case.id, banned_expected=len(case.banned_asks))
    pipeline_usage, judge_usage = UsageMetadataCallbackHandler(), UsageMetadataCallbackHandler()
    try:
        graph = build_graph(out_path=Path("out/evals") / f"{case.id}.html")
        final = graph.invoke({"brief": case.brief}, config={"callbacks": [pipeline_usage]})
        plan: StrategyPlan = final["plan"]
        variants: list[VariantResult] = sorted(final["variants"], key=lambda v: v.angle.index)
        verdict = judge.majority(
            [
                judge.run(case.brief, variants, load_rules(), callbacks=[judge_usage])
                for _ in range(JUDGE_SAMPLES)
            ]
        )

        compliant_angles = {a.angle_index for a in verdict.ads if a.compliant}
        on_brief = [a.on_brief for a in verdict.ads]
        result.variants = len(variants)
        result.rule_passes = sum(not check_draft(v.draft) for v in variants)
        result.approved = sum(v.status == "approved" for v in variants)
        result.judge_compliant = sum(v.angle.index in compliant_angles for v in variants)
        result.judge_on_brief = sum(on_brief) / len(on_brief) if on_brief else 0.0
        result.angles_distinct = verdict.angles_distinct
        result.banned_asks_honored = verdict.banned_asks_honored
        result.banned_dropped = len({d.rule_id for d in plan.dropped_asks} & set(case.banned_asks))
        result.rewrites = sum(v.rewrites for v in variants)
    except Exception as exc:  # a crashed case scores zero, so it shows up as a drop
        result.error = f"{type(exc).__name__}: {exc}"
    result.tokens = _total_tokens(pipeline_usage)
    result.judge_tokens = _total_tokens(judge_usage)
    return result


def aggregate(cases: list[CaseResult], variants_per_case: int = 3) -> dict[str, float]:
    # Denominators use the expected variant count so a crashed case counts as failing.
    n_variants = len(cases) * variants_per_case
    banned_expected = sum(c.banned_expected for c in cases)
    return {
        "rule_pass_rate": sum(c.rule_passes for c in cases) / n_variants,
        "approved_rate": sum(c.approved for c in cases) / n_variants,
        "judge_compliant_rate": sum(c.judge_compliant for c in cases) / n_variants,
        "judge_on_brief": sum(c.judge_on_brief for c in cases) / len(cases),
        "angles_distinct_rate": sum(c.angles_distinct for c in cases) / len(cases),
        "banned_asks_honored_rate": sum(c.banned_asks_honored for c in cases) / len(cases),
        "banned_ask_recall": (
            sum(c.banned_dropped for c in cases) / banned_expected if banned_expected else 1.0
        ),
        "rewrites": sum(c.rewrites for c in cases),
        "tokens": sum(c.tokens for c in cases),
        "judge_tokens": sum(c.judge_tokens for c in cases),
        "errors": sum(c.error is not None for c in cases),
    }


def compare(current: dict[str, float], baseline: dict[str, float]) -> list[str]:
    """Return one message per regression; empty means no regression."""
    failures = []
    for name in QUALITY_METRICS:
        if current[name] < baseline[name]:
            failures.append(f"{name} dropped: {baseline[name]:.3f} -> {current[name]:.3f}")
    for name in COST_METRICS:
        limit = baseline[name] * (1 + COST_GROWTH_LIMIT)
        if current[name] > limit:
            failures.append(
                f"{name} grew more than {COST_GROWTH_LIMIT:.0%}: "
                f"{baseline[name]:g} -> {current[name]:g} (limit {limit:g})"
            )
    if current["errors"] > baseline["errors"]:
        failures.append(f"errors increased: {baseline['errors']:g} -> {current['errors']:g}")
    return failures


def _print_report(cases: list[CaseResult], metrics: dict, baseline: dict | None) -> None:
    print(
        f"{'case':<5} {'rules':>5} {'appr':>5} {'judge':>5} {'brief':>5} "
        f"{'distinct':>8} {'banned':>7} {'rewr':>4} {'tokens':>7}"
    )
    for c in cases:
        banned = f"{c.banned_dropped}/{c.banned_expected}" if c.banned_expected else "-"
        print(
            f"{c.id:<5} {c.rule_passes:>3}/3 {c.approved:>3}/3 {c.judge_compliant:>3}/3 "
            f"{c.judge_on_brief:>5.2f} {str(c.angles_distinct):>8} {banned:>7} "
            f"{c.rewrites:>4} {c.tokens:>7}" + (f"  ERROR {c.error}" if c.error else "")
        )
    print()
    for name, value in metrics.items():
        line = (
            f"{name:<26} {value:>10.3f}" if isinstance(value, float) else f"{name:<26} {value:>10}"
        )
        if baseline is not None and name in baseline:
            line += f"   (baseline {baseline[name]:g})"
        print(line)


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="python -m evals.run")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--save-baseline", action="store_true", help=f"write {BASELINE_PATH}")
    mode.add_argument("--compare", type=Path, metavar="BASELINE", help="exit 1 on regression")
    args = parser.parse_args(argv)

    baseline = json.loads(args.compare.read_text())["metrics"] if args.compare else None
    golden = load_golden()
    with ThreadPoolExecutor(max_workers=CONCURRENCY) as pool:
        cases = list(pool.map(run_case, golden))
    metrics = aggregate(cases)

    payload = {
        "created": datetime.now(UTC).isoformat(timespec="seconds"),
        "metrics": metrics,
        "cases": [c.model_dump() for c in cases],
    }
    RESULTS_DIR.mkdir(exist_ok=True)
    LATEST_PATH.write_text(json.dumps(payload, indent=2))
    if args.save_baseline:
        BASELINE_PATH.write_text(json.dumps(payload, indent=2))

    _print_report(cases, metrics, baseline)
    print(
        f"\nresults: {LATEST_PATH}"
        + (f", baseline saved: {BASELINE_PATH}" if args.save_baseline else "")
    )
    if baseline is None:
        return 0
    failures = compare(metrics, baseline)
    for f in failures:
        print(f"REGRESSION: {f}")
    print("compare: FAIL" if failures else "compare: OK")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
