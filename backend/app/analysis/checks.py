"""Deterministic compliance checks. No AI is involved anywhere in this module.

Every finding is either measured from the file ("deterministic") or a
pattern-based flag that a person must confirm ("heuristic").
"""

from __future__ import annotations

import re
from collections import Counter, defaultdict
from dataclasses import dataclass
from typing import Optional

from ..schemas import Finding, Location, RuleSet, SectionRule
from .docx_parser import Note, Para, ParsedDocument, count_words

FRONT_MATTER = "(Front matter)"
_COVER_NAMES = {"cover page", "title page", "cover", "cover sheet"}
_TOC_NAMES = {"table of contents", "contents"}
MAX_LOCATIONS = 12

_PREFIX = re.compile(
    r"^\s*(?:\(?(?:[IVXLCDM]+|[ivxlcdm]+|[A-Za-z]|\d+(?:\.\d+)*)[.)]|\d+(?:\.\d+)+|\d+(?=\s))\s*"
)


def normalize(text: str) -> str:
    text = _PREFIX.sub("", text.strip(), count=1)
    return re.sub(r"[^a-z0-9]+", " ", text.lower()).strip()


def excerpt(text: str, n: int = 110) -> str:
    text = " ".join(text.split())
    return text if len(text) <= n else text[: n - 1] + "…"


@dataclass
class Section:
    name: str
    rule: Optional[SectionRule]
    start: int  # first paragraph index
    end: int  # one past the last paragraph index
    words: int = 0
    note_words: int = 0


def _rule_names(rule: SectionRule) -> set[str]:
    return {normalize(n) for n in [rule.name, *rule.aliases] if normalize(n)}


def split_sections(doc: ParsedDocument, rules: RuleSet) -> list[Section]:
    lookup: dict[str, SectionRule] = {}
    for rule in rules.sections:
        for n in _rule_names(rule):
            lookup.setdefault(n, rule)

    matched = {
        p.index: lookup[normalize(p.text)]
        for p in doc.paragraphs
        if p.heading_level and normalize(p.text) in lookup
    }
    top = min((doc.paragraphs[i].heading_level for i in matched), default=1)
    # Capitalised or bold lines before the first recognised section are cover-page
    # text, not headings, unless the author gave them a real heading style.
    for p in doc.paragraphs[: min(matched, default=0)]:
        if p.heading_basis == "heuristic":
            p.heading_level = p.heading_basis = None

    sections = [Section(FRONT_MATTER, None, 0, 0)]
    for p in doc.paragraphs:
        if p.index in matched:
            sections.append(Section(matched[p.index].name, matched[p.index], p.index, p.index))
        elif p.heading_level and p.heading_level <= top:
            sections.append(Section(excerpt(p.text, 80), None, p.index, p.index))
        cur = sections[-1]
        cur.end = p.index + 1
        cur.words += count_words(p.text)
        cur.note_words += sum(count_words(doc.notes[i].text) for i in p.footnote_ids)
    return sections


