(() => {
  const byId = (id) => document.getElementById(`review-${id}`);
  const main = document.querySelector("main.page");
  const tools = byId("tools");
  const dialog = byId("dialog");
  const add = byId("add");
  const open = byId("open");
  const editor = byId("editor");
  const note = byId("note");
  const list = byId("comments");
  const submit = byId("submit");
  const status = byId("status");
  const endpoint = new URL("feedback", location.href);
  let state;
  let selection;
  let editing;
  let busy = false;

  const walker = document.createTreeWalker(main, NodeFilter.SHOW_TEXT);
  const textNodes = [];
  let length = 0;
  while (walker.nextNode()) {
    const node = walker.currentNode;
    textNodes.push({ node, start: length, end: length + node.length });
    length += node.length;
  }

  function captureSelection() {
    const selected = window.getSelection();
    if (!selected?.rangeCount || selected.isCollapsed) return null;
    const range = selected.getRangeAt(0);
    if (!main.contains(range.startContainer) || !main.contains(range.endContainer)) return null;
    const quote = selected.toString();
    if (!quote.trim()) return null;

    const prefix = document.createRange();
    prefix.selectNodeContents(main);
    prefix.setEnd(range.startContainer, range.startOffset);
    const start = prefix.toString().length;
    const end = start + range.toString().length;
    const step_ids = Array.from(main.querySelectorAll("details.step"))
      .filter((step) => range.intersectsNode(step))
      .map((step) => JSON.parse(step.dataset.stepId));
    return { quote, start, end, step_ids };
  }

  function commentRange(comment) {
    const first = textNodes.find(({ start, end }) => start <= comment.start && comment.start < end);
    const last = textNodes.find(({ start, end }) => start < comment.end && comment.end <= end);
    if (!first || !last) return null;
    const range = document.createRange();
    range.setStart(first.node, comment.start - first.start);
    range.setEnd(last.node, comment.end - last.start);
    return range;
  }

  function updateControls() {
    add.disabled = busy || !state || state.submitted || !selection;
    submit.disabled = busy || !state?.comments.length || state.submitted;
    for (const control of dialog.querySelectorAll("textarea, button[data-change], button[type='submit']")) {
      control.disabled = busy || !!state?.submitted;
    }
  }

  function showInbox() {
    byId("inbox").hidden = false;
    editor.hidden = true;
    editing = null;
  }

  function showEditor(comment) {
    editing = comment;
    byId("quote").textContent = comment.quote;
    note.value = comment.note;
    byId("inbox").hidden = true;
    editor.hidden = false;
    status.textContent = "";
    if (!dialog.open) dialog.showModal();
    note.focus();
  }

  function showPassage(range) {
    for (let parent = range.startContainer.parentElement; parent; parent = parent.parentElement) {
      if (parent.matches("details")) parent.open = true;
    }
    dialog.close();
    range.startContainer.parentElement.scrollIntoView({ block: "center" });
  }

  function action(label, click, changesDraft = false) {
    const button = document.createElement("button");
    button.type = "button";
    button.textContent = label;
    if (changesDraft) button.dataset.change = "";
    button.addEventListener("click", click);
    return button;
  }

  function render() {
    list.replaceChildren();
    const ranges = [];
    for (const comment of state.comments) {
      const row = document.createElement("li");
      const quote = document.createElement("blockquote");
      const message = document.createElement("p");
      quote.textContent = comment.quote;
      message.textContent = comment.note;
      row.append(quote, message);
      const range = commentRange(comment);
      if (range) {
        ranges.push(range);
        row.append(action("Show in plan", () => showPassage(range)));
      }
      if (!state.submitted) {
        row.append(
          action("Edit", () => showEditor(comment), true),
          action("Remove", () => save(state.comments.filter(({ id }) => id !== comment.id)), true),
        );
      }
      list.append(row);
    }
    if (window.CSS?.highlights && window.Highlight) {
      CSS.highlights.set("plan-feedback", new Highlight(...ranges));
    }
    open.textContent = state.submitted ? "Feedback submitted" : `Feedback (${state.comments.length})`;
    byId("hint").hidden = state.submitted;
    byId("empty").hidden = state.comments.length > 0;
    submit.hidden = state.submitted;
    updateControls();
  }

  async function save(comments, submitBatch = false, closeOnSave = false) {
    if (busy || state.submitted) return;
    busy = true;
    updateControls();
    status.textContent = submitBatch ? "Submitting feedback…" : "Saving comment…";
    try {
      const response = await fetch(endpoint, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ comments, version: state.version, submit: submitBatch }),
      });
      const result = await response.json();
      if (!response.ok && response.status !== 409) {
        status.textContent = result.error ?? "Could not save feedback. Try again.";
        return;
      }
      state = result;
      if (state.submitted || response.ok) showInbox();
      render();
      if (state.submitted) {
        status.textContent = "Feedback submitted.";
      } else if (response.status === 409) {
        status.textContent = "Feedback changed in another tab. Review the latest comments before saving again.";
      } else {
        status.textContent = "Draft saved.";
        if (dialog.open && closeOnSave) dialog.close();
        if (dialog.open) byId("close").focus();
      }
    } catch {
      status.textContent = "Could not reach the review. Try again or reopen the review from the CLI.";
    } finally {
      busy = false;
      updateControls();
    }
  }

  document.addEventListener("selectionchange", () => {
    selection = captureSelection();
    updateControls();
  });
  // Keep the text selected when clicking the toolbar with a mouse.
  add.addEventListener("mousedown", (event) => event.preventDefault());
  add.addEventListener("click", () => {
    if (!selection) return;
    showEditor({ ...selection, id: crypto.randomUUID(), note: "" });
    window.getSelection().removeAllRanges();
  });
  open.addEventListener("click", () => {
    if (!editing) showInbox();
    dialog.showModal();
  });
  byId("close").addEventListener("click", () => dialog.close());
  byId("cancel").addEventListener("click", () => {
    showInbox();
    status.textContent = "";
    byId("close").focus();
  });
  editor.addEventListener("submit", (event) => {
    event.preventDefault();
    const value = note.value.trim();
    if (!value) {
      status.textContent = "Enter a comment before saving.";
      return;
    }
    const comment = { ...editing, note: value };
    const exists = state.comments.some(({ id }) => id === comment.id);
    const comments = exists
      ? state.comments.map((saved) => saved.id === comment.id ? comment : saved)
      : [...state.comments, comment];
    save(comments, false, !exists);
  });
  submit.addEventListener("click", () => save(state.comments, true));

  async function load() {
    try {
      const response = await fetch(endpoint);
      if (!response.ok) throw new Error();
      state = await response.json();
      render();
    } catch {
      status.textContent = "Could not load feedback. Reload the preview to try again.";
      byId("empty").hidden = true;
    }
  }

  tools.hidden = false;
  document.body.classList.add("review-enabled");
  load();
})();
