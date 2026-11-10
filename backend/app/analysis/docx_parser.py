"""Read a DOCX into a plain structure the checks can work on.

python-docx opens the package; formatting is resolved from the raw XML so the
same code handles body text and footnotes (which python-docx does not expose).
"""

from __future__ import annotations

import re
import zipfile
from dataclasses import dataclass, field
from typing import Optional

from docx import Document
from docx.oxml.ns import qn
from lxml import etree

MAX_UNCOMPRESSED_BYTES = 300 * 1024 * 1024
_SAFE_PARSER = etree.XMLParser(resolve_entities=False, no_network=True)
_A_NS = "http://schemas.openxmlformats.org/drawingml/2006/main"
_MC_FALLBACK = "{http://schemas.openxmlformats.org/markup-compatibility/2006}Fallback"
_EP_NS = "http://schemas.openxmlformats.org/officeDocument/2006/extended-properties"


class InvalidDocument(ValueError):
    pass


@dataclass
class Run:
    text: str
    font: Optional[str]
    size_pt: float


@dataclass
class Para:
    index: int
    text: str
    runs: list[Run]
    style_name: str
    heading_level: Optional[int] = None
    heading_basis: Optional[str] = None  # "style" | "heuristic"
    auto_numbered: bool = False
    line_spacing: Optional[float] = None  # multiple of single spacing
    line_spacing_fixed_pt: Optional[float] = None  # exact / at-least spacing
    in_toc_field: bool = False
    footnote_ids: list[int] = field(default_factory=list)


@dataclass
class Note:
    number: int  # display number, in order of first reference
    kind: str  # "footnote" | "endnote"
    text: str
    runs: list[Run]
    paragraph: Optional[int]  # index of the body paragraph that references it


@dataclass
class Margins:
    top_cm: float
    bottom_cm: float
    left_cm: float
    right_cm: float


@dataclass
class ParsedDocument:
    paragraphs: list[Para]
    notes: list[Note]
    margins: list[Margins]
    has_page_number_field: bool
    has_toc_field: bool
    stored_page_count: Optional[int]


def count_words(text: str) -> int:
    """Whitespace-delimited tokens, the same convention Microsoft Word uses."""
    return len(text.split())


# ---------------------------------------------------------------- styles


