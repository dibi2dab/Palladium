from __future__ import annotations

import hashlib
import logging
import re
from datetime import date
from urllib.parse import urlparse

from src.intelligence.funding import UNKNOWN
from src.intelligence import classification

logger = logging.getLogger(__name__)


def normalize_name(name: str) -> str:
    name = name.strip().lower()
    # keep hangul (가-힣) so Korean company names survive normalization/dedup
    name = re.sub(r"[^a-z0-9가-힣\s\-.]", "", name)
    name = re.sub(r"\s+", " ", name)
    return name.strip()


def extract_domain(url: str) -> str:
    try:
        parsed = urlparse(url)
        return parsed.netloc.lower().replace("www.", "")
    except Exception:
        return ""


def extract_github(url: str) -> str | None:
    m = re.search(r"github\.com/([^/]+)/([^/]+)", url)
    if m:
        return f"{m.group(1).lower()}/{m.group(2).lower().removesuffix('.git')}"
    return None


def extract_ticker(text: str) -> str | None:
    m = re.search(r"\b([A-Z]{1,5})\b", text)
    if m:
        return m.group(1)
    return None


def compute_entity_id(name: str, url: str = "", domain: str = "", github: str = "") -> str:
    parts = []
    if github:
        parts.append(f"gh:{github}")
    if domain:
        parts.append(f"dom:{domain}")
    parts.append(f"nm:{normalize_name(name)}")
    key = "|".join(parts)
    return hashlib.md5(key.encode()).hexdigest()[:12]


class Entity:
    def __init__(self, entity_id: str, name: str, url: str = "",
                 category: str = "Other", description: str = ""):
        self.id = entity_id
        self.name = name
        self.url = url
        self.category = category
        self.description = description
        self.domain = extract_domain(url) if url else ""
        self.github = extract_github(url) if url else ""
        self.ticker: str | None = None
        self.first_seen = date.today().isoformat()
        self.last_seen = date.today().isoformat()
        self.signal_counts: dict[str, int] = {}
        self.signal_sources: list[str] = []
        self.tags: list[str] = []
        self.startup_stage: str = UNKNOWN
        self.entity_type: str = classification.OTHER
        self.parent_company: str | None = None
        self.event_types: list[str] = []
        self.investors: list[str] = []
        self.accelerators: list[str] = []
        self.funding_history: list[dict] = []
        self.total_funding_m: float | None = None
        self.funding_status: str = ""  # confirmed / planned / withdrawn
        self.events: list[dict] = []
        self.search_interest: dict | None = None
        self.news_momentum: dict | None = None
        self.community_momentum: dict | None = None
        self.hiring_growth: dict | None = None
        self.is_korean: bool = False

    @property
    def signal_diversity(self) -> int:
        return len([k for k, v in self.signal_counts.items() if v > 0])

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "url": self.url,
            "category": self.category,
            "description": self.description,
            "domain": self.domain,
            "github": self.github,
            "ticker": self.ticker,
            "first_seen": self.first_seen,
            "last_seen": self.last_seen,
            "signal_counts": self.signal_counts,
            "signal_sources": self.signal_sources,
            "tags": self.tags,
            "startup_stage": self.startup_stage,
            "entity_type": self.entity_type,
            "parent_company": self.parent_company,
            "event_types": self.event_types,
            "investors": self.investors,
            "accelerators": self.accelerators,
            "funding_history": self.funding_history,
            "total_funding_m": self.total_funding_m,
            "funding_status": self.funding_status,
            "events": self.events,
            "search_interest": self.search_interest,
            "news_momentum": self.news_momentum,
            "community_momentum": self.community_momentum,
            "hiring_growth": self.hiring_growth,
            "is_korean": self.is_korean,
        }

    @classmethod
    def from_dict(cls, d: dict) -> Entity:
        e = cls(
            entity_id=d["id"],
            name=d["name"],
            url=d.get("url", ""),
            category=d.get("category", "Other"),
            description=d.get("description", ""),
        )
        e.domain = d.get("domain", "")
        e.github = d.get("github", "")
        e.ticker = d.get("ticker")
        e.first_seen = d.get("first_seen", e.first_seen)
        e.last_seen = d.get("last_seen", e.last_seen)
        e.signal_counts = d.get("signal_counts", {})
        e.signal_sources = d.get("signal_sources", [])
        e.tags = d.get("tags", [])
        e.startup_stage = d.get("startup_stage", UNKNOWN)
        e.entity_type = d.get("entity_type", classification.OTHER)
        e.parent_company = d.get("parent_company")
        e.event_types = d.get("event_types", [])
        e.investors = d.get("investors", [])
        e.accelerators = d.get("accelerators", [])
        e.funding_history = d.get("funding_history", [])
        e.total_funding_m = d.get("total_funding_m")
        e.funding_status = d.get("funding_status", "")
        e.events = d.get("events", [])
        e.search_interest = d.get("search_interest")
        e.news_momentum = d.get("news_momentum")
        e.community_momentum = d.get("community_momentum")
        e.hiring_growth = d.get("hiring_growth")
        e.is_korean = bool(d.get("is_korean", False))

        # Migration: upgrade old success-only funding_history entries.
        for r in e.funding_history:
            r.setdefault("currency", r.get("currency", "USD"))
            r.setdefault("status", r.get("status", "confirmed"))
        return e

    def add_event(self, event_type: str, description: str = "",
                  url: str = "", date_str: str | None = None) -> bool:
        """Record an event, deduped across sources for (type, date).

        Returns True when a NEW event was recorded, False when it was an
        already-seen event on the same day (so callers can merge sources).
        """
        date_str = date_str or date.today().isoformat()
        for ev in self.events:
            if ev.get("type") == event_type and ev.get("date") == date_str:
                if url and url not in ev.get("sources", []):
                    ev.setdefault("sources", []).append(url)
                return False
        self.events.append({
            "type": event_type,
            "date": date_str,
            "description": description[:300],
            "url": url,
            "sources": [url] if url else [],
        })
        if event_type not in self.event_types:
            self.event_types.append(event_type)
        return True


