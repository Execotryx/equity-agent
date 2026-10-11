import { describe, expect, it, vi } from "vitest";

vi.mock("@/components/ReportView", () => ({ ReportView: () => null }));
import ReportPage, { generateMetadata } from "./page";

describe("report route parameters", () => {
  it.each(["%", "%ZZ", "frhc_kz", "brk.b"])("uses decoded Next.js parameters safely: %s", async (ticker) => {
    const props = { params: Promise.resolve({ ticker }), searchParams: Promise.resolve({}) };
    const page = await ReportPage(props);
    expect(page.key).toBe(ticker.toUpperCase());
    expect((await generateMetadata(props)).title).toContain(ticker.toUpperCase());
  });
});
