"""Palladium Markdown reports.

Rule-based, markdown-only daily reports written under reports/<date>/.
Section domains (startup-radar, market-anomaly, ...) are emitted ONLY when
the domain actually has meaningful items. Numbers and funding shown come
from observed data — no fabricated figures.
"""
from __future__ import annotations

from src.intelligence.scoring import ScoredEntity
from src.intelligence.classification import ENTITY_TYPE_LABELS, EVENT_TYPE_LABELS
from src.intelligence.funding import format_amount_kr, STAGE_LABELS_KO
from src.report.formatter import format_reasons, format_score_change
from src.analyzers.trajectory import ACCELERATING, GROWING
from src import analyzers
from src import timeutil

# (filename, [section title substrings that map to this domain report])
REPORT_FILES: dict[str, list[str]] = {
    "startup-radar.md": ["글로벌 스타트업"],
    "market-anomaly.md": ["글로벌 공개시장"],
    "tech-trend.md": ["글로벌 기술"],
    "product-opportunity.md": ["글로벌 제품"],
    "deal-mna.md": ["글로벌 M&A"],
}

KOREA_SECTION_KEYS = ["한국 투자", "한국 공개시장", "한국 기술"]


def _md(v: str) -> str:
    if not v:
        return ""
    return (v.replace("|", "\\|").replace("\n", " ")
            .replace("\r", " ").strip())


def _new_repeat(scored: ScoredEntity) -> str:
    return "재확인" if scored.previous_score > 0 else "신규"


def _entity_block(scored: ScoredEntity) -> str:
    e = scored.entity
    lines: list[str] = []
    lines.append(
        f"### {_md(e.name)} — {scored.score.total}점 · "
        f"{scored.judgement} · {scored.opportunity_type} · 신뢰도 {scored.confidence}%"
    )
    lines.append("")

    meta: list[str] = []
    et = scored.entity_type
    et_label = ENTITY_TYPE_LABELS.get(et, et)
    meta.append(f"종류: {_md(et_label)}")
    ev_labels = [EVENT_TYPE_LABELS.get(x, x) for x in scored.event_types[:4]]
    if ev_labels:
        meta.append(f"이벤트: {', '.join(_md(x) for x in ev_labels)}")
    stage_label = STAGE_LABELS_KO.get(e.startup_stage, "")
    if stage_label:
        meta.append(f"단계: {_md(stage_label)}")
    meta.append(f"판정: {_md(scored.judgement)}")
    meta.append(
        f"기회 유형: {scored.opportunity_type}"
        f" ({analyzers.opp_type_label(scored.opportunity_type)})"
    )
    meta.append(f"근거 품질: {scored.evidence_quality}"
                f"({analyzers.quality_label(scored.evidence_quality)})")
    meta.append(
        f"궤적: {scored.trajectory}({analyzers.traj_label(scored.trajectory)}) · "
        f"생애주기: {scored.lifecycle}({analyzers.lifecycle_label(scored.lifecycle)})"
    )
    meta.append(f"신규/재확인: {_new_repeat(scored)}")
    lines.append("- " + "\n- ".join(meta))

    if e.description:
        lines.append("")
        lines.append(f"> {_md(e.description[:200])}")

    funding = _funding_lines(scored)
    if funding:
        lines.append("")
        lines.append("- **투자/성장**: " + " · ".join(funding))

    if e.investors:
        lines.append("- **주요 투자자**: " + ", ".join(_md(x) for x in e.investors[:5]))
    if e.accelerators:
        lines.append("- **액셀러레이터**: " + ", ".join(_md(x) for x in e.accelerators[:3]))

    if scored.previous_score > 0:
        lines.append(f"- **점수 변화**: {format_score_change(scored.previous_score, scored.score.total)}")

    if scored.convergence:
        conv = ", ".join(analyzers.convergence_label(c) for c in scored.convergence)
        lines.append(f"- **교차 신호**: {conv} (CONVERGENCE)")

    reasons = format_reasons(scored)
    if reasons:
        lines.append("")
        lines.append("**근거**")
        lines.append("")
        for r in reasons[:8]:
            lines.append(f"- {_md(r)}")

    n = scored.narrative or {}
    for key, title in (("why", "왜 주목?"), ("investment", "투자 관점"), ("risk", "주의할 점")):
        if n.get(key):
            lines.append("")
            lines.append(f"**{title}**")
            lines.append("")
            lines.append(_md(n[key]))

    chain = _evidence_chain(scored)
    if chain:
        lines.append("")
        lines.append("**Evidence Chain**")
        lines.append("")
        for item in chain:
            lines.append(f"- {item}")

    lines.append("")
    lines.append("---")
    lines.append("")
    return "\n".join(lines)