class _Styles:
    def __init__(self, styles_el, theme_fonts: dict[str, str]):
        self.by_id: dict[str, etree._Element] = {}
        self.default_para: Optional[str] = None
        self.theme_fonts = theme_fonts
        self.doc_rpr = None
        self.doc_ppr = None
        if styles_el is None:
            return
        for st in styles_el.findall(qn("w:style")):
            sid = st.get(qn("w:styleId"))
            if sid is None:
                continue
            self.by_id[sid] = st
            if st.get(qn("w:type")) == "paragraph" and st.get(qn("w:default")) in ("1", "true"):
                self.default_para = sid
        self.doc_rpr = styles_el.find(f"{qn('w:docDefaults')}/{qn('w:rPrDefault')}/{qn('w:rPr')}")
        self.doc_ppr = styles_el.find(f"{qn('w:docDefaults')}/{qn('w:pPrDefault')}/{qn('w:pPr')}")

    def chain(self, style_id: Optional[str]):
        seen = set()
        while style_id and style_id not in seen and style_id in self.by_id:
            seen.add(style_id)
            st = self.by_id[style_id]
            yield st
            based = st.find(qn("w:basedOn"))
            style_id = based.get(qn("w:val")) if based is not None else None

    def name(self, style_id: Optional[str]) -> str:
        st = self.by_id.get(style_id or "")
        if st is None:
            return ""
        n = st.find(qn("w:name"))
        return n.get(qn("w:val"), "") if n is not None else ""

    def _font_of(self, rpr) -> Optional[str]:
        if rpr is None:
            return None
        rf = rpr.find(qn("w:rFonts"))
        if rf is None:
            return None
        name = rf.get(qn("w:ascii")) or rf.get(qn("w:hAnsi"))
        if name:
            return name
        theme = rf.get(qn("w:asciiTheme")) or rf.get(qn("w:hAnsiTheme"))
        if theme:
            return self.theme_fonts.get("major" if theme.startswith("major") else "minor")
        return None

    @staticmethod
    def _size_of(rpr) -> Optional[float]:
        if rpr is None:
            return None
        sz = rpr.find(qn("w:sz"))
        if sz is None:
            return None
        try:
            return int(sz.get(qn("w:val"))) / 2
        except (TypeError, ValueError):
            return None

    def _rpr_sources(self, run_rpr, para_style: Optional[str]):
        yield run_rpr
        if run_rpr is not None:
            rs = run_rpr.find(qn("w:rStyle"))
            if rs is not None:
                for st in self.chain(rs.get(qn("w:val"))):
                    yield st.find(qn("w:rPr"))
        for st in self.chain(para_style or self.default_para):
            yield st.find(qn("w:rPr"))
        yield self.doc_rpr

    def run_format(self, run_rpr, para_style: Optional[str]) -> tuple[Optional[str], float]:
        font, size = None, None
        for rpr in self._rpr_sources(run_rpr, para_style):
            if font is None:
                font = self._font_of(rpr)
            if size is None:
                size = self._size_of(rpr)
            if font is not None and size is not None:
                break
        return font, size if size is not None else 10.0  # OOXML default is 10pt

    def spacing(self, ppr, para_style: Optional[str]) -> tuple[Optional[float], Optional[float]]:
        """Returns (multiple, fixed_pt); exactly one is set."""
        sources = [ppr]
        sources += [st.find(qn("w:pPr")) for st in self.chain(para_style or self.default_para)]
        sources.append(self.doc_ppr)
        for src in sources:
            if src is None:
                continue
            sp = src.find(qn("w:spacing"))
            if sp is None or sp.get(qn("w:line")) is None:
                continue
            try:
                line = int(sp.get(qn("w:line")))
            except ValueError:
                continue
            if sp.get(qn("w:lineRule"), "auto") == "auto":
                return line / 240, None
            return None, line / 20
        return 1.0, None

    def outline_level(self, ppr, para_style: Optional[str]) -> Optional[int]:
        sources = [ppr] + [st.find(qn("w:pPr")) for st in self.chain(para_style)]
        for src in sources:
            if src is None:
                continue
            ol = src.find(qn("w:outlineLvl"))
            if ol is not None:
                try:
                    lvl = int(ol.get(qn("w:val")))
                except (TypeError, ValueError):
                    continue
                return lvl + 1 if lvl < 9 else None
        return None

    def has_numbering(self, ppr, para_style: Optional[str]) -> bool:
        sources = [ppr] + [st.find(qn("w:pPr")) for st in self.chain(para_style)]
        for src in sources:
            if src is None:
                continue
            num = src.find(qn("w:numPr"))
            if num is not None:
                nid = num.find(qn("w:numId"))
                return nid is None or nid.get(qn("w:val")) != "0"
        return False


# ---------------------------------------------------------------- helpers


def _own_runs(p):
    """Runs belonging to this paragraph, not to paragraphs nested inside it
    (text boxes) and not to legacy fallback copies of drawings."""
    stack = list(reversed(list(p)))
    while stack:
        el = stack.pop()
        if not isinstance(el.tag, str):
            continue
        if el.tag in (qn("w:p"), _MC_FALLBACK, qn("w:txbxContent")):
            continue
        if el.tag == qn("w:r"):
            yield el
            # drawings anchored in a run may hold text boxes; skip them
            continue
        stack.extend(reversed(list(el)))


def _run_text(r) -> tuple[str, list[tuple[str, int]]]:
    parts, refs = [], []
    for el in r:
        if el.tag == qn("w:t"):
            parts.append(el.text or "")
        elif el.tag in (qn("w:tab"), qn("w:br"), qn("w:cr")):
            parts.append(" ")
        elif el.tag == qn("w:noBreakHyphen"):
            parts.append("-")
        elif el.tag in (qn("w:footnoteReference"), qn("w:endnoteReference")):
            try:
                kind = "footnote" if el.tag == qn("w:footnoteReference") else "endnote"
                refs.append((kind, int(el.get(qn("w:id")))))
            except (TypeError, ValueError):
                pass
    return "".join(parts), refs


def _iter_paragraphs(root):
    for p in root.iter(qn("w:p")):
        if any(a.tag == _MC_FALLBACK for a in p.iterancestors()):
            continue
        yield p


_FIELD_RE = re.compile(r"^\s*(\w+)")


def _field_names(root) -> set[str]:
    names = set()
    for el in root.iter(qn("w:instrText"), qn("w:fldSimple")):
        instr = el.text if el.tag == qn("w:instrText") else el.get(qn("w:instr"))
        m = _FIELD_RE.match(instr or "")
        if m:
            names.add(m.group(1).upper())
    return names


def _theme_fonts(package) -> dict[str, str]:
    fonts = {}
    for part in package.iter_parts():
        if not str(part.partname).startswith("/word/theme/"):
            continue
        try:
            root = etree.fromstring(part.blob, _SAFE_PARSER)
        except etree.XMLSyntaxError:
            continue
        for key in ("major", "minor"):
            latin = root.find(f".//{{{_A_NS}}}{key}Font/{{{_A_NS}}}latin")
            if latin is not None and latin.get("typeface"):
                fonts[key] = latin.get("typeface")
        break
    return fonts


