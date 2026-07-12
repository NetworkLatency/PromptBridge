import { browser } from "wxt/browser";

import {
  CAPTURED_CONTEXT_KEY,
  isCapturedContext,
  type CapturedContext,
} from "./captured-context";

export async function saveCapturedContext(context: CapturedContext): Promise<void> {
  await browser.storage.session.set({ [CAPTURED_CONTEXT_KEY]: context });
}

export async function loadCapturedContext(): Promise<CapturedContext | null> {
  const stored = await browser.storage.session.get(CAPTURED_CONTEXT_KEY);
  const context = stored[CAPTURED_CONTEXT_KEY];
  return isCapturedContext(context) ? context : null;
}

export async function clearCapturedContext(): Promise<void> {
  await browser.storage.session.remove(CAPTURED_CONTEXT_KEY);
}