class EntityManager:
    def __init__(self, store):
        self.store = store
        self.entities: dict[str, Entity] = {}
        self._load()

    def _load(self):
        raw = self.store.load_entities()
        for eid, edata in raw.items():
            try:
                self.entities[eid] = Entity.from_dict(edata)
            except Exception as e:
                logger.warning(f"Skipping malformed entity {eid}: {e}")

    def find_or_create(self, name: str, url: str = "",
                       category: str = "Other", description: str = "") -> Entity:
        domain = extract_domain(url) if url else ""
        github = extract_github(url) if url else ""
        eid = compute_entity_id(name, url, domain, github)

        if eid in self.entities:
            entity = self.entities[eid]
            entity.last_seen = date.today().isoformat()
            if description and len(description) > len(entity.description):
                entity.description = description
            if url and not entity.url:
                entity.url = url
                entity.domain = domain
                entity.github = github
            return entity

        entity = Entity(eid, name, url, category, description)
        entity.domain = domain
        entity.github = github
        self.entities[eid] = entity
        return entity

    def get(self, entity_id: str) -> Entity | None:
        return self.entities.get(entity_id)

    def get_all(self) -> list[Entity]:
        return list(self.entities.values())

    def save(self):
        data = {eid: e.to_dict() for eid, e in self.entities.items()}
        self.store.save_entities(data)

    def find_similar(self, name: str, url: str = "") -> Entity | None:
        norm = normalize_name(name)
        for e in self.entities.values():
            if normalize_name(e.name) == norm:
                return e
        # GitHub owner/repo is a unique subject identifier: two entries
        # pointing at the same repository are the same project.
        github = extract_github(url)
        if github:
            for e in self.entities.values():
                if e.github == github:
                    return e
        return None