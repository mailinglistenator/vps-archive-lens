// VPS Archive Lens - Background Service Worker

function setupContextMenu() {
  chrome.contextMenus.removeAll(() => {
    chrome.contextMenus.create({
      id: "vps_archive_lens",
      title: "Archive & Unpaywall with VPS",
      contexts: ["page", "link"]
    });
  });
}

chrome.runtime.onInstalled.addListener((details) => {
  setupContextMenu();
  if (details.reason === "install") {
    chrome.runtime.openOptionsPage();
  }
});

chrome.runtime.onStartup.addListener(() => {
  setupContextMenu();
});

chrome.contextMenus.onClicked.addListener(async (info, tab) => {
  if (info.menuItemId !== "vps_archive_lens") return;

  const targetUrl = info.linkUrl || info.pageUrl || tab?.url;
  if (!targetUrl || targetUrl.startsWith("chrome://") || targetUrl.startsWith("about:")) {
    console.warn("Invalid URL for archiving:", targetUrl);
    return;
  }

  const { vpsUrl = "", apiToken = "" } = await chrome.storage.sync.get(["vpsUrl", "apiToken"]);

  if (!vpsUrl) {
    chrome.runtime.openOptionsPage();
    return;
  }

  const cleanVpsUrl = vpsUrl.replace(/\/+$/, "");
  const archiveEndpoint = `${cleanVpsUrl}/archive?url=${encodeURIComponent(targetUrl)}${apiToken ? `&token=${encodeURIComponent(apiToken)}` : ""}`;

  chrome.tabs.create({
    url: archiveEndpoint,
    index: tab ? tab.index + 1 : undefined
  });
});
