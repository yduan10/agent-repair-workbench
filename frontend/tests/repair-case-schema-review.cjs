// Independent H4 contract checks; synthetic DTOs, no API or model calls.
const fs = require('node:fs');
const vm = require('node:vm');
const assert = require('node:assert/strict');
const ts = require('typescript');
const source = fs.readFileSync('lib/repairs.ts', 'utf8');
const compiled = ts.transpileModule(source, {compilerOptions: {module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022}}).outputText;
const api = {exports: {}};
vm.runInNewContext(compiled, {exports: api.exports, module: api, require: id => id === './runs' ? {} : require(id)});
const spec = fs.readFileSync('tests/repairs.spec.ts', 'utf8');
const fixture = spec.slice(spec.indexOf('const A ='), spec.indexOf('function diff('));
const data = vm.runInNewContext(fixture + '\nsample()', {});
let checks = 0;
function check(value, valid) {
  assert.equal(api.exports.detailSchema.safeParse(value).success, valid);
  checks++;
}
for (const caseId of ['output_mismatch', 'counter_offset']) {
  const x = structuredClone(data);
  x.task.case_id = caseId;
  const fingerprint = caseId === 'counter_offset' ? 'count_value' : 'count_type';
  for (const step of x.comparisons[0].slots[0].steps) if (step.code !== 'ok') step.code = fingerprint;
  check(x, true);
  for (const count of [0, 1, 3]) {
    const bad = structuredClone(x);
    bad.comparisons[0].slots = bad.comparisons[0].slots.slice(0, count);
    check(bad, false);
  }
  const crossed = structuredClone(x);
  crossed.task.case_id = caseId === 'counter_offset' ? 'output_mismatch' : 'counter_offset';
  check(crossed, false);
  const mixed = structuredClone(x);
  mixed.comparisons[0].slots[0].steps.find(s => s.name === 'valid_zero').code = fingerprint === 'count_type' ? 'count_value' : 'count_type';
  check(mixed, false);
  const old = structuredClone(x); old.schema_version = 1; check(old, false);
  const unknown = structuredClone(x); unknown.task.case_id = 'arbitrary'; check(unknown, false);
  const accepted = structuredClone(x); accepted.comparisons[0].accepted = true; check(accepted, false);
  const unfinished = structuredClone(x); unfinished.comparisons[0].slots[3].steps[2] = {...unfinished.comparisons[0].slots[3].steps[2], status: 'not_run', code: 'not_run'}; check(unfinished, false);
}
console.log(`${checks} independent schema checks passed`);
