/* ============================================================
   Universal Video Downloader — app.js
   ============================================================ */

'use strict';

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------
const INFO_DEBOUNCE_MS     = 800; 
const QUEUE_POLL_INTERVAL_MS = 1000; 

// ---------------------------------------------------------------------------
// State
// ---------------------------------------------------------------------------
let selectedType    = 0;
let selectedQuality = '1080p';
let queuePollTimer  = null;
let infoDebounceTimer = null;
let lastRenderedQueue = ''; 

// ---------------------------------------------------------------------------
// Wait for pywebview JS API
// ---------------------------------------------------------------------------
function waitForApi(cb) {
  if (window.pywebview && window.pywebview.api) {
    cb();
  } else {
    window.addEventListener('pywebviewready', cb, { once: true });
  }
}

// ---------------------------------------------------------------------------
// Tab switching
// ---------------------------------------------------------------------------
function initTabs() {
  document.querySelectorAll('.tab-btn').forEach(btn => {
    btn.addEventListener('click', () => {
      const target = btn.dataset.tab;
      document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
      document.querySelectorAll('.tab-content').forEach(s => s.classList.remove('active'));
      btn.classList.add('active');
      document.getElementById('tab-' + target).classList.add('active');
    });
  });
}

// ---------------------------------------------------------------------------
// Title bar: drag + buttons
// ---------------------------------------------------------------------------
function initTitleBar() {
  const titlebar = document.getElementById('titlebar');

  let dragging = false;
  let startX = 0, startY = 0;

  titlebar.addEventListener('mousedown', e => {
    if (e.target.closest('#titlebar-controls')) return;
    dragging = true;
    startX = e.screenX;
    startY = e.screenY;
  });

  document.addEventListener('mousemove', e => {
    if (!dragging) return;
    const dx = e.screenX - startX;
    const dy = e.screenY - startY;
    if (Math.abs(dx) > 2 || Math.abs(dy) > 2) {
      if (window.pywebview && window.pywebview.api && window.pywebview.api.move_window) {
        window.pywebview.api.move_window(dx, dy);
      }
      startX = e.screenX;
      startY = e.screenY;
    }
  });

  document.addEventListener('mouseup', () => { dragging = false; });

  document.getElementById('btn-minimize').addEventListener('click', () => {
    if (window.pywebview && window.pywebview.api) {
      window.pywebview.api.minimize_to_tray();
    }
  });

  document.getElementById('btn-close').addEventListener('click', () => {
    if (window.pywebview && window.pywebview.api) {
      window.pywebview.api.close_window();
    }
  });
}

// ---------------------------------------------------------------------------
// Segmented controls (type only — quality is dynamic, handled in updateQualitySelector)
// ---------------------------------------------------------------------------
function initSegmented() {
  document.querySelectorAll('#type-group .seg-btn').forEach(btn => {
    btn.addEventListener('click', () => {
      document.querySelectorAll('#type-group .seg-btn').forEach(b => b.classList.remove('active'));
      btn.classList.add('active');
      selectedType = parseInt(btn.dataset.idx, 10);
    });
  });
}

function updateQualitySelector(qualities, platform) {
  const qualityCard = document.getElementById('quality-card');
  const group = document.getElementById('quality-group');

  if (!qualities || qualities.length === 0) {
    qualityCard.classList.add('hidden');
    selectedQuality = 'best';
    return;
  }

  qualityCard.classList.remove('hidden');
  group.innerHTML = qualities.map((q, i) =>
    `<button class="seg-btn${i === 0 ? ' active' : ''}" data-quality="${q}">${q}</button>`
  ).join('');

  selectedQuality = qualities[0];

  group.querySelectorAll('.seg-btn').forEach(btn => {
    btn.addEventListener('click', () => {
      group.querySelectorAll('.seg-btn').forEach(b => b.classList.remove('active'));
      btn.classList.add('active');
      selectedQuality = btn.dataset.quality;
    });
  });
}

