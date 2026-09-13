from __future__ import annotations

from src.intelligence.scoring import ScoredEntity, JUDGEMENT_LABELS
from src.intelligence.classification import ENTITY_TYPE_LABELS, EVENT_TYPE_LABELS
from src.intelligence.funding import format_amount_kr, STAGE_LABELS_KO
from src.report.formatter import format_reasons, format_score_change
from src import timeutil


def render_email(
    sections: list[dict],
    breakouts: list[dict] | None = None,
    watchlist: list[dict] | None = None,
    warnings: list[str] | None = None,
    macro_signals: list[str] | None = None,
    trends: dict[str, list[int]] | None = None,
    generated_at: str = "",
    collection_window: str = "",
    source_status: dict | None = None,
    report_links: list[tuple[str, str]] | None = None,
) -> str:
    generated_at = generated_at or timeutil.korean_datetime_str()
    collection_window = collection_window or ""
    trends = trends or {}
    source_status = source_status or {}
    report_links = report_links or []

    sections_html = "".join(_render_section(s, trends) for s in sections)
    breakout_html = _render_breakouts(breakouts or [])
    watchlist_html = _render_watchlist(watchlist or [])
    warnings_html = _render_warnings(warnings or [])
    macro_html = _render_macro(macro_signals or [])
    status_html = _render_source_status(source_status)
    links_html = _render_report_links(report_links)

    total_count = sum(len(s["items"]) for s in sections)

    window_html = (f'<div class="date">수집 기준: {_esc(collection_window)}</div>'
                   if collection_window else "")

    return f"""\
<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Palladium Daily Intelligence | {generated_at}</title>
<style>
body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Apple SD Gothic Neo', 'Malgun Gothic', sans-serif; background: #0d1117; color: #c9d1d9; margin: 0; padding: 0; }}
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
.score-judge {{ font-size: 11px; color: #8b949e; text-align: right; }}
.meta {{ display: flex; gap: 6px; flex-wrap: wrap; margin-bottom: 8px; }}
.tag {{ display: inline-block; padding: 2px 8px; border-radius: 12px; font-size: 11px; font-weight: 500; }}
.tag-type {{ background: #1f6feb33; color: #58a6ff; }}
.tag-stage {{ background: #3fb95033; color: #3fb950; }}
.tag-invest {{ background: #f0883e33; color: #f0883e; }}
.tag-bad {{ background: #da363333; color: #f85149; }}
.tag-cat {{ background: #30363d; color: #c9d1d9; }}
.tag-new {{ background: #2dd4bf22; color: #2dd4bf; }}
.tag-repeat {{ background: #bc8cff22; color: #bc8cff; }}
.desc {{ color: #8b949e; font-size: 13px; line-height: 1.5; margin-bottom: 8px; }}
.why {{ background: #1f6feb14; border-left: 3px solid #58a6ff; padding: 8px 10px; margin: 8px 0; font-size: 13px; line-height: 1.6; color: #dbe9ff; border-radius: 0 6px 6px 0; white-space: pre-line; }}
.narrative-block {{ margin: 8px 0; }}
.narrative-title {{ color: #8b949e; font-size: 11px; text-transform: none; letter-spacing: .05em; margin-bottom: 2px; }}
.narrative-body {{ font-size: 13px; line-height: 1.6; color: #e6edf3; white-space: pre-line; }}
.risk {{ color: #f0883e; }}
.reasons {{ margin: 8px 0; }}
.reason {{ font-size: 12px; color: #c9d1d9; padding: 2px 0; }}
.reason::before {{ content: "\\2022 "; color: #58a6ff; }}
.info-row {{ margin-top: 6px; font-size: 13px; }}
.info-label {{ color: #8b949e; font-size: 11px; letter-spacing: .03em; margin-bottom: 2px; }}
.info-value {{ color: #e6edf3; }}
.trend {{ margin-top: 8px; font-size: 12px; color: #8b949e; }}
.trend b {{ color: #e6edf3; }}
.score-change {{ font-size: 12px; padding: 4px 8px; border-radius: 4px; display: inline-block; margin-top: 4px; }}
.score-up {{ background: #23863633; color: #3fb950; }}
.score-down {{ background: #da363333; color: #f85149; }}
.score-same {{ background: #30363d; color: #8b949e; }}
.breakout-card {{ background: #161b22; border: 1px solid #238636; border-radius: 8px; padding: 12px 16px; margin-bottom: 8px; }}
.breakout-name {{ font-weight: 600; color: #3fb950; text-decoration: none; }}
.breakout-change {{ color: #f0883e; font-weight: 600; }}
.watch-item {{ padding: 8px 0; border-bottom: 1px solid #21262d; font-size: 14px; }}
.watch-item:last-child {{ border-bottom: none; }}
.watch-name {{ color: #58a6ff; font-weight: 500; text-decoration: none; }}
.watch-score {{ color: #8b949e; font-size: 12px; }}
.macro-item {{ padding: 4px 0; font-size: 13px; color: #bc8cff; }}
.status-table {{ width: 100%; border-collapse: collapse; font-size: 13px; margin-top: 4px; }}
.status-table th, .status-table td {{ border: 1px solid #30363d; padding: 6px 8px; text-align: left; }}
.status-table th {{ color: #8b949e; font-weight: 500; background: #161b22; }}
.report-link {{ display: inline-block; margin: 4px 6px 4px 0; padding: 4px 10px; border-radius: 12px; background: #161b22; border: 1px solid #30363d; color: #58a6ff; text-decoration: none; font-size: 12px; }}
.warning {{ background: #9e6a0333; border: 1px solid #9e6a03; border-radius: 8px; padding: 12px 16px; margin-bottom: 12px; font-size: 13px; color: #e3b341; }}
.footer {{ text-align: center; padding: 20px 0; border-top: 1px solid #30363d; color: #484f58; font-size: 12px; }}
</style>
</head>
<body>
<div class="container">
  <div class="header">
    <h1>Palladium Daily Intelligence</h1>
    <div class="date">{generated_at} · 기준시각(한국)</div>
    {window_html}
    <div class="count">오늘 감지된 기회: {total_count}개 (최대 50개)</div>
  </div>

  {warnings_html}
  {sections_html}
  {breakout_html}
  {watchlist_html}
  {macro_html}
  {status_html}
  {links_html}

  <div class="footer">
    Palladium Daily Intelligence 자동 생성 | {generated_at}
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
    cls = f"section-title {icon}" if icon else "section-title"

    cards = [""]
    for scored in items:
        cards.append(_render_card(scored, trends))
    return f"""
  <div class="section">
    <div class="{cls}">{title}</div>
    {"".join(cards)}
  </div>"""


def _meta_tags(scored: ScoredEntity, stage_label: str) -> str:
    e = scored.entity
    tags = []

    if scored.previous_score > 0:
        tags.append('<span class="tag tag-repeat">기존 이벤트 재확인</span>')
    else:
        tags.append('<span class="tag tag-new">신규 이벤트</span>')

    type_label = ENTITY_TYPE_LABELS.get(scored.entity_type)
    if type_label:
        tags.append(f'<span class="tag tag-type">{_esc(type_label)}</span>')

    for etype in scored.event_types[:3]:
        label = EVENT_TYPE_LABELS.get(etype)
        if label:
            tags.append(f'<span class="tag tag-cat">{_esc(label)}</span>')

    if stage_label:
        tags.append(f'<span class="tag tag-stage">{_esc(stage_label)}</span>')

    status_label = {
        "confirmed": None,
        "planned": "투자 계획",
        "withdrawn": "투자 무산/철회",
    }.get(e.funding_status)
    if status_label:
        tags.append(f'<span class="tag tag-bad">{_esc(status_label)}</span>')

    if e.category and e.category.lower() not in ("other", "기타"):
        tags.append(f'<span class="tag tag-cat">{_esc(e.category)}</span>')

    conf = scored.confidence
    conf_class = "tag-stage" if conf >= 70 else "tag-type" if conf >= 40 else "tag-bad"
    tags.append(f'<span class="tag {conf_class}">신뢰도 {conf}%</span>')

    return "".join(tags)


def _score_change_html(scored: ScoredEntity) -> str:
    if scored.previous_score <= 0:
        return ""
    change_text = format_score_change(scored.previous_score, scored.score.total)
    change_class = ("score-up" if scored.score_change > 0
                    else "score-down" if scored.score_change < 0 else "score-same")
    return f'<div class="score-change {change_class}">{_esc(change_text)}</div>'


def _investors_html(scored: ScoredEntity) -> str:
    e = scored.entity
    investors = [i.capitalize() for i in e.investors[:5]]
    if not investors and not e.accelerators:
        return ""
    pieces = []
    if investors:
        pieces.append(f'<div class="info-label">주요 투자자</div>'
                      f'<div class="info-value">{_esc(", ".join(investors))}</div>')
    if e.accelerators:
        pieces.append(f'<div class="info-label">액셀러레이터</div>'
                      f'<div class="info-value">{_esc(", ".join(a.capitalize() for a in e.accelerators))}</div>')
    return f'<div class="info-row">{"".join(pieces)}</div>'


def _funding_html(scored: ScoredEntity) -> str:
    e = scored.entity
    history = e.funding_history
    if not history:
        return ""
    row = ""
    lines = []
    for h in history[-3:]:
        d = h.get("date", "") or ""
        stage = STAGE_LABELS_KO.get(h.get("round"), "")
        amt = format_amount_kr(h.get("amount_m"), h.get("currency", "USD"))
        status = {
            "withdrawn": "무산",
            "planned": "계획",
            "confirmed": "확정",
        }.get(h.get("status"), "확정")
        parts = [p for p in (d, stage, amt, status) if p]
        if parts:
            lines.append(" · ".join(parts))
    if lines:
        row += '<div class="info-label">투자 현황</div>' + "".join(
            f'<div class="info-value">{_esc(l)}</div>' for l in reversed(lines)
        )
    if e.parent_company:
        row += f'<div class="info-label">모기업</div><div class="info-value">{_esc(e.parent_company)}</div>'
    return f'<div class="info-row">{row}</div>'


def _trend_html(scored: ScoredEntity, trends: dict[str, list[int]]) -> str:
    if scored.previous_score > 0:
        scores = [scored.previous_score, scored.score.total]
        return f'<div class="trend">점수 추이: <b>{" → ".join(str(v) for v in scores)}</b></div>'
    trend = trends.get(scored.entity.id)
    if trend:
        return f'<div class="trend">점수 추이: <b>{" → ".join(str(v) for v in trend)}</b></div>'
    return ""


def _confidence_evidence_html(scored: ScoredEntity) -> str:
    if not scored.conf_evidence:
        return ""
    items = " · ".join(_esc(x) for x in scored.conf_evidence[:5])
    return f'<div class="info-row"><div class="info-label">신뢰도 근거</div><div class="info-value">{items}</div></div>'


def _narrative_html(scored: ScoredEntity) -> str:
    n = scored.narrative or {}
    blocks = []
    if n.get("why"):
        blocks.append(
            f'<div class="narrative-block"><div class="narrative-title">왜 주목?</div>'
            f'<div class="narrative-body">{_esc(n["why"])}</div></div>'
        )
    if n.get("investment"):
        blocks.append(
            f'<div class="narrative-block"><div class="narrative-title">투자 관점</div>'
            f'<div class="narrative-body">{_esc(n["investment"])}</div></div>'
        )
    if n.get("risk"):
        blocks.append(
            f'<div class="narrative-block"><div class="narrative-title risk">주의할 점</div>'
            f'<div class="narrative-body risk">{_esc(n["risk"])}</div></div>'
        )
    return "".join(blocks)


def _render_card(scored: ScoredEntity, trends: dict[str, list[int]]) -> str:
    e = scored.entity
    s = scored.score
    stage_label = STAGE_LABELS_KO.get(e.startup_stage, "")
    judge_label = JUDGEMENT_LABELS.get(scored.judgement, "")

    name_link = f'<a href="{_esc(e.url)}" target="_blank">{_esc(e.name)}</a>'
    reasons = format_reasons(scored)
    reasons_html = "".join(f'<div class="reason">{_esc(r)}</div>' for r in reasons[:8])

    score_change_html = _score_change_html(scored)
    funding_html = _funding_html(scored)
    investors_html = _investors_html(scored)
    trend_html = _trend_html(scored, trends)
    evidence_html = _confidence_evidence_html(scored)
    narrative_html = _narrative_html(scored)

    return f"""
    <div class="card">
      <div class="card-header">
        <div>
          <div class="card-name">{name_link}</div>
          <div class="meta">{_meta_tags(scored, stage_label)}</div>
        </div>
        <div class="card-scores">
          <div class="score-main">{s.total}</div>
          <div class="score-judge">{_esc(judge_label)}</div>
        </div>
      </div>
      <div class="desc">{_esc(e.description[:300])}</div>
      {narrative_html}
      <div class="reasons">{reasons_html}</div>
      {funding_html}
      {investors_html}
      {evidence_html}
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
        점수: {b.get('prev_score', 0)} &rarr; {b.get('curr_score', 0)}
      </div>
    </div>""")
    return f"""
  <div class="section">
    <div class="section-title venture">급등 감지</div>
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
      <span class="watch-score">점수: {score}</span>
    </div>""")
    return f"""
  <div class="section">
    <div class="section-title public">관심 목록</div>
    {"".join(items)}
  </div>"""


def _render_macro(signals: list[str]) -> str:
    if not signals:
        return ""
    items = "".join(f'<div class="macro-item">{_esc(s)}</div>' for s in signals[:5])
    return f"""
  <div class="section">
    <div class="section-title macro">거시경제 신호</div>
    {items}
  </div>"""


def _render_warnings(warnings: list[str]) -> str:
    return "".join(f'<div class="warning">{_esc(w)}</div>' for w in warnings)


def _esc(text: str) -> str:
    if not text:
        return ""
    return (text.replace("&", "&amp;").replace("<", "&lt;")
            .replace(">", "&gt;").replace('"', "&quot;"))


def _render_source_status(source_status: dict) -> str:
    if not source_status:
        return ""
    rows = []
    for name, info in source_status.items():
        status = _esc(info.get("status", "?"))
        n = info.get("items", 0)
        rows.append(f'<tr><td>{_esc(name)}</td><td>{status}</td><td>{n}</td></tr>')
    return f"""
  <div class="section">
    <div class="section-title macro">데이터 수집 상태</div>
    <table class="status-table">
      <tr><th>소스</th><th>상태</th><th>항목 수</th></tr>
      {"".join(rows)}
    </table>
  </div>"""


def _render_report_links(report_links: list[tuple[str, str]]) -> str:
    if not report_links:
        return ""
    items = []
    for label, url in report_links:
        items.append(f'<a href="{_esc(url)}" class="report-link" target="_blank">{_esc(label)}</a>')
    return f"""
  <div class="section">
    <div class="section-title product">보고서 (GitHub Markdown)</div>
    {"".join(items)}
  </div>"""