from __future__ import annotations

import json
import logging
import os
import re
from typing import Optional

from openai import OpenAI

from src.ai.prompts import SYSTEM_PROMPT, build_batch_analysis_prompt, build_analysis_prompt
from src.models import Opportunity, Analysis, ScoreBreakdown


logger = logging.getLogger(__name__)


class AIAnalyzer:
    def __init__(self):
        api_key = os.environ.get("AI_API_KEY", "")
        model = os.environ.get("AI_MODEL", "gpt-4o-mini")
        base_url = os.environ.get("AI_BASE_URL", None)

        if not api_key:
            logger.warning("AI_API_KEY not set. Analysis will use defaults.")
            self.client = None
            self.model = model
            return

        kwargs = {"api_key": api_key}
        if base_url:
            kwargs["base_url"] = base_url
        self.client = OpenAI(**kwargs)
        self.model = model

    def analyze_batch(self, items: list[Opportunity], batch_size: int = 10) -> list[Opportunity]:
        if not self.client:
            logger.warning("No AI client. Assigning default scores.")
            return self._assign_defaults(items)

        analyzed: list[Opportunity] = []
        for i in range(0, len(items), batch_size):
            batch = items[i : i + batch_size]
            results = self._call_batch(batch)
            analyzed.extend(results)

        analyzed.sort(key=lambda o: o.total_score, reverse=True)
        return analyzed

    def _call_batch(self, batch: list[Opportunity]) -> list[Opportunity]:
        items_data = [opp.to_dict() for opp in batch]
        prompt = build_batch_analysis_prompt(items_data)

        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": prompt},
                ],
                temperature=0.3,
                max_tokens=8000,
            )
            content = response.choices[0].message.content or ""
            return self._parse_batch_response(batch, content)
        except Exception as e:
            logger.error(f"AI batch analysis failed: {e}")
            return self._assign_defaults(batch)

    def analyze_single(self, opp: Opportunity) -> Opportunity:
        if not self.client:
            return opp

        prompt = build_analysis_prompt(opp.to_dict())
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": prompt},
                ],
                temperature=0.3,
                max_tokens=4000,
            )
            content = response.choices[0].message.content or ""
            return self._parse_single_response(opp, content)
        except Exception as e:
            logger.error(f"AI single analysis failed for {opp.name}: {e}")
            return opp

    def _parse_batch_response(self, batch: list[Opportunity], content: str) -> list[Opportunity]:
        json_str = self._extract_json(content)
        if not json_str:
            logger.warning("Failed to extract JSON from batch response")
            return self._assign_defaults(batch)

        try:
            results = json.loads(json_str)
        except json.JSONDecodeError as e:
            logger.warning(f"Failed to parse JSON: {e}")
            return self._assign_defaults(batch)

        if not isinstance(results, list):
            return self._assign_defaults(batch)

        for i, opp in enumerate(batch):
            if i < len(results):
                self._apply_result(opp, results[i])
            else:
                self._set_default_score(opp)

        return batch

    def _parse_single_response(self, opp: Opportunity, content: str) -> Opportunity:
        json_str = self._extract_json(content)
        if not json_str:
            return opp

        try:
            result = json.loads(json_str)
        except json.JSONDecodeError:
            return opp

        self._apply_result(opp, result)
        return opp

    def _apply_result(self, opp: Opportunity, result: dict):
        scores = result.get("scores", {})
        opp.score = ScoreBreakdown(
            market_size=scores.get("market_size", 0),
            growth=scores.get("growth", 0),
            traction=scores.get("traction", 0),
            monetization=scores.get("monetization", 0),
            competition=scores.get("competition", 0),
            entry_barrier=scores.get("entry_barrier", 0),
            timing=scores.get("timing", 0),
            defensibility=scores.get("defensibility", 0),
        )
        opp.total_score = result.get("total_score", opp.score.total)
        opp.types = result.get("types", ["WATCH"])
        opp.confidence = result.get("confidence", "Low")

        opp.analysis = Analysis(
            market_size=str(scores.get("market_size", 0)),
            growth=str(scores.get("growth", 0)),
            traction=str(scores.get("traction", 0)),
            monetization=str(scores.get("monetization", 0)),
            competition=str(scores.get("competition", 0)),
            entry_barrier=str(scores.get("entry_barrier", 0)),
            timing=str(scores.get("timing", 0)),
            defensibility=str(scores.get("defensibility", 0)),
            business_potential=result.get("business_potential", "Unknown"),
            investment_potential=result.get("investment_potential", "Unknown"),
            reasoning=result.get("reasoning", "No reasoning provided"),
            facts=result.get("facts", []),
            inferences=result.get("inferences", []),
        )

    def _extract_json(self, text: str) -> str | None:
        m = re.search(r"```json\s*\n?(.*?)\n?```", text, re.DOTALL)
        if m:
            return m.group(1).strip()

        m = re.search(r"\[\s*\{.*?\}\s*\]", text, re.DOTALL)
        if m:
            return m.group(0)

        m = re.search(r"\{\s*\"scores\".*?\}", text, re.DOTALL)
        if m:
            return m.group(0)

        return None

    def _assign_defaults(self, items: list[Opportunity]) -> list[Opportunity]:
        for opp in items:
            self._set_default_score(opp)
        return items

    def _set_default_score(self, opp: Opportunity):
        if opp.score is None:
            opp.score = ScoreBreakdown()
        if opp.total_score == 0:
            opp.total_score = opp.score.total
        if not opp.types:
            opp.types = ["WATCH"]
        if opp.confidence == "Low":
            opp.confidence = "Low"
        if opp.analysis is None:
            opp.analysis = Analysis(reasoning="AI analysis not available")
