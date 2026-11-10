"""HTTP API for the Moot Court Memorial Toolkit."""

from __future__ import annotations

import json
import os
import re
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse

from . import db
from .analysis.docx_parser import InvalidDocument
from .analysis.report import build_report, render_html
from .schemas import ProjectCreate, RuleSet, SectionRule

MAX_UPLOAD_BYTES = 25 * 1024 * 1024


@asynccontextmanager
async def lifespan(_: FastAPI):
    db.init()
    yield


app = FastAPI(title="Moot Court Memorial Toolkit", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=os.environ.get("MCMT_CORS_ORIGINS", "http://localhost:3000").split(","),
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["Content-Disposition"],
)


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def starter_rules() -> RuleSet:
    """A blank starting point. Section names are common memorial headings so
    the user has something to edit; no limits or formatting values are
    pre-filled because those must come from the competition's own rules."""
    names = [
        ("Cover Page", ["Title Page"]),
        ("Table of Contents", ["Contents"]),
        ("Index of Authorities", ["Table of Authorities", "List of Authorities"]),
        ("Statement of Jurisdiction", []),
        ("Statement of Facts", []),
        ("Summary of Pleadings", ["Summary of Arguments", "Summary of Argument"]),
        ("Pleadings", ["Arguments", "Arguments Advanced", "Legal Arguments", "Written Pleadings"]),
        ("Prayer for Relief", ["Prayer", "Conclusion", "Submissions"]),
    ]
    return RuleSet(sections=[SectionRule(name=n, aliases=a) for n, a in names])


def _project(conn, project_id: str):
    row = conn.execute("SELECT * FROM projects WHERE id = ?", (project_id,)).fetchone()
    if row is None:
        raise HTTPException(404, "Project not found")
    return row


def _project_json(row) -> dict:
    d = dict(row)
    d["rules"] = json.loads(d["rules"])
    return d


def _doc_json(row) -> dict:
    d = dict(row)
    d.pop("stored_name", None)
    return d


@app.get("/api/health")
def health():
    return {"status": "ok"}


@app.get("/api/rules/starter")
def get_starter_rules() -> RuleSet:
    return starter_rules()


@app.get("/api/projects")
def list_projects():
    with db.connect() as conn:
        rows = conn.execute(
            """SELECT p.*,
                      (SELECT COUNT(*) FROM documents d WHERE d.project_id = p.id) AS document_count,
                      (SELECT summary FROM reports r WHERE r.project_id = p.id
                        ORDER BY r.created_at DESC, r.rowid DESC LIMIT 1) AS last_summary,
                      (SELECT created_at FROM reports r WHERE r.project_id = p.id
                        ORDER BY r.created_at DESC, r.rowid DESC LIMIT 1) AS last_review_at
               FROM projects p ORDER BY p.created_at DESC, p.rowid DESC"""
        ).fetchall()
    out = []
    for r in rows:
        d = dict(r)
        d.pop("rules")
        d["last_summary"] = json.loads(d["last_summary"]) if d["last_summary"] else None
        out.append(d)
    return out


@app.post("/api/projects", status_code=201)
def create_project(body: ProjectCreate):
    pid = uuid.uuid4().hex
    with db.connect() as conn:
        conn.execute(
            "INSERT INTO projects VALUES (?, ?, ?, ?, ?, ?, ?)",
            (pid, body.competition_name.strip(), body.edition.strip(), body.team_name.strip(), body.party,
             starter_rules().model_dump_json(), now()),
        )
        return _project_json(_project(conn, pid))


@app.get("/api/projects/{project_id}")
def get_project(project_id: str):
    with db.connect() as conn:
        project = _project_json(_project(conn, project_id))
        docs = conn.execute(
            "SELECT * FROM documents WHERE project_id = ? ORDER BY uploaded_at DESC, rowid DESC", (project_id,)
        ).fetchall()
        reports = conn.execute(
            "SELECT id, document_id, created_at, summary FROM reports WHERE project_id = ? "
            "ORDER BY created_at DESC, rowid DESC",
            (project_id,),
        ).fetchall()
    project["documents"] = [_doc_json(d) for d in docs]
    project["reports"] = [{**dict(r), "summary": json.loads(r["summary"])} for r in reports]
    return project


@app.put("/api/projects/{project_id}")
def update_project(project_id: str, body: ProjectCreate):
    with db.connect() as conn:
        _project(conn, project_id)
        conn.execute(
            "UPDATE projects SET competition_name = ?, edition = ?, team_name = ?, party = ? WHERE id = ?",
            (body.competition_name.strip(), body.edition.strip(), body.team_name.strip(), body.party, project_id),
        )
        return _project_json(_project(conn, project_id))


@app.put("/api/projects/{project_id}/rules")
def update_rules(project_id: str, rules: RuleSet):
    names = [s.name.strip().casefold() for s in rules.sections]
    if any(not n for n in names):
        raise HTTPException(422, "Every section needs a name.")
    if len(set(names)) != len(names):
        raise HTTPException(422, "Section names must be unique.")
    with db.connect() as conn:
        _project(conn, project_id)
        conn.execute("UPDATE projects SET rules = ? WHERE id = ?", (rules.model_dump_json(), project_id))
    return rules


