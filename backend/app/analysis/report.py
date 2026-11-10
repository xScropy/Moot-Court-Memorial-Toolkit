"""Run the checks and assemble / export the compliance report."""

from __future__ import annotations

from datetime import datetime, timezone
from html import escape

from ..schemas import RuleSet
from .checks import Analysis
from .docx_parser import count_words, parse_docx

NOT_CHECKED = [
    "Whether any cited authority exists, is quoted accurately, is current, or is good law.",
    "Full OSCOLA or Bluebook conformity of individual citations.",
    "Consistency between footnotes and the Index of Authorities.",
    "The quality, logic or persuasiveness of the legal arguments.",
    "Grammar, spelling and legal writing style.",
    "Paragraph spacing, heading fonts, and the position or format of page numbers.",
    "The contents of the cover page and other submission requirements (file name, anonymity, deadline).",
]

SCORE_NOTE = (
    "The compliance indicator summarises the automated checks that ran against the rules you configured. "
    "It is not an assessment of legal merit and does not predict how the memorial will be scored."
)


def build_report(path: str, rules: RuleSet) -> dict:
    doc = parse_docx(path)
    analysis = Analysis(doc, rules)
    findings = analysis.run()
    counts = {s: sum(1 for f in findings if f.status == s) for s in ("PASS", "WARNING", "FAIL")}
    total = sum(counts.values())
    score = round(100 * (counts["PASS"] + 0.5 * counts["WARNING"]) / total) if total else None
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "summary": {
            "score": score,
            "counts": counts,
            "words": analysis.word_totals(),
            "pages": {"stored": doc.stored_page_count, "limit": rules.page_limit.max_pages},
            "footnotes": sum(1 for n in doc.notes if n.kind == "footnote"),
            "endnotes": sum(1 for n in doc.notes if n.kind == "endnote"),
        },
        "findings": [f.model_dump() for f in findings],
        "sections": [
            {
                "name": s.name,
                "configured": s.rule is not None,
                "excluded": bool(s.rule and s.rule.exclude_from_word_count),
                "paragraph": s.start,
                "words": s.words,
                "footnote_words": s.note_words,
                "limit": s.rule.max_words if s.rule else None,
            }
            for s in analysis.sections
            if s.words or s.rule is not None
        ],
        "footnotes": [
            {
                "number": n.number,
                "kind": n.kind,
                "text": n.text,
                "words": count_words(n.text),
                "paragraph": n.paragraph,
                "section": analysis.section_of[n.paragraph] if n.paragraph is not None else None,
            }
            for n in doc.notes
        ],
        "document": {
            "paragraphs": [
                {"i": p.index, "text": p.text, "level": p.heading_level}
                for p in doc.paragraphs
                if p.text.strip()
            ]
        },
        "not_checked": NOT_CHECKED,
        "score_note": SCORE_NOTE,
    }


# ---------------------------------------------------------------- export

_GROUPS = [
    ("FAIL", "Critical issues"),
    ("WARNING", "Warnings"),
    ("PASS", "Passed requirements"),
]
_CATEGORY = {
    "structure": "Structure",
    "limits": "Word and page limits",
    "formatting": "Formatting",
    "headings": "Headings",
    "citations": "Citations and footnotes",
}


def _where(loc: dict) -> str:
    bits = []
    if loc.get("section"):
        bits.append(loc["section"])
    if loc.get("footnote"):
        bits.append(f"footnote {loc['footnote']}")
    elif loc.get("paragraph") is not None:
        bits.append(f"paragraph {loc['paragraph'] + 1}")
    return ", ".join(bits)


