import { NextRequest } from "next/server";
import { beforeEach, describe, expect, it, vi } from "vitest";

const backend = vi.hoisted(() => vi.fn());
vi.mock("@/lib/api/server", () => ({ backendRawRequest: backend }));

import { GET } from "./[...path]/route";

const context = (path: string[]) => ({ params: Promise.resolve({ path }) });

describe("courseware asset proxy", () => {
  beforeEach(() => backend.mockReset());

  it("streams immutable backend bytes without a local-file fallback", async () => {
    backend.mockResolvedValue(new Response(new Uint8Array([1, 2, 3]), { status: 200, headers: {
      "Content-Type": "image/png", "Content-Length": "3", "Cache-Control": "public, max-age=31536000, immutable",
      ETag: '"0123456789abcdef0123456789abcdef"', "X-Mira-File-Source": "remote",
    } }));
    const result = await GET(new NextRequest("http://localhost/api/learning/textbooks/assets/textbooks/a.png"), context(["textbooks", "a.png"]));
    expect(result.status).toBe(200);
    expect(new Uint8Array(await result.arrayBuffer())).toEqual(new Uint8Array([1, 2, 3]));
    expect(result.headers.get("X-Mira-File-Source")).toBe("remote");
    expect(backend).toHaveBeenCalledWith("/api/v2/student/learning/textbooks/assets/textbooks/a.png", expect.any(Object));
  });

  it("rejects traversal and query injection before contacting the backend", async () => {
    for (const [url, path] of [
      ["http://localhost/api/learning/textbooks/assets/textbooks/a.png?path=other", ["textbooks", "a.png"]],
      ["http://localhost/api/learning/textbooks/assets/textbooks/../a.png", ["textbooks", "..", "a.png"]],
    ] as const) {
      const result = await GET(new NextRequest(url), context([...path]));
      expect(result.status).toBe(400);
    }
    expect(backend).not.toHaveBeenCalled();
  });

  it("preserves a backend not-found response without reading public files", async () => {
    backend.mockResolvedValue(Response.json({ ok: false, error: "courseware_asset_not_found" }, { status: 404 }));
    const result = await GET(new NextRequest("http://localhost/api/learning/textbooks/assets/textbooks/missing.png"), context(["textbooks", "missing.png"]));
    expect(result.status).toBe(404);
    expect(await result.json()).toMatchObject({ error: "courseware_asset_not_found" });
  });
});
