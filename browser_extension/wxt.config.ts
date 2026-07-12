import { defineConfig } from "wxt";

export default defineConfig({
  targetBrowsers: ["chrome", "edge", "firefox"],
  manifest: ({ browser }) => ({
    name: "PromptBridge",
    description: "Capture selected page text for a local multilingual model workflow.",
    permissions: ["contextMenus", "storage"],
    action: {
      default_title: "Open PromptBridge",
    },
    ...(browser === "firefox"
      ? {
          browser_specific_settings: {
            gecko: {
              id: "promptbridge@promptbridge.local",
              strict_min_version: "115.0",
              data_collection_permissions: {
                required: ["none"],
              },
            },
          },
        }
      : {}),
  }),
});
