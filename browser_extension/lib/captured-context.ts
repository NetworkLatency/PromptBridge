export const CAPTURED_CONTEXT_KEY = "capturedContext";

export interface CapturedContext {
  text: string;
  pageTitle: string;
  sourceOrigin: string;
  capturedAt: string;
}

export interface SelectionSource {
  selectionText?: string;
  pageUrl?: string;
  pageTitle?: string;
}

export function createCapturedContext(
  source: SelectionSource,
  now: Date = new Date(),
): CapturedContext | null {
  const text = source.selectionText?.trim();
  if (!text) {
    return null;
  }

  return {
    text,
    pageTitle: source.pageTitle?.trim() ?? "",
    sourceOrigin: extractWebOrigin(source.pageUrl),
    capturedAt: now.toISOString(),
  };
}

export function isCapturedContext(value: unknown): value is CapturedContext {
  if (!value || typeof value !== "object") {
    return false;
  }

  const candidate = value as Record<string, unknown>;
  return (
    typeof candidate.text === "string" &&
    candidate.text.length > 0 &&
    typeof candidate.pageTitle === "string" &&
    typeof candidate.sourceOrigin === "string" &&
    typeof candidate.capturedAt === "string"
  );
}

function extractWebOrigin(rawUrl?: string): string {
  if (!rawUrl) {
    return "";
  }

  try {
    const url = new URL(rawUrl);
    return url.protocol === "http:" || url.protocol === "https:" ? url.origin : "";
  } catch {
    return "";
  }
}
