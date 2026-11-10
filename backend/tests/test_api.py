import importlib

import pytest
from fastapi.testclient import TestClient

from .make_docx import GOOD_BODY, GOOD_NOTES, make


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("MCMT_DATA_DIR", str(tmp_path / "data"))
    from app import db, main
    importlib.reload(db)
    importlib.reload(main)
    with TestClient(main.app) as c:
        yield c


def test_full_workflow(client, tmp_path):
    p = client.post("/api/projects", json={"competition_name": "Test Moot", "edition": "2027",
                                           "party": "Applicant"}).json()
    rules = p["rules"]
    assert rules["word_limit"]["total_max"] is None  # nothing invented
    rules["word_limit"] = {"total_max": 9000, "count_footnotes": False, "source": "Rule 5.1"}
    rules["formatting"]["font_family"] = "Times New Roman"
    assert client.put(f"/api/projects/{p['id']}/rules", json=rules).status_code == 200

    path = tmp_path / "memo.docx"
    make(path, GOOD_BODY, GOOD_NOTES)
    with open(path, "rb") as fh:
        d = client.post(f"/api/projects/{p['id']}/documents", files={"file": ("memo.docx", fh)},
                        data={"version_label": "Draft 1"})
    assert d.status_code == 201, d.text
    rid = client.post(f"/api/documents/{d.json()['id']}/reviews").json()["id"]

    report = client.get(f"/api/reports/{rid}").json()
    limit = next(f for f in report["findings"] if f["check"] == "total_words")
    assert limit["status"] == "PASS" and limit["rule_source"] == "Rule 5.1"
    assert report["meta"]["version_label"] == "Draft 1"

    html = client.get(f"/api/reports/{rid}/export")
    assert html.status_code == 200 and "attachment" in html.headers["content-disposition"]
    assert "Memorial compliance report" in html.text and "Rule 5.1" in html.text
    assert client.get(f"/api/reports/{rid}/export?format=json").json()["summary"]["footnotes"] == 5

    detail = client.get(f"/api/projects/{p['id']}").json()
    assert len(detail["documents"]) == 1 and len(detail["reports"]) == 1
    assert client.get("/api/projects").json()[0]["last_summary"]["footnotes"] == 5

    assert client.delete(f"/api/projects/{p['id']}").status_code == 204
    assert client.get(f"/api/reports/{rid}").status_code == 404
    assert not list((tmp_path / "data" / "uploads").iterdir())


def test_upload_validation(client):
    p = client.post("/api/projects", json={"competition_name": "T", "party": "Respondent"}).json()
    url = f"/api/projects/{p['id']}/documents"
    assert client.post(url, files={"file": ("memo.pdf", b"%PDF-1.7")}).status_code == 415
    assert client.post(url, files={"file": ("memo.docx", b"hello")}).status_code == 415
    d = client.post(url, files={"file": ("memo.docx", b"PK broken")})
    assert d.status_code == 201
    assert client.post(f"/api/documents/{d.json()['id']}/reviews").status_code == 422
    assert client.post("/api/projects", json={"competition_name": "T", "party": "Judge"}).status_code == 422


def test_duplicate_section_names_rejected(client):
    p = client.post("/api/projects", json={"competition_name": "T", "party": "Applicant"}).json()
    rules = p["rules"]
    rules["sections"].append(dict(rules["sections"][0]))
    assert client.put(f"/api/projects/{p['id']}/rules", json=rules).status_code == 422