class Analysis:
    def __init__(self, doc: ParsedDocument, rules: RuleSet):
        self.doc = doc
        self.rules = rules
        self.sections = split_sections(doc, rules)
        self.section_of: list[str] = [""] * len(doc.paragraphs)
        for s in self.sections:
            for i in range(s.start, s.end):
                self.section_of[i] = s.name
        self.findings: list[Finding] = []

    # ---- helpers

    def loc(self, p: Para) -> Location:
        return Location(section=self.section_of[p.index], paragraph=p.index, excerpt=excerpt(p.text))

    def note_loc(self, n: Note) -> Location:
        return Location(
            section=self.section_of[n.paragraph] if n.paragraph is not None else None,
            paragraph=n.paragraph,
            footnote=n.number if n.kind == "footnote" else None,
            excerpt=("Endnote %d: " % n.number if n.kind == "endnote" else "") + excerpt(n.text),
        )

    def add(self, category, check, status, title, detail="", **kw):
        locations = kw.pop("locations", [])
        extra = len(locations) - MAX_LOCATIONS
        if extra > 0:
            detail = (detail + f" Showing the first {MAX_LOCATIONS} of {len(locations)} locations.").strip()
        self.findings.append(
            Finding(category=category, check=check, status=status, title=title, detail=detail,
                    locations=locations[:MAX_LOCATIONS], **kw)
        )

    def body_paragraphs(self) -> list[Para]:
        """Running text: not headings, not contents entries, not the front matter."""
        front_end = self.sections[0].end if len(self.sections) > 1 else 0
        return [
            p for p in self.doc.paragraphs
            if p.text.strip() and not p.heading_level and not p.in_toc_field and p.index >= front_end
        ]

    # ---- structure

    def check_structure(self):
        found = defaultdict(list)
        for s in self.sections:
            if s.rule is not None:
                found[s.rule.name].append(s)
        front = self.sections[0]
        for rule in self.rules.sections:
            names = _rule_names(rule)
            hits = found.get(rule.name, [])
            if hits:
                self.add("structure", "section_present", "PASS", f"{rule.name} found",
                         rule_source=rule.source, locations=[self.loc(self.doc.paragraphs[hits[0].start])])
                if len(hits) > 1:
                    self.add("structure", "section_duplicate", "WARNING",
                             f"{rule.name} appears {len(hits)} times",
                             "More than one heading matches this section.", rule_source=rule.source,
                             locations=[self.loc(self.doc.paragraphs[h.start]) for h in hits])
                continue
            if names & _COVER_NAMES:
                if front.words and len(self.sections) > 1:
                    self.add("structure", "section_present", "PASS", f"{rule.name} found",
                             "Text appears before the first section heading and is treated as the cover page. "
                             "Its contents are not checked.", manual_check=True, rule_source=rule.source,
                             locations=[Location(section=FRONT_MATTER, paragraph=0)])
                    continue
            if names & _TOC_NAMES and self.doc.has_toc_field:
                self.add("structure", "section_present", "PASS", f"{rule.name} found",
                         "An automatic table of contents is present.", rule_source=rule.source)
                continue
            if rule.required:
                self.add("structure", "section_present", "FAIL", f"{rule.name} not found",
                         "No heading matches this section name or its aliases. If the section exists under "
                         "a different heading, add that heading as an alias in the competition rules.",
                         rule_source=rule.source)

        if self.rules.enforce_section_order and self.rules.sections:
            order = {r.name: i for i, r in enumerate(self.rules.sections)}
            seen, sequence = set(), []
            for s in self.sections:
                if s.rule is not None and s.rule.name not in seen:
                    seen.add(s.rule.name)
                    sequence.append(s)
            bad = [
                (a, b) for a, b in zip(sequence, sequence[1:]) if order[a.rule.name] > order[b.rule.name]
            ]
            if bad:
                self.add("structure", "section_order", "WARNING", "Sections are not in the configured order",
                         "; ".join(f"“{b.name}” comes after “{a.name}”" for a, b in bad) + ".",
                         locations=[self.loc(self.doc.paragraphs[b.start]) for _, b in bad])
            elif len(sequence) > 1:
                self.add("structure", "section_order", "PASS", "Sections follow the configured order")

    # ---- limits

    def word_totals(self) -> dict:
        wl = self.rules.word_limit
        body = sum(s.words for s in self.sections)
        notes = sum(count_words(n.text) for n in self.doc.notes)
        counted = 0
        for s in self.sections:
            if s.rule is not None and s.rule.exclude_from_word_count:
                continue
            counted += s.words + (s.note_words if wl.count_footnotes else 0)
        return {"body": body, "notes": notes, "counted": counted, "limit": wl.total_max}

    def check_limits(self):
        wl = self.rules.word_limit
        totals = self.word_totals()
        excluded = [r.name for r in self.rules.sections if r.exclude_from_word_count]
        basis = (
            f"Counted {totals['counted']:,} words "
            f"({'including' if wl.count_footnotes else 'excluding'} footnotes"
            + (f"; excluding sections: {', '.join(excluded)}" if excluded else "")
            + "). Words are whitespace-separated, as in Microsoft Word."
        )
        if wl.total_max is not None:
            over = totals["counted"] - wl.total_max
            if over > 0:
                self.add("limits", "total_words", "FAIL",
                         f"Word limit exceeded by {over:,} words", f"Limit {wl.total_max:,}. {basis}",
                         rule_source=wl.source)
            else:
                self.add("limits", "total_words", "PASS",
                         f"Within the word limit ({totals['counted']:,} of {wl.total_max:,})", basis,
                         rule_source=wl.source)
            unmatched_excluded = [
                r.name for r in self.rules.sections
                if r.exclude_from_word_count and not any(s.rule is r for s in self.sections)
            ]
            if unmatched_excluded:
                self.add("limits", "excluded_sections", "WARNING",
                         "Some excluded sections were not located",
                         "These sections are excluded from the word count but no matching heading was found, "
                         "so their words may have been counted: " + ", ".join(unmatched_excluded) + ".",
                         manual_check=True, rule_source=wl.source)

        by_rule = defaultdict(lambda: [0, None])
        for s in self.sections:
            if s.rule is not None and s.rule.max_words:
                by_rule[s.rule.name][0] += s.words + (s.note_words if wl.count_footnotes else 0)
                by_rule[s.rule.name][1] = by_rule[s.rule.name][1] or s
        for rule in self.rules.sections:
            if rule.name not in by_rule:
                continue
            words, sec = by_rule[rule.name]
            where = [self.loc(self.doc.paragraphs[sec.start])]
            if words > rule.max_words:
                self.add("limits", "section_words", "FAIL",
                         f"{rule.name} exceeds its limit by {words - rule.max_words:,} words",
                         f"{words:,} words; limit {rule.max_words:,}.", rule_source=rule.source, locations=where)
            else:
                self.add("limits", "section_words", "PASS",
                         f"{rule.name} within its limit ({words:,} of {rule.max_words:,})",
                         rule_source=rule.source, locations=where)

        pl = self.rules.page_limit
        if pl.max_pages is not None:
            pages = self.doc.stored_page_count
            note = ("A DOCX file has no fixed pages. This is the page count Word stored when the file was last "
                    "saved, and it may be out of date. Confirm against the final PDF.")
            if pages is None:
                self.add("limits", "pages", "WARNING", "Page count could not be determined",
                         f"The file does not record a page count. Check the {pl.max_pages}-page limit manually.",
                         manual_check=True, rule_source=pl.source)
            elif pages > pl.max_pages:
                self.add("limits", "pages", "FAIL", f"Page limit exceeded ({pages} of {pl.max_pages} pages)",
                         note, manual_check=True, rule_source=pl.source)
            else:
                self.add("limits", "pages", "PASS", f"Within the page limit ({pages} of {pl.max_pages} pages)",
                         note, manual_check=True, rule_source=pl.source)

    # ---- formatting

    def check_formatting(self):
        f = self.rules.formatting
        src = f.source
        body = self.body_paragraphs()

        if f.font_family:
            want = f.font_family.strip().casefold()
            chars, bad, unknown = Counter(), [], []
            for p in self.doc.paragraphs:
                fonts = {r.font for r in p.runs if r.text.strip()}
                for r in p.runs:
                    if r.text.strip():
                        chars[r.font or "unspecified"] += len(r.text)
                if any(x and x.casefold() != want for x in fonts):
                    bad.append(p)
                elif None in fonts:
                    unknown.append(p)
            for n in self.doc.notes:
                for r in n.runs:
                    if r.text.strip():
                        chars[r.font or "unspecified"] += len(r.text)
            bad_notes = [n for n in self.doc.notes
                         if any(r.text.strip() and r.font and r.font.casefold() != want for r in n.runs)]
            usage = ", ".join(f"{k} ({v:,} chars)" for k, v in chars.most_common(5))
            if bad or bad_notes:
                self.add("formatting", "font_family", "FAIL", f"Text found in a font other than {f.font_family}",
                         f"Fonts in use: {usage}.", rule_source=src,
                         locations=[self.loc(p) for p in bad] + [self.note_loc(n) for n in bad_notes])
            elif unknown:
                self.add("formatting", "font_family", "WARNING", "Font could not be determined for some text",
                         "The file does not name a font for these paragraphs, so Word falls back to a default.",
                         manual_check=True, rule_source=src, locations=[self.loc(p) for p in unknown])
            else:
                self.add("formatting", "font_family", "PASS", f"All text is in {f.font_family}", rule_source=src)

        if f.font_size_pt:
            bad = [p for p in body if any(r.text.strip() and abs(r.size_pt - f.font_size_pt) > 0.01 for r in p.runs)]
            scope = "Headings, the cover page and contents entries are not included in this check."
            if bad:
                sizes = Counter(r.size_pt for p in bad for r in p.runs
                                if r.text.strip() and abs(r.size_pt - f.font_size_pt) > 0.01)
                self.add("formatting", "font_size", "FAIL", f"Body text not in {f.font_size_pt:g} pt",
                         "Other sizes found: " + ", ".join(f"{s:g} pt" for s in sorted(sizes)) + ". " + scope,
                         rule_source=src, locations=[self.loc(p) for p in bad])
            else:
                self.add("formatting", "font_size", "PASS", f"Body text is {f.font_size_pt:g} pt", scope,
                         rule_source=src)

        if f.footnote_font_size_pt and self.doc.notes:
            want = f.footnote_font_size_pt
            bad = [n for n in self.doc.notes if any(r.text.strip() and abs(r.size_pt - want) > 0.01 for r in n.runs)]
            if bad:
                self.add("formatting", "footnote_font_size", "FAIL", f"Footnote text not in {want:g} pt",
                         rule_source=src, locations=[self.note_loc(n) for n in bad])
            else:
                self.add("formatting", "footnote_font_size", "PASS", f"Footnote text is {want:g} pt",
                         rule_source=src)

        if f.line_spacing:
            bad = [p for p in body if p.line_spacing is not None and abs(p.line_spacing - f.line_spacing) > 0.011]
            fixed = [p for p in body if p.line_spacing is None]
            if bad:
                found = sorted({round(p.line_spacing, 2) for p in bad})
                self.add("formatting", "line_spacing", "FAIL", f"Line spacing is not {f.line_spacing:g} throughout",
                         "Other spacing found: " + ", ".join(f"{x:g}" for x in found)
                         + ". Headings, the cover page and contents entries are not included.",
                         rule_source=src, locations=[self.loc(p) for p in bad])
            elif fixed:
                self.add("formatting", "line_spacing", "WARNING", "Some paragraphs use fixed line spacing",
                         "These paragraphs use an exact or minimum spacing in points, which cannot be compared "
                         f"directly with a spacing of {f.line_spacing:g} lines.", manual_check=True,
                         rule_source=src, locations=[self.loc(p) for p in fixed])
            else:
                self.add("formatting", "line_spacing", "PASS", f"Body text uses {f.line_spacing:g} line spacing",
                         rule_source=src)

        wanted = {"top": f.margin_top_cm, "bottom": f.margin_bottom_cm,
                  "left": f.margin_left_cm, "right": f.margin_right_cm}
        if any(v is not None for v in wanted.values()) and self.doc.margins:
            problems = []
            for i, m in enumerate(self.doc.margins, 1):
                for side, want in wanted.items():
                    if want is None:
                        continue
                    got = getattr(m, f"{side}_cm")
                    wrong = got < want - 0.02 if f.margin_mode == "minimum" else abs(got - want) > 0.02
                    if wrong:
                        problems.append(f"layout section {i}: {side} margin {got:g} cm "
                                        f"({'minimum' if f.margin_mode == 'minimum' else 'required'} {want:g} cm)")
            if problems:
                self.add("formatting", "margins", "FAIL", "Margins do not meet the requirement",
                         "; ".join(problems[:8]) + ".", rule_source=src)
            else:
                self.add("formatting", "margins", "PASS", "Margins meet the requirement", rule_source=src)

        if f.page_numbers_required:
            if self.doc.has_page_number_field:
                self.add("formatting", "page_numbers", "PASS", "Page numbering is present",
                         "A page-number field was found in a header or footer. Its position and format are "
                         "not checked.", rule_source=src)
            else:
                self.add("formatting", "page_numbers", "FAIL", "No page numbering found",
                         "No page-number field was found in any header or footer.", rule_source=src)

    # ---- headings

    @staticmethod
    def _scheme(p: Para) -> tuple[str, Optional[str]]:
        if p.auto_numbered:
            return "automatic", None
        t = p.text.strip()
        m = re.match(r"^(\(?)([IVXLCDM]+|[ivxlcdm]+|[A-Za-z]|\d+(?:\.\d+)*)([.)])\s", t)
        if not m:
            m2 = re.match(r"^(\d+(?:\.\d+)+)\s", t)
            return ("decimal", m2.group(1)) if m2 else ("none", None)
        tok = m.group(2)
        wrap = "(x)" if m.group(1) else ("x)" if m.group(3) == ")" else "x.")
        if tok[0].isdigit():
            kind = "decimal" if "." in tok else "number"
        elif len(tok) == 1 and tok.upper() not in "IVX":
            kind = "letter" if tok.isupper() else "lower letter"
        elif re.fullmatch(r"[IVXLCDM]+", tok):
            kind = "roman"
        elif re.fullmatch(r"[ivxlcdm]+", tok):
            kind = "lower roman"
        else:
            kind = "letter" if tok.isupper() else "lower letter"
        return f"{kind} {wrap}", tok

    @staticmethod
    def _value(kind: str, tok: str) -> Optional[int]:
        if kind.startswith(("roman", "lower roman")):
            vals = dict(I=1, V=5, X=10, L=50, C=100, D=500, M=1000)
            total, prev = 0, 0
            for ch in reversed(tok.upper()):
                v = vals[ch]
                total += -v if v < prev else v
                prev = max(prev, v)
            return total
        if kind.startswith(("letter", "lower letter")):
            return ord(tok.upper()) - 64
        if kind.startswith("number"):
            return int(tok)
        if kind.startswith("decimal"):
            return int(tok.split(".")[-1])
        return None

    def check_headings(self):
        headings = [p for p in self.doc.paragraphs if p.heading_level]
        if not headings:
            self.add("headings", "headings_detected", "WARNING", "No headings were detected",
                     "Apply Word heading styles to section and argument headings so they can be checked.")
            return
        guessed = sum(1 for p in headings if p.heading_basis == "heuristic")
        if guessed:
            self.add("headings", "headings_detected", "WARNING",
                     f"{guessed} of {len(headings)} headings do not use a Word heading style",
                     "These were recognised from bold or capitalised text, so heading levels are estimates. "
                     "Using Word heading styles makes every heading check more reliable.",
                     basis="heuristic", manual_check=True,
                     locations=[self.loc(p) for p in headings if p.heading_basis == "heuristic"])

        section_starts = {s.start for s in self.sections if s.start or s.name != FRONT_MATTER}
        # empty headings and skipped levels
        empty, skipped = [], []
        for a, b in zip(headings, headings[1:] + [None]):
            end = b.index if b is not None else len(self.doc.paragraphs)
            has_body = any(self.doc.paragraphs[i].text.strip() for i in range(a.index + 1, end))
            if not has_body and (b is None or b.heading_level <= a.heading_level):
                empty.append(a)
            if (b is not None and b.heading_level > a.heading_level + 1
                    and a.heading_basis == b.heading_basis == "style"):
                skipped.append(b)
        if empty:
            self.add("headings", "empty_heading", "WARNING", "Headings with no text beneath them",
                     locations=[self.loc(p) for p in empty])
        else:
            self.add("headings", "empty_heading", "PASS", "Every heading is followed by content")
        if skipped:
            self.add("headings", "skipped_level", "WARNING", "Heading levels are skipped",
                     "Each of these headings is more than one level deeper than the heading before it.",
                     locations=[self.loc(p) for p in skipped])

        # numbering and capitalisation, per section and level
        groups: dict[tuple[str, int], list[Para]] = defaultdict(list)
        for p in headings:
            if p.index not in section_starts:
                groups[(self.section_of[p.index], p.heading_level)].append(p)
        mixed, gaps, caps = [], [], []
        for (section, level), items in groups.items():
            schemes = [self._scheme(p) for p in items]
            kinds = Counter(k for k, _ in schemes)
            if len(kinds) > 1:
                common = kinds.most_common(1)[0][0]
                odd = [p for p, (k, _) in zip(items, schemes) if k != common]
                mixed.append((section, level, kinds, odd))
            # sequence: restart whenever a shallower heading intervenes
            prev: Optional[tuple[Para, str, int]] = None
            for p, (k, tok) in zip(items, schemes):
                val = self._value(k, tok) if tok else None
                if prev is not None and any(
                    h.heading_level < level for h in headings if prev[0].index < h.index < p.index
                ):
                    prev = None
                if val is not None:
                    if prev is not None and prev[1] == k and val != prev[2] + 1:
                        gaps.append(p)
                    elif prev is None and val != 1:
                        gaps.append(p)
                    prev = (p, k, val)
            styles = Counter(
                "capitals" if all(c.isupper() for c in p.text if c.isalpha()) else "mixed case" for p in items
            )
            if len(styles) > 1:
                rare = styles.most_common()[-1][0]
                caps.extend(p for p in items
                            if ("capitals" if all(c.isupper() for c in p.text if c.isalpha()) else "mixed case") == rare)
        if mixed:
            detail = "; ".join(
                f"{sec}, level {lvl}: " + ", ".join(f"{n}× {k}" for k, n in kinds.most_common())
                for sec, lvl, kinds, _ in mixed
            )
            self.add("headings", "numbering_scheme", "WARNING", "Inconsistent heading numbering",
                     "Headings at the same level use different numbering styles. " + detail + ".",
                     basis="heuristic", locations=[self.loc(p) for *_, odd in mixed for p in odd])
        else:
            self.add("headings", "numbering_scheme", "PASS", "Heading numbering style is consistent at each level")
        if gaps:
            self.add("headings", "numbering_sequence", "WARNING", "Heading numbers are out of sequence",
                     "Each of these headings does not follow on from the heading before it at the same level.",
                     basis="heuristic", locations=[self.loc(p) for p in gaps])
        else:
            self.add("headings", "numbering_sequence", "PASS", "Heading numbers run in sequence")
        if caps:
            self.add("headings", "capitalisation", "WARNING", "Inconsistent heading capitalisation",
                     "Headings at the same level mix full capitals with mixed case.",
                     basis="heuristic", locations=[self.loc(p) for p in caps])

    # ---- citations

    def check_citations(self):
        notes = self.doc.notes
        style = self.rules.citations.style
        src = self.rules.citations.source
        if not notes:
            self.add("citations", "notes_detected", "WARNING", "No footnotes or endnotes found",
                     "Citation checks only examine footnotes and endnotes. In-text citations are not reviewed.",
                     rule_source=src)
            return
        fn = [n for n in notes if n.kind == "footnote"]
        en = [n for n in notes if n.kind == "endnote"]
        self.add("citations", "notes_detected", "PASS",
                 f"Extracted {len(fn)} footnote{'s' if len(fn) != 1 else ''}"
                 + (f" and {len(en)} endnote{'s' if len(en) != 1 else ''}" if en else ""))

        def flag(check, status, ok_title, bad_title, bad, detail="", basis="deterministic"):
            if bad:
                self.add("citations", check, status, bad_title, detail, basis=basis, rule_source=src,
                         locations=[self.note_loc(n) for n in bad])
            elif ok_title:
                self.add("citations", check, "PASS", ok_title, basis=basis, rule_source=src)

        flag("empty_note", "FAIL", "No empty footnotes", "Empty footnotes",
             [n for n in notes if not n.text.strip()])

        placeholder = re.compile(
            r"\[\s*(?:citation|cite|source|ref(?:erence)?|pin(?:point)?)\b[^\]]*\]|\bTODO\b|\bTBC\b|\bXXX+\b"
            r"|\?\?\?|\[\s*\]|\binsert (?:cite|citation|source)", re.I)
        flag("placeholder", "FAIL", "No placeholder text in footnotes", "Placeholder text left in footnotes",
             [n for n in notes if placeholder.search(n.text)],
             "These footnotes contain drafting placeholders such as TODO or [citation].")

        # cross-references must point backwards to an existing footnote
        xref = re.compile(r"\(n\.?\s*(\d+)\)|\b(?:supra|above|infra|below),?\s+(?:note|n\.?|fn\.?)\s*(\d+)", re.I)
        broken = []
        for n in fn:
            for m in xref.finditer(n.text):
                target = int(m.group(1) or m.group(2))
                forward = re.match(r"infra|below", m.group(0), re.I)
                if target > len(fn) or target < 1 or target == n.number or (target > n.number and not forward):
                    broken.append(n)
                    break
        flag("cross_reference", "FAIL", "Footnote cross-references point to earlier footnotes",
             "Footnote cross-references point to the wrong place", broken,
             "Each of these refers to a footnote number that does not exist, to itself, or to a later footnote. "
             "This often happens when footnotes are added or removed after the reference was typed.")

        ibid = re.compile(r"^\W*(?:ibid|ibidem|id)\b\.?", re.I)
        first_ibid = [n for kind in (fn, en) for n in kind[:1] if ibid.match(n.text)]
        flag("ibid_first", "FAIL", None, "First footnote uses ibid/id with nothing to refer back to", first_ibid)

        if style != "none":
            no_stop = [n for n in notes if n.text.strip() and not re.search(r"[.!?][)\]”\"’']*$", n.text.strip())]
            flag("closing_punctuation", "WARNING", "Footnotes end with closing punctuation",
                 "Footnotes not closed with a full stop", no_stop)

        uses = {
            "ibid": [n for n in notes if re.search(r"\bibid\b", n.text, re.I)],
            "Id.": [n for n in notes if re.search(r"(?:^|[\s(;])Id\.", n.text)],
            "supra": [n for n in notes if re.search(r"\bsupra\b", n.text, re.I)],
            "(n X)": [n for n in notes if re.search(r"\(n\.?\s*\d+\)", n.text)],
        }
        if style == "oscola":
            bad = uses["Id."] + [n for n in uses["supra"] if n not in uses["Id."]]
            flag("short_form_style", "WARNING", "Short-form references are consistent with OSCOLA",
                 "Short-form references that are not OSCOLA style", bad,
                 "OSCOLA uses “ibid” and “(n X)” for repeat citations; these footnotes use “Id.” or “supra”.",
                 basis="heuristic")
        elif style == "bluebook":
            bad = uses["ibid"] + [n for n in uses["(n X)"] if n not in uses["ibid"]]
            flag("short_form_style", "WARNING", "Short-form references are consistent with Bluebook",
                 "Short-form references that are not Bluebook style", bad,
                 "Bluebook uses “Id.” and “supra note X” for repeat citations; these footnotes use “ibid” "
                 "or “(n X)”.", basis="heuristic")
        else:
            for a, b in (("ibid", "Id."), ("supra", "(n X)")):
                if uses[a] and uses[b]:
                    minority = min(uses[a], uses[b], key=len)
                    flag("short_form_style", "WARNING", None,
                         f"Both “{a}” and “{b}” are used for repeat citations", minority,
                         f"{len(uses[a])} footnotes use “{a}” and {len(uses[b])} use “{b}”.", basis="heuristic")

        variants = [
            ("case-name separator", {"v": r"\b[A-Z][\w’'-]*\s+v\s+[A-Z]", "v.": r"\b[A-Z][\w’'-]*\s+v\.\s+[A-Z]",
                                     "vs": r"\b[A-Z][\w’'-]*\s+vs\.?\s+[A-Z]"}),
            ("paragraph pinpoint", {"para": r"\bparas?\s+\d", "para.": r"\bparas?\.\s*\d", "¶": r"¶+\s*\d"}),
            ("page pinpoint", {"p.": r"\bpp?\.\s*\d", "at": r"\bat\s+\d"}),
        ]
        inconsistent = False
        for label, forms in variants:
            hits = {k: [n for n in notes if re.search(rx, n.text)] for k, rx in forms.items()}
            hits = {k: v for k, v in hits.items() if v}
            if len(hits) > 1:
                inconsistent = True
                major = max(hits, key=lambda k: len(hits[k]))
                odd = [n for k, v in hits.items() if k != major for n in v]
                self.add("citations", "format_consistency", "WARNING", f"Inconsistent {label} format",
                         ", ".join(f"“{k}” in {len(v)} footnote{'s' if len(v) != 1 else ''}" for k, v in hits.items())
                         + ". The locations listed use the less common form.",
                         basis="heuristic", rule_source=src,
                         locations=[self.note_loc(n) for n in sorted({id(n): n for n in odd}.values(),
                                                                    key=lambda n: (n.kind, n.number))])
        if not inconsistent:
            self.add("citations", "format_consistency", "PASS",
                     "Case-name separators and pinpoint abbreviations are used consistently",
                     basis="heuristic", rule_source=src)

        if self.rules.citations.require_pinpoints:
            pin = re.compile(r"\bparas?\b|¶|\bpp?\.|\bat\s+\d|\barts?\b|\barticles?\b|§|\bs(?:ec(?:tion)?)?s?\.?\s*\d"
                             r"|\bch(?:apter)?\b|\brule\s+\d|,\s*\d+(?:[-–]\d+)?\s*[.)]*\s*$", re.I)
            missing = [n for n in notes if n.text.strip() and not pin.search(n.text)]
            flag("pinpoints", "WARNING", "Every footnote appears to carry a pinpoint",
                 "Footnotes that may lack a pinpoint reference", missing,
                 "No paragraph, page, article or section reference was recognised in these footnotes.",
                 basis="heuristic")

    def run(self) -> list[Finding]:
        self.check_structure()
        self.check_limits()
        self.check_formatting()
        self.check_headings()
        self.check_citations()
        return self.findings
