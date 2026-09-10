"""Korean narrative generation ('왜 주목?' / '투자 관점' / '주의할 점').

Template + data driven; never fabricates numbers that were not observed.
"""
from __future__ import annotations

from src.intelligence.funding import (
    PRE_SEED, SEED, SERIES_A, SERIES_B, SERIES_C, GROWTH, PUBLIC, UNKNOWN,
    format_amount_kr,
)
from src.intelligence import classification


def build_narrative(entity, breakdown, event_types, stage, judgement) -> dict:
    why = _why(entity, breakdown, event_types, stage)
    investment = _investment_view(entity, breakdown, event_types, stage)
    risk = _risk(entity, breakdown, event_types, stage)
    return {
        "why": why,
        "investment": investment,
        "risk": risk,
    }


def _has(events, etype) -> bool:
    return etype in set(events)


def _why(entity, breakdown, event_types, stage) -> str:
    parts = []
    latest = _latest_confirmed_round(entity)
    status = entity.funding_status

    if status == "withdrawn":
        planned = format_amount_kr(latest.get("amount_m"), latest.get("currency", "USD")) if latest and latest.get("amount_m") else "계획 규모"
        parts.append(
            f"이 기업은 투자 유치가 취소/무산된 이벤트가 확인됐습니다. "
            f"('{planned}' 규모의 계획이었으나 성사되지 않았습니다.)"
        )
    elif latest and latest.get("amount_m") is not None:
        amt = format_amount_kr(latest["amount_m"], latest.get("currency", "USD"))
        stage_label = _stage(stage)
        parts.append(f"{stage_label} 단계에서 {amt} 규모의 투자 유치가 확인됐습니다.")
    elif breakdown.funding > 0:
        parts.append("투자 유치 신호가 확인된 기업입니다.")

    if breakdown.smart_money > 0 and entity.investors:
        parts.append("주요 투자자가 참여했습니다.")
    if breakdown.accelerator > 0 and entity.accelerators:
        parts.append("유명 액셀러레이터 출신이라는 신호가 있습니다.")
    if breakdown.hiring > 0:
        parts.append("채용 활동이 늘고 있어 성장을 준비 중인 것으로 보입니다.")
    if breakdown.momentum > 0:
        parts.append("성장 모멘텀이 감지됐습니다.")
    if breakdown.customer > 0:
        parts.append("고객 확보/매출 신호가 확인됩니다.")

    if not parts:
        parts.append(
            "아직 공개된 투자·성장 데이터가 제한적입니다. "
            "이후 추가 신호가 확인될 때 재평가가 필요합니다."
        )
    return "\n".join(parts)


def _investment_view(entity, breakdown, event_types, stage) -> str:
    views = []
    if _has(event_types, classification.FUNDING) and breakdown.funding > 0:
        views.append(
            "투자 유치가 확인된 기업으로, 초기 단계라면 높은 성장 가능성이 있지만 "
            "실제 매출과 사업 지속 가능성은 추가 확인이 필요합니다."
        )
    elif _has(event_types, classification.PRODUCT_LAUNCH):
        views.append(
            "제품 출시가 확인됐습니다. 투자 관점에서는 이후 사용자 성장과 "
            "매출 전환 여부가 관건입니다."
        )
    elif breakdown.hiring > 0 or breakdown.customer > 0:
        views.append(
            "데이터가 많지 않지만 성장 신호가 하나 이상 확인됐습니다. "
            "투자 전 단계 후보로 관찰하기 적합합니다."
        )
    else:
        views.append(
            "현재 확인된 정보가 적어 투자 관점의 판단을 내리기 이릅니다. "
            "추가 신호를 모니터링하는 것이 바람직합니다."
        )

    if entity.entity_type == classification.PUBLIC_COMPANY:
        views.append("상장 기업이므로 공시·실적 데이터를 통해 검증이 가능합니다.")

    if _has(event_types, classification.ACQUISITION):
        views.append("인수합병 이벤트는 대상 기업 가치 재평가로 이어질 수 있습니다.")
    return "\n".join(views)


def _risk(entity, breakdown, event_types, stage) -> str:
    risks = []
    if entity.funding_status == "withdrawn":
        risks.append("투자 유치 무산/철회가 확인됐습니다 — 시장 신뢰도에 부정적일 수 있습니다.")
    elif stage == UNKNOWN and breakdown.funding > 0:
        risks.append("투자 단계가 명확하지 않아 규모의 해석에 주의가 필요합니다.")

    if not entity.investors and breakdown.funding > 0:
        risks.append("투자금 출처(주요 VC)가 확인되지 않았습니다.")

    if entity.entity_type in (classification.PRODUCT,):
        risks.append("단일 제품 중심이며, 기업 수준의 펀더멘털은 확인이 필요합니다.")

    if entity.total_funding_m is None and breakdown.funding > 0:
        risks.append("공개된 투자 규모 데이터가 제한적입니다.")

    if not risks:
        if breakdown.news > 0 and breakdown.total - breakdown.news < 20:
            risks.append("현재 확인된 정보가 단일 뉴스 보도 위주일 수 있습니다.")
        else:
            risks.append("현재 공개된 실적 정보가 제한적입니다. 추가 확인이 필요합니다.")
    return "\n".join(risks)


def _latest_confirmed_round(entity):
    confirmed = [r for r in entity.funding_history
                 if r.get("status", "confirmed") == "confirmed"]
    if not confirmed:
        return None
    return confirmed[-1]


def _stage(stage) -> str:
    return {
        PRE_SEED: "시드 전 단계",
        SEED: "시드",
        SERIES_A: "시리즈 A",
        SERIES_B: "시리즈 B",
        SERIES_C: "시리즈 C",
        GROWTH: "성장 후기",
        PUBLIC: "상장",
    }.get(stage, "")