"""Palladium Markdown reports.

Rule-based, markdown-only daily reports written under reports/<date>/.
Every domain report file is generated EVERY run; a domain without findings
contains an explicit empty-state note instead of fabricated items.
"""
from __future__ import annotations

from src.intelligence.scoring import ScoredEntity
from src.intelligence.classification import ENTITY_TYPE_LABELS, EVENT_TYPE_LABELS
from src.intelligence.funding import format_amount_kr, STAGE_LABELS_KO
from src.collectors.real_estate import format_amount_manwon
from src.report.formatter import format_reasons, format_score_change
from src.analyzers.trajectory import ACCELERATING, GROWING
from src import analyzers
from src import timeutil

# filename -> (section-title substrings that map to this domain,
#              display title, empty-state note)
REPORT_FILES: dict[str, tuple[list[str], str, str]] = {
    "startup-radar.md": (
        ["글로벌 스타트업"], "글로벌 스타트업 & 벤처",
        "이번 수집 주기에 감지된 Pre-Funding 성장 후보가 없습니다."),
    "market-anomaly.md": (
        ["글로벌 공개시장"], "글로벌 공개시장 이상 (Market Anomaly)",
        "감지된 공개시장 이상 징후(급등·급락·거래량/거래대금 급증)가 없습니다."),
    "product-opportunity.md": (
        ["글로벌 제품"], "제품 기회 (Product Opportunity)",
        "감지된 제품/수요 신호가 없습니다."),
    "deal-mna.md": (
        ["글로벌 M&A"], "딜 & M&A (Deal & M&A)",
        "이번 수집 주기에 감지된 M&A/딜 이벤트가 없습니다."),
}

KOREA_SECTION_KEYS = ["한국 투자", "한국 공개시장", "한국 기술"]

TECH_TREND_N = 12


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
             "dart-events.md", "company-growth.md", "second-order.md", "market-entry.md",
             "real-estate.md"]
    for name in order:
        label = name.replace("-", " ").replace(".md", "")
        out.append(f"[{label}]({name})")
    out.append("")
    return "\n".join(out) + "\n"


def _domain_file(filename: str, title: str, items: list[ScoredEntity],
                 empty_note: str) -> str:
    if not items:
        return f"# ⚡ {title}\n\n> {empty_note}\n"
    return f"# ⚡ {title}\n\n" + _render_section(title, items)


def _render_real_estate(scored: list[ScoredEntity],
                        source_status: dict) -> str:
    """Real-estate report: REAL reported trades from the 국토부 실거래 API.

    Only entities that received a real_estate collection THIS cycle are shown
    (last_seen == today). Trades within a region are sorted by price descending
    (top deals view). No synthetic numbers — every row is an actual deal.
    """
    today = timeutil.date_kst()
    regions: dict[str, dict] = {}
    for s in scored:
        re_dict = s.entity.real_estate or {}
        trades = re_dict.get("trades") or []
        if not trades or s.entity.last_seen != today:
            continue
        region = re_dict.get("region") or "기타"
        rows = []
        for t in sorted(trades, key=lambda t: t.get("amount_manwon", 0),
                        reverse=True)[:8]:
            apt = _md(t.get("apt", ""))
            parts = [p for p in (
                format_amount_manwon(t.get("amount_manwon", 0)),
                f"{t['area']:g}㎡" if t.get("area") else "",
                f"{t['floor']}층" if t.get("floor") else "",
                t.get("deal_date", ""),
            ) if p]
            rows.append(f"- **{apt}** — " + " · ".join(parts))
        if rows:
            bucket = regions.setdefault(region, {"rows": [], "max": 0})
            bucket["rows"].extend(rows)
            bucket["max"] = max(bucket["max"], max(t.get("amount_manwon", 0)
                                                   for t in trades))

    if not regions:
        skipped = source_status.get("real_estate", {}).get("status") == "SKIPPED"
        note = (
            "> 국토교통부 아파트매매 실거래 API 키(REAL_ESTATE_API_KEY)가 "
            "설정되지 않아 수집이 SKIPPED 처리되었습니다. data.go.kr에서 "
            "서비스키를 발급받아 등록하면 실거래가가 자동으로 채워집니다.\n"
            if skipped else
            "> 이번 수집 주기에 감지된 실거래 기록이 없습니다.\n")
        return f"# 🏠 부동산/경매 기회 (Real Estate)\n\n{note}"

    blocks = ["# 🏠 부동산/경매 기회 (Real Estate)", ""]
    blocks.append("> 한국 주요 지역 아파트 실거래가 — 실제 체결가 (국토교통부 "
                  "아파트매매 실거래 API 기준). AI 생성 수치 없음.")
    blocks.append("")
    for region, bucket in sorted(regions.items(),
                                 key=lambda kv: kv[1]["max"], reverse=True):
        blocks.append(f"## {region}")
        blocks.append("")
        blocks.extend(bucket["rows"])
        blocks.append("")
    return "\n".join(blocks).rstrip() + "\n"


