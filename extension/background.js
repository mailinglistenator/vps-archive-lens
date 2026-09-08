// VPS Archive Lens - Background Service Worker

const DEFAULT_VPS_URL = "http://localhost:8888";
const DEFAULT_API_TOKEN = "";

function setupContextMenu() {
  chrome.contextMenus.removeAll(() => {
    // 1. Direct DOM Push (Primary context menu for current page)
    chrome.contextMenus.create({
      id: "vps_archive_push",
      title: "🚀 Push Tab DOM to VPS (Bypass Cloudflare)",
      contexts: ["page"]
    });

    // 2. Remote VPS Fetch (For links or background fetch)
    chrome.contextMenus.create({
      id: "vps_archive_remote",
      title: "🌐 Fetch & Archive via VPS",
      contexts: ["page", "link"]
    });
  });
}

chrome.runtime.onInstalled.addListener(() => {
  setupContextMenu();
});

chrome.runtime.onStartup.addListener(() => {
  setupContextMenu();
});

chrome.contextMenus.onClicked.addListener(async (info, tab) => {
  const { vpsUrl = DEFAULT_VPS_URL, apiToken = DEFAULT_API_TOKEN } = await chrome.storage.sync.get(["vpsUrl", "apiToken"]);
  const cleanVpsUrl = vpsUrl.replace(/\/+$/, "");

  if (info.menuItemId === "vps_archive_push") {
    if (!tab || !tab.id || !tab.url || !tab.url.startsWith("http")) {
      console.warn("Cannot push DOM from non-http page:", tab?.url);
      return;
    }

    try {
      const injectionResults = await chrome.scripting.executeScript({
        target: { tabId: tab.id },
        func: () => ({
          html: document.documentElement.outerHTML,
          url: window.location.href,
          title: document.title
        })
      });

      if (!injectionResults || !injectionResults[0] || !injectionResults[0].result) {
        throw new Error("Could not extract page contents.");
      }

      const { html, url, title } = injectionResults[0].result;
      const pushEndpoint = `${cleanVpsUrl}/archive/push${apiToken ? `?token=${encodeURIComponent(apiToken)}` : ""}`;

      const resp = await fetch(pushEndpoint, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ url, html, title })
      });

      if (!resp.ok) {
        const err = await resp.text();
        throw new Error(`Server returned ${resp.status}: ${err}`);
      }

      const meta = await resp.json();
      chrome.tabs.create({
        url: meta.view_url || `${cleanVpsUrl}/view/${meta.id}`,
        index: tab.index + 1
      });
    } catch (err) {
      console.error("Direct DOM push failed:", err);
    }
    return;
  }

  if (info.menuItemId === "vps_archive_remote") {
    const targetUrl = info.linkUrl || info.pageUrl || tab?.url;
    if (!targetUrl || targetUrl.startsWith("chrome://") || targetUrl.startsWith("about:")) {
      console.warn("Invalid URL for archiving:", targetUrl);
      return;
    }

    const archiveEndpoint = `${cleanVpsUrl}/archive?url=${encodeURIComponent(targetUrl)}${apiToken ? `&token=${encodeURIComponent(apiToken)}` : ""}`;
    chrome.tabs.create({
      url: archiveEndpoint,
      index: tab ? tab.index + 1 : undefined
    });
  }
});
