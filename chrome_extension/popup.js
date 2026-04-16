const SUPPORTED = /^https?:\/\/(www\.)?(jable\.tv|missav\.(ai|com))\//;

const dot = document.getElementById('dot');
const statusText = document.getElementById('status-text');
const urlInput = document.getElementById('url');
const sendBtn = document.getElementById('send-btn');
const pageBtn = document.getElementById('page-btn');
const msg = document.getElementById('msg');

let appOnline = false;

// Check app status
chrome.runtime.sendMessage({ action: 'checkApp' }, (res) => {
  appOnline = res && res.ok;
  dot.classList.toggle('online', appOnline);
  dot.classList.toggle('offline', !appOnline);
  statusText.textContent = appOnline ? 'App running' : 'App offline';
  sendBtn.disabled = !appOnline;
  pageBtn.disabled = !appOnline;
});

// URL input
urlInput.addEventListener('input', () => {
  sendBtn.disabled = !appOnline || !urlInput.value.trim();
});

// Send URL
sendBtn.addEventListener('click', () => {
  const url = urlInput.value.trim();
  if (!url) return;
  if (!SUPPORTED.test(url)) {
    showMsg('Unsupported URL', 'err');
    return;
  }
  sendBtn.disabled = true;
  chrome.runtime.sendMessage({ action: 'download', url }, (res) => {
    sendBtn.disabled = false;
    if (res && res.ok) {
      showMsg('Sent successfully!', 'ok');
      urlInput.value = '';
    } else {
      showMsg(res ? res.error : 'Failed to connect', 'err');
    }
  });
});

// Send current page
pageBtn.addEventListener('click', () => {
  chrome.tabs.query({ active: true, currentWindow: true }, (tabs) => {
    const url = tabs[0]?.url;
    if (!url || !SUPPORTED.test(url)) {
      showMsg('Not a supported video page', 'err');
      return;
    }
    pageBtn.disabled = true;
    chrome.runtime.sendMessage({ action: 'download', url }, (res) => {
      pageBtn.disabled = false;
      if (res && res.ok) {
        showMsg('Sent successfully!', 'ok');
      } else {
        showMsg(res ? res.error : 'Failed to connect', 'err');
      }
    });
  });
});

function showMsg(text, type) {
  msg.textContent = text;
  msg.className = 'msg ' + (type || '');
  setTimeout(() => { msg.textContent = ''; msg.className = 'msg'; }, 3000);
}
