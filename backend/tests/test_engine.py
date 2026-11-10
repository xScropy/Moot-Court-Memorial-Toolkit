import pytest

from app.analysis.docx_parser import InvalidDocument, count_words, parse_docx
from app.analysis.report import build_report
from app.main import starter_rules
from app.schemas import RuleSet

from .make_docx import GOOD_BODY, GOOD_NOTES, make


def rules(**over) -> RuleSet:
    r = starter_rules()
    r.word_limit.total_max = 500
    r.page_limit.max_pages = 10
    f = r.formatting
    f.font_family, f.font_size_pt, f.footnote_font_size_pt, f.line_spacing = "Times New Roman", 12, 10, 2.0
    f.margin_top_cm = f.margin_bottom_cm = f.margin_left_cm = f.margin_right_cm = 2.54
    f.page_numbers_required = True
    r.citations.style = "oscola"
    for k, v in over.items():
        setattr(r, k, v)
    return r


def by_check(report, check):
    return [f for f in report["findings"] if f["check"] == check]


def status(report, check):
    return {f["status"] for f in by_check(report, check)}


@pytest.fixture
def good(tmp_path):
    path = tmp_path / "good.docx"
    make(path, GOOD_BODY, GOOD_NOTES, pages=8)
    return str(path)


def test_compliant_memorial_has_no_failures(good):
    report = build_report(good, rules())
    bad = [f for f in report["findings"] if f["status"] != "PASS"]
    assert bad == [], [(f["check"], f["title"]) for f in bad]
    assert report["summary"]["score"] == 100
    assert report["summary"]["footnotes"] == 5


def test_word_count_matches_whitespace_tokens(good):
    report = build_report(good, rules())
    expected = sum(count_words(t.replace("{fn}", "")) for _, t in GOOD_BODY)
    assert report["summary"]["words"]["body"] == expected
    assert report["summary"]["words"]["notes"] == sum(count_words(n) for n in GOOD_NOTES)
    assert report["summary"]["words"]["counted"] == expected


def test_footnotes_and_exclusions_change_counted_total(good):
    r = rules()
    r.word_limit.count_footnotes = True
    for s in r.sections:
        if s.name in ("Table of Contents", "Index of Authorities"):
            s.exclude_from_word_count = True
    w = build_report(good, r)["summary"]["words"]
    # the two excluded sections are five words each and carry no footnotes
    assert w["counted"] == w["body"] + w["notes"] - 2 * count_words("TABLE OF CONTENTS Listed here.")


def test_footnotes_extracted_in_order_with_location(good):
    notes = build_report(good, rules())["footnotes"]
    assert [n["text"] for n in notes] == GOOD_NOTES
    assert [n["number"] for n in notes] == [1, 2, 3, 4, 5]
    assert notes[0]["section"] == "Statement of Facts"
    assert notes[4]["section"] == "Pleadings"


def test_missing_section_and_limits_fail(tmp_path):
    body = [b for b in GOOD_BODY if "JURISDICTION" not in b[1] or b[0] != "h1"]
    body = [b for b in body if not b[1].startswith("The parties have submitted")]
    path = tmp_path / "m.docx"
    make(path, body, GOOD_NOTES, pages=12)
    r = rules()
    r.word_limit.total_max = 50
    next(s for s in r.sections if s.name == "Statement of Facts").max_words = 3
    report = build_report(str(path), r)
    missing = [f for f in by_check(report, "section_present") if f["status"] == "FAIL"]
    assert [f["title"] for f in missing] == ["Statement of Jurisdiction not found"]
    assert status(report, "total_words") == {"FAIL"}
    assert status(report, "pages") == {"FAIL"}
    over = [f for f in by_check(report, "section_words") if f["status"] == "FAIL"]
    assert len(over) == 1 and over[0]["locations"][0]["section"] == "Statement of Facts"


def test_alias_matches_and_order_warning(tmp_path):
    body = list(GOOD_BODY)
    i = next(k for k, b in enumerate(body) if b[1] == "SUMMARY OF PLEADINGS")
    body[i] = ("h1", "SUMMARY OF ARGUMENTS")
    # move the prayer to the front of the document body
    prayer = body[-2:]
    body = body[:2] + prayer + body[2:-2]
    path = tmp_path / "o.docx"
    make(path, body, GOOD_NOTES)
    report = build_report(str(path), rules())
    assert all(f["status"] == "PASS" for f in by_check(report, "section_present"))
    assert status(report, "section_order") == {"WARNING"}


