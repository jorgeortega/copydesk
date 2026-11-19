"""CLI: uv run python -m copydesk "<brief>" """

import sys

from langchain_core.callbacks import UsageMetadataCallbackHandler

from copydesk.graph import build_graph


def main(argv: list[str]) -> int:
    if len(argv) != 1 or not argv[0].strip():
        print('usage: python -m copydesk "<brief>"', file=sys.stderr)
        return 2

    usage = UsageMetadataCallbackHandler()
    final = build_graph().invoke({"brief": argv[0]}, config={"callbacks": [usage]})

    for ask in final["plan"].dropped_asks:
        print(f"dropped: {ask.ask} [{ask.rule_id}]")
    for v in sorted(final["variants"], key=lambda v: v.angle.index):
        print(f"{v.angle.index}. {v.angle.name:<24} {v.status:<9} rewrites={v.rewrites}")
        for x in v.violations:
            print(f"     - {x.rule_id} ({x.field}): {x.excerpt!r}")
    for model, u in usage.usage_metadata.items():
        print(
            f"tokens [{model}]: in={u['input_tokens']} out={u['output_tokens']} "
            f"total={u['total_tokens']}"
        )
    print(f"report: {final['report_path']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
