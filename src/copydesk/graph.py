"""The copydesk workflow: strategist -> Send x3 -> (copywriter <-> compliance) -> report.

The fan-out and the rewrite limit are business rules, so they are fixed edges.
"""

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from langgraph.graph import END, START, StateGraph
from langgraph.types import Send

from copydesk import report
from copydesk.agents import compliance_reviewer, copywriter, strategist
from copydesk.rules import RuleBook, check_draft, load_rules
from copydesk.schemas import AdDraft, CopyRequest, StrategyPlan, VariantResult, Violation
from copydesk.state import GraphState, VariantInput, VariantOutput, VariantState

MAX_REWRITES = 2


@dataclass(frozen=True)
class Agents:
    strategist: Callable[[str], StrategyPlan]
    copywriter: Callable[[CopyRequest], AdDraft]
    reviewer: Callable[[AdDraft, list[Violation]], list[Violation]]
    rule_check: Callable[[AdDraft], list[Violation]]


def default_agents(rulebook: RuleBook | None = None) -> Agents:
    rulebook = rulebook or load_rules()
    return Agents(
        strategist=lambda brief: strategist.run(brief, rulebook),
        copywriter=lambda request: copywriter.run(request, rulebook),
        reviewer=lambda draft, known: compliance_reviewer.run(draft, rulebook, known),
        rule_check=lambda draft: check_draft(draft, rulebook),
    )


def build_variant_graph(agents: Agents):
    def write(state: VariantState) -> dict:
        request = CopyRequest(
            brief=state.brief,
            angle=state.angle,
            previous_draft=state.draft,
            violations=state.violations,
        )
        return {"draft": agents.copywriter(request)}

    def rule_check(state: VariantState) -> dict:
        return {"violations": agents.rule_check(state.draft)}

    def llm_review(state: VariantState) -> dict:
        return {"violations": state.violations + agents.reviewer(state.draft, state.violations)}

    def route(state: VariantState) -> Literal["finalize", "bump_rewrites"]:
        if state.violations and state.rewrites < MAX_REWRITES:
            return "bump_rewrites"
        return "finalize"

    def bump_rewrites(state: VariantState) -> dict:
        return {"rewrites": state.rewrites + 1}

    def finalize(state: VariantState) -> dict:
        result = VariantResult(
            angle=state.angle,
            draft=state.draft,
            status="flagged" if state.violations else "approved",
            rewrites=state.rewrites,
            violations=state.violations,
        )
        return {"variants": [result]}

    graph = StateGraph(VariantState, input_schema=VariantInput, output_schema=VariantOutput)
    graph.add_node("copywriter", write)
    graph.add_node("rule_check", rule_check)
    graph.add_node("llm_review", llm_review)
    graph.add_node("bump_rewrites", bump_rewrites)
    graph.add_node("finalize", finalize)
    graph.add_edge(START, "copywriter")
    graph.add_edge("copywriter", "rule_check")
    graph.add_edge("rule_check", "llm_review")
    graph.add_conditional_edges("llm_review", route, ["finalize", "bump_rewrites"])
    graph.add_edge("bump_rewrites", "copywriter")
    graph.add_edge("finalize", END)
    return graph.compile()


def build_graph(agents: Agents | None = None, out_path: Path = Path("out/report.html")):
    agents = agents or default_agents()

    def plan(state: GraphState) -> dict:
        return {"plan": agents.strategist(state.brief)}

    def fan_out(state: GraphState) -> list[Send]:
        return [
            Send("variant", VariantInput(brief=state.brief, angle=angle))
            for angle in state.plan.angles
        ]

    def write_report(state: GraphState) -> dict:
        variants = sorted(state.variants, key=lambda v: v.angle.index)
        report.write(out_path, state.brief, state.plan, variants)
        return {"report_path": str(out_path)}

    graph = StateGraph(GraphState)
    graph.add_node("strategist", plan)
    graph.add_node("variant", build_variant_graph(agents))
    graph.add_node("report", write_report)
    graph.add_edge(START, "strategist")
    graph.add_conditional_edges("strategist", fan_out, ["variant"])
    graph.add_edge("variant", "report")
    graph.add_edge("report", END)
    return graph.compile()
