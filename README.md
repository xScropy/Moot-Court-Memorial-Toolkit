# Moot Court Memorial Toolkit

*Draft smarter. Check better. Submit with confidence.*

Upload a moot court memorial (DOCX), enter your competition's rules, and get a
PASS / WARNING / FAIL compliance report tied to locations in the document.

This is the MVP described in the product requirements. Every check is
rule-based; no AI model is used.

## What it checks

| Area | Checks |
| --- | --- |
| Structure | Each configured section is present (with aliases), duplicates, section order |
| Limits | Total words, words per section, excluded sections, footnotes in or out, page limit |
| Formatting | Font, body and footnote font size, line spacing, margins, page numbering |
| Headings | Numbering gaps, mixed numbering styles, skipped levels, empty headings, capitalisation |
| Footnotes | Extraction, empty notes, placeholders, broken cross-references, short-form and format consistency, optional pinpoint flag |

Findings measured from the file are separated from pattern-based flags, which
are labelled and always need a person to confirm.

### Deliberate limits

- **No competition rules are shipped.** New projects start with common section
  headings only; limits and formatting values must be entered from the official
  rules, each with an optional source reference that is shown on the report.
- **Citation checks are about form only.** Nothing here verifies that an
  authority exists, is current, or is good law.
- **Page count** is the figure Word stored at last save, because a DOCX has no
  fixed pages. It is always marked for manual verification.
- **Not built yet:** accounts and access control, PDF upload, handbook upload
  with AI extraction, Index of Authorities generation, AI argument and language
  review, version comparison. Without authentication, run this locally or on a
  trusted network only.

## Run it

Backend (Python 3.11+):

```bash
cd backend
pip install -r requirements-dev.txt
uvicorn app.main:app --reload --port 8000
pytest                      # run the tests
```

Frontend (Node 20+):

```bash
cd frontend
npm install
npm run dev                 # http://localhost:3000
```

Configuration:

| Variable | Where | Default |
| --- | --- | --- |
| `NEXT_PUBLIC_API_URL` | frontend | `http://localhost:8000` |
| `MCMT_CORS_ORIGINS` | backend | `http://localhost:3000` (comma-separated) |
| `MCMT_DATA_DIR` | backend | `backend/data` (SQLite database and uploads) |

Deleting a project or document removes its uploaded files and reports.

## Layout

```
backend/app/analysis/docx_parser.py   DOCX -> paragraphs, headings, footnotes, formatting
backend/app/analysis/checks.py        the compliance checks
backend/app/analysis/report.py        report assembly and HTML export
backend/app/main.py                   FastAPI routes
frontend/app, frontend/components     Next.js pages: landing, projects, workspace, report
```

Storage is SQLite and local disk to keep the MVP runnable without
infrastructure; the PRD's PostgreSQL / Supabase stack is the intended next step
along with authentication.
