import type { Status, Summary } from "@/lib/api";
import { STATUS_STYLE } from "@/lib/api";

export function Badge({ status, children }: { status: Status; children?: React.ReactNode }) {
  return (
    <span className={`inline-flex items-center rounded px-2 py-0.5 text-xs font-semibold ring-1 ${STATUS_STYLE[status]}`}>
      {children ?? status}
    </span>
  );
}

export function Counts({ summary }: { summary: Summary }) {
  return (
    <span className="flex flex-wrap gap-1.5">
      <Badge status="FAIL">{summary.counts.FAIL} fail</Badge>
      <Badge status="WARNING">{summary.counts.WARNING} warning</Badge>
      <Badge status="PASS">{summary.counts.PASS} pass</Badge>
    </span>
  );
}

export function ErrorNote({ message }: { message: string | null }) {
  if (!message) return null;
  return (
    <p role="alert" className="rounded-md border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-800">
      {message}
    </p>
  );
}