def _funding_lines(scored: ScoredEntity) -> list[str]:
    lines = []
    for h in scored.entity.funding_history[-3:]:
        d = h.get("date", "")
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
    return lines


def _evidence_chain(scored: ScoredEntity) -> list[str]:
    e = scored.entity
    chain: list[str] = []
    for ev in (e.events or [])[-5:]:
        label = EVENT_TYPE_LABELS.get(ev.get("type"), ev.get("type", ""))
        d = ev.get("date", "")
        desc = _md(ev.get("description", ""))[:120]
        url = ev.get("url", "") or ""
        srcs = ev.get("sources", []) or []
        src_txt = " · ".join(s.split(":")[-1] for s in srcs if s)
        if url:
            chain.append(f"`{label}` {d} — {desc} ([출처]({url})) [{src_txt}]")
        else:
            chain.append(f"`{label}` {d} — {desc} [{src_txt}]")
    if e.signal_sources:
        srcs = [s.split(":")[-1] for s in e.signal_sources if s]
        chain.append(f"출처: {', '.join(dict.fromkeys(srcs))}")
    return chain


def _render_section(title: str, items: list[ScoredEntity]) -> str:
    blocks = [f"## {title}", ""]
    for scored in items:
        blocks.append(_entity_block(scored))
    return "\n".join(blocks) + "\n"


def _top_table(items: list[ScoredEntity]) -> str:
    rows = ["| # | 대상 | 점수 | 판정 | 유형 | 신뢰도 |", "|---|------|-----|-----|-----|-------|"]
    for i, s in enumerate(items[:10], 1):
        url = s.entity.url or ""
        name = _md(s.entity.name)
        link = f"[{name}]({url})" if url else name
        rows.append(f"| {i} | {link} | {s.score.total} | {_md(s.judgement)} | "
                    f"{s.opportunity_type} | {s.confidence}% |")
    return "\n".join(rows)


def _breakout_table(breakouts: list[dict]) -> str:
    if not breakouts:
        return ""
    rows = ["| 대상 | 전일 | 금일 | 상승률 |", "|------|------|------|--------|"]
    for b in breakouts[:10]:
        url = b.get("url", "")
        name = _md(b.get("name", "Unknown"))
        link = f"[{name}]({url})" if url else name
        rows.append(f"| {link} | {b.get('prev_score', 0)} | {b.get('curr_score', 0)} | "
                    f"+{b.get('score_change_pct', 0)}% |")
    return "\n".join(rows)


def _source_status_table(source_status: dict) -> str:
    if not source_status:
        return "_수집 상태 정보 없음_"
    rows = ["| 소스 | 상태 | 항목 수 |", "|------|------|---------|"]
    for name, info in source_status.items():
        status = info.get("status", "?")
        n = info.get("items", 0)
        rows.append(f"| {name} | {status} | {n} |")
    return "\n".join(rows)


