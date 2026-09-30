(() => {
  "use strict";

  // Endpoints - must match backend/main.py
  const API = {
    health: "/health",
    chat: "/chat",
    docQuery: "/document/query",
    docStatus: "/document/status",
    session: (id) => `/session/${encodeURIComponent(id)}`,
  };
  const REQUEST_TIMEOUT_MS = 70000;

  const state = { sessionId: null, mode: "chat", busy: false, docCount: null };

  const $ = (id) => document.getElementById(id);
  const els = {
    messages: $("messages"), form: $("composer"), input: $("input"), send: $("send-btn"),
    clear: $("clear-btn"), toast: $("toast"), status: $("status"), hint: $("mode-hint"),
    modeChat: $("mode-chat"), modeDocs: $("mode-docs"),
  };

  // ---------- helpers ----------
  class ApiError extends Error {
    constructor(message, code) { super(message); this.code = code; }
  }

  let toastTimer;
  function showToast(text) {
    els.toast.textContent = text;
    els.toast.hidden = false;
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => { els.toast.hidden = true; }, 6000);
  }

  async function apiFetch(url, options = {}) {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), REQUEST_TIMEOUT_MS);
    try {
      const res = await fetch(url, {
        ...options,
        headers: { "Content-Type": "application/json" },
        signal: controller.signal,
      });
      let data = null;
      try { data = await res.json(); } catch { /* non-JSON body */ }
      if (!res.ok) {
        const err = data && data.error;
        throw new ApiError(err ? err.message : `Request failed (${res.status}).`, err ? err.code : "HTTP_ERROR");
      }
      return data;
    } catch (e) {
      if (e instanceof ApiError) throw e;
      if (e.name === "AbortError") throw new ApiError("The request timed out. Please try again.", "TIMEOUT");
      throw new ApiError("Could not reach the server. Is it running?", "NETWORK");
    } finally {
      clearTimeout(timer);
    }
  }

  // Safe rendering: builds DOM nodes with textContent (never innerHTML).
  function appendInline(parent, text) {
    text.split(/(\*\*[^*]+\*\*)/g).forEach((part) => {
      if (part.startsWith("**") && part.endsWith("**") && part.length > 4) {
        const strong = document.createElement("strong");
        strong.textContent = part.slice(2, -2);
        parent.appendChild(strong);
      } else if (part) {
        parent.appendChild(document.createTextNode(part));
      }
    });
  }

  function renderRichText(container, text) {
    let list = null;
    let para = null;
    const flush = () => { list = null; para = null; };
    text.split("\n").forEach((raw) => {
      const line = raw.trim();
      const bullet = line.match(/^(?:[-*•]|\d+[.)])\s+(.*)$/);
      if (!line) { flush(); return; }
      if (bullet) {
        para = null;
        if (!list) { list = document.createElement("ul"); container.appendChild(list); }
        const li = document.createElement("li");
        appendInline(li, bullet[1]);
        list.appendChild(li);
      } else {
        list = null;
        if (!para) { para = document.createElement("p"); container.appendChild(para); }
        else para.appendChild(document.createElement("br"));
        appendInline(para, line);
      }
    });
  }

  function scrollToBottom() { els.messages.scrollTop = els.messages.scrollHeight; }

  function addMessage(role, text, opts = {}) {
    const div = document.createElement("div");
    div.className = `msg ${role}`;
    if (opts.crisis) div.classList.add("crisis");
    if (opts.notFound) div.classList.add("notfound");
    if (role === "user") div.textContent = text;
    else renderRichText(div, text);

    if (opts.sources && opts.sources.length) {
      const details = document.createElement("details");
      details.className = "sources";
      const summary = document.createElement("summary");
      summary.textContent = `Sources (${opts.sources.length})`;
      details.appendChild(summary);
      const ul = document.createElement("ul");
      opts.sources.forEach((s) => {
        const li = document.createElement("li");
        const page = s.page ? `, page ${s.page}` : "";
        li.textContent = `${s.file}${page}: ${s.snippet}`;
        ul.appendChild(li);
      });
      details.appendChild(ul);
      div.appendChild(details);
    }
    els.messages.appendChild(div);
    scrollToBottom();
    return div;
  }

  function addTyping() {
    const div = document.createElement("div");
    div.className = "msg ai";
    div.setAttribute("aria-label", "Assistant is typing");
    const dots = document.createElement("span");
    dots.className = "typing";
    dots.innerHTML = "<span></span><span></span><span></span>"; // static markup, no user data
    div.appendChild(dots);
    els.messages.appendChild(div);
    scrollToBottom();
    return div;
  }

  function setBusy(busy) {
    state.busy = busy;
    els.send.disabled = busy;
    els.send.textContent = busy ? "Sending…" : "Send";
  }

  function autoGrow() {
    els.input.style.height = "auto";
    els.input.style.height = `${Math.min(els.input.scrollHeight, 160)}px`;
  }

  // ---------- modes ----------
  function welcome() {
    els.messages.replaceChildren();
    addMessage(
      "ai",
      state.mode === "chat"
        ? "Hi, I'm a wellbeing assistant. I can share general information about stress, sleep, mood, and coping skills. What's on your mind?"
        : "Ask a question and I'll answer using only the documents in the documents folder, and show you where the answer came from."
    );
  }

  async function refreshDocStatus() {
    try {
      const s = await apiFetch(API.docStatus);
      state.docCount = s.count;
    } catch { state.docCount = null; }
    updateHint();
  }

  function updateHint() {
    if (state.mode !== "docs") { els.hint.hidden = true; return; }
    els.hint.hidden = false;
    els.hint.textContent =
      state.docCount === 0
        ? "No documents found. Add PDF, TXT or MD files to the documents folder."
        : state.docCount === null
          ? "Answers come only from the documents in the documents folder."
          : `Answers come only from ${state.docCount} document${state.docCount === 1 ? "" : "s"} in the documents folder. The first question may take a few seconds while they are indexed.`;
  }

  function setMode(mode) {
    if (state.busy || mode === state.mode) return;
    state.mode = mode;
    els.modeChat.classList.toggle("active", mode === "chat");
    els.modeDocs.classList.toggle("active", mode === "docs");
    els.modeChat.setAttribute("aria-selected", String(mode === "chat"));
    els.modeDocs.setAttribute("aria-selected", String(mode === "docs"));
    els.input.placeholder = mode === "chat"
      ? "Type a message. Enter to send, Shift+Enter for a new line."
      : "Ask a question about your documents.";
    welcome();
    if (mode === "docs") refreshDocStatus(); else updateHint();
    els.input.focus();
  }

  // ---------- actions ----------
  async function sendMessage() {
    const text = els.input.value.trim();
    if (state.busy) return;
    if (!text) { showToast("Please type a message before sending."); return; }

    addMessage("user", text);
    els.input.value = "";
    autoGrow();
    setBusy(true);
    const typing = addTyping();

    try {
      if (state.mode === "chat") {
        const data = await apiFetch(API.chat, {
          method: "POST",
          body: JSON.stringify({ message: text, session_id: state.sessionId }),
        });
        state.sessionId = data.session_id;
        typing.remove();
        addMessage("ai", data.reply, { crisis: data.is_crisis });
      } else {
        const data = await apiFetch(API.docQuery, {
          method: "POST",
          body: JSON.stringify({ question: text }),
        });
        typing.remove();
        addMessage("ai", data.answer, {
          crisis: data.is_crisis,
          notFound: !data.found && !data.is_crisis,
          sources: data.sources,
        });
      }
    } catch (err) {
      typing.remove();
      if (err.code === "SESSION_NOT_FOUND") state.sessionId = null;
      showToast(err.message);
    } finally {
      setBusy(false);
      els.input.focus();
    }
  }

  async function clearChat() {
    if (state.busy) return;
    const id = state.sessionId;
    state.sessionId = null;
    welcome();
    if (id) {
      try { await apiFetch(API.session(id), { method: "DELETE" }); } catch { /* already gone */ }
    }
    els.input.focus();
  }

  async function checkHealth() {
    try {
      const h = await apiFetch(API.health);
      if (h.ai_configured) {
        els.status.dataset.state = "ok";
        els.status.textContent = "Online";
      } else {
        els.status.dataset.state = "warn";
        els.status.textContent = "API key missing";
        showToast("The server has no AI API key yet. Add it to the .env file and restart.");
      }
    } catch {
      els.status.dataset.state = "down";
      els.status.textContent = "Offline";
    }
  }

  // ---------- init ----------
  els.form.addEventListener("submit", (e) => { e.preventDefault(); sendMessage(); });
  els.input.addEventListener("input", autoGrow);
  els.input.addEventListener("keydown", (e) => {
    if (e.key === "Enter" && !e.shiftKey && !e.isComposing) { e.preventDefault(); sendMessage(); }
  });
  els.clear.addEventListener("click", clearChat);
  els.modeChat.addEventListener("click", () => setMode("chat"));
  els.modeDocs.addEventListener("click", () => setMode("docs"));

  welcome();
  checkHealth();
  els.input.focus();
})();
