import { describe, expect, it } from "vitest";

import { createCapturedContext, isCapturedContext } from "../lib/captured-context";

describe("createCapturedContext", () => {
  it("keeps the complete selection but stores only the page origin", () => {
    const context = createCapturedContext(
      {
        selectionText: "  Context engineering\nwith source details  ",
        pageTitle: "  Example article  ",
        pageUrl: "https://example.com/private/path?token=secret#section",
      },
      new Date("2026-07-12T08:00:00.000Z"),
    );

    expect(context).toEqual({
      text: "Context engineering\nwith source details",
      pageTitle: "Example article",
      sourceOrigin: "https://example.com",
      capturedAt: "2026-07-12T08:00:00.000Z",
    });
    expect(JSON.stringify(context)).not.toContain("token=secret");
  });

  it("rejects an empty selection", () => {
    expect(createCapturedContext({ selectionText: "   " })).toBeNull();
  });

  it("does not expose non-web page URLs", () => {
    const context = createCapturedContext({
      selectionText: "local text",
      pageUrl: "file:///C:/private/notes.txt",
    });

    expect(context?.sourceOrigin).toBe("");
  });

  it("does not apply an arbitrary text budget", () => {
    const selectionText = "multilingual context ".repeat(20_000);

    expect(createCapturedContext({ selectionText })?.text).toBe(selectionText.trim());
  });
});

describe("isCapturedContext", () => {
  it("accepts the stored payload shape", () => {
    expect(
      isCapturedContext({
        text: "selected text",
        pageTitle: "Title",
        sourceOrigin: "https://example.com",
        capturedAt: "2026-07-12T08:00:00.000Z",
      }),
    ).toBe(true);
  });

  it("rejects partial storage values", () => {
    expect(isCapturedContext({ text: "selected text" })).toBe(false);
  });
});