def _stored_pages(package) -> Optional[int]:
    for part in package.iter_parts():
        if str(part.partname) == "/docProps/app.xml":
            try:
                root = etree.fromstring(part.blob, _SAFE_PARSER)
                pages = root.findtext(f"{{{_EP_NS}}}Pages")
                return int(pages) if pages and int(pages) > 0 else None
            except (etree.XMLSyntaxError, ValueError):
                return None
    return None


def _part_root(part):
    el = getattr(part, "element", None)
    if el is not None:
        return el
    try:
        return etree.fromstring(part.blob, _SAFE_PARSER)
    except etree.XMLSyntaxError:
        return None


_NUM_PREFIX = re.compile(
    r"^\s*(?:\(?(?:[IVXLCDM]+|[ivxlcdm]+|[A-Za-z]|\d+(?:\.\d+)*)[.)]\s+|\d+(?:\.\d+)*\s+)"
)


def _heuristic_heading(text: str, runs_bold: bool, has_note: bool) -> Optional[int]:
    """Guess whether an unstyled paragraph is a heading."""
    stripped = text.strip()
    if not stripped or has_note or len(stripped.split()) > 20 or len(stripped) > 160:
        return None
    letters = [c for c in stripped if c.isalpha()]
    if len(letters) < 3:
        return None
    all_caps = all(c.isupper() for c in letters)
    if not (all_caps or runs_bold):
        return None
    if stripped.endswith((";", ",", ":")):
        return None
    if re.search(r"[\s.\u2026]\d+$", stripped):  # looks like a typed contents line
        return None
    if all_caps and not _NUM_PREFIX.match(stripped):
        return 1
    m = re.match(r"^\s*\(?([IVXLCDM]+|[A-Z]|\d+(?:\.\d+)*|[a-z]|[ivxlcdm]+)[.)]", stripped)
    if m:
        tok = m.group(1)
        if re.fullmatch(r"[IVXLCDM]+", tok) and tok not in ("C", "D", "L", "M"):
            return 1 if all_caps else 2
        if re.fullmatch(r"[A-Z]", tok):
            return 2
        if tok[0].isdigit():
            return min(3 + tok.count("."), 6)
        return 4
    return 1 if all_caps else 2


# ---------------------------------------------------------------- main


