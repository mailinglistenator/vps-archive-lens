// VPS Archive Lens - Popup Script

async function openArchive(targetUrl) {
  if (!targetUrl || !targetUrl.startsWith("http")) {
    alert("Please enter a valid http/https URL.");
    return;
  }

  const { vpsUrl = "", apiToken = "" } = await chrome.storage.sync.get(["vpsUrl", "apiToken"]);
  if (!vpsUrl) {
    chrome.runtime.openOptionsPage();
    return;
  }

  const cleanVpsUrl = vpsUrl.replace(/\/+$/, "");
  const archiveEndpoint = `${cleanVpsUrl}/archive?url=${encodeURIComponent(targetUrl)}${apiToken ? `&token=${encodeURIComponent(apiToken)}` : ""}`;

  chrome.tabs.create({ url: archiveEndpoint });
  window.close();
}

document.addEventListener("DOMContentLoaded", () => {
  const currentTabBtn = document.getElementById("archiveCurrentTab");
  const customUrlBtn = document.getElementById("archiveCustomUrl");
  const customUrlInput = document.getElementById("customUrl");
  const settingsBtn = document.getElementById("openSettings");

  currentTabBtn.addEventListener("click", async () => {
    const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
    if (tab && tab.url) {
      openArchive(tab.url);
    }
  });

  customUrlBtn.addEventListener("click", () => {
    const url = customUrlInput.value.trim();
    if (url) openArchive(url);
  });

  customUrlInput.addEventListener("keydown", (e) => {
    if (e.key === "Enter") {
      const url = customUrlInput.value.trim();
      if (url) openArchive(url);
    }
  });

  settingsBtn.addEventListener("click", () => {
    if (chrome.runtime.openOptionsPage) {
      chrome.runtime.openOptionsPage();
    } else {
      window.open(chrome.runtime.getURL("options.html"));
    }
  });
});
