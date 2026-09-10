from __future__ import annotations

from datetime import date

from src.intelligence.scoring import ScoredEntity
from src.intelligence.funding import STAGE_LABELS, format_amount
from src.report.formatter import format_reasons, format_score_change


def render_email(
    sections: list[dict],
    breakouts: list[dict] | None = None,
    watchlist: list[dict] | None = None,
    warnings: list[str] | None = None,
    macro_signals: list[str] | None = None,
    trends: dict[str, list[int]] | None = None,
) -> str:
    today = date.today().isoformat()
    trends = trends or {}

    sections_html = "".join(_render_section(s, trends) for s in sections)
    breakout_html = _render_breakouts(breakouts or [])
    watchlist_html = _render_watchlist(watchlist or [])
    warnings_html = _render_warnings(warnings or [])
    macro_html = _render_macro(macro_signals or [])

    total_count = sum(len(s["items"]) for s in sections)

    return f"""\
<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Opportunity Scanner | {today}</title>
<style>
body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background: #0d1117; color: #c9d1d9; margin: 0; padding: 0; }}
.container {{ max-width: 680px; margin: 0 auto; padding: 20px; }}
.header {{ text-align: center; padding: 30px 0 20px; border-bottom: 1px solid #30363d; }}
.header h1 {{ color: #58a6ff; font-size: 24px; margin: 0; }}
.header .date {{ color: #8b949e; font-size: 14px; margin-top: 8px; }}
.header .count {{ color: #f0883e; font-size: 13px; margin-top: 4px; }}
.section {{ margin: 24px 0; }}
.section-title {{ font-size: 16px; font-weight: 600; margin-bottom: 12px; padding-bottom: 8px; border-bottom: 1px solid #21262d; }}
.section-title.fire {{ color: #f0883e; }}
.section-title.venture {{ color: #3fb950; }}
.section-title.public {{ color: #58a6ff; }}
.section-title.tech {{ color: #bc8cff; }}
.section-title.product {{ color: #2dd4bf; }}
.section-title.ma {{ color: #f0883e; }}
.section-title.macro {{ color: #8b949e; }}
.card {{ background: #161b22; border: 1px solid #30363d; border-radius: 8px; padding: 16px; margin-bottom: 12px; }}
.card-header {{ display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 8px; }}
.card-name {{ font-size: 16px; font-weight: 600; color: #c9d1d9; }}
.card-name a {{ color: #58a6ff; text-decoration: none; }}
.card-scores {{ display: flex; gap: 12px; align-items: center; flex-shrink: 0; }}
.score-main {{ font-size: 22px; font-weight: 700; color: #f0883e; }}
.score-conf {{ font-size: 12px; color: #8b949e; text-align: right; }}
.meta {{ display: flex; gap: 6px; flex-wrap: wrap; margin-bottom: 8px; }}
.tag {{ display: inline-block; padding: 2px 8px; border-radius: 12px; font-size: 11px; font-weight: 500; }}
.tag-type {{ background: #1f6feb33; color: #58a6ff; }}
.tag-stage {{ background: #3fb95033; color: #3fb950; }}
.tag-invest {{ background: #f0883e33; color: #f0883e; }}
.tag-conf-high {{ background: #238636; color: #fff; }}
.tag-conf-med {{ background: #9e6a03; color: #fff; }}
.tag-conf-low {{ background: #da3633; color: #fff; }}
.tag-cat {{ background: #30363d; color: #c9d1d9; }}
.desc {{ color: #8b949e; font-size: 13px; line-height: 1.5; margin-bottom: 8px; }}
.reasons {{ margin: 8px 0; }}
.reason {{ font-size: 12px; color: #c9d1d9; padding: 2px 0; }}
.reason::before {{ content: "\\2022 "; color: #58a6ff; }}
.info-row {{ margin-top: 6px; font-size: 13px; }}
.info-label {{ color: #8b949e; font-size: 11px; text-transform: uppercase; letter-spacing: .03em; margin-bottom: 2px; }}
.info-value {{ color: #e6edf3; }}
.trend {{ margin-top: 8px; font-size: 12px; color: #8b949e; }}
.trend b {{ color: #e6edf3; }}
.score-change {{ font-size: 12px; padding: 4px 8px; border-radius: 4px; display: inline-block; margin-top: 4px; }}
.score-up {{ background: #23863633; color: #3fb950; }}
.score-down {{ background: #da363333; color: #f85149; }}
.score-same {{ background: #30363d; color: #8b949e; }}
.metrics {{ display: flex; gap: 12px; flex-wrap: wrap; margin-top: 8px; font-size: 12px; color: #8b949e; }}
.metric {{ display: flex; align-items: center; gap: 4px; }}
.metric-val {{ color: #c9d1d9; font-weight: 600; }}
.breakout-card {{ background: #161b22; border: 1px solid #238636; border-radius: 8px; padding: 12px 16px; margin-bottom: 8px; }}
.breakout-name {{ font-weight: 600; color: #3fb950; text-decoration: none; }}
.breakout-change {{ color: #f0883e; font-weight: 600; }}
.watch-item {{ padding: 8px 0; border-bottom: 1px solid #21262d; font-size: 14px; }}
.watch-item:last-child {{ border-bottom: none; }}
.watch-name {{ color: #58a6ff; font-weight: 500; text-decoration: none; }}
.watch-score {{ color: #8b949e; font-size: 12px; }}
.macro-item {{ padding: 4px 0; font-size: 13px; color: #bc8cff; }}
.warning {{ background: #9e6a0333; border: 1px solid #9e6a03; border-radius: 8px; padding: 12px 16px; margin-bottom: 12px; font-size: 13px; color: #e3b341; }}
.footer {{ text-align: center; padding: 20px 0; border-top: 1px solid #30363d; color: #484f58; font-size: 12px; }}
</style>
</head>
<body>
<div class="container">
  <div class="header">
    <h1>OPPORTUNITY SCANNER</h1>
    <div class="date">{today}</div>
    <div class="count">{total_count} opportunities detected</div>
  </div>

  {warnings_html}
  {sections_html}
  {breakout_html}
  {watchlist_html}
  {macro_html}

  <div class="footer">
    Generated by Opportunity Scanner | {today}
  </div>
</div>
</body>
</html>"""


