export const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export type Status = "PASS" | "WARNING" | "FAIL";
export type Party = "Applicant" | "Respondent";

export interface SectionRule {
  name: string;
  aliases: string[];
  required: boolean;
  max_words: number | null;
  exclude_from_word_count: boolean;
  source: string;
}

export interface RuleSet {
  sections: SectionRule[];
  enforce_section_order: boolean;
  word_limit: { total_max: number | null; count_footnotes: boolean; source: string };
  page_limit: { max_pages: number | null; source: string };
  formatting: {
    font_family: string | null;
    font_size_pt: number | null;
    footnote_font_size_pt: number | null;
    line_spacing: number | null;
    margin_top_cm: number | null;
    margin_bottom_cm: number | null;
    margin_left_cm: number | null;
    margin_right_cm: number | null;
    margin_mode: "minimum" | "exact";
    page_numbers_required: boolean;
    source: string;
  };
  citations: { style: "none" | "oscola" | "bluebook" | "other"; require_pinpoints: boolean; source: string };
  special_instructions: string;
}

export interface Summary {
  score: number | null;
  counts: Record<Status, number>;
  words: { body: number; notes: number; counted: number; limit: number | null };
  pages: { stored: number | null; limit: number | null };
  footnotes: number;
  endnotes: number;
}

export interface ProjectInput {
  competition_name: string;
  edition: string;
  team_name: string;
  party: Party;
}

export interface ProjectListItem extends ProjectInput {
  id: string;
  created_at: string;
  document_count: number;
  last_summary: Summary | null;
  last_review_at: string | null;
}

export interface DocumentItem {
  id: string;
  filename: string;
  version_label: string;
  size_bytes: number;
  uploaded_at: string;
}

export interface ReportListItem {
  id: string;
  document_id: string;
  created_at: string;
  summary: Summary;
}

export interface Project extends ProjectInput {
  id: string;
  created_at: string;
  rules: RuleSet;
  documents: DocumentItem[];
  reports: ReportListItem[];
}

export interface FindingLocation {
  section: string | null;
  paragraph: number | null;
  footnote: number | null;
  excerpt: string | null;
}

export interface Finding {
  category: "structure" | "limits" | "formatting" | "headings" | "citations";
  check: string;
  status: Status;
  title: string;
  detail: string;
  basis: "deterministic" | "heuristic";
  manual_check: boolean;
  rule_source: string;
  locations: FindingLocation[];
}

export interface Report {
  id: string;
  project_id: string;
  document_id: string;
  generated_at: string;
  meta: ProjectInput & { filename: string; version_label: string; special_instructions: string };
  summary: Summary;
  findings: Finding[];
  sections: {
    name: string;
    configured: boolean;
    excluded: boolean;
    paragraph: number;
    words: number;
    footnote_words: number;
    limit: number | null;
  }[];
  footnotes: {
    number: number;
    kind: "footnote" | "endnote";
    text: string;
    words: number;
    paragraph: number | null;
    section: string | null;
  }[];
  document: { paragraphs: { i: number; text: string; level: number | null }[] };
  not_checked: string[];
  score_note: string;
}

export async function api<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response;
  try {
    res = await fetch(`${API_URL}${path}`, init);
  } catch {
    throw new Error(`Cannot reach the analysis service at ${API_URL}. Is the backend running?`);
  }
  if (!res.ok) {
    let message = `Request failed (${res.status})`;
    try {
      const body = await res.json();
      if (typeof body.detail === "string") message = body.detail;
      else if (Array.isArray(body.detail) && body.detail[0]?.msg)
        message = body.detail.map((d: { msg: string }) => d.msg).join("; ");
    } catch {}
    throw new Error(message);
  }
  return res.status === 204 ? (undefined as T) : res.json();
}

export const json = (method: string, body: unknown): RequestInit => ({
  method,
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify(body),
});

export const formatDate = (iso: string) =>
  new Date(iso).toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" });

export const STATUS_STYLE: Record<Status, string> = {
  FAIL: "bg-red-50 text-red-800 ring-red-200",
  WARNING: "bg-amber-50 text-amber-800 ring-amber-200",
  PASS: "bg-emerald-50 text-emerald-800 ring-emerald-200",
};