def _summary_md(
    generated_at,
    collection_window: str,
    sections: list[dict],
    scored: list[ScoredEntity],
    macro_events: list[dict],
    macro_signals: list[str],
    breakouts: list[dict],
    source_status: dict,
    second_order: list[dict],
    watchlist: list[dict],
    all_items: list[ScoredEntity],
    generated: set[str],
) -> str:
    total = sum(len(s["items"]) for s in sections)
    top = sections[0]["items"] if sections else []
    new_count = sum(1 for s in all_items if s.previous_score <= 0)
    repeat_count = sum(1 for s in all_items if s.previous_score > 0)
    conv_list = [s for s in all_items if s.convergence]

    out: list[str] = []
    out.append("# ⚡ Palladium Daily Summary")
    out.append("")
    out.append(f"> 생성시각(한국): **{timeutil.korean_datetime_str(generated_at)}**")
    if collection_window:
        out.append(f"> 수집 기준: {collection_window}")
    out.append("> 규칙 기반 분석 (AI 없음) · 최대 보고 항목: 50개")
    out.append("")

    out.append("## 실행 요약")
    out.append("")
    out.append(f"- 감지된 기회: **{total}개** (섹션 수: {len(sections)})")
    out.append(f"- 최우선(TOP, ≥70점): {len(top)}")
    out.append(f"- 급등(Breakout): {len(breakouts)} · 워치리스트: {len(watchlist)}")
    out.append(f"- 교차 신호(수렴): {len(conv_list)}")
    out.append(f"- 신규 이벤트: {new_count} · 기존 재확인: {repeat_count}")
    out.append("")

    if top:
        out.append("## 최우선 기회 (TOP)")
        out.append("")
        out.append(_top_table(top))
        out.append("")

    breakouts_tbl = _breakout_table(breakouts)
    if breakouts_tbl:
        out.append("## 주요 변화 (Breakout)")
        out.append("")
        out.append(breakouts_tbl)
        out.append("")

    if conv_list:
        out.append("## 교차 신호 (Convergence)")
        out.append("")
        for s in conv_list[:10]:
            labels = ", ".join(analyzers.convergence_label(c) for c in s.convergence)
            out.append(f"- **{_md(s.entity.name)}** — {labels} (점수 {s.score.total})")
        out.append("")

    if second_order:
        out.append("## 2차 기회 (Second-Order)")
        out.append("")
        out.append("> 파생/가능성 기반. 확인된 숫자가 아니며 추가 검증이 필요합니다.")
        out.append("")
        for so in second_order[:12]:
            trigger = _md(so.get("trigger", ""))
            url = so.get("url", "")
            target = f"[{trigger}]({url})" if url else trigger
            chain = "; ".join(_md(x) for x in so.get("chain", []))
            out.append(f"- **{target}** ({so.get('status', 'Derived')}) → {chain}")
        out.append("")

    if macro_signals:
        out.append("## 거시경제 신호")
        out.append("")
        for ms in macro_signals[:5]:
            out.append(f"- {_md(ms)}")
        out.append("")

    watch = [(w.get("name", ""), w.get("score", 0), w.get("url", "")) for w in (watchlist or [])[:5]]
    if watch:
        out.append("## 워치리스트")
        out.append("")
        for name, score, url in watch:
            link = f"[{_md(name)}]({url})" if url else _md(name)
            out.append(f"- {link} — 점수 {score}")
        out.append("")

    out.append("## 데이터 수집 상태")
    out.append("")
    out.append(_source_status_table(source_status))
    out.append("")

    out.append("## 보고서 링크")
    out.append("")
    order = ["daily-summary.md", "opportunities.md", "startup-radar.md", "market-anomaly.md",
             "tech-trend.md", "product-opportunity.md", "deal-mna.md", "korea-company.md",
             "dart-events.md", "company-growth.md", "second-order.md", "market-entry.md"]
    for name in order:
        if name in generated:
            label = name.replace("-", " ").replace(".md", "")
            out.append(f"[{label}]({name})")
    out.append("")
    return "\n".join(out) + "\n"


def _domain_file(filename: str, title: str, items: list[ScoredEntity]) -> str | None:
    if not items:
        return None
    return f"# ⚡ {title}\n\n" + _render_section(title, items)