def _render_section(section: dict, trends: dict[str, list[int]]) -> str:
    items = section.get("items") or []
    if not items:
        return ""
    icon = section.get("icon", "")
    title = section.get("title", "")
    kind = section.get("kind", "simple")
    cls = f"section-title {icon}" if icon else "section-title"

    cards = []
    for scored in items:
        if kind == "venture":
            cards.append(_render_invest_card(scored, trends))
        else:
            cards.append(_render_scored_card(scored, trends))
    return f"""
  <div class="section">
    <div class="{cls}">{title}</div>
    {"".join(cards)}
  </div>"""


def _meta_tags(scored: ScoredEntity, stage_label: str) -> str:
    e = scored.entity
    tags = "".join(f'<span class="tag tag-type">{t}</span>' for t in scored.types)

    conf = scored.confidence
    conf_class = "tag-conf-high" if conf >= 70 else "tag-conf-med" if conf >= 40 else "tag-conf-low"
    conf_tag = f'<span class="tag {conf_class}">Conf: {conf}</span>'
    cat_tag = f'<span class="tag tag-cat">{_esc(e.category)}</span>'

    pieces = [tags, conf_tag, cat_tag]
    if stage_label:
        pieces.insert(1, f'<span class="tag tag-stage">{_esc(stage_label)}</span>')
    if e.total_funding_m:
        pieces.append(f'<span class="tag tag-invest">Total ${e.total_funding_m:.1f}M</span>')
    return "".join(pieces)


def _score_change_html(scored: ScoredEntity) -> str:
    if scored.previous_score <= 0:
        return ""
    change_text = format_score_change(scored.previous_score, scored.score.total)
    change_class = ("score-up" if scored.score_change > 0
                    else "score-down" if scored.score_change < 0 else "score-same")
    return f'<div class="score-change {change_class}">{_esc(change_text)}</div>'


def _investors_html(scored: ScoredEntity) -> str:
    e = scored.entity
    investors = e.investors[:5]
    if not investors and not e.accelerators:
        return ""
    pieces = []
    if investors:
        pieces.append(f'<div class="info-label">Investors</div>'
                      f'<div class="info-value">{_esc(", ".join(i.capitalize() for i in investors))}</div>')
    if e.accelerators:
        pieces.append(f'<div class="info-label">Accelerator</div>'
                      f'<div class="info-value">{_esc(", ".join(a.capitalize() for a in e.accelerators))}</div>')
    return f'<div class="info-row">{"".join(pieces)}</div>'


def _funding_html(scored: ScoredEntity) -> str:
    e = scored.entity
    history = e.funding_history
    if not history:
        return ""
    row = ""
    if e.total_funding_m:
        row += f'<div class="info-label">Funding</div><div class="info-value">Total {format_amount(e.total_funding_m)}</div>'
    lines = []
    for h in history[-3:]:
        d = h.get("date", "") or ""
        stage = STAGE_LABELS.get(h.get("round"), "")
        amt = format_amount(h.get("amount_m"))
        parts = [p for p in (d, stage, amt) if p]
        if parts:
            lines.append(" · ".join(parts))
    if lines:
        row += '<div class="info-label">Funding History</div>' + "".join(
            f'<div class="info-value">{_esc(l)}</div>' for l in reversed(lines)
        )
    return f'<div class="info-row">{row}</div>'


