const APP_URL = 'http://localhost:8088';
const SUPPORTED = /^https?:\/\/(www\.)?(jable\.tv|missav\.(ai|com))\//;

// Right-click context menu
chrome.runtime.onInstalled.addListener(() => {
  chrome.contextMenus.create({
    id: 'jable-download',
    title: 'Send to JableTV Downloader',
    contexts: ['page', 'link'],
    documentUrlPatterns: [
      '*://*.jable.tv/*',
      '*://*.missav.ai/*',
      '*://*.missav.com/*',
    ],
  });
});

chrome.contextMenus.onClicked.addListener((info, tab) => {
  if (info.menuItemId !== 'jable-download') return;
  const url = info.linkUrl || info.pageUrl;
  if (url && SUPPORTED.test(url)) {
    sendToApp(url);
  }
});

// Receive messages from content script or popup
chrome.runtime.onMessage.addListener((msg, sender, sendResponse) => {
  if (msg.action === 'download') {
    sendToApp(msg.url).then(sendResponse);
    return true; // async response
  }
  if (msg.action === 'downloadBatch') {
    sendBatchToApp(msg.urls).then(sendResponse);
    return true;
  }
  if (msg.action === 'checkApp') {
    checkApp().then(sendResponse);
    return true;
  }
});

async function sendToApp(videoUrl) {
  try {
    const res = await fetch(`${APP_URL}/_nicegui/api/download`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ url: videoUrl }),
    });
    if (res.ok) return { ok: true };
    return { ok: false, error: `HTTP ${res.status}` };
  } catch (e) {
    return { ok: false, error: e.message };
  }
}

async function sendBatchToApp(urls) {
  try {
    const res = await fetch(`${APP_URL}/_nicegui/api/download-batch`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ urls }),
    });
    if (res.ok) return { ok: true };
    return { ok: false, error: `HTTP ${res.status}` };
  } catch (e) {
    return { ok: false, error: e.message };
  }
}

async function checkApp() {
  try {
    const res = await fetch(`${APP_URL}/_nicegui/api/status`, {
      method: 'GET',
    });
    if (res.ok) return { ok: true };
    return { ok: false };
  } catch {
    return { ok: false };
  }
}