def render_markdown_reports(
    sections: list[dict],
    scored: list[ScoredEntity],
    macro_events: list[dict],
    macro_signals: list[str],
    breakouts: list[dict],
    source_status: dict,
    generated_at,
    collection_window: str,
    second_order: list[dict],
    watchlist: list[dict] | None = None,
) -> dict[str, str]:
    """Return {filename: markdown}. Only files with content are produced."""
    watchlist = watchlist or []
    all_items = [s for sec in sections for s in sec["items"]]
    files: dict[str, str] = {}

    base = generated_at or timeutil.now_kst()

    # opportunities.md: every section as a heading with full entity blocks.
    opp: list[str] = ["# ⚡ 전일 기회 상세 (Opportunities)", ""]
    for sec in sections:
        opp.append(_render_section(sec.get("title", ""), sec["items"]))
    if opp[1:]:
        files["opportunities.md"] = "\n".join(opp)

    # Domain reports (only when the domain has items).
    for filename, keys in REPORT_FILES.items():
        matched: list[dict] = []
        for sec in sections:
            if any(k in (sec.get("title") or "") for k in keys):
                matched.append(sec)
        items = [s for sec in matched for s in sec["items"]]
        if items and matched:
            domain_title = " / ".join(sec.get("title", "") for sec in matched)
            md_body = _domain_file(filename, domain_title, items)
            if md_body:
                files[filename] = md_body

    # Company growth: non-Korean entities with an accelerating/growing score
    # trajectory across days — surfaced only when history supports it.
    growth = sorted(
        (s for s in all_items
         if not s.entity.is_korean
         and s.trajectory in (ACCELERATING, GROWING)),
        key=lambda s: s.score.total, reverse=True,
    )[:15]
    if growth:
        blocks = ["# 📈 성장 가속 후보 (Company Growth)", ""]
        blocks.append("> 스코어 궤적이 상승(ACCELERATING/GROWING)으로 전환된 글로벌 기업 후보입니다.")
        blocks.append("")
        for s in growth:
            url = s.entity.url or ""
            name = _md(s.entity.name)
            link = f"[{name}]({url})" if url else name
            blocks.append(f"- **{link}** (점수 {s.score.total}, {s.opportunity_type}) — "
                          f"궤적 {analyzers.traj_label(s.trajectory)} · "
                          f"생애주기 {analyzers.lifecycle_label(s.lifecycle)}")
        files["company-growth.md"] = "\n".join(blocks) + "\n"

    # Korea combined report.
    korea_items: list[tuple[str, list[ScoredEntity]]] = []
    for sec in sections:
        if any(k in (sec.get("title") or "") for k in KOREA_SECTION_KEYS) and sec["items"]:
            korea_items.append((sec.get("title", "🇰🇷 한국"), sec["items"]))
    if korea_items:
        blocks = ["# 🇰🇷 한국 기업 검토 (Korea Company)", ""]
        for title, items in korea_items:
            blocks.append(_render_section(title, items))
        files["korea-company.md"] = "\n".join(blocks)

    # DART events (only when DART-sourced Korea items exist).
    dart_items = [s for s in all_items if s.entity.is_korean
                  and any("dart" in (src or "").lower() for src in s.entity.signal_sources)]
    if dart_items:
        files["dart-events.md"] = _render_section("DART 공시 이벤트", dart_items)

    # Second-order.
    if second_order:
        blocks = ["# 🔗 2차 기회 (Second-Order)", ""]
        blocks.append("> 아래 항목은 관측된 신호에서 파생된 **가능성**입니다. "
                      "확인된 숫자가 아니며 추가 검증이 필요합니다.")
        blocks.append("")
        for so in second_order:
            trigger = _md(so.get("trigger", ""))
            url = so.get("url", "")
            target = f"[{trigger}]({url})" if url else trigger
            blocks.append(f"### {target} — {so.get('status', 'Derived')}")
            blocks.append("")
            for c in so.get("chain", []):
                blocks.append(f"- {_md(c)}")
            blocks.append("")
        files["second-order.md"] = "\n".join(blocks)

    # Market entry candidates: global (non-Korean) products with Korean
    # news coverage — evidence that the product is reaching Korean users.
    entry = [s for s in all_items if not s.entity.is_korean
             and any("korea_news" in (src or "").lower() for src in s.entity.signal_sources)]
    if entry:
        blocks = ["# 🚪 국내 진입 후보 (Market Entry)", ""]
        blocks.append("> 한국 뉴스에서 다뤄진 글로벌 제품/기업. 진입 시점 판단은 후보 수준입니다.")
        blocks.append("")
        for s in entry[:10]:
            blocks.append(f"- **{_md(s.entity.name)}** (점수 {s.score.total}, "
                          f"{s.opportunity_type}) — {_md(s.entity.description[:120])}")
        files["market-entry.md"] = "\n".join(blocks) + "\n"

    generated = set(files.keys())
    files = {"daily-summary.md": _summary_md(
        base, collection_window, sections, scored, macro_events, macro_signals,
        breakouts, source_status, second_order, watchlist, all_items, generated,
    )} | files
    return files


def report_links(date_iso: str, repo_url: str, branch: str = "main") -> dict[str, str]:
    """Absolute GitHub blob URLs for each report file (used by the email)."""
    return {
        name: f"{repo_url}/blob/{branch}/reports/{date_iso}/{name}"
        for name in REPORT_FILES.keys() | {"daily-summary.md", "opportunities.md",
                                           "korea-company.md", "dart-events.md",
                                           "second-order.md", "market-entry.md",
                                           "company-growth.md"}
    }