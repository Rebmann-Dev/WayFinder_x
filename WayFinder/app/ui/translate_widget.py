"""Floating live-translate widget, pinned to the bottom-right of the page.

Architecture note — why two scripts:

Streamlit renders `components.html` content inside a `srcdoc` iframe with
a synthetic origin. That iframe has no `allow="microphone"` permission,
which breaks the Web Speech API: Chrome's `SpeechRecognition` streams
audio to a Google service and reports `event.error === "network"` when
called from an unauthorized origin, even if the constructor is pulled
from `window.parent`.

To fix it, the widget source lives inside a `<script type="text/plain">`
tag (not executed by the browser) and a tiny bootstrap reads that text
and injects it as a real `<script>` element into the **parent**
document. That script then executes at the top-level Streamlit origin,
where mic permissions resolve correctly. Translation also happens in
the parent context, which keeps CORS/fetch consistent.

- Translation: Google Translate's free unofficial `translate_a/single`
  endpoint (no API key required).
- Voice-to-text: the browser-native Web Speech API
  (`webkitSpeechRecognition` / `SpeechRecognition`), so no extra Python
  dependencies are needed. Supported in Chromium-based browsers and
  recent Safari.
"""

import streamlit.components.v1 as components


# NOTE: `type="text/plain"` keeps the browser from parsing/executing this
# block as JavaScript. The bootstrap below reads its textContent and
# injects it as a real script into the PARENT document so it runs in the
# top-level Streamlit origin.
_WIDGET_HTML = r"""
<script type="text/plain" id="wf-translate-source">
(function () {
  // Idempotent install — if a prior Streamlit rerun already attached the
  // widget, leave the existing instance (and its in-flight state) alone.
  if (document.getElementById("wf-translate-root")) return;

  // ── Styles ────────────────────────────────────────────────────────
  const style = document.createElement("style");
  style.id = "wf-translate-style";
  style.textContent = `
    #wf-translate-root {
      position: fixed;
      right: 24px;
      bottom: 24px;
      z-index: 2147483647;
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto,
        "Helvetica Neue", Arial, sans-serif;
      color: #f1f5f9;
    }
    #wf-translate-fab {
      width: 52px;
      height: 52px;
      border-radius: 50%;
      background: #3b82f6;
      color: #ffffff;
      border: none;
      box-shadow: 0 6px 20px rgba(0, 0, 0, 0.35),
                  0 2px 6px rgba(59, 130, 246, 0.35);
      cursor: pointer;
      display: flex;
      align-items: center;
      justify-content: center;
      font-size: 22px;
      transition: transform 0.15s ease, background 0.15s ease;
    }
    #wf-translate-fab:hover {
      background: #2563eb;
      transform: translateY(-1px);
    }
    #wf-translate-panel {
      position: absolute;
      right: 0;
      bottom: 64px;
      width: 340px;
      background: #0f172a;
      border: 1px solid #334155;
      border-radius: 14px;
      box-shadow: 0 16px 40px rgba(0, 0, 0, 0.45);
      padding: 14px;
      display: none;
    }
    #wf-translate-panel.wf-open { display: block; }

    .wf-tr-header {
      display: flex;
      align-items: center;
      justify-content: space-between;
      margin-bottom: 10px;
    }
    .wf-tr-title {
      font-size: 0.88rem;
      font-weight: 600;
      color: #f1f5f9;
      letter-spacing: -0.01em;
    }
    .wf-tr-close {
      background: transparent;
      color: #94a3b8;
      border: none;
      font-size: 18px;
      line-height: 1;
      cursor: pointer;
      padding: 2px 6px;
      border-radius: 6px;
    }
    .wf-tr-close:hover { color: #f1f5f9; background: #1e293b; }

    .wf-tr-row {
      display: flex;
      gap: 8px;
      align-items: center;
      margin-bottom: 8px;
    }
    .wf-tr-label {
      font-size: 0.68rem;
      font-weight: 600;
      letter-spacing: 0.08em;
      color: #94a3b8;
      text-transform: uppercase;
    }
    .wf-tr-select {
      flex: 1;
      background: #1e293b;
      color: #f1f5f9;
      border: 1px solid #334155;
      border-radius: 8px;
      padding: 6px 8px;
      font-size: 0.85rem;
      outline: none;
    }
    .wf-tr-select:focus { border-color: #3b82f6; }

    .wf-tr-textarea {
      width: 100%;
      min-height: 72px;
      max-height: 180px;
      resize: vertical;
      background: #1e293b;
      color: #f1f5f9;
      border: 1px solid #334155;
      border-radius: 10px;
      padding: 9px 11px;
      font-size: 0.88rem;
      font-family: inherit;
      outline: none;
      box-sizing: border-box;
    }
    .wf-tr-textarea:focus { border-color: #3b82f6; }

    .wf-tr-actions {
      display: flex;
      gap: 8px;
      margin: 8px 0;
    }
    .wf-tr-btn {
      flex: 1;
      border: 1px solid #334155;
      background: #1e293b;
      color: #e2e8f0;
      padding: 7px 10px;
      border-radius: 9px;
      font-size: 0.83rem;
      font-weight: 500;
      cursor: pointer;
      display: flex;
      align-items: center;
      justify-content: center;
      gap: 6px;
      transition: all 0.15s ease;
    }
    .wf-tr-btn:hover {
      border-color: #3b82f6;
      color: #93c5fd;
      background: #1e3a8a33;
    }
    .wf-tr-btn.wf-primary {
      background: #3b82f6;
      border-color: #3b82f6;
      color: #ffffff;
    }
    .wf-tr-btn.wf-primary:hover {
      background: #2563eb;
      border-color: #2563eb;
      color: #ffffff;
    }
    .wf-tr-btn.wf-recording {
      background: #dc2626;
      border-color: #dc2626;
      color: #ffffff;
      animation: wf-pulse 1.2s ease-in-out infinite;
    }
    @keyframes wf-pulse {
      0%, 100% { box-shadow: 0 0 0 0 rgba(220, 38, 38, 0.55); }
      50%      { box-shadow: 0 0 0 8px rgba(220, 38, 38, 0.00); }
    }

    .wf-tr-output {
      background: #1e293b;
      border: 1px solid #334155;
      border-radius: 10px;
      padding: 9px 11px;
      font-size: 0.88rem;
      color: #f1f5f9;
      min-height: 42px;
      white-space: pre-wrap;
      word-wrap: break-word;
    }
    .wf-tr-output.wf-muted { color: #64748b; }
    .wf-tr-status {
      font-size: 0.72rem;
      color: #94a3b8;
      margin-top: 6px;
      min-height: 14px;
    }
    .wf-tr-status.wf-error { color: #f87171; }
  `;
  document.head.appendChild(style);

  // ── Markup ────────────────────────────────────────────────────────
  const root = document.createElement("div");
  root.id = "wf-translate-root";
  root.innerHTML = `
    <div id="wf-translate-panel" role="dialog" aria-label="Live translate">
      <div class="wf-tr-header">
        <div class="wf-tr-title">🌐 Live translate</div>
        <button class="wf-tr-close" id="wf-tr-close" aria-label="Close">✕</button>
      </div>

      <div class="wf-tr-row">
        <span class="wf-tr-label">To</span>
        <select class="wf-tr-select" id="wf-tr-target">
          <option value="es">Spanish</option>
          <option value="fr">French</option>
          <option value="de">German</option>
          <option value="it">Italian</option>
          <option value="pt">Portuguese</option>
          <option value="ja">Japanese</option>
          <option value="ko">Korean</option>
          <option value="zh-CN">Chinese (Simplified)</option>
          <option value="ar">Arabic</option>
          <option value="hi">Hindi</option>
          <option value="ru">Russian</option>
          <option value="nl">Dutch</option>
          <option value="sv">Swedish</option>
          <option value="tr">Turkish</option>
          <option value="vi">Vietnamese</option>
          <option value="th">Thai</option>
          <option value="en">English</option>
        </select>
      </div>

      <textarea
        id="wf-tr-input"
        class="wf-tr-textarea"
        placeholder="Type or speak a phrase…"
      ></textarea>

      <div class="wf-tr-actions">
        <button class="wf-tr-btn" id="wf-tr-mic" type="button">
          🎤 <span id="wf-tr-mic-label">Speak</span>
        </button>
        <button class="wf-tr-btn wf-primary" id="wf-tr-go" type="button">
          Translate
        </button>
      </div>

      <div class="wf-tr-output wf-muted" id="wf-tr-output">
        Translation will appear here.
      </div>
      <div class="wf-tr-status" id="wf-tr-status"></div>
    </div>

    <button id="wf-translate-fab" type="button" aria-label="Open live translate" title="Live translate">
      🌐
    </button>
  `;
  document.body.appendChild(root);

  // ── Element refs ──────────────────────────────────────────────────
  const fab     = document.getElementById("wf-translate-fab");
  const panel   = document.getElementById("wf-translate-panel");
  const closeBt = document.getElementById("wf-tr-close");
  const input   = document.getElementById("wf-tr-input");
  const target  = document.getElementById("wf-tr-target");
  const goBtn   = document.getElementById("wf-tr-go");
  const micBtn  = document.getElementById("wf-tr-mic");
  const micLbl  = document.getElementById("wf-tr-mic-label");
  const output  = document.getElementById("wf-tr-output");
  const status  = document.getElementById("wf-tr-status");

  // ── Panel open/close ──────────────────────────────────────────────
  fab.addEventListener("click", () => {
    panel.classList.toggle("wf-open");
    if (panel.classList.contains("wf-open")) input.focus();
  });
  closeBt.addEventListener("click", () => panel.classList.remove("wf-open"));

  // ── Translation via Google Translate free endpoint ────────────────
  function setStatus(msg, isError) {
    status.textContent = msg || "";
    status.classList.toggle("wf-error", !!isError);
  }

  async function translate() {
    const text = (input.value || "").trim();
    if (!text) {
      setStatus("Enter some text to translate.", true);
      return;
    }
    const tl = target.value || "es";
    setStatus("Translating…", false);
    output.classList.add("wf-muted");
    output.textContent = "…";

    const url =
      "https://translate.googleapis.com/translate_a/single" +
      "?client=gtx&sl=auto&dt=t&q=" + encodeURIComponent(text) +
      "&tl=" + encodeURIComponent(tl);

    try {
      const res = await fetch(url);
      if (!res.ok) throw new Error("HTTP " + res.status);
      const data = await res.json();
      const translated = (data && data[0] || [])
        .map(seg => (seg && seg[0]) || "")
        .join("");
      if (!translated) throw new Error("Empty response");
      output.classList.remove("wf-muted");
      output.textContent = translated;
      setStatus("", false);
    } catch (err) {
      output.classList.add("wf-muted");
      output.textContent = "Translation failed.";
      setStatus("Could not reach translation service.", true);
    }
  }

  goBtn.addEventListener("click", translate);
  input.addEventListener("keydown", (e) => {
    // Cmd/Ctrl+Enter submits
    if ((e.metaKey || e.ctrlKey) && e.key === "Enter") {
      e.preventDefault();
      translate();
    }
  });

  // ── Voice-to-text via Web Speech API ──────────────────────────────
  // Runs in the top-level document context, so mic permissions resolve
  // against the Streamlit origin (no iframe sandbox issues).
  const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
  let recognition = null;
  let recording = false;

  if (!SR) {
    micBtn.disabled = true;
    micBtn.title = "Voice input not supported in this browser";
    micBtn.style.opacity = "0.55";
    micBtn.style.cursor = "not-allowed";
  } else {
    recognition = new SR();
    recognition.continuous = false;
    recognition.interimResults = true;
    recognition.lang = "en-US";

    recognition.onresult = (event) => {
      let finalText = "";
      let interim = "";
      for (let i = event.resultIndex; i < event.results.length; i++) {
        const r = event.results[i];
        if (r.isFinal) finalText += r[0].transcript;
        else interim += r[0].transcript;
      }
      if (finalText) {
        input.value = (input.value ? input.value.trim() + " " : "") + finalText.trim();
        setStatus("", false);
      } else if (interim) {
        setStatus("Listening: " + interim, false);
      }
    };
    recognition.onerror = (e) => {
      const code = (e && e.error) || "unknown";
      let msg = "Mic error: " + code;
      if (code === "network") {
        msg = "Mic network error — the browser couldn't reach the speech service. " +
              "Make sure the app is served over https:// or http://localhost, and " +
              "that Chrome can reach Google services.";
      } else if (code === "not-allowed" || code === "service-not-allowed") {
        msg = "Microphone permission denied. Enable mic access for this site in " +
              "your browser's site settings and reload.";
      } else if (code === "no-speech") {
        msg = "No speech detected — try again a bit closer to the mic.";
      }
      setStatus(msg, true);
      stopRecording();
    };
    recognition.onend = () => stopRecording();
  }

  function startRecording() {
    if (!recognition || recording) return;
    try {
      recognition.start();
      recording = true;
      micBtn.classList.add("wf-recording");
      micLbl.textContent = "Stop";
      setStatus("Listening…", false);
    } catch (err) {
      setStatus("Mic unavailable.", true);
    }
  }
  function stopRecording() {
    recording = false;
    micBtn.classList.remove("wf-recording");
    micLbl.textContent = "Speak";
    try { recognition && recognition.stop(); } catch (_) {}
  }
  micBtn.addEventListener("click", () => {
    if (!recognition) return;
    if (recording) stopRecording();
    else startRecording();
  });
})();
</script>

<script>
// Bootstrap — runs inside Streamlit's component iframe. Reads the
// widget source above and injects it as a real <script> element into
// the PARENT document so the widget (and, critically, the Web Speech
// API calls) execute at the top-level Streamlit origin.
(function () {
  const parentDoc = window.parent.document;

  // Guard: don't re-install if the widget is already mounted.
  if (parentDoc.getElementById("wf-translate-root")) return;

  const srcEl = document.getElementById("wf-translate-source");
  if (!srcEl) return;

  const boot = parentDoc.createElement("script");
  boot.type = "text/javascript";
  boot.textContent = srcEl.textContent;
  parentDoc.head.appendChild(boot);
})();
</script>
"""


def render_translate_widget() -> None:
    """Mount the floating live-translate widget onto the parent document.

    Renders a zero-height component; the bootstrap JS reads the embedded
    widget source and injects it into the parent document so the widget
    executes at the top-level Streamlit origin (required for mic
    permissions to resolve against the visible URL).
    """
    components.html(_WIDGET_HTML, height=0, width=0)
