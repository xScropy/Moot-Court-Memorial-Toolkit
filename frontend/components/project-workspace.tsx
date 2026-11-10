"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useCallback, useEffect, useRef, useState } from "react";
import { api, formatDate, json, type Project, type RuleSet } from "@/lib/api";
import ProjectForm from "./project-form";
import RulesEditor from "./rules-editor";
import { Counts, ErrorNote } from "./ui";

type Tab = "documents" | "rules";

export default function ProjectWorkspace() {
  const id = useSearchParams().get("id");
  const router = useRouter();
  const [project, setProject] = useState<Project | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [tab, setTab] = useState<Tab>("documents");
  const [editing, setEditing] = useState(false);
  const [busy, setBusy] = useState<string | null>(null);
  const [label, setLabel] = useState("");
  const fileRef = useRef<HTMLInputElement>(null);

  const load = useCallback(async () => {
    if (!id) return;
    try {
      setProject(await api<Project>(`/api/projects/${id}`));
    } catch (e) {
      setError((e as Error).message);
    }
  }, [id]);
  useEffect(() => {
    if (!id) return;
    api<Project>(`/api/projects/${id}`)
      .then(setProject)
      .catch((e) => setError(e.message));
  }, [id]);

  const run = async (what: string, fn: () => Promise<void>) => {
    setError(null);
    setBusy(what);
    try {
      await fn();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(null);
    }
  };

  const review = (documentId: string) =>
    run(`review:${documentId}`, async () => {
      const r = await api<{ id: string }>(`/api/documents/${documentId}/reviews`, { method: "POST" });
      router.push(`/report?id=${r.id}`);
    });

  const upload = (e: React.FormEvent) => {
    e.preventDefault();
    const file = fileRef.current?.files?.[0];
    if (!file) return setError("Choose a DOCX file first.");
    run("upload", async () => {
      const body = new FormData();
      body.append("file", file);
      body.append("version_label", label);
      await api(`/api/projects/${id}/documents`, { method: "POST", body });
      setLabel("");
      if (fileRef.current) fileRef.current.value = "";
      await load();
    });
  };

  if (!id) return <ErrorNote message="No project selected." />;
  if (!project) return error ? <ErrorNote message={error} /> : <p className="text-sm text-slate-500">Loading project…</p>;

  const rulesSet =
    project.rules.word_limit.total_max != null ||
    project.rules.page_limit.max_pages != null ||
    Object.entries(project.rules.formatting).some(([k, v]) => k !== "margin_mode" && k !== "source" && v) ||
    project.rules.citations.style !== "none";

  return (
    <div className="space-y-6">
      <div>
        <Link href="/projects" className="text-sm text-brand hover:underline">
          ← All projects
        </Link>
        {editing ? (
          <div className="card mt-3">
            <ProjectForm
              initial={project}
              submitLabel="Save details"
              onCancel={() => setEditing(false)}
              onSubmit={(value) =>
                run("details", async () => {
                  await api(`/api/projects/${project.id}`, json("PUT", value));
                  setEditing(false);
                  await load();
                })
              }
            />
          </div>
        ) : (
          <div className="mt-2 flex flex-wrap items-start justify-between gap-3">
            <div>
              <h1 className="h-serif text-3xl font-semibold">
                {project.competition_name} {project.edition}
              </h1>
              <p className="mt-1 text-slate-600">
                Memorial for the {project.party}
                {project.team_name && ` · ${project.team_name}`}
              </p>
            </div>
            <div className="flex gap-2">
              <button className="btn-ghost" onClick={() => setEditing(true)}>
                Edit details
              </button>
              <button
                className="btn-ghost text-red-700"
                onClick={() => {
                  if (confirm("Delete this project, its uploaded memorials and all reports? This cannot be undone."))
                    run("delete", async () => {
                      await api(`/api/projects/${project.id}`, { method: "DELETE" });
                      router.push("/projects");
                    });
                }}
              >
                Delete
              </button>
            </div>
          </div>
        )}
      </div>

      <ErrorNote message={error} />

      <div role="tablist" className="flex gap-1 border-b border-line">
        {(
          [
            ["documents", "Memorials and reviews"],
            ["rules", "Competition rules"],
          ] as const
        ).map(([key, text]) => (
          <button
            key={key}
            role="tab"
            aria-selected={tab === key}
            onClick={() => setTab(key)}
            className={`-mb-px border-b-2 px-4 py-2 text-sm font-medium ${
              tab === key ? "border-brand text-brand" : "border-transparent text-slate-600 hover:text-ink"
            }`}
          >
            {text}
          </button>
        ))}
      </div>

      {tab === "rules" && (
        <div className="card">
          <RulesEditor
            initial={project.rules}
            onSave={async (rules: RuleSet) => {
              setError(null);
              try {
                await api(`/api/projects/${project.id}/rules`, json("PUT", rules));
                await load();
              } catch (e) {
                setError((e as Error).message);
                throw e;
              }
            }}
          />
        </div>
      )}

      {tab === "documents" && (
        <div className="space-y-6">
          {!rulesSet && (
            <div className="rounded-md border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-900">
              No limits or formatting rules are set yet, so a review will only check sections, headings and
              footnotes.{" "}
              <button className="font-semibold underline" onClick={() => setTab("rules")}>
                Enter your competition rules
              </button>
            </div>
          )}

          <form onSubmit={upload} className="card">
            <h2 className="h-serif text-xl font-semibold">Upload a memorial</h2>
            <p className="mt-1 text-sm text-slate-600">DOCX only, up to 25 MB. Each upload is kept as a separate version.</p>
            <div className="mt-4 grid gap-3 sm:grid-cols-[1fr_1fr_auto] sm:items-end">
              <label>
                <span className="label">File</span>
                <input
                  ref={fileRef}
                  type="file"
                  accept=".docx,application/vnd.openxmlformats-officedocument.wordprocessingml.document"
                  className="input file:mr-3 file:rounded file:border-0 file:bg-slate-100 file:px-3 file:py-1 file:text-sm"
                />
              </label>
              <label>
                <span className="label">Version name (optional)</span>
                <input className="input" placeholder="e.g. Draft 2" maxLength={100} value={label} onChange={(e) => setLabel(e.target.value)} />
              </label>
              <button className="btn" disabled={busy === "upload"}>
                {busy === "upload" ? "Uploading…" : "Upload"}
              </button>
            </div>
          </form>

          <section className="card">
            <h2 className="h-serif text-xl font-semibold">Uploaded memorials</h2>
            {project.documents.length === 0 ? (
              <p className="mt-2 text-sm text-slate-600">Nothing uploaded yet.</p>
            ) : (
              <ul className="mt-3 divide-y divide-line">
                {project.documents.map((d) => {
                  const reports = project.reports.filter((r) => r.document_id === d.id);
                  return (
                    <li key={d.id} className="py-4">
                      <div className="flex flex-wrap items-center justify-between gap-3">
                        <div className="min-w-0">
                          <p className="truncate font-medium">
                            {d.version_label ? `${d.version_label} · ` : ""}
                            {d.filename}
                          </p>
                          <p className="text-xs text-slate-500">
                            Uploaded {formatDate(d.uploaded_at)} · {(d.size_bytes / 1024).toFixed(0)} KB
                          </p>
                        </div>
                        <div className="flex gap-2">
                          <button className="btn" disabled={busy !== null} onClick={() => review(d.id)}>
                            {busy === `review:${d.id}` ? "Checking…" : reports.length ? "Run review again" : "Run review"}
                          </button>
                          <button
                            className="btn-ghost text-red-700"
                            disabled={busy !== null}
                            onClick={() => {
                              if (confirm(`Delete ${d.filename} and its reports?`))
                                run("delete-doc", async () => {
                                  await api(`/api/documents/${d.id}`, { method: "DELETE" });
                                  await load();
                                });
                            }}
                          >
                            Delete
                          </button>
                        </div>
                      </div>
                      {reports.length > 0 && (
                        <ul className="mt-3 space-y-1.5">
                          {reports.map((r, i) => (
                            <li key={r.id}>
                              <Link
                                href={`/report?id=${r.id}`}
                                className="flex flex-wrap items-center gap-x-3 gap-y-1 rounded-md bg-slate-50 px-3 py-2 text-sm hover:bg-slate-100"
                              >
                                <span className="font-medium text-brand">{i === 0 ? "Latest report" : "Earlier report"}</span>
                                <span className="text-xs text-slate-500">{formatDate(r.created_at)}</span>
                                <span className="ml-auto flex items-center gap-2">
                                  <Counts summary={r.summary} />
                                </span>
                              </Link>
                            </li>
                          ))}
                        </ul>
                      )}
                    </li>
                  );
                })}
              </ul>
            )}
          </section>
        </div>
      )}
    </div>
  );
}
