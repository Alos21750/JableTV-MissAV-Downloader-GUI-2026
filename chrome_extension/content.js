// Content script — runs on jable.tv and missav pages
// Adds a floating download button on video pages

(function () {
  'use strict';

  const VIDEO_URL_RE = /^https?:\/\/(www\.)?(jable\.tv\/videos\/|missav\.(ai|com)\/\w+\/)/;
  const pageUrl = window.location.href;

  // Only inject on video pages
  if (!VIDEO_URL_RE.test(pageUrl)) {
    injectListPageButtons();
    return;
  }

  // Floating download button on video pages
  const btn = document.createElement('div');
  btn.id = 'jdl-fab';
  btn.textContent = '\u2B07';
  btn.title = 'Send to JableTV Downloader';
  document.body.appendChild(btn);

  function setBtn(text, cls, duration) {
    btn.textContent = text;
    if (cls) btn.classList.add(cls);
    if (duration) {
      setTimeout(() => {
        btn.textContent = '\u2B07';
        if (cls) btn.classList.remove(cls);
        btn.title = 'Send to JableTV Downloader';
      }, duration);
    }
  }

  btn.addEventListener('click', () => {
    btn.classList.add('jdl-loading');
    btn.textContent = '\u23F3';
    chrome.runtime.sendMessage(
      { action: 'download', url: pageUrl },
      (res) => {
        btn.classList.remove('jdl-loading');
        if (res && res.ok) {
          setBtn('\u2713', 'jdl-ok', 2000);
        } else {
          btn.title = res ? res.error : 'App not running';
          setBtn('\u2717', 'jdl-err', 3000);
        }
      }
    );
  });

  // List/browse pages — add download icon to each video card
  function injectListPageButtons() {
    const cards = document.querySelectorAll(
      '.video-img-box a[href], .thumb-overlay a[href], a.cover-md[href]'
    );
    cards.forEach((card) => {
      const href = card.href;
      if (!href || !VIDEO_URL_RE.test(href)) return;
      if (card.querySelector('.jdl-card-btn')) return;

      const dlBtn = document.createElement('div');
      dlBtn.className = 'jdl-card-btn';
      dlBtn.textContent = '\u2B07';
      dlBtn.title = 'Send to Downloader';
      dlBtn.addEventListener('click', (e) => {
        e.preventDefault();
        e.stopPropagation();
        dlBtn.textContent = '\u23F3';
        chrome.runtime.sendMessage(
          { action: 'download', url: href },
          (res) => {
            if (res && res.ok) {
              dlBtn.textContent = '\u2713';
              dlBtn.classList.add('jdl-ok');
            } else {
              dlBtn.textContent = '\u2717';
              dlBtn.classList.add('jdl-err');
            }
            setTimeout(() => {
              dlBtn.textContent = '\u2B07';
              dlBtn.classList.remove('jdl-ok', 'jdl-err');
            }, 2000);
          }
        );
      });

      card.style.position = 'relative';
      card.appendChild(dlBtn);
    });
  }
})();
