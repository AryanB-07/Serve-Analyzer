import { describe, expect, it } from "vitest";

import { ApiError } from "./client";
import { createMockClient, MOCK_STAGES } from "./mockClient";

function setup() {
  let t = 0;
  const fixtures: Record<string, unknown> = {
    "/mock/demo-serve-1/result.json": { id: "demo-serve-1", phases: { contact: 124 } },
    "/mock/analyses.json": { items: [{ id: "demo-serve-1" }], next_cursor: null },
  };
  const client = createMockClient({
    now: () => t,
    latencyMs: 0,
    fetchJson: async <T,>(path: string) => fixtures[path] as T,
  });
  return { client, advance: (ms: number) => (t += ms) };
}

const request = { hand: "right", filename: "serve.mp4", content_type: "video/mp4", size_bytes: 10 } as const;

describe("mock client", () => {
  it("walks through the worker stages to success", async () => {
    const { client, advance } = setup();
    const { analysis } = await client.createAnalysis(request);
    await client.startAnalysis(analysis.id);

    const seen: string[] = [];
    for (const stage of MOCK_STAGES) {
      seen.push((await client.getAnalysis(analysis.id)).status);
      advance(stage.ms);
    }
    seen.push((await client.getAnalysis(analysis.id)).status);
    expect(seen).toEqual(["queued", "extracting_pose", "analyzing", "rendering", "succeeded"]);

    const result = await client.getResult(analysis.id);
    expect(result.id).toBe(analysis.id);
  });

  it("refuses results before success", async () => {
    const { client } = setup();
    const { analysis } = await client.createAnalysis(request);
    await expect(client.getResult(analysis.id)).rejects.toBeInstanceOf(ApiError);
  });

  it("fails files named 'fail' and allows a retry", async () => {
    const { client, advance } = setup();
    const { analysis } = await client.createAnalysis({ ...request, filename: "fail.mp4" });
    await client.startAnalysis(analysis.id);
    advance(60_000);
    const failed = await client.getAnalysis(analysis.id);
    expect(failed.status).toBe("failed");
    expect(failed.error?.code).toBe("NO_PERSON_DETECTED");

    expect((await client.retryAnalysis(analysis.id)).status).toBe("queued");
    advance(60_000);
    expect((await client.getAnalysis(analysis.id)).status).toBe("succeeded");
  });

  it("lists new analyses before the fixtures", async () => {
    const { client } = setup();
    const { analysis } = await client.createAnalysis(request);
    const list = await client.listAnalyses();
    expect(list.items.map((a) => a.id)).toEqual([analysis.id, "demo-serve-1"]);
  });
});
