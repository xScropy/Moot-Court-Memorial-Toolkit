"use client";

import { useState } from "react";
import type { RuleSet, SectionRule } from "@/lib/api";

const num = (v: string) => (v.trim() === "" || Number.isNaN(Number(v)) ? null : Number(v));

function Num({
  label,
  value,
  onChange,
  step = 1,
  unit,
}: {
  label: string;
  value: number | null;
  onChange: (v: number | null) => void;
  step?: number;
  unit?: string;
}) {
  return (
    <label>
      <span className="label">
        {label}
        {unit && <span className="font-normal normal-case text-slate-500"> ({unit})</span>}
      </span>
      <input
        className="input"
        type="number"
        min={0}
        step={step}
        placeholder="Not checked"
        value={value ?? ""}
        onChange={(e) => onChange(num(e.target.value))}
      />
    </label>
  );
}

function Source({ value, onChange }: { value: string; onChange: (v: string) => void }) {
  return (
    <label className="sm:col-span-2 lg:col-span-4">
      <span className="label">Source in the official rules</span>
      <input
        className="input"
        placeholder="e.g. Rule 6.2, 2027 Official Rules"
        value={value}
        onChange={(e) => onChange(e.target.value)}
      />
    </label>
  );
}

function Check({ label, checked, onChange }: { label: string; checked: boolean; onChange: (v: boolean) => void }) {
  return (
    <label className="flex items-center gap-2 text-sm">
      <input type="checkbox" className="size-4 accent-[#1d3a6b]" checked={checked} onChange={(e) => onChange(e.target.checked)} />
      {label}
    </label>
  );
}

const group = "grid gap-4 sm:grid-cols-2 lg:grid-cols-4";
const legend = "h-serif mb-3 text-lg font-semibold";