def _remove_files(stored_names):
    for name in stored_names:
        try:
            (db.uploads_dir() / name).unlink(missing_ok=True)
        except OSError:
            pass


@app.delete("/api/projects/{project_id}", status_code=204)
def delete_project(project_id: str):
    with db.connect() as conn:
        _project(conn, project_id)
        names = [r["stored_name"] for r in
                 conn.execute("SELECT stored_name FROM documents WHERE project_id = ?", (project_id,))]
        conn.execute("DELETE FROM projects WHERE id = ?", (project_id,))
    _remove_files(names)


@app.post("/api/projects/{project_id}/documents", status_code=201)
async def upload_document(project_id: str, file: UploadFile = File(...), version_label: str = Form("")):
    filename = os.path.basename(file.filename or "memorial.docx")
    filename = re.sub(r"[\x00-\x1f]", "", filename)[:200] or "memorial.docx"
    if not filename.lower().endswith(".docx"):
        raise HTTPException(415, "Only DOCX files are supported in this version. Save the memorial as .docx.")
    data = await file.read(MAX_UPLOAD_BYTES + 1)
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(413, "The file is larger than 25 MB.")
    if not data.startswith(b"PK"):
        raise HTTPException(415, "The file is not a valid DOCX document.")
    did = uuid.uuid4().hex
    stored = f"{did}.docx"
    with db.connect() as conn:
        _project(conn, project_id)
        (db.uploads_dir() / stored).write_bytes(data)
        conn.execute(
            "INSERT INTO documents VALUES (?, ?, ?, ?, ?, ?, ?)",
            (did, project_id, filename, version_label.strip()[:100], stored, len(data), now()),
        )
        return _doc_json(conn.execute("SELECT * FROM documents WHERE id = ?", (did,)).fetchone())


@app.delete("/api/documents/{document_id}", status_code=204)
def delete_document(document_id: str):
    with db.connect() as conn:
        row = conn.execute("SELECT stored_name FROM documents WHERE id = ?", (document_id,)).fetchone()
        if row is None:
            raise HTTPException(404, "Document not found")
        conn.execute("DELETE FROM documents WHERE id = ?", (document_id,))
    _remove_files([row["stored_name"]])


@app.post("/api/documents/{document_id}/reviews", status_code=201)
def run_review(document_id: str):
    with db.connect() as conn:
        doc = conn.execute("SELECT * FROM documents WHERE id = ?", (document_id,)).fetchone()
        if doc is None:
            raise HTTPException(404, "Document not found")
        project = _project(conn, doc["project_id"])
    rules = RuleSet.model_validate_json(project["rules"])
    try:
        result = build_report(str(db.uploads_dir() / doc["stored_name"]), rules)
    except InvalidDocument as exc:
        raise HTTPException(422, str(exc))
    rid = uuid.uuid4().hex
    with db.connect() as conn:
        conn.execute(
            "INSERT INTO reports VALUES (?, ?, ?, ?, ?, ?, ?)",
            (rid, document_id, doc["project_id"], result["generated_at"], rules.model_dump_json(),
             json.dumps(result["summary"]), json.dumps(result)),
        )
    return {"id": rid}


def _load_report(report_id: str) -> dict:
    with db.connect() as conn:
        row = conn.execute(
            """SELECT r.*, d.filename, d.version_label, p.competition_name, p.edition, p.team_name, p.party
               FROM reports r JOIN documents d ON d.id = r.document_id JOIN projects p ON p.id = r.project_id
               WHERE r.id = ?""",
            (report_id,),
        ).fetchone()
    if row is None:
        raise HTTPException(404, "Report not found")
    rules = json.loads(row["rules"])
    meta = {k: row[k] for k in ("filename", "version_label", "competition_name", "edition", "team_name", "party")}
    meta["special_instructions"] = rules.get("special_instructions", "")
    return {
        "id": row["id"],
        "project_id": row["project_id"],
        "document_id": row["document_id"],
        "meta": meta,
        "rules": rules,
        **json.loads(row["result"]),
    }


@app.get("/api/reports/{report_id}")
def get_report(report_id: str):
    return _load_report(report_id)


@app.get("/api/reports/{report_id}/export")
def export_report(report_id: str, format: str = "html"):
    report = _load_report(report_id)
    stem = re.sub(r"[^A-Za-z0-9._-]+", "_", report["meta"]["filename"].rsplit(".", 1)[0]) or "memorial"
    if format == "json":
        report.pop("document", None)
        return JSONResponse(
            report, headers={"Content-Disposition": f'attachment; filename="{stem}-compliance-report.json"'}
        )
    if format != "html":
        raise HTTPException(400, "format must be html or json")
    return HTMLResponse(
        render_html(report, report["meta"]),
        headers={"Content-Disposition": f'attachment; filename="{stem}-compliance-report.html"'},
    )