def test_formatting_failures(tmp_path):
    path = tmp_path / "f.docx"
    make(path, GOOD_BODY, GOOD_NOTES, font="Arial", size=11, spacing=1.5, margin_cm=2.0, page_numbers=False)
    report = build_report(str(path), rules())
    for check in ("font_family", "font_size", "line_spacing", "margins", "page_numbers"):
        assert status(report, check) == {"FAIL"}, check
    assert status(report, "footnote_font_size") == {"PASS"}
    assert by_check(report, "font_size")[0]["locations"][0]["paragraph"] is not None


def test_exact_margin_mode(good, tmp_path):
    r = rules()
    r.formatting.margin_top_cm = 2.0  # document has 2.54
    assert status(build_report(good, r), "margins") == {"PASS"}
    r.formatting.margin_mode = "exact"
    assert status(build_report(good, r), "margins") == {"FAIL"}


def test_heading_problems(tmp_path):
    body = [
        ("h1", "PLEADINGS"),
        ("h2", "I. FIRST SUBMISSION"), ("p", "Text."),
        ("h2", "III. THIRD SUBMISSION"),  # gap, and empty
        ("h2", "B. Fourth submission"), ("p", "Text."),  # mixed scheme and capitalisation
        ("h1", "PRAYER FOR RELIEF"), ("p", "Text."),
    ]
    path = tmp_path / "h.docx"
    make(path, body)
    report = build_report(str(path), rules())
    assert status(report, "numbering_sequence") == {"WARNING"}
    assert status(report, "numbering_scheme") == {"WARNING"}
    assert status(report, "empty_heading") == {"WARNING"}
    assert status(report, "capitalisation") == {"WARNING"}
    assert by_check(report, "empty_heading")[0]["locations"][0]["excerpt"] == "III. THIRD SUBMISSION"


def test_unstyled_headings_detected_heuristically(tmp_path):
    body = [("p", "STATEMENT OF FACTS"), ("p", "Aurora and Borealis are neighbouring states with a long border."),
            ("p", "PRAYER FOR RELIEF"), ("p", "The Applicant requests relief from the Court in this matter.")]
    path = tmp_path / "u.docx"
    make(path, body)
    report = build_report(str(path), rules())
    found = {f["title"] for f in by_check(report, "section_present") if f["status"] == "PASS"}
    assert {"Statement of Facts found", "Prayer for Relief found"} <= found
    assert status(report, "headings_detected") == {"WARNING"}


def test_citation_problems(tmp_path):
    notes = [
        "ibid 4.",                                    # nothing to refer back to
        "Corfu Channel (UK v. Albania) [1949] ICJ Rep 4, 22",  # v. and no full stop
        "Nicaragua (n 7) para 14.",                   # forward / missing target
        "[citation needed]",
        "Id. at 5.",                                  # Bluebook form under OSCOLA
        "Oil Platforms (Iran v United States) [2003] ICJ Rep 161.",
    ]
    body = [("h1", "PLEADINGS"), ("p", "One.{fn} Two.{fn} Three.{fn} Four.{fn} Five.{fn} Six.{fn}")]
    path = tmp_path / "c.docx"
    make(path, body, notes)
    r = rules()
    r.citations.require_pinpoints = True
    report = build_report(str(path), r)
    assert status(report, "ibid_first") == {"FAIL"}
    assert [l["footnote"] for l in by_check(report, "cross_reference")[0]["locations"]] == [3]
    assert [l["footnote"] for l in by_check(report, "placeholder")[0]["locations"]] == [4]
    assert 2 in [l["footnote"] for l in by_check(report, "closing_punctuation")[0]["locations"]]
    assert [l["footnote"] for l in by_check(report, "short_form_style")[0]["locations"]] == [5]
    assert status(report, "format_consistency") == {"WARNING"}
    assert 6 in [l["footnote"] for l in by_check(report, "pinpoints")[0]["locations"]]
    # format checks never assert legal validity
    assert not any("valid" in f["title"].lower() or "good law" in f["title"].lower() for f in report["findings"])


def test_unconfigured_rules_produce_no_findings_for_them(good):
    report = build_report(good, RuleSet())
    assert not by_check(report, "total_words") and not by_check(report, "font_family")
    assert not by_check(report, "section_present")


def test_invalid_file_rejected(tmp_path):
    p = tmp_path / "x.docx"
    p.write_bytes(b"PK not really a zip")
    with pytest.raises(InvalidDocument):
        parse_docx(str(p))