export default function RulesEditor({
  initial,
  onSave,
}: {
  initial: RuleSet;
  onSave: (rules: RuleSet) => Promise<void>;
}) {
  const [rules, setRules] = useState(initial);
  const [dirty, setDirty] = useState(false);
  const [state, setState] = useState<"idle" | "saving" | "saved">("idle");

  const update = (patch: Partial<RuleSet>) => {
    setRules((r) => ({ ...r, ...patch }));
    setDirty(true);
    setState("idle");
  };
  const setSection = (i: number, patch: Partial<SectionRule>) =>
    update({ sections: rules.sections.map((s, k) => (k === i ? { ...s, ...patch } : s)) });
  const move = (i: number, d: number) => {
    const next = [...rules.sections];
    [next[i], next[i + d]] = [next[i + d], next[i]];
    update({ sections: next });
  };
  const f = rules.formatting;
  const setF = (patch: Partial<RuleSet["formatting"]>) => update({ formatting: { ...f, ...patch } });

  return (
    <form
      className="space-y-8"
      onSubmit={async (e) => {
        e.preventDefault();
        setState("saving");
        try {
          await onSave(rules);
          setDirty(false);
          setState("saved");
        } catch {
          setState("idle");
        }
      }}
    >
      <p className="rounded-md bg-slate-50 px-3 py-2 text-sm text-slate-700">
        Enter these values from your competition&rsquo;s official rules. Nothing here is pre-filled from any
        competition: the section names are common headings to get you started, and any field left empty is simply
        not checked.
      </p>

      <fieldset>
        <legend className={legend}>Required sections</legend>
        <div className="space-y-3">
          {rules.sections.map((s, i) => (
            <div key={i} className="rounded-md border border-line p-3">
              <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-12">
                <label className="lg:col-span-3">
                  <span className="label">Section name</span>
                  <input className="input" required value={s.name} onChange={(e) => setSection(i, { name: e.target.value })} />
                </label>
                <label className="lg:col-span-4">
                  <span className="label">Also accept these headings</span>
                  <input
                    className="input"
                    placeholder="Comma-separated"
                    value={s.aliases.join(", ")}
                    onChange={(e) => setSection(i, { aliases: e.target.value.split(",").map((a) => a.trimStart()) })}
                  />
                </label>
                <label className="lg:col-span-2">
                  <span className="label">Max words</span>
                  <input
                    className="input"
                    type="number"
                    min={1}
                    placeholder="No limit"
                    value={s.max_words ?? ""}
                    onChange={(e) => setSection(i, { max_words: num(e.target.value) })}
                  />
                </label>
                <label className="lg:col-span-3">
                  <span className="label">Source</span>
                  <input className="input" placeholder="Rule reference" value={s.source} onChange={(e) => setSection(i, { source: e.target.value })} />
                </label>
              </div>
              <div className="mt-3 flex flex-wrap items-center gap-x-5 gap-y-2">
                <Check label="Mandatory" checked={s.required} onChange={(v) => setSection(i, { required: v })} />
                <Check
                  label="Exclude from total word count"
                  checked={s.exclude_from_word_count}
                  onChange={(v) => setSection(i, { exclude_from_word_count: v })}
                />
                <span className="ml-auto flex gap-1">
                  <button type="button" className="btn-ghost px-2" disabled={i === 0} onClick={() => move(i, -1)} aria-label={`Move ${s.name} up`}>
                    ↑
                  </button>
                  <button
                    type="button"
                    className="btn-ghost px-2"
                    disabled={i === rules.sections.length - 1}
                    onClick={() => move(i, 1)}
                    aria-label={`Move ${s.name} down`}
                  >
                    ↓
                  </button>
                  <button
                    type="button"
                    className="btn-ghost text-red-700"
                    onClick={() => update({ sections: rules.sections.filter((_, k) => k !== i) })}
                  >
                    Remove
                  </button>
                </span>
              </div>
            </div>
          ))}
        </div>
        <div className="mt-3 flex flex-wrap items-center gap-4">
          <button
            type="button"
            className="btn-ghost"
            onClick={() =>
              update({
                sections: [
                  ...rules.sections,
                  { name: "", aliases: [], required: true, max_words: null, exclude_from_word_count: false, source: "" },
                ],
              })
            }
          >
            Add section
          </button>
          <Check
            label="Sections must appear in this order"
            checked={rules.enforce_section_order}
            onChange={(v) => update({ enforce_section_order: v })}
          />
        </div>
      </fieldset>

      <fieldset>
        <legend className={legend}>Word and page limits</legend>
        <div className={group}>
          <Num label="Total word limit" value={rules.word_limit.total_max} onChange={(v) => update({ word_limit: { ...rules.word_limit, total_max: v } })} />
          <div className="flex items-end pb-2">
            <Check
              label="Footnotes count towards the limit"
              checked={rules.word_limit.count_footnotes}
              onChange={(v) => update({ word_limit: { ...rules.word_limit, count_footnotes: v } })}
            />
          </div>
          <label className="sm:col-span-2">
            <span className="label">Source for word limit</span>
            <input className="input" placeholder="Rule reference" value={rules.word_limit.source} onChange={(e) => update({ word_limit: { ...rules.word_limit, source: e.target.value } })} />
          </label>
          <Num label="Page limit" value={rules.page_limit.max_pages} onChange={(v) => update({ page_limit: { ...rules.page_limit, max_pages: v } })} />
          <label className="sm:col-span-1 lg:col-span-3">
            <span className="label">Source for page limit</span>
            <input className="input" placeholder="Rule reference" value={rules.page_limit.source} onChange={(e) => update({ page_limit: { ...rules.page_limit, source: e.target.value } })} />
          </label>
        </div>
      </fieldset>

      <fieldset>
        <legend className={legend}>Formatting</legend>
        <div className={group}>
          <label>
            <span className="label">Font</span>
            <input className="input" placeholder="Not checked" value={f.font_family ?? ""} onChange={(e) => setF({ font_family: e.target.value || null })} />
          </label>
          <Num label="Body font size" unit="pt" step={0.5} value={f.font_size_pt} onChange={(v) => setF({ font_size_pt: v })} />
          <Num label="Footnote font size" unit="pt" step={0.5} value={f.footnote_font_size_pt} onChange={(v) => setF({ footnote_font_size_pt: v })} />
          <Num label="Line spacing" unit="lines" step={0.05} value={f.line_spacing} onChange={(v) => setF({ line_spacing: v })} />
          <Num label="Top margin" unit="cm" step={0.01} value={f.margin_top_cm} onChange={(v) => setF({ margin_top_cm: v })} />
          <Num label="Bottom margin" unit="cm" step={0.01} value={f.margin_bottom_cm} onChange={(v) => setF({ margin_bottom_cm: v })} />
          <Num label="Left margin" unit="cm" step={0.01} value={f.margin_left_cm} onChange={(v) => setF({ margin_left_cm: v })} />
          <Num label="Right margin" unit="cm" step={0.01} value={f.margin_right_cm} onChange={(v) => setF({ margin_right_cm: v })} />
          <label>
            <span className="label">Margins are</span>
            <select className="input" value={f.margin_mode} onChange={(e) => setF({ margin_mode: e.target.value as "minimum" | "exact" })}>
              <option value="minimum">A minimum</option>
              <option value="exact">An exact size</option>
            </select>
          </label>
          <div className="flex items-end pb-2">
            <Check label="Page numbers required" checked={f.page_numbers_required} onChange={(v) => setF({ page_numbers_required: v })} />
          </div>
          <p className="self-end pb-2 text-xs text-slate-500 sm:col-span-2">1 inch = 2.54 cm</p>
          <Source value={f.source} onChange={(v) => setF({ source: v })} />
        </div>
      </fieldset>

      <fieldset>
        <legend className={legend}>Citations</legend>
        <div className={group}>
          <label>
            <span className="label">Citation style</span>
            <select
              className="input"
              value={rules.citations.style}
              onChange={(e) => update({ citations: { ...rules.citations, style: e.target.value as RuleSet["citations"]["style"] } })}
            >
              <option value="none">None specified</option>
              <option value="oscola">OSCOLA</option>
              <option value="bluebook">Bluebook</option>
              <option value="other">Other</option>
            </select>
          </label>
          <div className="flex items-end pb-2 lg:col-span-3">
            <Check
              label="Flag footnotes that appear to lack a pinpoint"
              checked={rules.citations.require_pinpoints}
              onChange={(v) => update({ citations: { ...rules.citations, require_pinpoints: v } })}
            />
          </div>
          <Source value={rules.citations.source} onChange={(v) => update({ citations: { ...rules.citations, source: v } })} />
        </div>
      </fieldset>

      <fieldset>
        <legend className={legend}>Special instructions</legend>
        <textarea
          className="input min-h-24"
          placeholder="Anything else from the rules you want printed on the report as a manual reminder, such as anonymity or file-naming requirements."
          value={rules.special_instructions}
          onChange={(e) => update({ special_instructions: e.target.value })}
        />
      </fieldset>

      <div className="sticky bottom-0 -mx-5 -mb-5 flex items-center gap-3 rounded-b-lg border-t border-line bg-white px-5 py-3">
        <button className="btn" disabled={!dirty || state === "saving"}>
          {state === "saving" ? "Saving…" : "Save rules"}
        </button>
        <span className="text-sm text-slate-600" aria-live="polite">
          {dirty ? "Unsaved changes" : state === "saved" ? "Rules saved" : ""}
        </span>
      </div>
    </form>
  );
}