def _trend_html(scored: ScoredEntity, trends: dict[str, list[int]]) -> str:
    if scored.previous_score > 0:
        scores = [scored.previous_score, scored.score.total]
        label = "Score"
        return f'<div class="trend">{label} trend: <b>{" → ".join(str(v) for v in scores)}</b></div>'
    trend = trends.get(scored.entity.id)
    if trend:
        return f'<div class="trend">Score: <b>{" → ".join(str(v) for v in trend)}</b></div>'
    return ""


def _render_invest_card(scored: ScoredEntity, trends: dict[str, list[int]]) -> str:
    e = scored.entity
    s = scored.score
    stage_label = STAGE_LABELS.get(e.startup_stage, "")

    name_link = f'<a href="{_esc(e.url)}" target="_blank">{_esc(e.name)}</a>'
    reasons = format_reasons(scored)
    reasons_html = "".join(f'<div class="reason">{_esc(r)}</div>' for r in reasons[:6])

    score_change_html = _score_change_html(scored)
    funding_html = _funding_html(scored)
    investors_html = _investors_html(scored)
    trend_html = _trend_html(scored, trends)

    return f"""
    <div class="card">
      <div class="card-header">
        <div>
          <div class="card-name">🚀 {name_link}</div>
          <div class="meta">{_meta_tags(scored, stage_label)}</div>
        </div>
        <div class="card-scores">
          <div class="score-main">{s.total}</div>
          <div class="score-conf">Conf<br>{scored.confidence}</div>
        </div>
      </div>
      {funding_html}
      {investors_html}
      <div class="reasons">{reasons_html}</div>
      {score_change_html}
      {trend_html}
    </div>"""


def _render_scored_card(scored: ScoredEntity, trends: dict[str, list[int]]) -> str:
    e = scored.entity
    s = scored.score
    stage_label = STAGE_LABELS.get(e.startup_stage, "")

    name_link = f'<a href="{_esc(e.url)}" target="_blank">{_esc(e.name)}</a>'
    reasons = format_reasons(scored)
    reasons_html = "".join(f'<div class="reason">{_esc(r)}</div>' for r in reasons[:6])
    score_change_html = _score_change_html(scored)
    trend_html = _trend_html(scored, trends)

    metrics_parts = []
    for label, val in s.top_signals()[:4]:
        metrics_parts.append(f'<div class="metric">{label}: <span class="metric-val">+{val}</span></div>')
    metrics_html = f'<div class="metrics">{"".join(metrics_parts)}</div>' if metrics_parts else ""

    return f"""
    <div class="card">
      <div class="card-header">
        <div>
          <div class="card-name">{name_link}</div>
          <div class="meta">{_meta_tags(scored, stage_label)}</div>
        </div>
        <div class="card-scores">
          <div class="score-main">{s.total}</div>
        </div>
      </div>
      <div class="desc">{_esc(e.description[:300])}</div>
      <div class="reasons">{reasons_html}</div>
      {metrics_html}
      {score_change_html}
      {trend_html}
    </div>"""


def _render_breakouts(breakouts: list[dict]) -> str:
    if not breakouts:
        return ""
    items = []
    for b in breakouts[:3]:
        name = _esc(b.get("name", "Unknown"))
        url = b.get("url", "#")
        items.append(f"""
    <div class="breakout-card">
      <a href="{_esc(url)}" class="breakout-name">{name}</a>
      <span class="breakout-change"> +{b.get('score_change_pct', 0)}%</span>
      <div style="font-size:12px;color:#8b949e;margin-top:4px">
        Score: {b.get('prev_score', 0)} &rarr; {b.get('curr_score', 0)}
      </div>
    </div>""")
    return f"""
  <div class="section">
    <div class="section-title venture">BREAKOUT ALERTS</div>
    {"".join(items)}
  </div>"""


def _render_watchlist(watchlist: list[dict]) -> str:
    if not watchlist:
        return ""
    items = []
    for w in watchlist[:5]:
        name = _esc(w.get("name", ""))
        url = w.get("url", "#")
        score = w.get("score", 0)
        items.append(f"""
    <div class="watch-item">
      <a href="{_esc(url)}" class="watch-name">{name}</a>
      <span class="watch-score">Score: {score}</span>
    </div>""")
    return f"""
  <div class="section">
    <div class="section-title public">WATCHLIST</div>
    {"".join(items)}
  </div>"""


def _render_macro(signals: list[str]) -> str:
    if not signals:
        return ""
    items = "".join(f'<div class="macro-item">{_esc(s)}</div>' for s in signals[:5])
    return f"""
  <div class="section">
    <div class="section-title macro">MACRO SIGNALS</div>
    {items}
  </div>"""


def _render_warnings(warnings: list[str]) -> str:
    return "".join(f'<div class="warning">{_esc(w)}</div>' for w in warnings)


def _esc(text: str) -> str:
    if not text:
        return ""
    return (text.replace("&", "&amp;").replace("<", "&lt;")
            .replace(">", "&gt;").replace('"', "&quot;"))