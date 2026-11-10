"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { useEffect, useMemo, useRef, useState } from "react";
import { API_URL, api, formatDate, type Finding, type FindingLocation, type Report, type Status } from "@/lib/api";
import { Badge, ErrorNote } from "./ui";

const GROUPS: [Status, string, string][] = [
  ["FAIL", "Critical issues", "Requirements that are not met. Resolve these before submitting."],
  ["WARNING", "Warnings", "Possible problems that need your judgement."],
  ["PASS", "Passed requirements", ""],
];
const CATEGORY: Record<Finding["category"], string> = {
  structure: "Structure",
  limits: "Limits",
  formatting: "Formatting",
  headings: "Headings",
  citations: "Citations",
};
type Tab = "issues" | "footnotes" | "words";

function where(l: FindingLocation) {
  const bits = [];
  if (l.section) bits.push(l.section);
  if (l.footnote) bits.push(`footnote ${l.footnote}`);
  else if (l.paragraph != null) bits.push(`paragraph ${l.paragraph + 1}`);
  return bits.join(", ");
}

function Stat({ label, value, sub, tone }: { label: string; value: string; sub?: string; tone?: "bad" | "ok" }) {
  return (
    <div className="card p-4">
      <p className="label mb-0">{label}</p>
      <p className={`mt-1 text-2xl font-semibold tabular-nums ${tone === "bad" ? "text-red-700" : ""}`}>{value}</p>
      {sub && <p className="text-xs text-slate-500">{sub}</p>}
    </div>
  );
}

