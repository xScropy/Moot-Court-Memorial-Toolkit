import { Suspense } from "react";
import ReportView from "@/components/report-view";

export default function ReportPage() {
  return (
    <Suspense fallback={<p className="text-sm text-slate-500">Loading…</p>}>
      <ReportView />
    </Suspense>
  );
}
