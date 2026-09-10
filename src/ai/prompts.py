from __future__ import annotations

SYSTEM_PROMPT = """\
너는 기술 스타트업 투자자이자 사업 전략 분석가다.

주어진 데이터만을 기반으로 분석하라.
확인되지 않은 정보를 사실처럼 작성하지 마라.
정보가 부족하면 Unknown이라고 표시하라.
단순한 인기나 바이럴을 사업 기회로 착각하지 마라.
실제 사용자의 지불 의사와 지속 가능한 수익모델을 중요하게 평가하라.
대형 기업이 쉽게 복제할 수 있는 기능인지 판단하라.
현재 시점에서 왜 이 기회가 존재하는지 분석하라.
"""


def build_analysis_prompt(item: dict) -> str:
    name = item.get("name", "Unknown")
    url = item.get("url", "N/A")
    description = item.get("description", "N/A")
    category = item.get("category", "Unknown")
    source = item.get("source", "Unknown")
    metrics = item.get("metrics", {})
    business_info = item.get("business_info", {})

    metrics_str = "\n".join(
        f"  - {k}: {v}" for k, v in metrics.items() if v is not None
    ) or "  No metrics available"

    biz_str = "\n".join(
        f"  - {k}: {v}" for k, v in business_info.items() if v is not None
    ) or "  No business information available"

    return f"""\
아래 기회를 분석하고 평가하라.

== 기본 정보 ==
이름: {name}
URL: {url}
카테고리: {category}
출처: {source}
설명: {description}

== 수집된 메트릭 ==
{metrics_str}

== 사업 정보 ==
{biz_str}

== 분석 요청 ==
다음 관점에서 분석하라:

1. Market Size: 시장이 얼마나 큰가? (0~20점)
2. Growth: 최근 성장하고 있는가? (0~20점)
3. Traction: 실제 사용자가 존재하는가? (0~15점)
4. Monetization: 어떻게 돈을 벌 수 있는가? (0~15점)
5. Competition: 경쟁자가 얼마나 많은가? (0~10점)
6. Entry Barrier: 새로운 경쟁자가 들어가기 어려운가? (0~10점)
7. Timing: 지금 이 시점에 등장한 이유가 있는가? (0~5점)
8. Defensibility: 장기적인 경쟁우위를 만들 수 있는가? (0~5점)

== 평가 유형 ==
다음 중 하나 이상을 선택하라:
- INVEST: 투자 대상
- BUILD: 직접 사업화
- ACQUIRE: 인수 대상
- WATCH: 지속 관찰
- IGNORE: 무시

== 신뢰도 ==
High / Medium / Low 중 선택하라.
- 여러 출처에서 확인 가능하면 High
- 정보가 일부 부족하면 Medium
- 대부분 추정이면 Low

== 사실 vs 추론 ==
반드시 구분하라:
- FACT: 실제 출처에서 확인된 정보
- INFERENCE: 데이터를 바탕으로 한 추론

== 출력 형식 ==
반드시 아래 JSON 형식으로 출력하라. 다른 텍스트를 포함하지 마라.

```json
{{
  "market_size": "점수와 한줄 설명",
  "growth": "점수와 한줄 설명",
  "traction": "점수와 한줄 설명",
  "monetization": "점수와 한줄 설명",
  "competition": "점수와 한줄 설명",
  "entry_barrier": "점수와 한줄 설명",
  "timing": "점수와 한줄 설명",
  "defensibility": "점수와 한줄 설명",
  "business_potential": "한줄 요약",
  "investment_potential": "한줄 요약",
  "reasoning": "왜 이 점수를 부여했는지 3~5줄 설명",
  "types": ["BUILD"],
  "confidence": "Medium",
  "facts": ["FACT 1", "FACT 2"],
  "inferences": ["INFERENCE 1", "INFERENCE 2"]
}}
```"""


def build_batch_analysis_prompt(items: list[dict]) -> str:
    items_text = ""
    for i, item in enumerate(items, 1):
        metrics = item.get("metrics", {})
        metrics_str = ", ".join(
            f"{k}={v}" for k, v in metrics.items() if v is not None
        ) or "N/A"
        items_text += f"""
{i}. [{item.get('name', 'Unknown')}]({item.get('url', 'N/A')})
   Category: {item.get('category', 'Unknown')}
   Source: {item.get('source', 'Unknown')}
   Description: {item.get('description', 'N/A')[:200]}
   Metrics: {metrics_str}
"""

    return f"""\
아래 {len(items)}개의 기회를 분석하고 각각 평가하라.

{items_text}

각 기회에 대해 다음을 평가하라:
- Market Size (0~20), Growth (0~20), Traction (0~15), Monetization (0~15)
- Competition (0~10), Entry Barrier (0~10), Timing (0~5), Defensibility (0~5)

각 기회에 대해 INVEST / BUILD / ACQUIRE / WATCH / IGNORE 중 선택하라.
신뢰도(High/Medium/Low), 사실 vs 추론도 구분하라.

반드시 아래 JSON 배열 형식으로 출력하라:

```json
[
  {{
    "name": "프로젝트 이름",
    "scores": {{
      "market_size": 점수,
      "growth": 점수,
      "traction": 점수,
      "monetization": 점수,
      "competition": 점수,
      "entry_barrier": 점수,
      "timing": 점수,
      "defensibility": 점수
    }},
    "total_score": 총점,
    "types": ["BUILD"],
    "confidence": "Medium",
    "business_potential": "한줄 요약",
    "investment_potential": "한줄 요약",
    "reasoning": "3~5줄 설명",
    "facts": ["FACT 1"],
    "inferences": ["INFERENCE 1"]
  }}
]
```"""
