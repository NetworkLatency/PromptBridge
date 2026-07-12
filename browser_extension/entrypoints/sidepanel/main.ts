import { Copy, createIcons, Trash2 } from "lucide";
import { browser } from "wxt/browser";

import { CAPTURED_CONTEXT_KEY, isCapturedContext, type CapturedContext } from "../../lib/captured-context";
import { clearCapturedContext, loadCapturedContext } from "../../lib/capture-store";
import "./style.css";

const emptyState = requireElement<HTMLElement>("empty-state");
const captureView = requireElement<HTMLElement>("capture-view");
const pageTitle = requireElement<HTMLElement>("page-title");
const sourceOrigin = requireElement<HTMLElement>("source-origin");
const capturedAt = requireElement<HTMLTimeElement>("captured-at");
const capturedText = requireElement<HTMLTextAreaElement>("captured-text");
const copyButton = requireElement<HTMLButtonElement>("copy-button");
const clearButton = requireElement<HTMLButtonElement>("clear-button");
const statusMessage = requireElement<HTMLElement>("status-message");

let currentContext: CapturedContext | null = null;
let statusTimer: number | undefined;

createIcons({ icons: { Copy, Trash2 } });

copyButton.addEventListener("click", async () => {
  if (!currentContext) {
    return;
  }

  try {
    await navigator.clipboard.writeText(currentContext.text);
    showStatus("已复制");
  } catch {
    capturedText.select();
    showStatus("请选择系统复制命令");
  }
});

clearButton.addEventListener("click", async () => {
  await clearCapturedContext();
  render(null);
  showStatus("已清除");
});

browser.storage.onChanged.addListener((changes, areaName) => {
  if (areaName !== "session" || !(CAPTURED_CONTEXT_KEY in changes)) {
    return;
  }

  const nextValue = changes[CAPTURED_CONTEXT_KEY]?.newValue;
  render(isCapturedContext(nextValue) ? nextValue : null);
});

void loadCapturedContext().then(render);

function render(context: CapturedContext | null): void {
  currentContext = context;
  emptyState.hidden = context !== null;
  captureView.hidden = context === null;

  if (!context) {
    pageTitle.textContent = "";
    sourceOrigin.textContent = "";
    capturedAt.textContent = "";
    capturedText.value = "";
    return;
  }

  pageTitle.textContent = context.pageTitle || "未命名页面";
  sourceOrigin.textContent = context.sourceOrigin || "本地或受限页面";
  capturedAt.dateTime = context.capturedAt;
  capturedAt.textContent = formatCapturedAt(context.capturedAt);
  capturedText.value = context.text;
}

function formatCapturedAt(value: string): string {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return "";
  }

  return new Intl.DateTimeFormat("zh-CN", {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  }).format(date);
}

function showStatus(message: string): void {
  window.clearTimeout(statusTimer);
  statusMessage.textContent = message;
  statusTimer = window.setTimeout(() => {
    statusMessage.textContent = "";
  }, 1800);
}

function requireElement<T extends HTMLElement>(id: string): T {
  const element = document.getElementById(id);
  if (!element) {
    throw new Error(`Missing required element: #${id}`);
  }
  return element as T;
}
