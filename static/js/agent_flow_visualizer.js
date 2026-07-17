(() => {
  "use strict";

  const root = document.getElementById("agentFlowVisualizer");
  if (!root) return;

  const svg = root.querySelector("[data-flow-svg]");
  const nodesLayer = root.querySelector("[data-flow-nodes]");
  const edgesLayer = root.querySelector("[data-flow-edges]");
  const executionSelect = root.querySelector("[data-flow-execution]");
  const errorBox = root.querySelector("[data-flow-error]");
  const NS = "http://www.w3.org/2000/svg";
  let mode = "architecture";
  let data = null;
  let executions = [];
  let selectedNodeId = null;
  let viewBox = { x: 0, y: 0, width: 1100, height: 620 };
  let naturalBox = { ...viewBox };
  let pollTimer = null;
  let requestController = null;
  let playbackIndex = -1;
  let playbackTimer = null;
  let dragOrigin = null;

  function element(name, attributes = {}) {
    const node = document.createElementNS(NS, name);
    Object.entries(attributes).forEach(([key, value]) => node.setAttribute(key, value));
    return node;
  }

  function formatDuration(ms) {
    if (ms === null || ms === undefined) return "—";
    if (ms < 1000) return `${ms} ms`;
    return `${(ms / 1000).toFixed(ms < 10000 ? 1 : 0)} s`;
  }

  function formatDate(value) {
    if (!value) return "—";
    return new Intl.DateTimeFormat("es-EC", { dateStyle: "short", timeStyle: "medium" }).format(new Date(value));
  }

  async function getJson(url) {
    requestController?.abort();
    requestController = new AbortController();
    const response = await fetch(url, { credentials: "same-origin", signal: requestController.signal, headers: { Accept: "application/json" } });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    return response.json();
  }

  function setError(visible) {
    errorBox.hidden = !visible;
  }

  function calculateLayout(nodes, edges) {
    const ids = nodes.map((node) => node.id);
    const indegree = Object.fromEntries(ids.map((id) => [id, 0]));
    const outgoing = Object.fromEntries(ids.map((id) => [id, []]));
    edges.forEach((edge) => { if (edge.source in outgoing && edge.target in indegree) { outgoing[edge.source].push(edge.target); indegree[edge.target] += 1; } });
    const queue = ids.filter((id) => indegree[id] === 0);
    const rank = Object.fromEntries(ids.map((id) => [id, 0]));
    while (queue.length) {
      const current = queue.shift();
      outgoing[current].forEach((target) => { rank[target] = Math.max(rank[target], rank[current] + 1); indegree[target] -= 1; if (indegree[target] === 0) queue.push(target); });
    }
    const groups = {};
    ids.forEach((id) => { (groups[rank[id]] ||= []).push(id); });
    const positions = {};
    Object.entries(groups).forEach(([level, group]) => {
      group.forEach((id, index) => { positions[id] = { x: 70 + Number(level) * 245, y: 55 + index * 125 }; });
    });
    const maxRank = Math.max(...Object.values(rank));
    const maxGroup = Math.max(...Object.values(groups).map((group) => group.length));
    return { positions, width: 180 + maxRank * 245, height: Math.max(280, 100 + maxGroup * 125) };
  }

  function renderGraph() {
    if (!data) return;
    nodesLayer.replaceChildren(); edgesLayer.replaceChildren();
    const layout = calculateLayout(data.nodes, data.edges);
    naturalBox = { x: 0, y: 0, width: layout.width, height: layout.height };
    viewBox = { ...naturalBox };
    svg.setAttribute("viewBox", `${viewBox.x} ${viewBox.y} ${viewBox.width} ${viewBox.height}`);

    data.edges.forEach((edge) => {
      const from = layout.positions[edge.source]; const to = layout.positions[edge.target];
      if (!from || !to) return;
      const path = element("path", { d: `M ${from.x + 190} ${from.y + 37} C ${from.x + 215} ${from.y + 37}, ${to.x - 25} ${to.y + 37}, ${to.x} ${to.y + 37}`, class: `agent-flow-edge${edge.taken ? " is-taken" : ""}`, "marker-end": "url(#agentFlowArrow)" });
      edgesLayer.appendChild(path);
      if (edge.condition) {
        const label = element("text", { x: (from.x + to.x + 190) / 2, y: Math.min(from.y, to.y) + 25, class: "agent-flow-edge-label" });
        label.textContent = edge.condition; edgesLayer.appendChild(label);
      }
    });

    data.nodes.forEach((node) => {
      const position = layout.positions[node.id];
      const group = element("g", { class: `agent-flow-node status-${node.status}${selectedNodeId === node.id ? " is-selected" : ""}`, transform: `translate(${position.x} ${position.y})`, tabindex: "0", role: "button", "aria-label": `${node.label}: ${node.status_meta?.label || node.status}` });
      group.dataset.nodeId = node.id;
      group.appendChild(element("rect", { width: "190", height: "74", rx: "13" }));
      const title = element("text", { x: "16", y: "29", class: "agent-flow-node-title" }); title.textContent = node.label; group.appendChild(title);
      const status = element("text", { x: "16", y: "53", class: "agent-flow-node-status" }); status.textContent = node.status_meta?.label || node.status; group.appendChild(status);
      group.addEventListener("click", () => selectNode(node.id));
      group.addEventListener("keydown", (event) => { if (event.key === "Enter" || event.key === " ") { event.preventDefault(); selectNode(node.id); } });
      nodesLayer.appendChild(group);
    });
    renderLegend(); renderTextAlternative();
  }

  function humanizeKey(value) {
    return String(value).replaceAll("_", " ").replace(/^./, (letter) => letter.toUpperCase());
  }

  function appendReadable(container, value, depth = 0) {
    if (value === null || value === undefined || value === "") {
      const empty = document.createElement("span"); empty.className = "text-muted"; empty.textContent = "Sin dato"; container.appendChild(empty); return;
    }
    if (typeof value !== "object") {
      const text = document.createElement("span"); text.textContent = String(value); container.appendChild(text); return;
    }
    if (Array.isArray(value)) {
      const list = document.createElement("ul"); list.className = "agent-flow-readable-list";
      value.forEach((item) => { const row = document.createElement("li"); appendReadable(row, item, depth + 1); list.appendChild(row); }); container.appendChild(list); return;
    }
    const list = document.createElement("dl"); list.className = `agent-flow-readable${depth ? " is-nested" : ""}`;
    Object.entries(value).forEach(([key, item]) => { const term = document.createElement("dt"); term.textContent = humanizeKey(key); const description = document.createElement("dd"); appendReadable(description, item, depth + 1); list.append(term, description); }); container.appendChild(list);
  }

  function textBlock(container, value, emptyText) {
    container.replaceChildren();
    if (value === null || value === undefined || (Array.isArray(value) && !value.length) || (typeof value === "object" && !Array.isArray(value) && !Object.keys(value).length)) {
      const empty = document.createElement("p"); empty.className = "text-muted small"; empty.textContent = emptyText; container.appendChild(empty); return;
    }
    appendReadable(container, value);
  }

  function selectNode(nodeId) {
    selectedNodeId = nodeId; renderGraph();
    const node = data.nodes.find((item) => item.id === nodeId); if (!node) return;
    root.querySelector("[data-flow-detail-empty]").hidden = true;
    const detail = root.querySelector("[data-flow-detail]"); detail.hidden = false;
    detail.querySelector("[data-flow-detail-status]").textContent = node.status_meta?.label || node.status;
    detail.querySelector("[data-flow-detail-title]").textContent = node.label;
    detail.querySelector("[data-flow-detail-purpose]").textContent = node.purpose;
    detail.querySelector("[data-flow-detail-owner]").textContent = node.owner;
    detail.querySelector("[data-flow-detail-question]").textContent = node.question;
    detail.querySelector("[data-flow-detail-duration]").textContent = formatDuration(node.latest_event?.duration_ms);
    textBlock(detail.querySelector("[data-flow-detail-input]"), node.latest_event?.input || node.inputs, "No existe una entrada registrada para este nodo.");
    textBlock(detail.querySelector("[data-flow-detail-output]"), node.latest_event?.output || node.outputs, "No existe una salida registrada para este nodo.");
    textBlock(detail.querySelector("[data-flow-detail-changes]"), node.latest_event?.changes, "Este evento no registró cambios operativos.");
    textBlock(detail.querySelector("[data-flow-detail-sources]"), node.latest_event?.sources, "Este nodo no utilizó evidencia documental.");
  }

  function renderLegend() {
    const container = root.querySelector("[data-flow-legend]"); container.replaceChildren();
    Object.entries(data.states || {}).forEach(([state, meta]) => { const item = document.createElement("span"); item.className = `status-${state}`; item.textContent = meta.label; item.title = meta.help; container.appendChild(item); });
  }

  function renderTextAlternative() {
    const list = root.querySelector("[data-flow-text-list]"); list.replaceChildren();
    data.nodes.forEach((node) => { const item = document.createElement("li"); item.textContent = `${node.label}: ${node.status_meta?.label || node.status}. ${node.purpose}`; list.appendChild(item); });
  }

  function renderTimeline() {
    const list = root.querySelector("[data-flow-events]"); list.replaceChildren();
    const events = data?.events || [];
    if (!events.length) { const item = document.createElement("li"); item.className = "text-muted"; item.textContent = mode === "architecture" ? "El modo arquitectura no utiliza una ejecución." : "Esta ejecución todavía no registra eventos observables."; list.appendChild(item); return; }
    events.forEach((event, index) => {
      const item = document.createElement("li"); item.className = `status-${event.status}${index === playbackIndex ? " is-current" : ""}`; item.tabIndex = 0;
      const node = data.nodes.find((candidate) => candidate.id === event.node_id);
      const heading = document.createElement("strong"); heading.textContent = `${event.order}. ${node?.label || event.node_id} — ${event.status_label}`;
      const summary = document.createElement("p"); summary.textContent = event.summary;
      const time = document.createElement("small"); time.textContent = `${formatDate(event.started_at)} · ${formatDuration(event.duration_ms)}`;
      item.append(heading, summary, time); item.addEventListener("click", () => { playbackIndex = index; applyPlaybackState(); selectNode(event.node_id); renderTimeline(); }); list.appendChild(item);
    });
  }

  function updateSummary() {
    const execution = data?.execution;
    const values = execution ? { status: execution.status_label, operator: execution.operator, stage: execution.stage?.replaceAll("_", " "), duration: formatDuration(execution.duration_ms) } : { status: "Arquitectura", operator: "—", stage: "Flujo general", duration: "—" };
    Object.entries(values).forEach(([key, value]) => { root.querySelector(`[data-flow-summary="${key}"]`).textContent = value || "—"; });
  }

  function schedulePolling() {
    clearTimeout(pollTimer); pollTimer = null;
    if (mode === "execution" && data?.poll) pollTimer = setTimeout(() => loadExecution(executionSelect.value, true), 2000);
  }

  async function loadArchitecture() {
    clearTimeout(pollTimer); mode = "architecture"; setModeButtons();
    try { data = await getJson(root.dataset.architectureUrl); selectedNodeId = null; playbackIndex = -1; setError(false); renderGraph(); renderTimeline(); updateSummary(); }
    catch (error) { if (error.name !== "AbortError") setError(true); }
  }

  async function loadExecutions() {
    const result = await getJson(root.dataset.executionsUrl); executions = result.executions || [];
    executionSelect.replaceChildren();
    if (!executions.length) { const option = document.createElement("option"); option.textContent = "No existen ejecuciones registradas"; executionSelect.appendChild(option); executionSelect.disabled = true; return; }
    executions.forEach((execution) => { const option = document.createElement("option"); option.value = execution.id; option.textContent = `${new Date(execution.started_at).toLocaleString("es-EC")} · ${execution.status_label}`; executionSelect.appendChild(option); });
    executionSelect.disabled = false;
  }

  async function loadExecution(id, preserveSelection = false) {
    if (!id) return;
    try {
      const execution = executions.find((item) => item.id === id);
      data = await getJson(execution?.detail_url || `/api/langgraph/ejecuciones/${id}/`);
      data.nodes.forEach((node) => { node.finalStatus = node.status; node.finalStatusMeta = node.status_meta; });
      if (!preserveSelection) { selectedNodeId = null; playbackIndex = data.events.length - 1; }
      setError(false); renderGraph(); renderTimeline(); updateSummary(); schedulePolling();
    } catch (error) { if (error.name !== "AbortError") { setError(true); schedulePolling(); } }
  }

  async function switchToExecution() {
    mode = "execution"; setModeButtons();
    try { await loadExecutions(); if (executions.length) await loadExecution(executionSelect.value || executions[0].id); else { data = null; renderTimeline(); updateSummary(); } }
    catch (error) { if (error.name !== "AbortError") setError(true); }
  }

  function setModeButtons() {
    root.querySelectorAll("[data-flow-mode]").forEach((button) => { const active = button.dataset.flowMode === mode; button.classList.toggle("btn-primary", active); button.classList.toggle("btn-outline-primary", !active); button.setAttribute("aria-pressed", String(active)); });
    executionSelect.disabled = mode !== "execution" || !executions.length;
  }

  function playback(action) {
    const events = data?.events || []; if (!events.length) return;
    clearInterval(playbackTimer); playbackTimer = null;
    if (action === "first") playbackIndex = 0;
    if (action === "previous") playbackIndex = Math.max(0, playbackIndex - 1);
    if (action === "next") playbackIndex = Math.min(events.length - 1, playbackIndex + 1);
    if (action === "last") playbackIndex = events.length - 1;
    applyPlaybackState(); selectNode(events[playbackIndex].node_id); renderTimeline();
  }

  function applyPlaybackState() {
    if (!data?.execution || playbackIndex < 0) return;
    const visibleEvents = data.events.slice(0, playbackIndex + 1);
    const visited = ["__start__"];
    data.nodes.forEach((node) => {
      node.status = node.id === "__start__" ? "completed" : "pending";
      node.status_meta = data.states[node.status];
    });
    visibleEvents.forEach((event) => {
      const node = data.nodes.find((candidate) => candidate.id === event.node_id);
      if (node) { node.status = event.status; node.status_meta = data.states[event.status]; }
      if (event.status !== "running" && visited.at(-1) !== event.node_id) visited.push(event.node_id);
    });
    if (playbackIndex === data.events.length - 1) {
      data.nodes.forEach((node) => {
        if (node.status === "pending" && node.finalStatus === "skipped") { node.status = "skipped"; node.status_meta = data.states.skipped; }
      });
      const end = data.nodes.find((node) => node.id === "__end__");
      if (end?.finalStatus === "completed") { end.status = "completed"; end.status_meta = data.states.completed; visited.push("__end__"); }
    }
    const pathPairs = new Set(visited.slice(1).map((nodeId, index) => `${visited[index]}:${nodeId}`));
    data.edges.forEach((edge) => { edge.taken = pathPairs.has(`${edge.source}:${edge.target}`); });
  }

  function togglePlayback() {
    if (playbackTimer) { clearInterval(playbackTimer); playbackTimer = null; root.querySelector("[data-flow-play] i").className = "bi bi-play-fill"; return; }
    const delay = Number(root.querySelector("[data-flow-speed]").value); root.querySelector("[data-flow-play] i").className = "bi bi-pause-fill";
    if (playbackIndex < 0 || playbackIndex >= (data?.events?.length || 0) - 1) playbackIndex = -1;
    playbackTimer = setInterval(() => { const events = data?.events || []; if (playbackIndex >= events.length - 1) { togglePlayback(); return; } playback("next"); }, delay);
    playback("next");
  }

  function updateViewBox() { svg.setAttribute("viewBox", `${viewBox.x} ${viewBox.y} ${viewBox.width} ${viewBox.height}`); }
  root.querySelectorAll("[data-flow-mode]").forEach((button) => button.addEventListener("click", () => button.dataset.flowMode === "architecture" ? loadArchitecture() : switchToExecution()));
  root.querySelector("[data-flow-refresh]").addEventListener("click", () => mode === "architecture" ? loadArchitecture() : loadExecution(executionSelect.value));
  executionSelect.addEventListener("change", () => loadExecution(executionSelect.value));
  root.querySelectorAll("[data-flow-step]").forEach((button) => button.addEventListener("click", () => playback(button.dataset.flowStep)));
  root.querySelector("[data-flow-play]").addEventListener("click", togglePlayback);
  root.querySelectorAll("[data-flow-zoom]").forEach((button) => button.addEventListener("click", () => { const factor = button.dataset.flowZoom === "in" ? 0.8 : 1.25; viewBox.width *= factor; viewBox.height *= factor; updateViewBox(); }));
  root.querySelector("[data-flow-fit]").addEventListener("click", () => { viewBox = { ...naturalBox }; updateViewBox(); });
  root.querySelector("[data-flow-export]").addEventListener("click", () => { const copy = svg.cloneNode(true); copy.setAttribute("xmlns", NS); const blob = new Blob([new XMLSerializer().serializeToString(copy)], { type: "image/svg+xml" }); const link = document.createElement("a"); link.href = URL.createObjectURL(blob); link.download = `flujo-agentico-${mode}.svg`; link.click(); URL.revokeObjectURL(link.href); });
  const canvas = root.querySelector("[data-flow-canvas]");
  canvas.addEventListener("pointerdown", (event) => { dragOrigin = { x: event.clientX, y: event.clientY, viewX: viewBox.x, viewY: viewBox.y }; canvas.setPointerCapture(event.pointerId); });
  canvas.addEventListener("pointermove", (event) => { if (!dragOrigin) return; const scaleX = viewBox.width / canvas.clientWidth; const scaleY = viewBox.height / canvas.clientHeight; viewBox.x = dragOrigin.viewX - (event.clientX - dragOrigin.x) * scaleX; viewBox.y = dragOrigin.viewY - (event.clientY - dragOrigin.y) * scaleY; updateViewBox(); });
  canvas.addEventListener("pointerup", () => { dragOrigin = null; });
  canvas.addEventListener("pointercancel", () => { dragOrigin = null; });
  canvas.addEventListener("wheel", (event) => { event.preventDefault(); const factor = event.deltaY < 0 ? 0.9 : 1.1; viewBox.width *= factor; viewBox.height *= factor; updateViewBox(); }, { passive: false });
  window.addEventListener("pagehide", () => { clearTimeout(pollTimer); clearInterval(playbackTimer); requestController?.abort(); });
  loadArchitecture();
})();