export default function ReportView() {
  const id = useSearchParams().get("id");
  const [report, setReport] = useState<Report | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [tab, setTab] = useState<Tab>("issues");
  const [category, setCategory] = useState<Finding["category"] | "all">("all");
  const [active, setActive] = useState<number | null>(null);
  const [showPassed, setShowPassed] = useState(false);
  const pane = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!id) return;
    api<Report>(`/api/reports/${id}`)
      .then(setReport)
      .catch((e) => setError(e.message));
  }, [id]);

  const flaggedNotes = useMemo(() => {
    const map = new Map<number, Status>();
    for (const f of report?.findings ?? [])
      if (f.status !== "PASS")
        for (const l of f.locations)
          if (l.footnote && map.get(l.footnote) !== "FAIL") map.set(l.footnote, f.status);
    return map;
  }, [report]);

  const goTo = (paragraph: number | null) => {
    if (paragraph == null || !report) return;
    // the preview only holds non-empty paragraphs; fall forward to the nearest one
    const target = report.document.paragraphs.find((p) => p.i >= paragraph);
    if (!target) return;
    setActive(target.i);
    requestAnimationFrame(() => {
      const el = pane.current?.querySelector(`[data-p="${target.i}"]`);
      el?.scrollIntoView({ block: "center", behavior: "smooth" });
    });
  };

  if (!id) return <ErrorNote message="No report selected." />;
  if (!report) return error ? <ErrorNote message={error} /> : <p className="text-sm text-slate-500">Loading report…</p>;

  const s = report.summary;
  const findings = report.findings.filter((f) => category === "all" || f.category === category);
  const ready = s.counts.FAIL === 0;

  return (
    <div className="space-y-6">
      <div>
        <Link href={`/project?id=${report.project_id}`} className="text-sm text-brand hover:underline">
          ← {report.meta.competition_name} {report.meta.edition}
        </Link>
        <div className="mt-2 flex flex-wrap items-start justify-between gap-3">
          <div className="min-w-0">
            <h1 className="h-serif text-3xl font-semibold">Compliance report</h1>
            <p className="mt-1 truncate text-slate-600">
              {report.meta.version_label && `${report.meta.version_label} · `}
              {report.meta.filename} · {report.meta.party} · reviewed {formatDate(report.generated_at)}
            </p>
          </div>
          <div className="flex gap-2">
            <a className="btn" href={`${API_URL}/api/reports/${report.id}/export?format=html`}>
              Download report
            </a>
            <a className="btn-ghost py-2" href={`${API_URL}/api/reports/${report.id}/export?format=json`}>
              JSON
            </a>
          </div>
        </div>
      </div>

      <div
        className={`rounded-md border px-4 py-3 text-sm ${
          ready ? "border-emerald-200 bg-emerald-50 text-emerald-900" : "border-red-200 bg-red-50 text-red-900"
        }`}
      >
        {ready ? (
          <>
            <strong>No failed requirements.</strong>{" "}
            {s.counts.WARNING > 0 && `${s.counts.WARNING} warning${s.counts.WARNING === 1 ? "" : "s"} still need your review. `}
            Check the items this report does not cover before you submit.
          </>
        ) : (
          <>
            <strong>
              {s.counts.FAIL} requirement{s.counts.FAIL === 1 ? "" : "s"} not met.
            </strong>{" "}
            Fix the critical issues below, upload the revised memorial and run the review again.
          </>
        )}
      </div>

      <div className="grid grid-cols-2 gap-3 lg:grid-cols-5">
        <Stat label="Compliance indicator" value={s.score == null ? "–" : `${s.score}%`} sub="Not a prediction of results" />
        <Stat
          label="Words counted"
          value={s.words.counted.toLocaleString()}
          sub={s.words.limit ? `Limit ${s.words.limit.toLocaleString()}` : "No limit set"}
          tone={s.words.limit && s.words.counted > s.words.limit ? "bad" : undefined}
        />
        <Stat
          label="Pages"
          value={s.pages.stored?.toString() ?? "Unknown"}
          sub={s.pages.limit ? `Limit ${s.pages.limit} · as last saved` : "As last saved in Word"}
          tone={s.pages.limit && s.pages.stored && s.pages.stored > s.pages.limit ? "bad" : undefined}
        />
        <Stat label="Footnotes" value={s.footnotes.toString()} sub={`${s.words.notes.toLocaleString()} words`} />
        <div className="card col-span-2 flex flex-col justify-center gap-1.5 p-4 lg:col-span-1">
          <Badge status="FAIL">{s.counts.FAIL} critical</Badge>
          <Badge status="WARNING">{s.counts.WARNING} warnings</Badge>
          <Badge status="PASS">{s.counts.PASS} passed</Badge>
        </div>
      </div>

      <div role="tablist" className="flex gap-1 overflow-x-auto border-b border-line">
        {(
          [
            ["issues", "Checklist"],
            ["footnotes", `Footnotes (${report.footnotes.length})`],
            ["words", "Word count by section"],
          ] as const
        ).map(([key, text]) => (
          <button
            key={key}
            role="tab"
            aria-selected={tab === key}
            onClick={() => setTab(key)}
            className={`-mb-px whitespace-nowrap border-b-2 px-4 py-2 text-sm font-medium ${
              tab === key ? "border-brand text-brand" : "border-transparent text-slate-600 hover:text-ink"
            }`}
          >
            {text}
          </button>
        ))}
      </div>

      <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_minmax(0,26rem)]">
        <div className="min-w-0 space-y-6">
          {tab === "issues" && (
            <>
              <div className="flex flex-wrap gap-1.5">
                {(["all", ...Object.keys(CATEGORY)] as (Finding["category"] | "all")[]).map((c) => {
                  const open = report.findings.filter((f) => (c === "all" || f.category === c) && f.status !== "PASS").length;
                  return (
                    <button
                      key={c}
                      onClick={() => setCategory(c)}
                      className={`rounded-full border px-3 py-1 text-xs font-medium ${
                        category === c ? "border-brand bg-brand text-white" : "border-line bg-white hover:bg-slate-50"
                      }`}
                    >
                      {c === "all" ? "All" : CATEGORY[c]}
                      {open > 0 && <span className="ml-1.5 opacity-80">{open}</span>}
                    </button>
                  );
                })}
              </div>

              {GROUPS.map(([status, title, hint]) => {
                const items = findings.filter((f) => f.status === status);
                const collapsed = status === "PASS" && !showPassed;
                return (
                  <section key={status}>
                    <div className="flex items-baseline justify-between gap-3">
                      <h2 className="h-serif text-xl font-semibold">
                        {title} <span className="text-slate-500">({items.length})</span>
                      </h2>
                      {status === "PASS" && items.length > 0 && (
                        <button className="text-sm text-brand hover:underline" onClick={() => setShowPassed((v) => !v)}>
                          {showPassed ? "Hide" : "Show"}
                        </button>
                      )}
                    </div>
                    {hint && items.length > 0 && <p className="text-sm text-slate-600">{hint}</p>}
                    {items.length === 0 && <p className="mt-1 text-sm text-slate-500">None.</p>}
                    {!collapsed && (
                      <ul className="mt-3 space-y-3">
                        {items.map((f, i) => (
                          <li key={`${f.check}-${i}`} className="card p-4">
                            <div className="flex flex-wrap items-center gap-2">
                              <Badge status={f.status} />
                              <span className="text-xs font-medium uppercase tracking-wide text-slate-500">{CATEGORY[f.category]}</span>
                              {f.basis === "heuristic" ? (
                                <span className="rounded bg-slate-100 px-1.5 py-0.5 text-xs text-slate-700" title="Found by pattern matching, not measured from the file. Confirm before acting.">
                                  Pattern-based flag
                                </span>
                              ) : (
                                f.manual_check && <span className="rounded bg-slate-100 px-1.5 py-0.5 text-xs text-slate-700">Verify manually</span>
                              )}
                            </div>
                            <p className="mt-2 font-medium">{f.title}</p>
                            {f.detail && <p className="mt-1 text-sm text-slate-700">{f.detail}</p>}
                            {f.rule_source && <p className="mt-1 text-xs text-slate-500">Rule source: {f.rule_source}</p>}
                            {f.locations.length > 0 && (
                              <ul className="mt-2 space-y-1">
                                {f.locations.map((l, k) => (
                                  <li key={k}>
                                    <button
                                      onClick={() => goTo(l.paragraph)}
                                      disabled={l.paragraph == null}
                                      className="w-full rounded px-2 py-1 text-left text-sm hover:bg-slate-50 disabled:hover:bg-transparent"
                                    >
                                      <span className="font-medium text-brand">{where(l) || "Document"}</span>
                                      {l.excerpt && <span className="text-slate-600"> — {l.excerpt}</span>}
                                    </button>
                                  </li>
                                ))}
                              </ul>
                            )}
                          </li>
                        ))}
                      </ul>
                    )}
                  </section>
                );
              })}

              <section className="card bg-slate-50 text-sm text-slate-700">
                <h2 className="h-serif text-lg font-semibold">Not covered by this report</h2>
                <ul className="mt-2 list-disc space-y-1 pl-5">
                  {report.not_checked.map((x) => (
                    <li key={x}>{x}</li>
                  ))}
                </ul>
                {report.meta.special_instructions && (
                  <>
                    <h3 className="mt-4 font-semibold">Your special instructions (check manually)</h3>
                    <p className="mt-1 whitespace-pre-wrap">{report.meta.special_instructions}</p>
                  </>
                )}
                <p className="mt-4 text-xs text-slate-500">{report.score_note}</p>
              </section>
            </>
          )}

          {tab === "footnotes" &&
            (report.footnotes.length === 0 ? (
              <p className="text-sm text-slate-600">No footnotes or endnotes were found in this document.</p>
            ) : (
              <ol className="card divide-y divide-line p-0">
                {report.footnotes.map((n) => {
                  const flag = n.kind === "footnote" ? flaggedNotes.get(n.number) : undefined;
                  return (
                    <li key={`${n.kind}-${n.number}`}>
                      <button onClick={() => goTo(n.paragraph)} className="flex w-full gap-3 px-4 py-2.5 text-left text-sm hover:bg-slate-50">
                        <span className="w-8 shrink-0 text-right font-semibold tabular-nums text-slate-500">
                          {n.kind === "endnote" ? "e" : ""}
                          {n.number}
                        </span>
                        <span className="min-w-0 flex-1 break-words">{n.text || <em className="text-slate-500">Empty</em>}</span>
                        {flag && <Badge status={flag}>{flag === "FAIL" ? "Issue" : "Check"}</Badge>}
                      </button>
                    </li>
                  );
                })}
              </ol>
            ))}

          {tab === "words" && (
            <div className="card overflow-x-auto p-0">
              <table className="w-full text-sm">
                <thead className="bg-slate-50 text-left text-xs uppercase tracking-wide text-slate-600">
                  <tr>
                    <th className="px-4 py-2">Section</th>
                    <th className="px-4 py-2 text-right">Words</th>
                    <th className="px-4 py-2 text-right">Footnote words</th>
                    <th className="px-4 py-2 text-right">Limit</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-line">
                  {report.sections.map((sec, i) => (
                    <tr key={i} className="cursor-pointer hover:bg-slate-50" onClick={() => goTo(sec.paragraph)}>
                      <td className="px-4 py-2">
                        {sec.name}
                        {sec.excluded && <span className="ml-2 text-xs text-slate-500">excluded from total</span>}
                        {!sec.configured && sec.name !== "(Front matter)" && (
                          <span className="ml-2 text-xs text-slate-500">not in your rules</span>
                        )}
                      </td>
                      <td className={`px-4 py-2 text-right tabular-nums ${sec.limit && sec.words > sec.limit ? "font-semibold text-red-700" : ""}`}>
                        {sec.words.toLocaleString()}
                      </td>
                      <td className="px-4 py-2 text-right tabular-nums">{sec.footnote_words.toLocaleString()}</td>
                      <td className="px-4 py-2 text-right tabular-nums">{sec.limit?.toLocaleString() ?? "—"}</td>
                    </tr>
                  ))}
                </tbody>
                <tfoot className="bg-slate-50 font-semibold">
                  <tr>
                    <td className="px-4 py-2">All text</td>
                    <td className="px-4 py-2 text-right tabular-nums">{s.words.body.toLocaleString()}</td>
                    <td className="px-4 py-2 text-right tabular-nums">{s.words.notes.toLocaleString()}</td>
                    <td className="px-4 py-2 text-right tabular-nums">{s.words.limit?.toLocaleString() ?? "—"}</td>
                  </tr>
                </tfoot>
              </table>
            </div>
          )}
        </div>

        <aside className="lg:sticky lg:top-4 lg:self-start">
          <div className="card p-0">
            <div className="border-b border-line px-4 py-2.5">
              <h2 className="text-sm font-semibold">Document text</h2>
              <p className="text-xs text-slate-500">Select a location in the report to jump to it. Layout is not reproduced.</p>
            </div>
            <div ref={pane} className="h-[32rem] overflow-y-auto px-4 py-3 font-serif text-sm leading-relaxed lg:h-[calc(100vh-9rem)]">
              {report.document.paragraphs.map((p) => (
                <p
                  key={p.i}
                  data-p={p.i}
                  className={`-mx-2 mb-2 break-words rounded px-2 py-0.5 ${p.level ? "mt-4 font-semibold" : ""} ${
                    active === p.i ? "bg-amber-100 ring-1 ring-amber-300" : ""
                  }`}
                >
                  {p.text}
                </p>
              ))}
            </div>
          </div>
        </aside>
      </div>
    </div>
  );
}
