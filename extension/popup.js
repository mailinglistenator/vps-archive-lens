// VPS Archive Lens - Popup Script

const DEFAULT_VPS_URL = "http://localhost:8888";
const DEFAULT_API_TOKEN = "";

function showStatus(text, type = "info") {
  const el = document.getElementById("statusMessage");
  if (!el) return;
  el.className = `status-${type}`;
  el.textContent = text;
  el.style.display = "block";
}

async function openArchive(targetUrl) {
  if (!targetUrl || !targetUrl.startsWith("http")) {
    showStatus("Please enter or navigate to a valid http/https URL.", "error");
    return;
  }

  const { vpsUrl = DEFAULT_VPS_URL, apiToken = DEFAULT_API_TOKEN } = await chrome.storage.sync.get(["vpsUrl", "apiToken"]);
  const cleanVpsUrl = vpsUrl.replace(/\/+$/, "");
  const archiveEndpoint = `${cleanVpsUrl}/archive?url=${encodeURIComponent(targetUrl)}${apiToken ? `&token=${encodeURIComponent(apiToken)}` : ""}`;

  chrome.tabs.create({ url: archiveEndpoint });
  window.close();
}

async function pushCurrentTabDOM() {
  try {
    const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
    if (!tab || !tab.url || !tab.url.startsWith("http")) {
      showStatus("Please navigate to a valid web page first.", "error");
      return;
    }

    showStatus("Extracting verified page DOM...", "info");

    const injectionResults = await chrome.scripting.executeScript({
      target: { tabId: tab.id },
      func: () => ({
        html: document.documentElement.outerHTML,
        url: window.location.href,
        title: document.title
      })
    });

    if (!injectionResults || !injectionResults[0] || !injectionResults[0].result) {
      throw new Error("Could not extract page contents from current tab.");
    }

    const { html, url, title } = injectionResults[0].result;
    showStatus("Uploading DOM snapshot to VPS...", "info");

    const { vpsUrl = DEFAULT_VPS_URL, apiToken = DEFAULT_API_TOKEN } = await chrome.storage.sync.get(["vpsUrl", "apiToken"]);
    const cleanVpsUrl = vpsUrl.replace(/\/+$/, "");
    const pushEndpoint = `${cleanVpsUrl}/archive/push${apiToken ? `?token=${encodeURIComponent(apiToken)}` : ""}`;

    const resp = await fetch(pushEndpoint, {
      method: "POST",
      headers: {
        "Content-Type": "application/json"
      },
      body: JSON.stringify({ url, html, title })
    });

    if (!resp.ok) {
      const errText = await resp.text();
      throw new Error(`Server returned ${resp.status}: ${errText}`);
    }

    const meta = await resp.json();
    showStatus("Snapshot saved! Opening...", "success");

    const targetViewUrl = meta.view_url || `${cleanVpsUrl}/view/${meta.id}`;
    chrome.tabs.create({
      url: targetViewUrl,
      index: tab.index + 1
    });

    setTimeout(() => {
      window.close();
    }, 500);

  } catch (err) {
    showStatus(`Failed: ${err.message}`, "error");
  }
}

document.addEventListener("DOMContentLoaded", () => {
  const pushBtn = document.getElementById("pushCurrentTab");
  const remoteTabBtn = document.getElementById("archiveCurrentTab");
  const customUrlBtn = document.getElementById("archiveCustomUrl");
  const customUrlInput = document.getElementById("customUrl");
  const settingsBtn = document.getElementById("openSettings");
  const dashboardLink = document.getElementById("openDashboard");

  if (pushBtn) {
    pushBtn.addEventListener("click", pushCurrentTabDOM);
  }

  if (remoteTabBtn) {
    remoteTabBtn.addEventListener("click", async () => {
      const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
      if (tab && tab.url) {
        openArchive(tab.url);
      }
    });
  }

  if (customUrlBtn) {
    customUrlBtn.addEventListener("click", () => {
      const url = customUrlInput.value.trim();
      if (url) {
        openArchive(url);
      }
    });
  }

  if (customUrlInput) {
    customUrlInput.addEventListener("keydown", (e) => {
      if (e.key === "Enter") {
        const url = customUrlInput.value.trim();
        if (url) openArchive(url);
      }
    });
  }

  if (settingsBtn) {
    settingsBtn.addEventListener("click", () => {
      if (chrome.runtime.openOptionsPage) {
        chrome.runtime.openOptionsPage();
      } else {
        window.open(chrome.runtime.getURL("options.html"));
      }
    });
  }

  if (dashboardLink) {
    dashboardLink.addEventListener("click", async (e) => {
      e.preventDefault();
      const { vpsUrl = DEFAULT_VPS_URL, apiToken = DEFAULT_API_TOKEN } = await chrome.storage.sync.get(["vpsUrl", "apiToken"]);
      const cleanVpsUrl = vpsUrl.replace(/\/+$/, "");
      chrome.tabs.create({ url: `${cleanVpsUrl}/list${apiToken ? `?token=${encodeURIComponent(apiToken)}` : ""}` });
      window.close();
    });
  }
});
