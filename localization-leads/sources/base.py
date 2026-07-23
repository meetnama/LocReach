"""
sources/base.py — Shared dataclasses and abstract base classes.

Every people source returns List[Person].
Every email source accepts a Person and returns Optional[EmailResult].
The pipeline orchestrates them without knowing the implementation details.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, List, Callable
from abc import ABC, abstractmethod


# ── Data models ───────────────────────────────────────────────────────────────

@dataclass
class Company:
    name:         str
    domain:       str
    url:          str
    linkedin_url: str = ""
    country:      str = ""


@dataclass
class Person:
    first:         str
    last:          str
    title:         str
    domain:        str
    company_name:  str
    linkedin_url:  str = ""
    people_source: str = ""   # which source found this person

    @property
    def full_name(self) -> str:
        return f"{self.first} {self.last}"


@dataclass
class EmailResult:
    email:    str
    label:    str    # e.g. "Hunter ✓", "Hunter ~", "Pattern ✓", "Site ✓"
    verified: bool = False   # True = already confirmed deliverable; skip MV re-check


@dataclass
class Lead:
    person:       Person
    email_result: EmailResult

    def to_dict(self) -> dict:
        """Flat dict for CSV / Excel export."""
        return {
            "Full Name":    self.person.full_name,
            "Email":        self.email_result.email,
            "Email Source": self.email_result.label,
            "Job Title":    self.person.title,
            "Company":      self.person.company_name,
            "Domain":       self.person.domain,
            "LinkedIn":     self.person.linkedin_url,
        }

    def to_db_dict(self) -> dict:
        """Dict matching the leads table schema."""
        return {
            "email":        self.email_result.email,
            "email_source": self.email_result.label,
            "full_name":    self.person.full_name,
            "first_name":   self.person.first,
            "last_name":    self.person.last,
            "title":        self.person.title,
            "company":      self.person.company_name,
            "domain":       self.person.domain,
            "country":      "",
            "linkedin_url": self.person.linkedin_url,
            "source_url":   "",
        }


# ── Log callback type ─────────────────────────────────────────────────────────

LogFn = Callable[[str, str], None]   # (tag, message) → None


# ── Abstract base classes ─────────────────────────────────────────────────────

class PeopleSource(ABC):
    """Finds employees/contacts at a given company.
    All people sources are tried for every company — results are merged
    and deduplicated by (first, last) before email enrichment begins.
    """
    name: str = "unknown"

    def __init__(self, log: LogFn = None):
        self._log: LogFn = log or (lambda tag, msg: print(f"[{tag:6}] {msg}"))

    def log(self, tag: str, msg: str) -> None:
        self._log(tag, msg)

    @abstractmethod
    def find_people(self, company: Company) -> List[Person]:
        ...


class EmailSource(ABC):
    """Finds/verifies an email address for a known person.
    Email sources are tried in priority order — first non-None result wins.
    """
    name: str = "unknown"

    def __init__(self, log: LogFn = None):
        self._log: LogFn = log or (lambda tag, msg: print(f"[{tag:6}] {msg}"))

    def log(self, tag: str, msg: str) -> None:
        self._log(tag, msg)

    @abstractmethod
    def find_email(self, person: Person) -> Optional[EmailResult]:
        ...
