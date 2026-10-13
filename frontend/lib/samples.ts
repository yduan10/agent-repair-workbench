import passing from "../../examples/passing.json";
import failing from "../../examples/failing.json";

const { result: _result, ...missing } = passing;
export const samples = [
  {
    id: "type",
    label: "结果类型不符",
    description: "返回值与契约不一致",
    value: JSON.stringify(failing, null, 2),
  },
  {
    id: "pass",
    label: "正常调用",
    description: "参数与结果均符合声明",
    value: JSON.stringify(passing, null, 2),
  },
  {
    id: "missing",
    label: "缺失结果",
    description: "信息不足，保持拒判",
    value: JSON.stringify(missing, null, 2),
  },
];