def render_html(report: dict, meta: dict) -> str:
    e = escape
    s = report["summary"]
    w = s["words"]
    rows = [
        ("Competition", f"{meta['competition_name']} {meta.get('edition') or ''}".strip()),
        ("Party", meta["party"]),
        ("Team", meta.get("team_name") or "—"),
        ("Document", f"{meta['filename']}" + (f" ({meta['version_label']})" if meta.get("version_label") else "")),
        ("Reviewed", report["generated_at"].replace("T", " ").replace("+00:00", " UTC")),
        ("Words counted", f"{w['counted']:,}" + (f" of {w['limit']:,} allowed" if w["limit"] else "")),
        ("Words in body / footnotes", f"{w['body']:,} / {w['notes']:,}"),
        ("Pages (as stored in file)", f"{s['pages']['stored'] or 'unknown'}"
         + (f" of {s['pages']['limit']} allowed" if s["pages"]["limit"] else "")),
        ("Footnotes", str(s["footnotes"]) + (f" (+{s['endnotes']} endnotes)" if s["endnotes"] else "")),
    ]
    out = [
        "<!doctype html><html lang='en'><head><meta charset='utf-8'>",
        f"<title>Compliance report – {e(meta['filename'])}</title>",
        "<meta name='viewport' content='width=device-width, initial-scale=1'>",
        "<style>body{font:15px/1.5 Georgia,serif;max-width:860px;margin:2rem auto;padding:0 1rem;color:#1c2333}"
        "h1{font-size:1.6rem;margin-bottom:.2rem}h2{font-size:1.2rem;margin-top:2rem;border-bottom:1px solid #ccd;"
        "padding-bottom:.3rem}table{border-collapse:collapse;width:100%}td,th{padding:.3rem .6rem;text-align:left;"
        "vertical-align:top;border-bottom:1px solid #e5e7ef}.f{margin:.9rem 0;padding:.6rem .8rem;border-left:4px "
        "solid #999;background:#f7f8fb;break-inside:avoid}.FAIL{border-color:#b42318}.WARNING{border-color:#b54708}"
        ".PASS{border-color:#067647}.tag{font:600 .72rem sans-serif;letter-spacing:.04em;margin-right:.5rem}"
        ".FAIL .tag{color:#b42318}.WARNING .tag{color:#b54708}.PASS .tag{color:#067647}.m{color:#5a6275;"
        "font-size:.88rem}ul{margin:.3rem 0 0 1.1rem;padding:0}.score{font-size:2rem;font-weight:700}"
        "@media print{body{margin:0}}</style></head><body>",
        "<h1>Memorial compliance report</h1>",
        "<p class='m'>Moot Court Memorial Toolkit</p>",
        f"<p><span class='score'>{s['score'] if s['score'] is not None else '–'}%</span> compliance indicator · "
        f"{s['counts']['FAIL']} fail · {s['counts']['WARNING']} warning · {s['counts']['PASS']} pass</p>",
        f"<p class='m'>{e(report['score_note'])}</p>",
        "<table>" + "".join(f"<tr><th>{e(k)}</th><td>{e(v)}</td></tr>" for k, v in rows) + "</table>",
    ]
    for status, title in _GROUPS:
        items = [f for f in report["findings"] if f["status"] == status]
        out.append(f"<h2>{title} ({len(items)})</h2>")
        if not items:
            out.append("<p class='m'>None.</p>")
        for f in items:
            out.append(f"<div class='f {status}'><span class='tag'>{status}</span><strong>{e(f['title'])}</strong>")
            tags = [_CATEGORY[f["category"]]]
            if f["basis"] == "heuristic":
                tags.append("pattern-based flag, confirm manually")
            elif f["manual_check"]:
                tags.append("verify manually")
            if f["rule_source"]:
                tags.append("rule source: " + f["rule_source"])
            out.append(f"<div class='m'>{e(' · '.join(tags))}</div>")
            if f["detail"]:
                out.append(f"<div>{e(f['detail'])}</div>")
            if f["locations"]:
                out.append("<ul>" + "".join(
                    f"<li class='m'><strong>{e(_where(l))}</strong>"
                    + (f": {e(l['excerpt'])}" if l.get("excerpt") else "") + "</li>"
                    for l in f["locations"]) + "</ul>")
            out.append("</div>")
    out.append("<h2>Word count by section</h2><table><tr><th>Section</th><th>Words</th><th>Footnote words</th>"
               "<th>Limit</th></tr>")
    for sec in report["sections"]:
        out.append(f"<tr><td>{e(sec['name'])}{' (excluded from total)' if sec['excluded'] else ''}</td>"
                   f"<td>{sec['words']:,}</td><td>{sec['footnote_words']:,}</td>"
                   f"<td>{sec['limit'] or '—'}</td></tr>")
    out.append("</table><h2>Not covered by this report</h2><ul>")
    out += [f"<li>{e(x)}</li>" for x in report["not_checked"]]
    out.append("</ul>")
    if meta.get("special_instructions"):
        out.append(f"<h2>Special instructions (check manually)</h2><p>{e(meta['special_instructions'])}</p>")
    out.append("</body></html>")
    return "".join(out)
