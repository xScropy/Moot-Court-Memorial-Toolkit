import { Suspense } from "react";
import ProjectWorkspace from "@/components/project-workspace";

export default function ProjectPage() {
  return (
    <Suspense fallback={<p className="text-sm text-slate-500">Loading…</p>}>
      <ProjectWorkspace />
    </Suspense>
  );
}
