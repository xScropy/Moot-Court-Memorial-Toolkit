"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useEffect, useState } from "react";
import { api, formatDate, json, type Project, type ProjectListItem } from "@/lib/api";
import ProjectForm from "./project-form";
import { Counts, ErrorNote } from "./ui";

export default function ProjectList() {
  const router = useRouter();
  const [projects, setProjects] = useState<ProjectListItem[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [creating, setCreating] = useState(useSearchParams().get("new") === "1");

  useEffect(() => {
    api<ProjectListItem[]>("/api/projects")
      .then(setProjects)
      .catch((e) => setError(e.message));
  }, []);

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h1 className="h-serif text-3xl font-semibold">Projects</h1>
        {!creating && (
          <button className="btn" onClick={() => setCreating(true)}>
            New project
          </button>
        )}
      </div>
      <ErrorNote message={error} />

      {creating && (
        <div className="card">
          <h2 className="h-serif mb-4 text-xl font-semibold">New memorial project</h2>
          <ProjectForm
            submitLabel="Create project"
            onCancel={() => setCreating(false)}
            onSubmit={async (value) => {
              setError(null);
              try {
                const p = await api<Project>("/api/projects", json("POST", value));
                router.push(`/project?id=${p.id}`);
              } catch (e) {
                setError((e as Error).message);
              }
            }}
          />
        </div>
      )}

      {projects === null && !error && <p className="text-sm text-slate-500">Loading projects…</p>}
      {projects?.length === 0 && !creating && (
        <div className="card text-center text-slate-600">
          <p>No projects yet. Create one to check your first memorial.</p>
        </div>
      )}
      <ul className="grid gap-4 md:grid-cols-2">
        {projects?.map((p) => (
          <li key={p.id}>
            <Link href={`/project?id=${p.id}`} className="card block transition hover:border-brand">
              <div className="flex items-start justify-between gap-3">
                <div>
                  <h2 className="h-serif text-lg font-semibold">
                    {p.competition_name} {p.edition}
                  </h2>
                  <p className="text-sm text-slate-600">
                    {p.party}
                    {p.team_name && ` · ${p.team_name}`} · {p.document_count} document{p.document_count === 1 ? "" : "s"}
                  </p>
                </div>
                {p.last_summary?.score != null && (
                  <span className="text-right">
                    <span className="block text-2xl font-semibold tabular-nums">{p.last_summary.score}%</span>
                    <span className="block text-[11px] uppercase tracking-wide text-slate-500">compliance</span>
                  </span>
                )}
              </div>
              <div className="mt-3 text-sm">
                {p.last_summary && p.last_review_at ? (
                  <div className="flex flex-wrap items-center gap-2">
                    <Counts summary={p.last_summary} />
                    <span className="text-xs text-slate-500">Last review {formatDate(p.last_review_at)}</span>
                  </div>
                ) : (
                  <span className="text-slate-500">No review run yet</span>
                )}
              </div>
            </Link>
          </li>
        ))}
      </ul>
    </div>
  );
}
