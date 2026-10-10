import { describe, expect, it } from "vitest";
import { normalizeTicker, streamUrl } from "./api";

describe("ticker validation", () => {
  it.each([
    [" frhc_kz ", "FRHC_KZ"], ["kspid", "KSPID"], ["brk.b", "BRK.B"],
    ["BRK-B", "BRK-B"], ["A_12345678", "A_12345678"],
  ])("normalizes %s", (raw, expected) => expect(normalizeTicker(raw)).toBe(expected));

  it.each(["_FRHC", "FRHC/KZ", "FRHC KZ", "A_123456789", "1_A", "A$B", ""])(
    "rejects %s", (raw) => expect(normalizeTicker(raw)).toBeNull(),
  );

  it("preserves underscores in SSE requests", () => {
    const url = new URL(streamUrl("FRHC_KZ", true));
    expect(url.searchParams.get("ticker")).toBe("FRHC_KZ");
    expect(url.searchParams.get("refresh")).toBe("true");
  });
});
