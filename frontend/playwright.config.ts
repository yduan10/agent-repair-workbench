import { defineConfig } from "@playwright/test";

const port = process.env.PW_PORT || "3010";
const apiPort = process.env.AWB_API_PORT || "8030";
for (const value of [port, apiPort]) {
  if (!/^\d{4,5}$/.test(value) || Number(value) < 1024 || Number(value) > 65535) throw new Error("invalid_test_port");
}
const baseURL = `http://127.0.0.1:${port}`;

export default defineConfig({
  testDir: "./tests",
  fullyParallel: false,
  workers: 1,
  timeout: 30000,
  use: {
    channel: process.env.PLAYWRIGHT_CHANNEL || undefined,
    baseURL,
    viewport: { width: 1440, height: 1000 },
    trace: "retain-on-failure",
  },
  webServer: [
    {
      command:
        `uv run --frozen --project .. uvicorn agent_workbench.api:app --host 127.0.0.1 --port ${apiPort} --no-access-log`,
      url: `http://127.0.0.1:${apiPort}/api/health`,
      reuseExistingServer: process.env.AWB_RUNS_E2E === "1" ? false : !process.env.CI,
    },
    {
      command: `npx next start --hostname 127.0.0.1 --port ${port}`,
      url: baseURL,
      reuseExistingServer: process.env.AWB_RUNS_E2E === "1" ? false : !process.env.CI,
    },
  ],
});
