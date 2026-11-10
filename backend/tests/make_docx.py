"""Build small memorial DOCX files for tests, including real footnotes."""

import re
import shutil
import zipfile

from docx import Document
from docx.shared import Cm, Pt

W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
MARK = "[[fn:%d]]"


def make(path, body, footnotes=(), font="Times New Roman", size=12, spacing=2.0, margin_cm=2.54,
         page_numbers=True, pages=None):
    """body: list of (kind, text); kind is 'h1'..'h3', 'p', or 'raw' (no formatting).
    Write {fn} in a paragraph to attach the next footnote."""
    doc = Document()
    st = doc.styles["Normal"]
    st.font.name, st.font.size = font, Pt(size)
    st.paragraph_format.line_spacing = spacing
    for s in doc.sections:
        s.top_margin = s.bottom_margin = s.left_margin = s.right_margin = Cm(margin_cm)
    n = 0
    for kind, text in body:
        while "{fn}" in text:
            n += 1
            text = text.replace("{fn}", MARK % n, 1)
        if kind.startswith("h"):
            p = doc.add_heading(text, level=int(kind[1]))
            for r in p.runs:
                r.font.name = font
        else:
            doc.add_paragraph(text)
    if page_numbers:
        fp = doc.sections[0].footer.paragraphs[0]
        fp._p.append(fp._p.makeelement(f"{{{W}}}fldSimple", {f"{{{W}}}instr": " PAGE "}))
    doc.save(path)
    _inject(path, list(footnotes), pages)


def _inject(path, footnotes, pages):
    tmp = str(path) + ".tmp"
    with zipfile.ZipFile(path) as zin, zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as zout:
        for item in zin.infolist():
            data = zin.read(item.filename)
            if item.filename == "word/document.xml" and footnotes:
                xml = data.decode()
                xml = re.sub(
                    r"\[\[fn:(\d+)\]\]",
                    lambda m: f'</w:t></w:r><w:r><w:footnoteReference w:id="{int(m.group(1)) + 1}"/></w:r>'
                              f'<w:r><w:t xml:space="preserve">',
                    xml,
                )
                data = xml.encode()
            elif item.filename == "[Content_Types].xml" and footnotes:
                data = data.replace(
                    b"</Types>",
                    b'<Override PartName="/word/footnotes.xml" ContentType="application/vnd.openxmlformats-'
                    b'officedocument.wordprocessingml.footnotes+xml"/></Types>',
                )
            elif item.filename == "word/_rels/document.xml.rels" and footnotes:
                data = data.replace(
                    b"</Relationships>",
                    b'<Relationship Id="rIdFn" Type="http://schemas.openxmlformats.org/officeDocument/2006/'
                    b'relationships/footnotes" Target="footnotes.xml"/></Relationships>',
                )
            elif item.filename == "docProps/app.xml" and pages is not None:
                if b"<Pages>" in data:
                    data = re.sub(rb"<Pages>\d+</Pages>", b"<Pages>%d</Pages>" % pages, data)
                else:
                    data = data.replace(b"</Properties>", b"<Pages>%d</Pages></Properties>" % pages)
            zout.writestr(item, data)
        if footnotes:
            notes = "".join(
                f'<w:footnote w:id="{i + 2}"><w:p><w:r><w:rPr><w:sz w:val="20"/></w:rPr>'
                f'<w:t xml:space="preserve">{_esc(t)}</w:t></w:r></w:p></w:footnote>'
                for i, t in enumerate(footnotes)
            )
            zout.writestr(
                "word/footnotes.xml",
                f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?><w:footnotes xmlns:w="{W}">'
                f'<w:footnote w:type="separator" w:id="0"><w:p/></w:footnote>'
                f'<w:footnote w:type="continuationSeparator" w:id="1"><w:p/></w:footnote>{notes}</w:footnotes>',
            )
    shutil.move(tmp, path)


def _esc(t):
    return t.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


GOOD_BODY = [
    ("p", "TEAM 42"), ("p", "MEMORIAL FOR THE APPLICANT"),
    ("h1", "TABLE OF CONTENTS"), ("p", "Listed here."),
    ("h1", "INDEX OF AUTHORITIES"), ("p", "Listed here."),
    ("h1", "STATEMENT OF JURISDICTION"), ("p", "The parties have submitted the dispute by special agreement."),
    ("h1", "STATEMENT OF FACTS"), ("p", "Aurora and Borealis are neighbouring states.{fn}"),
    ("h1", "SUMMARY OF PLEADINGS"), ("p", "The Court has jurisdiction and the claim is admissible."),
    ("h1", "PLEADINGS"),
    ("h2", "I. THE COURT HAS JURISDICTION"),
    ("p", "Consent is the basis of jurisdiction.{fn} The compromis records that consent.{fn}"),
    ("h3", "A. The special agreement is valid"), ("p", "It was signed by both agents.{fn}"),
    ("h3", "B. No reservation applies"), ("p", "Neither party has entered a reservation."),
    ("h2", "II. THE CLAIM IS ADMISSIBLE"), ("p", "Local remedies were exhausted.{fn}"),
    ("h1", "PRAYER FOR RELIEF"), ("p", "The Applicant respectfully requests the Court to adjudge and declare."),
]
GOOD_NOTES = [
    "Compromis, para 3.",
    "Monetary Gold Removed from Rome in 1943 (Italy v France) [1954] ICJ Rep 19, 32.",
    "ibid 33.",
    "Compromis (n 1) para 5.",
    "Interhandel (Switzerland v United States) [1959] ICJ Rep 6, 27.",
]