// ---------------------------------------------------------------------------
// URL input + debounced video info
// ---------------------------------------------------------------------------
function initUrlInput() {
  const input = document.getElementById('url-input');
  const preview = document.getElementById('preview-card');

  document.getElementById('btn-paste').addEventListener('click', async () => {
    try {
      const text = await navigator.clipboard.readText();
      if (text) {
        input.value = text.trim();
        triggerInfoFetch(text.trim());
      }
    } catch (_) {
    }
  });

  input.addEventListener('input', () => {
    const url = input.value.trim();
    clearTimeout(infoDebounceTimer);
    if (!url.startsWith('http')) {
      preview.classList.add('hidden');
      document.getElementById('quality-card').classList.add('hidden');
      return;
    }
    infoDebounceTimer = setTimeout(() => triggerInfoFetch(url), INFO_DEBOUNCE_MS);
  });
}

function triggerInfoFetch(url) {
  if (!url.startsWith('http')) return;
  if (!window.pywebview || !window.pywebview.api) return;

  window.pywebview.api.get_video_info(url).then(info => {
    if (info && info.title) {
      const thumb = document.getElementById('preview-thumb');
      if (info.thumbnail) {
        thumb.src = info.thumbnail;
        thumb.onerror = () => setThumbPlaceholder(thumb, '🎬');
        thumb.classList.remove('hidden');
      } else {
        setThumbPlaceholder(thumb, '🎬');
      }
      document.getElementById('preview-title').textContent = info.title;
      document.getElementById('preview-duration').textContent = info.duration || '';
      document.getElementById('preview-card').classList.remove('hidden');
      updateQualitySelector(info.qualities, info.platform);
    } else {
      document.getElementById('preview-card').classList.add('hidden');
    }
  }).catch(() => {
    document.getElementById('preview-card').classList.add('hidden');
  });
}

// ---------------------------------------------------------------------------
// Add to queue
// ---------------------------------------------------------------------------
function initAddToQueue() {
  document.getElementById('btn-add-queue').addEventListener('click', async () => {
    const url = document.getElementById('url-input').value.trim();
    if (!url) {
      setDlStatus('Please paste a URL first.', 'var(--warn)');
      return;
    }
    if (!window.pywebview || !window.pywebview.api) return;
    setDlStatus('Adding to queue…', 'var(--text-muted)');
    try {
      const result = await window.pywebview.api.add_to_queue(url, selectedType, selectedQuality);
      if (result && result.ok) {
        setDlStatus('✓ Added to queue!', 'var(--success)');
        document.getElementById('url-input').value = '';
        document.getElementById('preview-card').classList.add('hidden');
        document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
        document.querySelectorAll('.tab-content').forEach(s => s.classList.remove('active'));
        document.querySelector('.tab-btn[data-tab="queue"]').classList.add('active');
        document.getElementById('tab-queue').classList.add('active');
      } else {
        setDlStatus('Error: ' + (result && result.error ? result.error : 'Unknown error'), 'var(--danger)');
      }
    } catch (e) {
      setDlStatus('Error: ' + e, 'var(--danger)');
    }
  });
}

function setDlStatus(msg, color) {
  const el = document.getElementById('dl-status');
  el.textContent = msg;
  el.style.color = color || 'var(--text-muted)';
}

// ---------------------------------------------------------------------------
// Queue polling + rendering
// ---------------------------------------------------------------------------
function startQueuePolling() {
  if (queuePollTimer) clearInterval(queuePollTimer);
  queuePollTimer = setInterval(pollQueue, QUEUE_POLL_INTERVAL_MS);
  pollQueue();
}

async function pollQueue() {
  if (!window.pywebview || !window.pywebview.api) return;
  try {
    const items = await window.pywebview.api.get_queue();
    renderQueue(items);
  } catch (_) { /* ignore transient errors */ }
}

