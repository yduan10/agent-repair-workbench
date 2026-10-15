import passing from "../../examples/passing.json";
import failing from "../../examples/failing.json";

const { result: _result, ...missing } = passing;
export const samples = [
  {
    id: "type",
    label: "结果类型不符",
    description: "返回值类型与契约不一致，结论为不通过",
    value: JSON.stringify(failing, null, 2),
  },
  {
    id: "pass",
    label: "正常调用",
    description: "参数和返回结果都符合契约",
    value: JSON.stringify(passing, null, 2),
  },
  {
    id: "missing",
    label: "缺失结果",
    description: "证据没有 result，结论为无法判定",
    value: JSON.stringify(missing, null, 2),
  },
];
