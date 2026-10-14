import { notFound } from "next/navigation";
import AnalysisHistory from "../../../components/analysis-history";
import RunHistory from "../../../components/run-history";
import ModulePreview from "../../../components/module-preview";
import { modules, ModuleKey } from "../../../lib/modules";

export function generateStaticParams() {
  return Object.keys(modules).map((section) => ({ section }));
}
export default async function ModulePage({
  params,
}: {
  params: Promise<{ section: string }>;
}) {
  const { section } = await params;
  if (!Object.hasOwn(modules, section)) notFound();
  if (section === "diagnosis") return <AnalysisHistory />;
  if (section === "tasks") return <RunHistory />;
  return <ModulePreview section={section as ModuleKey} />;
}
