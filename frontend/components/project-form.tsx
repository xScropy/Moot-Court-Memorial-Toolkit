"use client";

import { useState } from "react";
import type { ProjectInput } from "@/lib/api";

export default function ProjectForm({
  initial,
  submitLabel,
  onSubmit,
  onCancel,
}: {
  initial?: ProjectInput;
  submitLabel: string;
  onSubmit: (value: ProjectInput) => Promise<void>;
  onCancel?: () => void;
}) {
  const [value, setValue] = useState<ProjectInput>(
    initial ?? { competition_name: "", edition: "", team_name: "", party: "Applicant" },
  );
  const [busy, setBusy] = useState(false);
  const set = (patch: Partial<ProjectInput>) => setValue((v) => ({ ...v, ...patch }));

  return (
    <form
      className="grid gap-4 sm:grid-cols-2"
      onSubmit={async (e) => {
        e.preventDefault();
        setBusy(true);
        try {
          await onSubmit(value);
        } finally {
          setBusy(false);
        }
      }}
    >
      <label>
        <span className="label">Competition name</span>
        <input
          className="input"
          required
          maxLength={200}
          value={value.competition_name}
          onChange={(e) => set({ competition_name: e.target.value })}
        />
      </label>
      <label>
        <span className="label">Edition / year</span>
        <input className="input" maxLength={100} value={value.edition} onChange={(e) => set({ edition: e.target.value })} />
      </label>
      <label>
        <span className="label">Team name (optional)</span>
        <input className="input" maxLength={200} value={value.team_name} onChange={(e) => set({ team_name: e.target.value })} />
      </label>
      <fieldset>
        <legend className="label">Party represented</legend>
        <div className="flex gap-2">
          {(["Applicant", "Respondent"] as const).map((p) => (
            <label
              key={p}
              className={`flex-1 cursor-pointer rounded-md border px-3 py-2 text-center text-sm font-medium ${
                value.party === p ? "border-brand bg-brand text-white" : "border-line bg-white"
              }`}
            >
              <input type="radio" name="party" className="sr-only" checked={value.party === p} onChange={() => set({ party: p })} />
              {p}
            </label>
          ))}
        </div>
      </fieldset>
      <div className="flex gap-2 sm:col-span-2">
        <button className="btn" disabled={busy}>
          {busy ? "Saving…" : submitLabel}
        </button>
        {onCancel && (
          <button type="button" className="btn-ghost" onClick={onCancel}>
            Cancel
          </button>
        )}
      </div>
    </form>
  );
}
