import { browser } from "wxt/browser";

import { createCapturedContext } from "../lib/captured-context";
import { saveCapturedContext } from "../lib/capture-store";

const CAPTURE_MENU_ID = "promptbridge.capture-selection";

interface BrowserWithSidebar {
  sidebarAction?: {
    open(): Promise<void>;
    toggle(): Promise<void>;
  };
}

export default defineBackground(() => {
  browser.runtime.onInstalled.addListener(() => {
    void installContextMenu().catch(reportBackgroundError);
  });

  browser.contextMenus.onClicked.addListener((info, tab) => {
    void handleContextMenuClick(info, tab).catch(reportBackgroundError);
  });

  configureToolbarAction();
});

async function installContextMenu(): Promise<void> {
  await browser.contextMenus.removeAll();
  browser.contextMenus.create({
    id: CAPTURE_MENU_ID,
    title: "发送到 PromptBridge",
    contexts: ["selection"],
  });
}

async function handleContextMenuClick(
  info: Browser.contextMenus.OnClickData,
  tab?: Browser.tabs.Tab,
): Promise<void> {
  if (info.menuItemId !== CAPTURE_MENU_ID) {
    return;
  }

  const context = createCapturedContext({
    selectionText: info.selectionText,
    pageUrl: info.pageUrl ?? tab?.url,
    pageTitle: tab?.title,
  });
  if (!context) {
    return;
  }

  // Start opening before the first await so Chromium keeps the context-menu user gesture.
  const panelPromise = openSidePanel(tab);
  await Promise.all([panelPromise, saveCapturedContext(context)]);
}

function configureToolbarAction(): void {
  if (browser.sidePanel) {
    void browser.sidePanel
      .setPanelBehavior({ openPanelOnActionClick: true })
      .catch(reportBackgroundError);
    return;
  }

  const { sidebarAction } = browser as typeof browser & BrowserWithSidebar;
  if (sidebarAction) {
    browser.browserAction.onClicked.addListener(() => {
      void sidebarAction.toggle().catch(reportBackgroundError);
    });
  }
}

async function openSidePanel(tab?: Browser.tabs.Tab): Promise<void> {
  if (browser.sidePanel) {
    if (tab?.windowId !== undefined) {
      await browser.sidePanel.open({ windowId: tab.windowId });
    }
    return;
  }

  const { sidebarAction } = browser as typeof browser & BrowserWithSidebar;
  if (!sidebarAction) {
    throw new Error("This browser does not expose a supported side panel API.");
  }
  await sidebarAction.open();
}

function reportBackgroundError(error: unknown): void {
  console.error("PromptBridge browser action failed.", error);
}