def _tech_trend_candidates(scored: list[ScoredEntity]) -> list[ScoredEntity]:
    """Tech-trend candidates ranked by REAL observed GitHub metrics.

    Only entities signalled by the technology collector this cycle qualify;
    star/forks numbers are actual values, never fabricated or inferred.
    """
    candidates: list[ScoredEntity] = []
    for s in scored:
        e = s.entity
        if e.is_korean:
            continue
        if "github_trending" not in {x.lower() for x in e.signal_sources}:
            continue
        gm = e.github_metrics or {}
        if not (gm.get("stars_today") or gm.get("stars")):
            continue
        candidates.append(s)
    candidates.sort(
        key=lambda s: ((s.entity.github_metrics or {}).get("stars_today") or 0,
                       (s.entity.github_metrics or {}).get("stars") or 0),
        reverse=True,
    )
    return candidates[:TECH_TREND_N]


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
    if not all_items:
        opp.append("> 이번 수집 주기에 감지된 기회가 없습니다.")
    for sec in sections:
        opp.append(_render_section(sec.get("title", ""), sec["items"]))
    files["opportunities.md"] = "\n".join(opp)

    # Domain reports — one file per domain, always emitted. A domain without
    # findings keeps an explicit empty-state note (no fabricated content).
    for filename, (keys, title, empty_note) in REPORT_FILES.items():
        matched = [sec for sec in sections
                   if any(k in (sec.get("title") or "") for k in keys)]
        items = [s for sec in matched for s in sec["items"]]
        if items and matched:
            title = " / ".join(sec.get("title", "") for sec in matched)
        files[filename] = _domain_file(filename, title, items, empty_note)

    # Tech trend: dedicated rule from REAL GitHub metrics (stars today/total),
    # surfaced only from technology-collector signals in this cycle. Falls back
    # to the quality-gated tech section, then to an explicit empty state.
    tech = _tech_trend_candidates(scored)
    if tech:
        blocks = ["# ⚡ 기술 트렌드 (Tech Trend)", ""]
        blocks.append("> GitHub 트렌딩에서 실측된 인기 프로젝트. "
                      "수치는 실제 수집값이며 AI로 생성하지 않습니다.")
        blocks.append("")
        for i, s in enumerate(tech[:TECH_TREND_N], 1):
            e = s.entity
            gm = e.github_metrics or {}
            stars_t = gm.get("stars_today") or 0
            stars = gm.get("stars") or 0
            forks = gm.get("forks") or 0
            lang = _md(gm.get("language") or "")
            url = e.url or ""
            name = _md(e.name)
            link = f"[{name}]({url})" if url else name
            head = f"### {i}. {link} — 오늘 +{stars_t:,} stars · 총 {stars:,} stars"
            if forks:
                head += f" · {forks:,} forks"
            if lang:
                head += f" · {lang}"
            blocks.append(head)
            blocks.append("")
            if e.description:
                desc = " ".join(e.description.replace("\r", " ").split())[:180]
                blocks.append(f"> {desc}")
            if e.category and e.category.lower() != "other":
                blocks.append(f"- 분야: {_md(e.category)}")
            blocks.append("")
        files["tech-trend.md"] = "\n".join(blocks)
    else:
        tech_matched = [sec for sec in sections
                        if any(k in (sec.get("title") or "") for k in ("글로벌 기술",))]
        tech_items = [s for sec in tech_matched for s in sec["items"]]
        if tech_items:
            files["tech-trend.md"] = _domain_file(
                "tech-trend.md", "글로벌 기술", tech_items[:TECH_TREND_N],
                "이번 수집 주기에 감지된 기술 트렌드 신호가 없습니다.")
        else:
            files["tech-trend.md"] = _domain_file(
                "tech-trend.md", "기술 트렌드 (Tech Trend)", [],
                "이번 수집 주기에 감지된 기술 트렌드 신호가 없습니다.")

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
    else:
        files["company-growth.md"] = (
            "# 📈 성장 가속 후보 (Company Growth)\n\n"
            "> 스코어 이력이 3일 이상 누적되는 시점부터 성장 가속 "
            "(ACCELERATING/GROWING) 후보를 산출합니다. "
            "이번 주기에는 아직 후보가 없습니다.\n")

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
    else:
        files["korea-company.md"] = (
            "# 🇰🇷 한국 기업 검토 (Korea Company)\n\n"
            "> 이번 수집 주기에 한국 섹션 기준을 충족하는 기업 이벤트가 "
            "감지되지 않았습니다. (감지된 한국 항목이 있다면 공개 방법·임계값 "
            "재검토가 필요합니다)\n")

    # DART events — always emitted; empty state when DART produced nothing.
    dart_items = [s for s in all_items if s.entity.is_korean
                  and any("dart" in (src or "").lower() for src in s.entity.signal_sources)]
    if dart_items:
        files["dart-events.md"] = _render_section("DART 공시 이벤트", dart_items)
    else:
        files["dart-events.md"] = (
            "# 📄 DART 공시 이벤트 (DART Events)\n\n"
            "> 이번 수집 주기에 감지된 DART 공시 이벤트가 없습니다. "
            "(OpenDART 접근 제한 등으로 수집이 SKIPPED 처리될 수 있습니다)\n")

    # Second-order — always emitted.
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
    else:
        files["second-order.md"] = (
            "# 🔗 2차 기회 (Second-Order)\n\n"
            "> 이번 수집 주기의 관측 신호에서 파생된 2차 기회를 산출하지 못했습니다.\n")

    # Market entry candidates: global (non-Korean) products with Korean
    # news coverage — evidence that the product is reaching Korean users.
    # Scanned over the FULL scored list (coverage alone surfaces a candidate,
    # regardless of the quality-gated section threshold).
    entry = sorted(
        (s for s in scored
         if not s.entity.is_korean
         and any("korea_news" in (src or "").lower() for src in s.entity.signal_sources)),
        key=lambda s: s.score.total, reverse=True,
    )[:10]
    if entry:
        blocks = ["# 🚪 국내 진입 후보 (Market Entry)", ""]
        blocks.append("> 한국 뉴스에서 다뤄진 글로벌 제품/기업. 진입 시점 판단은 후보 수준입니다.")
        blocks.append("")
        for s in entry:
            url = s.entity.url or ""
            name = _md(s.entity.name)
            link = f"[{name}]({url})" if url else name
            blocks.append(f"- **{link}** (점수 {s.score.total}, 신뢰도 {s.confidence}%) "
                          f"— {_md(s.entity.description[:160])}")
        files["market-entry.md"] = "\n".join(blocks) + "\n"
    else:
        files["market-entry.md"] = (
            "# 🚪 국내 진입 후보 (Market Entry)\n\n"
            "> 이번 수집 주기에 한국 시장 진입 후보로 분류된 글로벌 "
            "제품/기업이 없습니다.\n")

    # Real estate — REAL reported apartment deals from the 국토부 실거래 API.
    # Scanned over the FULL scored list (like market-entry): a real trade
    # surfaces regardless of the quality-gated section threshold.
    files["real-estate.md"] = _render_real_estate(scored, source_status)

    generated = set(files.keys())
    files = {"daily-summary.md": _summary_md(
        base, collection_window, sections, scored, macro_events, macro_signals,
        breakouts, source_status, second_order, watchlist, all_items,
    )} | files
    return files


def report_links(date_iso: str, repo_url: str, branch: str = "main") -> dict[str, str]:
    """Absolute GitHub blob URLs for each report file (used by the email)."""
    return {
        name: f"{repo_url}/blob/{branch}/reports/{date_iso}/{name}"
        for name in REPORT_FILES.keys() | {"daily-summary.md", "opportunities.md",
                                           "korea-company.md", "dart-events.md",
                                           "second-order.md", "market-entry.md",
                                           "company-growth.md", "real-estate.md",
                                           "tech-trend.md"}
    }