function renderQueue(items) {
  const key = JSON.stringify(items);
  if (key === lastRenderedQueue) return;
  lastRenderedQueue = key;

  const list = document.getElementById('queue-list');
  const completedGrid = document.getElementById('completed-grid');

  const active = items.filter(i => i.status !== 'done' && i.status !== 'error');
  const done   = items.filter(i => i.status === 'done');

  if (active.length === 0) {
    list.innerHTML = '<div class="empty-state">No active or pending downloads.</div>';
  } else {
    list.innerHTML = active.map(item => renderQueueCard(item)).join('');
  }

  if (done.length === 0) {
    completedGrid.innerHTML = '<div class="empty-state">No completed downloads yet.</div>';
  } else {
    completedGrid.innerHTML = done.map(item => renderCompletedCard(item)).join('');
    completedGrid.querySelectorAll('[data-open-path]').forEach(btn => {
      btn.addEventListener('click', e => {
        e.stopPropagation();
        const path = btn.dataset.openPath;
        if (window.pywebview && window.pywebview.api) {
          window.pywebview.api.open_file(path);
        }
      });
    });
    completedGrid.querySelectorAll('.btn-delete').forEach(btn => {
      btn.addEventListener('click', async e => {
        e.stopPropagation();
        const id = btn.dataset.itemId;
        if (!id || !window.pywebview || !window.pywebview.api) return;
        await window.pywebview.api.delete_item(id);
        pollQueue();
      });
    });
    completedGrid.querySelectorAll('.completed-card').forEach(card => {
      card.addEventListener('click', (e) => {
        if (e.target.closest('[data-open-path]')) return;
        const path = card.dataset.filePath;
        if (!path) return;
        if (card.dataset.isAlbum === '1') {
          openPhotoAlbumModal(path);
        } else {
          openVideoModal(path);
        }
      });
    });
  }
}

function statusLabel(status) {
  const map = {
    queued:      'Queued',
    downloading: 'Downloading…',
    analyzing:   'Analyzing…',
    converting:  'Converting…',
    merging:     'Merging streams…',
    done:        'Done',
    error:       'Error',
  };
  return map[status] || status;
}

function renderQueueCard(item) {
  const thumb = item.thumbnail
    ? `<img class="queue-thumb" src="${escHtml(item.thumbnail)}" alt="" onerror="handleThumbError(this)" />`
    : `<div class="queue-thumb thumb-placeholder">🎬</div>`;
  const title  = escHtml(item.title || item.url);
  const pct    = item.progress || 0;
  const speed  = item.speed ? `<span>${escHtml(item.speed)}</span>` : '';
  const statusCls = 'status-' + item.status;
  const progressBlock = item.status === 'downloading' || item.status === 'merging' || item.status === 'converting'
    ? item.progress > 0
      ? `<div class="progress-bar"><div class="progress-fill" style="width:${pct}%"></div></div>
         <div class="progress-info"><span>${pct}%</span>${speed}</div>`
      : `<div class="progress-bar"><div class="progress-fill progress-indeterminate" style="width:30%"></div></div>
         <div class="progress-info"><span>Downloading…</span>${speed}</div>`
    : '';
  return `<div class="queue-card">
    ${thumb}
    <div class="queue-meta">
      <div class="queue-title">${title}</div>
      <div class="queue-status ${statusCls}">${statusLabel(item.status)}</div>
      ${progressBlock}
    </div>
  </div>`;
}

function renderCompletedCard(item) {
  const thumb = item.thumbnail
    ? `<img class="completed-thumb" src="${escHtml(item.thumbnail)}" alt="" onerror="handleThumbError(this)" />`
    : `<div class="completed-thumb thumb-placeholder">🎬</div>`;
  const title = escHtml(item.title || item.url);
  const openBtn = item.file_path
    ? `<button class="btn btn-secondary btn-sm btn-explorer" data-open-path="${escHtml(item.file_path)}" onclick="event.stopPropagation()">Open in Explorer</button>`
    : '';
  const playIcon = item.is_album ? '🖼️' : '▶';
  return `<div class="completed-card" data-file-path="${escHtml(item.file_path || '')}" data-is-album="${item.is_album ? '1' : ''}" data-item-id="${escHtml(item.id)}">
    <div class="completed-thumb-wrap">
      ${thumb}
      <div class="completed-play-icon">${playIcon}</div>
    </div>
    <div class="completed-info">
      <div class="completed-title">${title}</div>
      <div class="completed-actions">
        ${openBtn}
        <button class="btn btn-danger btn-sm btn-delete" data-item-id="${escHtml(item.id)}" onclick="event.stopPropagation()" title="Delete file">🗑</button>
      </div>
    </div>
  </div>`;
}