def parse_docx(path: str) -> ParsedDocument:
    try:
        with zipfile.ZipFile(path) as zf:
            if sum(i.file_size for i in zf.infolist()) > MAX_UNCOMPRESSED_BYTES:
                raise InvalidDocument("The file is too large to analyse once decompressed.")
        doc = Document(path)
    except InvalidDocument:
        raise
    except Exception as exc:  # corrupt zip, not a Word file, etc.
        raise InvalidDocument("The file could not be read as a DOCX document.") from exc

    package = doc.part.package
    styles_el = None
    try:
        styles_el = doc.styles.element
    except Exception:
        pass
    styles = _Styles(styles_el, _theme_fonts(package))

    def build_runs(p, style_id):
        runs, refs, bold_all = [], [], True
        for r in _own_runs(p):
            text, r_refs = _run_text(r)
            refs.extend(r_refs)
            if not text:
                continue
            rpr = r.find(qn("w:rPr"))
            font, size = styles.run_format(rpr, style_id)
            runs.append(Run(text, font, size))
            if text.strip():
                b = None
                for src in styles._rpr_sources(rpr, style_id):
                    if src is not None and src.find(qn("w:b")) is not None:
                        b = src.find(qn("w:b")).get(qn("w:val"), "1") not in ("0", "false")
                        break
                bold_all = bold_all and bool(b)
        return runs, refs, bold_all and any(r.text.strip() for r in runs)

    paragraphs: list[Para] = []
    ref_order: list[tuple[str, int, int]] = []  # kind, id, paragraph index
    body = doc.element.body
    field_depth, toc_depth = 0, None
    for p in _iter_paragraphs(body):
        ppr = p.find(qn("w:pPr"))
        style_el = ppr.find(qn("w:pStyle")) if ppr is not None else None
        style_id = style_el.get(qn("w:val")) if style_el is not None else None
        style_name = styles.name(style_id or styles.default_para)
        runs, refs, bold_all = build_runs(p, style_id)
        text = "".join(r.text for r in runs)

        # Track whether we are inside a TOC field or TOC content control.
        touched_toc = toc_depth is not None
        for el in p.iter(qn("w:fldChar"), qn("w:instrText")):
            if el.tag == qn("w:instrText"):
                if toc_depth is None and re.match(r"\s*TOC\b", el.text or ""):
                    toc_depth = field_depth
                    touched_toc = True
                continue
            kind = el.get(qn("w:fldCharType"))
            if kind == "begin":
                field_depth += 1
            elif kind == "end":
                if toc_depth is not None and field_depth == toc_depth:
                    toc_depth = None
                field_depth = max(field_depth - 1, 0)
        in_sdt_toc = any(
            a.tag == qn("w:sdt") and "Table of Contents" in (a.xpath(
                "string(w:sdtPr/w:docPartObj/w:docPartGallery/@w:val)", namespaces=a.nsmap) or "")
            for a in p.iterancestors()
        )
        is_toc_entry = touched_toc or in_sdt_toc or style_name.lower().startswith("toc ")

        level, basis = None, None
        lname = style_name.lower()
        m = re.match(r"heading\s*(\d)", lname)
        if text.strip() and lname == "toc heading":
            level, basis = 1, "style"
        elif text.strip() and not is_toc_entry:
            if m:
                level, basis = int(m.group(1)), "style"
            elif lname == "title":
                level, basis = 1, "style"
            else:
                ol = styles.outline_level(ppr, style_id)
                if ol:
                    level, basis = ol, "style"
            if level is None and not any(a.tag == qn("w:tbl") for a in p.iterancestors()):
                guess = _heuristic_heading(text, bold_all, bool(refs))
                if guess:
                    level, basis = guess, "heuristic"

        multiple, fixed = styles.spacing(ppr, style_id)
        idx = len(paragraphs)
        paragraphs.append(
            Para(
                index=idx,
                text=text,
                runs=runs,
                style_name=style_name,
                heading_level=level,
                heading_basis=basis,
                auto_numbered=styles.has_numbering(ppr, style_id),
                line_spacing=multiple,
                line_spacing_fixed_pt=fixed,
                in_toc_field=is_toc_entry,
            )
        )
        for kind, nid in refs:
            ref_order.append((kind, nid, idx))

    # Footnotes and endnotes live in their own parts.
    note_els: dict[tuple[str, int], etree._Element] = {}
    for part in package.iter_parts():
        name = str(part.partname)
        if name not in ("/word/footnotes.xml", "/word/endnotes.xml"):
            continue
        root = _part_root(part)
        if root is None:
            continue
        kind = "footnote" if "footnotes" in name else "endnote"
        for el in root.findall(qn(f"w:{kind}")):
            if el.get(qn("w:type")) in ("separator", "continuationSeparator", "continuationNotice"):
                continue
            try:
                note_els[(kind, int(el.get(qn("w:id"))))] = el
            except (TypeError, ValueError):
                continue

    notes: list[Note] = []
    counters = {"footnote": 0, "endnote": 0}
    seen = set()
    for kind, nid, pidx in ref_order:
        if (kind, nid) in seen or (kind, nid) not in note_els:
            continue
        seen.add((kind, nid))
        counters[kind] += 1
        runs: list[Run] = []
        texts = []
        for p in _iter_paragraphs(note_els[(kind, nid)]):
            ppr = p.find(qn("w:pPr"))
            st = ppr.find(qn("w:pStyle")) if ppr is not None else None
            p_runs, _, _ = build_runs(p, st.get(qn("w:val")) if st is not None else None)
            runs.extend(p_runs)
            texts.append("".join(r.text for r in p_runs))
        notes.append(Note(counters[kind], kind, " ".join(t.strip() for t in texts).strip(), runs, pidx))
        paragraphs[pidx].footnote_ids.append(len(notes) - 1)

    margins = []
    for s in doc.sections:
        try:
            margins.append(
                Margins(
                    *(round((v or 0) / 360000, 2)
                      for v in (s.top_margin, s.bottom_margin, s.left_margin, s.right_margin))
                )
            )
        except Exception:
            continue

    has_page_field = False
    for part in package.iter_parts():
        name = str(part.partname)
        if name.startswith("/word/header") or name.startswith("/word/footer"):
            root = _part_root(part)
            if root is not None and "PAGE" in _field_names(root):
                has_page_field = True
                break

    return ParsedDocument(
        paragraphs=paragraphs,
        notes=notes,
        margins=margins,
        has_page_number_field=has_page_field,
        has_toc_field="TOC" in _field_names(body) or any(p.in_toc_field for p in paragraphs),
        stored_page_count=_stored_pages(package),
    )
