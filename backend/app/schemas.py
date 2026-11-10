"""Data models shared by the API and the analysis engine."""

from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field

Status = Literal["PASS", "WARNING", "FAIL"]
Category = Literal["structure", "limits", "formatting", "headings", "citations"]
# "deterministic": measured directly from the file. "heuristic": pattern-based
# guess that needs a human to confirm. Nothing in the MVP is AI-generated.
Basis = Literal["deterministic", "heuristic"]


class SectionRule(BaseModel):
    name: str
    aliases: list[str] = Field(default_factory=list)
    required: bool = True
    max_words: Optional[int] = Field(default=None, ge=1)
    exclude_from_word_count: bool = False
    source: str = ""


class WordLimitRule(BaseModel):
    total_max: Optional[int] = Field(default=None, ge=1)
    count_footnotes: bool = False
    source: str = ""


class PageLimitRule(BaseModel):
    max_pages: Optional[int] = Field(default=None, ge=1)
    source: str = ""


class FormattingRules(BaseModel):
    font_family: Optional[str] = None
    font_size_pt: Optional[float] = Field(default=None, gt=0)
    footnote_font_size_pt: Optional[float] = Field(default=None, gt=0)
    line_spacing: Optional[float] = Field(default=None, gt=0)
    margin_top_cm: Optional[float] = Field(default=None, ge=0)
    margin_bottom_cm: Optional[float] = Field(default=None, ge=0)
    margin_left_cm: Optional[float] = Field(default=None, ge=0)
    margin_right_cm: Optional[float] = Field(default=None, ge=0)
    margin_mode: Literal["minimum", "exact"] = "minimum"
    page_numbers_required: bool = False
    source: str = ""


class CitationRules(BaseModel):
    style: Literal["none", "oscola", "bluebook", "other"] = "none"
    require_pinpoints: bool = False
    source: str = ""


class RuleSet(BaseModel):
    """A competition profile. Every value is entered by the user; the app
    ships no competition rules of its own."""

    sections: list[SectionRule] = Field(default_factory=list)
    enforce_section_order: bool = True
    word_limit: WordLimitRule = Field(default_factory=WordLimitRule)
    page_limit: PageLimitRule = Field(default_factory=PageLimitRule)
    formatting: FormattingRules = Field(default_factory=FormattingRules)
    citations: CitationRules = Field(default_factory=CitationRules)
    special_instructions: str = ""


class ProjectCreate(BaseModel):
    competition_name: str = Field(min_length=1, max_length=200)
    edition: str = Field(default="", max_length=100)
    team_name: str = Field(default="", max_length=200)
    party: Literal["Applicant", "Respondent"]


class Location(BaseModel):
    section: Optional[str] = None
    paragraph: Optional[int] = None  # index into document.paragraphs
    footnote: Optional[int] = None  # footnote number as displayed
    excerpt: Optional[str] = None


class Finding(BaseModel):
    category: Category
    check: str
    status: Status
    title: str
    detail: str = ""
    basis: Basis = "deterministic"
    manual_check: bool = False
    rule_source: str = ""
    locations: list[Location] = Field(default_factory=list)
