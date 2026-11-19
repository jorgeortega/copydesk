"""report.html: one Meta-style ad card per variant with a status badge. Single file."""

from html import escape
from pathlib import Path

from copydesk.schemas import StrategyPlan, VariantResult

PAGE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Copydesk Report</title>
<style>
  :root {{ --bg:#f0f2f5; --card:#fff; --ink:#050505; --muted:#65676b; --line:#ced0d4;
          --ok:#1a7f37; --ok-bg:#dafbe1; --warn:#9a6700; --warn-bg:#fff8c5; --btn:#e4e6eb; }}
  * {{ box-sizing:border-box; }}
  body {{ margin:0; background:var(--bg); color:var(--ink);
         font:15px/1.4 -apple-system,BlinkMacSystemFont,"Segoe UI",Helvetica,Arial,sans-serif; }}
  main {{ max-width:1180px; margin:0 auto; padding:24px 16px; }}
  h1 {{ font-size:22px; margin:0 0 4px; }}
  .brief {{ color:var(--muted); margin:0 0 16px; }}
  .dropped {{ background:var(--warn-bg); border-radius:8px; padding:10px 14px; margin:0 0 20px; }}
  .dropped ul {{ margin:6px 0 0; padding-left:20px; }}
  .grid {{ display:grid; grid-template-columns:repeat(auto-fill,minmax(320px,1fr)); gap:20px; }}
  .wrap {{ display:flex; flex-direction:column; gap:8px; }}
  .meta {{ display:flex; justify-content:space-between; align-items:center; font-size:13px; }}
  .badge {{ font-weight:600; border-radius:999px; padding:2px 10px; font-size:12px; }}
  .approved {{ color:var(--ok); background:var(--ok-bg); }}
  .flagged {{ color:var(--warn); background:var(--warn-bg); }}
  .card {{ background:var(--card); border-radius:8px; box-shadow:0 1px 2px rgba(0,0,0,.2);
          overflow:hidden; }}
  .head {{ display:flex; gap:8px; align-items:center; padding:12px; }}
  .avatar {{ width:40px; height:40px; border-radius:50%; background:#1877f2; color:#fff;
            display:grid; place-items:center; font-weight:700; }}
  .page {{ font-weight:600; }}
  .sponsored {{ color:var(--muted); font-size:13px; }}
  .primary {{ padding:0 12px 12px; white-space:pre-wrap; }}
  .image {{ aspect-ratio:1.91/1; background:linear-gradient(135deg,#1877f2,#42b72a);
           color:#fff; display:grid; place-items:center; font-size:22px; font-weight:700;
           text-align:center; padding:16px; }}
  .foot {{ display:flex; gap:12px; align-items:center; justify-content:space-between;
          background:#f7f8fa; padding:10px 12px; border-top:1px solid var(--line); }}
  .domain {{ color:var(--muted); font-size:12px; text-transform:uppercase; }}
  .headline {{ font-weight:600; }}
  .desc {{ color:var(--muted); font-size:14px; }}
  .cta {{ background:var(--btn); border-radius:6px; padding:8px 12px; font-weight:600;
         white-space:nowrap; }}
  .issues {{ font-size:13px; margin:0; padding-left:18px; color:var(--warn); }}
</style>
</head>
<body>
<main>
<h1>Acme Telehealth: ad variants</h1>
<p class="brief">Brief: {brief}</p>
{dropped}
<div class="grid">
{cards}
</div>
</main>
</body>
</html>
"""

CARD = """<div class="wrap">
  <div class="meta"><span>Angle {index}: {angle}</span>
    <span class="badge {status}">{status} · {rewrites} rewrite{plural}</span></div>
  <article class="card">
    <div class="head"><div class="avatar">A</div>
      <div><div class="page">Acme Telehealth</div><div class="sponsored">Sponsored</div></div>
    </div>
    <div class="primary">{primary}</div>
    <div class="image">{hook}</div>
    <div class="foot">
      <div><div class="domain">acmetelehealth.example</div>
        <div class="headline">{headline}</div><div class="desc">{description}</div></div>
      <div class="cta">{cta}</div>
    </div>
  </article>
  {issues}
</div>"""


def _card(v: VariantResult) -> str:
    issues = ""
    if v.violations:
        items = "".join(
            f"<li><b>{escape(x.rule_id)}</b> ({escape(x.field)}): “{escape(x.excerpt)}”</li>"
            for x in v.violations
        )
        issues = f'<ul class="issues">{items}</ul>'
    return CARD.format(
        index=v.angle.index,
        angle=escape(v.angle.name),
        status=v.status,
        rewrites=v.rewrites,
        plural="" if v.rewrites == 1 else "s",
        primary=escape(v.draft.primary_text),
        hook=escape(v.angle.hook),
        headline=escape(v.draft.headline),
        description=escape(v.draft.description),
        cta=escape(v.draft.cta),
        issues=issues,
    )


def render(brief: str, plan: StrategyPlan, variants: list[VariantResult]) -> str:
    dropped = ""
    if plan.dropped_asks:
        items = "".join(
            f"<li>{escape(d.ask)}: {escape(d.reason)} <b>[{escape(d.rule_id)}]</b></li>"
            for d in plan.dropped_asks
        )
        dropped = f'<div class="dropped"><b>Dropped from the brief</b><ul>{items}</ul></div>'
    return PAGE.format(
        brief=escape(brief), dropped=dropped, cards="\n".join(_card(v) for v in variants)
    )


def write(path: Path, brief: str, plan: StrategyPlan, variants: list[VariantResult]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render(brief, plan, variants), encoding="utf-8")