// ---------------------------------------------------------------------------
// Clear done items
// ---------------------------------------------------------------------------
function initClearQueue() {
  document.getElementById('btn-clear-queue').addEventListener('click', async () => {
    if (!window.pywebview || !window.pywebview.api) return;
    await window.pywebview.api.clear_done();
    pollQueue();
  });
}

// ---------------------------------------------------------------------------
// Video modal
// ---------------------------------------------------------------------------
function openVideoModal(filePath) {
  const modal = document.getElementById('video-modal');
  const video = document.getElementById('modal-video');
  if (!window.pywebview || !window.pywebview.api) return;
  window.pywebview.api.get_video_data_url(filePath).then(dataUrl => {
    if (dataUrl) {
      video.src = dataUrl;
      modal.classList.remove('hidden');
      video.play().catch(() => {});
    }
  }).catch(() => {});
}

function closeVideoModal() {
  const modal = document.getElementById('video-modal');
  const video = document.getElementById('modal-video');
  video.pause();
  video.src = '';
  modal.classList.add('hidden');
}

function initModal() {
  document.getElementById('modal-close').addEventListener('click', closeVideoModal);
  document.getElementById('modal-overlay').addEventListener('click', closeVideoModal);
  document.getElementById('album-modal-close').addEventListener('click', closePhotoAlbumModal);
  document.getElementById('album-modal-overlay').addEventListener('click', closePhotoAlbumModal);
  document.getElementById('album-prev').addEventListener('click', () => navigateAlbum(-1));
  document.getElementById('album-next').addEventListener('click', () => navigateAlbum(1));
}

// ---------------------------------------------------------------------------
// Photo album modal
// ---------------------------------------------------------------------------
let _albumImages = [];
let _albumIndex  = 0;

function openPhotoAlbumModal(folderPath) {
  if (!window.pywebview || !window.pywebview.api) return;
  window.pywebview.api.get_album_files(folderPath).then(data => {
    _albumImages = data.images || [];
    _albumIndex  = 0;
    if (_albumImages.length === 0) return;

    const audio = document.getElementById('album-audio');
    if (data.audio) {
      audio.src = data.audio;
      audio.classList.remove('hidden');
    } else {
      audio.src = '';
      audio.classList.add('hidden');
    }

    _renderAlbumImage();
    document.getElementById('album-modal').classList.remove('hidden');
  }).catch(() => {});
}

function closePhotoAlbumModal() {
  const modal = document.getElementById('album-modal');
  const audio = document.getElementById('album-audio');
  audio.pause();
  audio.src = '';
  modal.classList.add('hidden');
  _albumImages = [];
}

function navigateAlbum(delta) {
  _albumIndex = Math.max(0, Math.min(_albumImages.length - 1, _albumIndex + delta));
  _renderAlbumImage();
}

function _renderAlbumImage() {
  document.getElementById('album-image').src = _albumImages[_albumIndex] || '';
  document.getElementById('album-counter').textContent = `${_albumIndex + 1} / ${_albumImages.length}`;
  document.getElementById('album-prev').disabled = _albumIndex === 0;
  document.getElementById('album-next').disabled = _albumIndex === _albumImages.length - 1;
}

// ---------------------------------------------------------------------------
// Utility
// ---------------------------------------------------------------------------
function escHtml(str) {
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}

function setThumbPlaceholder(imgEl, icon) {
  const div = document.createElement('div');
  div.className = imgEl.className + ' thumb-placeholder';
  div.textContent = icon || '🎬';
  imgEl.replaceWith(div);
}

function handleThumbError(imgEl) {
  setThumbPlaceholder(imgEl, '🎬');
}

// ---------------------------------------------------------------------------
// Bootstrap
// ---------------------------------------------------------------------------
function init() {
  initTabs();
  initTitleBar();
  initSegmented();
  initUrlInput();
  initAddToQueue();
  initClearQueue();
  initModal();
  startQueuePolling();
}

waitForApi(init);
