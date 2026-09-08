// VPS Archive Lens - Settings Script

document.addEventListener("DOMContentLoaded", async () => {
  const vpsUrlInput = document.getElementById("vpsUrl");
  const apiTokenInput = document.getElementById("apiToken");
  const saveBtn = document.getElementById("saveBtn");
  const testBtn = document.getElementById("testBtn");
  const statusDiv = document.getElementById("status");

  // Load saved options
  const data = await chrome.storage.sync.get(["vpsUrl", "apiToken"]);
  vpsUrlInput.value = data.vpsUrl || "";
  apiTokenInput.value = data.apiToken || "";

  function showStatus(msg, isError = false) {
    statusDiv.textContent = msg;
    statusDiv.className = isError ? "status-error" : "status-success";
    statusDiv.style.display = "block";
    setTimeout(() => {
      statusDiv.style.display = "none";
    }, 5000);
  }

  saveBtn.addEventListener("click", async () => {
    const vpsUrl = vpsUrlInput.value.trim().replace(/\/+$/, "");
    const apiToken = apiTokenInput.value.trim();

    if (!vpsUrl) {
      showStatus("Please enter your VPS archiver URL.", true);
      return;
    }

    await chrome.storage.sync.set({ vpsUrl, apiToken });
    showStatus("✓ Settings saved successfully!");
  });

  testBtn.addEventListener("click", async () => {
    const vpsUrl = vpsUrlInput.value.trim().replace(/\/+$/, "");
    const apiToken = apiTokenInput.value.trim();

    if (!vpsUrl) {
      showStatus("Please enter your VPS archiver URL first.", true);
      return;
    }

    showStatus("Testing connection to VPS...");
    try {
      const resp = await fetch(`${vpsUrl}/health`, {
        headers: apiToken ? { "Authorization": `Bearer ${apiToken}` } : {}
      });
      if (resp.ok) {
        const json = await resp.json();
        showStatus(`✓ Connection successful! Server is online (Snapshots: ${json.snapshots_count ?? 0}).`);
      } else {
        showStatus(`✗ Server returned HTTP ${resp.status}: ${resp.statusText}`, true);
      }
    } catch (err) {
      showStatus(`✗ Connection failed: ${err.message}. Ensure port is open or reachable.`, true);
    }
  });
});
