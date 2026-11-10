import { Suspense } from "react";
import ProjectList from "@/components/project-list";

export default function ProjectsPage() {
  return (
    <Suspense fallback={<p className="text-sm text-slate-500">Loading…</p>}>
      <ProjectList />
    </Suspense>
  );
}
