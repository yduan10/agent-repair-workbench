import type { Metadata } from "next";
import Workbench from "../../../components/workbench/workbench";

export const metadata: Metadata = {
  title: "调用检查",
  description: "粘贴或导入一次工具调用的证据，检查参数和返回值是否符合工具声明的契约。",
};

export default function WorkbenchPage() {
  return <Workbench />;
}
