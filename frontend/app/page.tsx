import Link from "next/link";

const FEATURES = [
  ["Mandatory sections", "Confirms each section your competition requires is present, and in the right order."],
  ["Word and page limits", "Counts words the way Word does, per section and in total, with the exclusions your rules allow."],
  ["Formatting", "Checks font, size, line spacing, margins and page numbering against the values you set."],
  ["Headings", "Finds numbering gaps, mixed numbering styles, skipped levels and headings with nothing beneath them."],
  ["Footnotes", "Extracts every footnote and flags broken cross-references, placeholders and inconsistent forms."],
  ["Downloadable report", "Pass, warning and fail for every requirement, each tied to a place in the document."],
];

export default function Home() {
  return (
    <div className="space-y-12">
      <section className="py-8 text-center">
        <h1 className="h-serif mx-auto max-w-3xl text-4xl font-semibold leading-tight sm:text-5xl">
          Draft smarter. Check better. Submit with confidence.
        </h1>
        <p className="mx-auto mt-5 max-w-2xl text-lg text-slate-600">
          Upload your memorial, enter your competition&rsquo;s rules, and get a compliance report that shows
          exactly what still needs fixing before you submit.
        </p>
        <div className="mt-8 flex flex-wrap justify-center gap-3">
          <Link href="/projects?new=1" className="btn px-6 py-3 text-base">
            Start a new project
          </Link>
          <Link href="/projects" className="btn-ghost px-6 py-3 text-base">
            Open existing projects
          </Link>
        </div>
      </section>

      <section className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {FEATURES.map(([title, text]) => (
          <div key={title} className="card">
            <h2 className="h-serif text-lg font-semibold">{title}</h2>
            <p className="mt-1.5 text-sm text-slate-600">{text}</p>
          </div>
        ))}
      </section>

      <section className="card text-sm text-slate-700">
        <h2 className="h-serif text-lg font-semibold">What this tool does not do</h2>
        <p className="mt-1.5">
          Every check is rule-based and measured from your file; this version uses no AI. It does not ship any
          competition&rsquo;s rules, so you enter them from your official handbook. It does not judge your legal
          arguments, and a correctly formatted citation is never treated as proof that the authority exists or is
          good law.
        </p>
      </section>
    </div>
  );
}
