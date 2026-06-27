const views = {
  dashboard: document.querySelector("#dashboardView"),
  infobox: document.querySelector("#infoboxView"),
  events: document.querySelector("#eventsView"),
  handovers: document.querySelector("#handoversView"),
  corrective: document.querySelector("#correctiveView"),
  preventive: document.querySelector("#preventiveView"),
  permits: document.querySelector("#permitsView"),
  assets: document.querySelector("#assetsView"),
  reports: document.querySelector("#reportsView"),
  users: document.querySelector("#usersView"),
  logbookadmin: document.querySelector("#logbookadminView"),
  audit: document.querySelector("#auditView"),
  readiness: document.querySelector("#readinessView"),
  system: document.querySelector("#systemView"),
  kksimport: document.querySelector("#kksimportView")
};
const pageTitles = {
  dashboard: "Operations Dashboard",
  infobox: "My Infobox",
  events: "Event Log",
  handovers: "Shift Handover",
  corrective: "Corrective Maintenance",
  preventive: "Preventive Maintenance",
  permits: "Permit to Work & LoA",
  assets: "KKS Asset Directory",
  reports: "System Reports",
  users: "Users & Roles",
  logbookadmin: "Logbook Administration",
  audit: "Audit Trail",
  readiness: "Pilot Readiness",
  system: "System Status",
  kksimport: "KKS Register Import"
};

const cmptMatrix = {
  0: { A: 6, B: 6, C: 6, D: 6, E: 6 },
  1: { A: 6, B: 6, C: 5, D: 4, E: 3 },
  2: { A: 6, B: 5, C: 4, D: 3, E: 2 },
  3: { A: 5, B: 4, C: 3, D: 2, E: 1 },
  4: { A: 4, B: 3, C: 2, D: 1, E: 1 },
  5: { A: 3, B: 2, C: 1, D: 1, E: 1 }
};
const cmptCategoryLabels = {
  P: "People (Safety risk)",
  E: "Environmental",
  A: "Asset Damage / Production Loss",
  R: "Reputation / Personnel / Welfare"
};
const userRoles = [
  "Shift Leader", "Maintenance Approver", "Maintenance Planner",
  "C&I Technician", "Electrical Technician", "Mechanical Technician",
  "System Administrator"
];
const pageTitle = document.querySelector("#pageTitle");
const sidebar = document.querySelector("#sidebar");
let assets = [];
let logbooks = [];
let selectedEventId = null;
let selectedEvent = null;
let selectedHandoverId = null;
let selectedHandover = null;
let editingEventId = null;
let eventAutoRefreshTimer = null;
let selectedLogbookIds = new Set();
let selectedRequestId = null;
let selectedCorrective = null;
let editingWorkRequestId = null;
let scheduleTypes = [];
let recurrentGroupAssets = [];
let editingRecurrentId = null;
let selectedRecurrentId = null;
let selectedRecurrent = null;
let preventiveViewMode = "list";
let preventiveCalendarMonth = new Date(new Date().getFullYear(), new Date().getMonth(), 1);
let selectedPermitId = null;
let selectedPermit = null;
let users = [];
let adminLogbooks = [];
let readinessItems = [];
let editingLogbookId = null;
let currentUser = null;
let currentInfoboxUserId = null;
let infoboxSource = "";
let infoboxState = "active";
let infoboxScope = "my";
let infoboxGroup = "";
let infoboxSearchTimer = null;
let selectedAssetId = null;
let assetTab = "overview";
let assetTreeItems = [];
let assetSearchTimer = null;
let validatedKksImportId = null;
const assetPickerTimers = new WeakMap();

function escapeHtml(value) {
  return String(value ?? "").replace(/[&<>"']/g, character => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#039;"
  })[character]);
}

function formatDate(value) {
  if (!value) return "-";
  return new Intl.DateTimeFormat("en-GB", {
    day: "2-digit", month: "short", year: "numeric",
    hour: "2-digit", minute: "2-digit"
  }).format(new Date(value));
}

function formatFileSize(bytes) {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}

function renderAttachmentPanel(entityType, entityId, items = []) {
  const canDelete = currentUser?.role_name === "System Administrator";
  return `
    <section class="attachment-panel" data-attachment-panel="${entityType}:${entityId}">
      <div class="section-title"><strong>Attachments</strong><span>${items.length} files</span></div>
      <div class="attachment-upload">
        <input type="file" class="attachment-file" accept=".pdf,.png,.jpg,.jpeg,.webp,.doc,.docx,.xls,.xlsx,.csv,.txt">
        <button type="button" class="button secondary attachment-upload-button"><i data-lucide="upload"></i> Upload</button>
      </div>
      <div class="attachment-list">
        ${items.map(item => `
          <article>
            <i data-lucide="paperclip"></i>
            <div><a href="/api/attachments/file/${item.id}">${escapeHtml(item.original_name)}</a><small>${formatFileSize(item.file_size)} / ${escapeHtml(item.uploaded_by_name)} / ${formatDate(item.created_at)}</small></div>
            ${canDelete ? `<button type="button" class="icon-button compact-action" data-delete-attachment="${item.id}" title="Delete attachment" aria-label="Delete attachment"><i data-lucide="trash-2"></i></button>` : ""}
          </article>
        `).join("") || '<div class="empty-compact">No supporting files attached.</div>'}
      </div>
      <div class="attachment-message"></div>
    </section>
  `;
}

function renderPrintCommand(entityType, entityId) {
  return `<a class="button secondary print-record-button" href="/print/${entityType}/${entityId}" target="_blank" rel="noopener"><i data-lucide="printer"></i> Print record</a>`;
}

function bindAttachmentPanel(entityType, entityId, reload) {
  const panel = document.querySelector(`[data-attachment-panel="${entityType}:${entityId}"]`);
  if (!panel) return;
  panel.querySelector(".attachment-upload-button").addEventListener("click", async () => {
    const input = panel.querySelector(".attachment-file");
    const message = panel.querySelector(".attachment-message");
    if (!input.files.length) {
      message.textContent = "Select a file first.";
      return;
    }
    const form = new FormData();
    form.append("file", input.files[0]);
    message.textContent = "Uploading...";
    const response = await fetch(`/api/attachments/${entityType}/${entityId}`, {
      method: "POST",
      body: form
    });
    const result = await response.json();
    if (!response.ok) {
      message.textContent = result.error || "Unable to upload file";
      return;
    }
    await reload();
  });
  panel.querySelectorAll("[data-delete-attachment]").forEach(button => {
    button.addEventListener("click", async () => {
      const response = await fetch(`/api/attachments/${button.dataset.deleteAttachment}`, {
        method: "DELETE"
      });
      const result = await response.json();
      if (!response.ok) throw new Error(result.error || "Unable to delete attachment");
      await reload();
    });
  });
}

function assetPickerElement(id) {
  return document.querySelector(`[data-asset-picker="${id}"]`);
}

function setAssetPicker(id, asset = null, disabled = false) {
  const picker = assetPickerElement(id);
  if (!picker) return;
  const hidden = picker.querySelector('input[type="hidden"]');
  const input = picker.querySelector(".asset-picker-input");
  const clear = picker.querySelector(".asset-picker-clear");
  hidden.value = asset?.id || "";
  input.value = asset ? `${asset.kks_code} - ${asset.description}` : "";
  input.disabled = disabled;
  clear.disabled = disabled;
  picker.classList.toggle("has-value", Boolean(asset));
  picker.classList.toggle("disabled", disabled);
  picker.dataset.selectedAsset = asset ? JSON.stringify(asset) : "";
  picker.querySelector(".asset-picker-results").innerHTML = "";
}

function selectedAssetIdFromPicker(id) {
  return Number(document.querySelector(`#${id}`).value || 0);
}

function selectedAssetFromPicker(id) {
  const picker = assetPickerElement(id);
  return picker?.dataset.selectedAsset ? JSON.parse(picker.dataset.selectedAsset) : null;
}

function renderAssetPickerResults(picker, items) {
  const results = picker.querySelector(".asset-picker-results");
  results.innerHTML = items.map(item => `
    <button type="button" class="asset-picker-result" data-picker-asset-id="${item.id}">
      <span><code>${escapeHtml(item.kks_code)}</code><strong>${escapeHtml(item.description)}</strong></span>
      <small>${escapeHtml(item.responsible_area || "Unassigned")} / ${escapeHtml(item.hierarchy_level)}</small>
    </button>
  `).join("") || '<div class="asset-picker-empty">No matching KKS records.</div>';
  results.classList.add("open");
  results.querySelectorAll("[data-picker-asset-id]").forEach(button => {
    button.addEventListener("click", () => {
      const asset = items.find(item => item.id === Number(button.dataset.pickerAssetId));
      setAssetPicker(picker.dataset.assetPicker, asset);
    });
  });
}

async function searchAssetPicker(picker, query) {
  const results = picker.querySelector(".asset-picker-results");
  if (query.length < 2) {
    results.innerHTML = '<div class="asset-picker-empty">Enter at least two characters.</div>';
    results.classList.add("open");
    return;
  }
  results.innerHTML = '<div class="asset-picker-empty">Searching KKS register...</div>';
  results.classList.add("open");
  const response = await fetch(`/api/assets?q=${encodeURIComponent(query)}&limit=40`);
  if (!response.ok) throw new Error("Unable to search KKS register");
  renderAssetPickerResults(picker, await response.json());
}

function initializeAssetPickers() {
  document.querySelectorAll("[data-asset-picker]").forEach(picker => {
    const input = picker.querySelector(".asset-picker-input");
    const hidden = picker.querySelector('input[type="hidden"]');
    const results = picker.querySelector(".asset-picker-results");
    input.addEventListener("input", () => {
      hidden.value = "";
      picker.classList.remove("has-value");
      window.clearTimeout(assetPickerTimers.get(picker));
      const timer = window.setTimeout(() => {
        searchAssetPicker(picker, input.value.trim()).catch(error => {
          results.innerHTML = `<div class="asset-picker-empty error">${escapeHtml(error.message)}</div>`;
          results.classList.add("open");
        });
      }, 250);
      assetPickerTimers.set(picker, timer);
    });
    input.addEventListener("focus", () => {
      if (results.innerHTML) results.classList.add("open");
    });
    picker.querySelector(".asset-picker-clear").addEventListener("click", () => {
      setAssetPicker(picker.dataset.assetPicker);
      input.focus();
    });
  });
  document.addEventListener("click", event => {
    document.querySelectorAll(".asset-picker-results.open").forEach(results => {
      if (!results.parentElement.contains(event.target)) results.classList.remove("open");
    });
  });
}

function localDateTimeValue() {
  const now = new Date();
  now.setMinutes(now.getMinutes() - now.getTimezoneOffset());
  return now.toISOString().slice(0, 16);
}

function openView(name, updateHash = true) {
  if (!views[name]) name = "dashboard";
  Object.values(views).forEach(view => view.classList.remove("active"));
  views[name].classList.add("active");
  pageTitle.textContent = pageTitles[name];
  document.querySelectorAll(".nav-item[data-view]").forEach(button => {
    button.classList.toggle("active", button.dataset.view === name);
  });
  sidebar.classList.remove("open");
  if (name === "dashboard") loadDashboard().catch(showGlobalError);
  if (name === "infobox") loadInfobox().catch(showInfoboxError);
  if (name === "events") loadEvents().catch(showEventError);
  if (name === "handovers") loadShiftHandovers().catch(showHandoverError);
  if (name === "corrective") loadCorrective().catch(showCorrectiveError);
  if (name === "preventive") loadPreventive().catch(showPreventiveError);
  if (name === "permits") loadSafetyPermits().catch(showSafetyPermitError);
  if (name === "assets") loadAssetWorkspace().catch(showAssetError);
  if (name === "reports") loadReports().catch(showReportError);
  if (name === "users") loadUsers().catch(showUserAdminError);
  if (name === "logbookadmin") loadAdminLogbooks().catch(showLogbookAdminError);
  if (name === "audit") loadAuditLogs().catch(showAuditError);
  if (name === "readiness") loadReadiness().catch(showReadinessError);
  if (name === "system") loadSystemStatus().catch(showSystemError);
  if (name === "kksimport") loadKksImports().catch(showKksImportError);
  if (updateHash && window.location.hash !== `#${name}`) {
    window.history.replaceState(null, "", `#${name}`);
  }
}

async function loadFoundation() {
  const [assetsResponse, logbooksResponse, meResponse] = await Promise.all([
    fetch("/api/assets?reference=1"), fetch("/api/logbooks"), fetch("/api/me")
  ]);
  if (!assetsResponse.ok || !logbooksResponse.ok || !meResponse.ok) throw new Error("Unable to load S-PULSE master data");
  assets = await assetsResponse.json();
  logbooks = await logbooksResponse.json();
  currentUser = await meResponse.json();
  currentInfoboxUserId = currentUser.id;
  populateMasterData();
  applyRolePermissions();
  initializeReportDates();
  openView(window.location.hash.slice(1) || "dashboard", false);
}

function populateMasterData() {
  renderLogbookFilter();
  document.querySelector("#entryLogbook").innerHTML = logbooks
    .filter(canCreateLogbookEntry)
    .map(item => `<option value="${item.id}">${escapeHtml(item.name)}</option>`).join("");
}

function renderLogbookFilter() {
  const menu = document.querySelector("#logbookFilterMenu");
  menu.innerHTML = logbooks.map(item => `
    <label><input type="checkbox" value="${item.id}" ${selectedLogbookIds.has(item.id) ? "checked" : ""}><span>${escapeHtml(item.name)}</span></label>
  `).join("");
  menu.querySelectorAll('input[type="checkbox"]').forEach(input => {
    input.addEventListener("change", () => {
      const id = Number(input.value);
      if (input.checked) selectedLogbookIds.add(id);
      else selectedLogbookIds.delete(id);
      updateLogbookFilterLabel();
      loadEvents().catch(showEventError);
    });
  });
  updateLogbookFilterLabel();
}

function updateLogbookFilterLabel() {
  const selected = logbooks.filter(item => selectedLogbookIds.has(item.id));
  document.querySelector("#logbookFilterButton span").textContent =
    !selected.length ? "All logbooks" :
      selected.length === 1 ? selected[0].name : `${selected.length} logbooks`;
}

function applyRolePermissions() {
  const role = currentUser.role_name;
  const isAdministrator = role === "System Administrator";
  const canPlan = isAdministrator || role === "Maintenance Planner";
  const isShiftLeader = isAdministrator || role === "Shift Leader";
  const canCreateEvent = logbooks.some(canCreateLogbookEntry);
  document.querySelector("#newScheduleType").hidden = !canPlan;
  document.querySelector("#newRecurrentTask").hidden = !canPlan;
  document.querySelector("#generatePreventiveMonth").hidden = !canPlan;
  document.querySelector("#newSafetyPermit").hidden = !isShiftLeader;
  document.querySelector("#newMainEntry").hidden = !canCreateEvent;
  document.querySelector("#dashboardNewEntry").hidden = !canCreateEvent;
  document.querySelectorAll(".admin-navigation").forEach(item => {
    item.hidden = !isAdministrator;
  });
}

function hasRole(...roles) {
  return currentUser?.role_name === "System Administrator" ||
    roles.includes(currentUser?.role_name);
}

function canCreateLogbookEntry(logbook) {
  return hasRole("Shift Leader") ||
    currentUser?.role_name === logbook.can_create_role ||
    currentUser?.department === logbook.can_create_role;
}

function executionRoleForDepartment(department) {
  return {
    "Control & Instrumentation": "C&I Technician",
    "Electrical Maintenance": "Electrical Technician",
    "Mechanical Maintenance": "Mechanical Technician",
    "Operations": "Shift Leader"
  }[department] || "Maintenance Planner";
}

function canPerformOrderAction(item, action) {
  const roles = {
    submit_plan: ["Maintenance Planner"],
    approve_plan: ["Maintenance Approver"],
    return_plan: ["Maintenance Approver"],
    confirm_execution: ["Shift Leader"],
    complete_work: [executionRoleForDepartment(item.main_department)],
    accept_work: ["Maintenance Approver"],
    deny_acceptance: ["Maintenance Approver"],
    resubmit_work: ["Maintenance Planner"]
  }[action] || [];
  return hasRole(...roles);
}

async function loadDashboard() {
  const [summaryResponse, eventsResponse] = await Promise.all([
    fetch("/api/dashboard"), fetch("/api/events")
  ]);
  if (!summaryResponse.ok || !eventsResponse.ok) throw new Error("Unable to load dashboard");
  const summary = await summaryResponse.json();
  const events = await eventsResponse.json();
  document.querySelector("#openEvents").textContent = summary.open_events;
  document.querySelector("#eventsToday").textContent = summary.events_today;
  document.querySelector("#activeAssets").textContent = summary.active_assets;
  document.querySelector("#logbookCount").textContent = summary.logbooks;
  document.querySelector("#openEventBadge").textContent = summary.open_events;
  document.querySelector("#requestBadge").textContent = summary.pending_requests || 0;
  document.querySelector("#preventiveBadge").textContent = summary.preventive_due || 0;
  document.querySelector("#permitBadge").textContent = summary.active_permits || 0;
  document.querySelector("#infoboxBadge").textContent = summary.my_infobox || 0;
  const readinessPanel = document.querySelector("#dashboardReadinessPanel");
  readinessPanel.hidden = !summary.readiness;
  if (summary.readiness) {
    document.querySelector("#dashboardReadinessDone").textContent = summary.readiness.done || 0;
    document.querySelector("#dashboardReadinessBlocked").textContent = summary.readiness.blocked || 0;
    document.querySelector("#dashboardReadinessPending").textContent = summary.readiness.pending || 0;
    document.querySelector("#dashboardReadinessPercent").textContent = `${summary.readiness.completion_percent || 0}%`;
    document.querySelector("#dashboardReadinessHint").textContent =
      `${summary.readiness.total || 0} checks tracked. Blocked items need S-PULSE owner approval.`;
  }
  document.querySelector("#recentEvents").innerHTML = events.slice(0, 6).map(item => `
    <article class="recent-event">
      <div><code>${escapeHtml(item.entry_no)}</code><small>${formatDate(item.event_date)}</small></div>
      <div><strong>${escapeHtml(item.subject)}</strong><small>${escapeHtml(item.kks_code || item.source_logbook_name)}</small></div>
      <span class="state-pill ${escapeHtml(item.state)}">${escapeHtml(item.state)}</span>
    </article>
  `).join("") || '<div class="empty-list">No event entries are available.</div>';
  lucide.createIcons();
}

function infoboxQueryString() {
  const parameters = new URLSearchParams();
  parameters.set("state", infoboxState);
  parameters.set("scope", infoboxScope);
  if (infoboxSource) parameters.set("source_type", infoboxSource);
  if (infoboxGroup) parameters.set("group_id", infoboxGroup);
  const query = document.querySelector("#infoboxSearch").value.trim();
  if (query) parameters.set("q", query);
  const timing = document.querySelector("#infoboxTiming").value;
  if (timing) parameters.set("timing", timing);
  const priority = document.querySelector("#infoboxPriority").value;
  if (priority) parameters.set("priority", priority);
  return `?${parameters.toString()}`;
}

function updateInfoboxDownloadLink() {
  document.querySelector("#downloadInfoboxHistory").href =
    `/api/infobox/history.csv${infoboxQueryString()}`;
}

function renderTeamWorkload(workload) {
  const container = document.querySelector("#teamWorkload");
  container.hidden = infoboxScope !== "team";
  if (container.hidden) return;
  const totals = workload.reduce((result, group) => ({
    active: result.active + (group.active || 0),
    available: result.available + (group.available || 0),
    claimed: result.claimed + (group.claimed || 0),
    overdue: result.overdue + (group.overdue || 0)
  }), { active: 0, available: 0, claimed: 0, overdue: 0 });
  const choices = [
    { id: "", name: "All teams", ...totals },
    ...workload
  ];
  container.innerHTML = choices.map(group => `
    <button class="team-workload-item ${String(group.id) === infoboxGroup ? "active" : ""}"
      data-workload-group="${group.id}" type="button">
      <span>${escapeHtml(group.name)}</span>
      <strong>${group.active || 0}</strong>
      <small>${group.available || 0} available / ${group.claimed || 0} claimed</small>
      ${group.overdue ? `<b>${group.overdue} overdue</b>` : '<b class="clear">On target</b>'}
    </button>
  `).join("");
  container.querySelectorAll("[data-workload-group]").forEach(button => {
    button.addEventListener("click", () => {
      infoboxGroup = button.dataset.workloadGroup;
      document.querySelector("#infoboxGroup").value = infoboxGroup;
      loadInfobox().catch(showInfoboxError);
    });
  });
}

async function loadInfobox() {
  const list = document.querySelector("#infoboxList");
  list.innerHTML = '<div class="loading">Loading personal tasks...</div>';
  const [itemsResponse, summaryResponse, workloadResponse] = await Promise.all([
    fetch(`/api/infobox${infoboxQueryString()}`),
    fetch(`/api/infobox/summary${infoboxQueryString()}`),
    fetch("/api/infobox/workload")
  ]);
  if (!itemsResponse.ok || !summaryResponse.ok || !workloadResponse.ok) throw new Error("Unable to load Infobox");
  const items = await itemsResponse.json();
  const summary = await summaryResponse.json();
  const workload = await workloadResponse.json();
  const groupSelect = document.querySelector("#infoboxGroup");
  groupSelect.hidden = infoboxScope !== "team";
  groupSelect.innerHTML = '<option value="">All responsibility groups</option>' +
    workload.map(group => `<option value="${group.id}">${escapeHtml(group.name)} (${group.active || 0})</option>`).join("");
  groupSelect.value = infoboxGroup;
  renderTeamWorkload(workload);
  document.querySelector("#infoboxTotal").textContent = summary.total || 0;
  document.querySelector("#infoboxHigh").textContent = summary.high_priority || 0;
  document.querySelector("#infoboxClaimed").textContent = summary.claimed || 0;
  document.querySelector("#infoboxOverdue").textContent = summary.overdue || 0;
  document.querySelector("#infoboxEscalated").textContent = summary.escalated || 0;
  document.querySelector("#infoboxCriticalEscalations").textContent = `${summary.critical_escalations || 0} at level 3`;
  document.querySelector("#infoboxCompletedCount").textContent = summary.completed || 0;
  document.querySelector("#infoboxBadge").textContent = summary.total || 0;
  document.querySelector("#infoboxTotalLabel").textContent =
    infoboxScope === "team" ? "Team open items" : "My open items";
  document.querySelector("#infoboxTotalHint").textContent =
    infoboxScope === "team" ? "Available or taken by the team" : "Available or claimed by me";
  document.querySelector("#infoboxClaimedLabel").textContent =
    infoboxScope === "team" ? "Claimed by team" : "Claimed by me";
  updateInfoboxDownloadLink();
  renderInfobox(items);
}

function sourceLabel(source) {
  return {
    work_request: "Work Request",
    work_order: "Work Order",
    preventive_task: "Preventive",
    permit: "Safety Permit",
    event: "Event",
    shift_handover: "Shift Handover"
  }[source] || source;
}

function dueStateLabel(state) {
  return {
    overdue: "Overdue",
    due_today: "Due today",
    upcoming: "Upcoming",
    no_target: "No target",
    completed: "Completed"
  }[state] || state;
}

function renderInfobox(items) {
  const list = document.querySelector("#infoboxList");
  if (!items.length) {
    list.innerHTML = `<div class="empty-list">No ${infoboxScope === "team" ? "team" : "personal"} workflow actions are available.</div>`;
    return;
  }
  list.innerHTML = items.map(item => `
    <article class="infobox-row ${item.status === "claimed" ? "claimed" : ""} ${escapeHtml(item.due_state)} escalation-${item.escalation_level || 0}">
      <span class="inbox-priority ${escapeHtml(item.priority)}">${escapeHtml(item.priority)}</span>
      <div><strong>${escapeHtml(item.title)}</strong><small>${escapeHtml(item.description)} / ${escapeHtml(sourceLabel(item.source_type))}</small></div>
      <div><strong>${escapeHtml(item.responsible_group_name)}</strong><small>${item.claimed_by_name ? `Taken by ${escapeHtml(item.claimed_by_name)}` : "Shared assignment"}</small></div>
      <div><strong>${item.status === "completed" ? formatDate(item.completed_at) : item.due_at ? formatDate(item.due_at) : "No target"}</strong><small class="due-state ${escapeHtml(item.due_state)}">${escapeHtml(dueStateLabel(item.due_state))} / ${item.age_hours || 0}h open</small>${item.escalation_level ? `<small class="escalation-label">Escalation level ${item.escalation_level}</small>` : ""}</div>
      <span class="inbox-state ${escapeHtml(item.status)}">${escapeHtml(item.status)}</span>
      <div class="inbox-actions">
        ${item.status === "open" ? `<button class="icon-button compact-action" data-claim-inbox="${item.id}" data-target-view="${escapeHtml(item.target_view)}" data-target-id="${item.target_id ?? ""}" title="Take and open action" aria-label="Take and open action"><i data-lucide="hand"></i></button>` : item.status === "claimed" && item.claimed_by === currentUser.id ? `<button class="icon-button compact-action" data-release-inbox="${item.id}" title="Release action" aria-label="Release action"><i data-lucide="undo-2"></i></button>` : ""}
        <button class="icon-button compact-action" data-open-target="${escapeHtml(item.target_view)}:${item.target_id ?? ""}" title="Open source" aria-label="Open source"><i data-lucide="arrow-up-right"></i></button>
        <button class="icon-button compact-action" data-inbox-history="${item.id}" title="Responsibility history" aria-label="Responsibility history"><i data-lucide="history"></i></button>
      </div>
      <div class="infobox-history" data-inbox-history-panel="${item.id}" hidden></div>
    </article>
  `).join("");
  list.querySelectorAll("[data-claim-inbox]").forEach(button => {
    button.addEventListener("click", () => claimAndOpenInfoboxItem(
      Number(button.dataset.claimInbox),
      button.dataset.targetView,
      Number(button.dataset.targetId)
    ).catch(showInfoboxError));
  });
  list.querySelectorAll("[data-release-inbox]").forEach(button => {
    button.addEventListener("click", () => releaseInfoboxItem(Number(button.dataset.releaseInbox)).catch(showInfoboxError));
  });
  list.querySelectorAll("[data-open-target]").forEach(button => {
    button.addEventListener("click", () => {
      const [targetView, targetId] = button.dataset.openTarget.split(":");
      openInfoboxTarget(targetView, Number(targetId));
    });
  });
  list.querySelectorAll("[data-inbox-history]").forEach(button => {
    button.addEventListener("click", () => toggleInfoboxHistory(
      Number(button.dataset.inboxHistory)
    ).catch(showInfoboxError));
  });
  lucide.createIcons();
}

async function claimInfoboxItem(itemId, reload = true) {
  const response = await fetch(`/api/infobox/${itemId}/claim`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({})
  });
  const result = await response.json();
  if (!response.ok) throw new Error(result.error || "Unable to take Infobox item");
  if (reload) await loadInfobox();
  return result;
}

async function claimAndOpenInfoboxItem(itemId, targetView, targetId) {
  await claimInfoboxItem(itemId, false);
  openInfoboxTarget(targetView, targetId);
}

async function releaseInfoboxItem(itemId) {
  const response = await fetch(`/api/infobox/${itemId}/release`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({})
  });
  const result = await response.json();
  if (!response.ok) throw new Error(result.error || "Unable to release Infobox item");
  await loadInfobox();
}

function openInfoboxTarget(targetView, targetId) {
  if (!views[targetView] || !targetId) throw new Error("Infobox source is unavailable");
  if (targetView === "events") selectedEventId = targetId;
  if (targetView === "corrective") selectedRequestId = targetId;
  if (targetView === "preventive") selectedRecurrentId = targetId;
  if (targetView === "permits") selectedPermitId = targetId;
  if (targetView === "handovers") selectedHandoverId = targetId;
  openView(targetView);
}

async function toggleInfoboxHistory(itemId) {
  const panel = document.querySelector(`[data-inbox-history-panel="${itemId}"]`);
  if (!panel.hidden) {
    panel.hidden = true;
    return;
  }
  panel.hidden = false;
  panel.innerHTML = '<div class="loading">Loading responsibility history...</div>';
  const response = await fetch(`/api/infobox/${itemId}/history`);
  const history = await response.json();
  if (!response.ok) throw new Error(history.error || "Unable to load responsibility history");
  panel.innerHTML = history.length ? history.map(entry => `
    <div class="infobox-history-entry">
      <i data-lucide="${entry.action === "claimed" ? "hand" : entry.action === "released" ? "undo-2" : entry.action === "completed" ? "check" : entry.action === "escalated" ? "triangle-alert" : entry.action === "reset" ? "rotate-ccw" : "users"}"></i>
      <strong>${escapeHtml(entry.action)}</strong>
      <span>${escapeHtml(entry.user_name || "S-PULSE workflow")}</span>
      <small>${escapeHtml(entry.details || "")}</small>
      <time>${formatDate(entry.created_at)}</time>
    </div>
  `).join("") : '<div class="empty-list">No responsibility history recorded.</div>';
  lucide.createIcons();
}

function showInfoboxError(error) {
  document.querySelector("#infoboxList").innerHTML = `<div class="error">${escapeHtml(error.message)}</div>`;
}

function eventQueryString() {
  const parameters = new URLSearchParams();
  const values = {
    q: document.querySelector("#eventSearch").value.trim(),
    logbook_ids: [...selectedLogbookIds].sort((a, b) => a - b).join(","),
    start: document.querySelector("#startDate").value,
    end: document.querySelector("#endDate").value,
    state: document.querySelector("#stateFilter").value
  };
  Object.entries(values).forEach(([key, value]) => {
    if (value) parameters.set(key, value);
  });
  const query = parameters.toString();
  return query ? `?${query}` : "";
}

async function loadEvents() {
  const list = document.querySelector("#eventList");
  list.innerHTML = '<div class="loading">Loading event log...</div>';
  const query = eventQueryString();
  const response = await fetch(`/api/events${query}`);
  if (!response.ok) throw new Error("Unable to load event log");
  const events = await response.json();
  document.querySelector("#downloadEventLog").href = `/api/events.csv${query}`;
  document.querySelector("#printShiftHandover").href = `/print/shift-handover${query}`;
  document.querySelector("#eventLastRefresh").textContent =
    `Updated ${new Intl.DateTimeFormat("en-GB", { hour: "2-digit", minute: "2-digit", second: "2-digit" }).format(new Date())}`;
  renderEvents(events);
  if (selectedEventId && events.some(item => item.id === selectedEventId)) {
    await selectEvent(selectedEventId);
  } else if (events.length) {
    await selectEvent(events[0].id);
  } else {
    selectedEventId = null;
    selectedEvent = null;
    renderEmptyDetail();
  }
}

function eventDateValue(value) {
  const dateValue = new Date(value);
  dateValue.setMinutes(dateValue.getMinutes() - dateValue.getTimezoneOffset());
  return dateValue.toISOString().slice(0, 10);
}

function setEventDateRange(start, end) {
  document.querySelector("#startDate").value = eventDateValue(start);
  document.querySelector("#endDate").value = eventDateValue(end);
  loadEvents().catch(showEventError);
}

function shiftEventDateRange(direction) {
  const today = new Date();
  today.setHours(0, 0, 0, 0);
  const startInput = document.querySelector("#startDate").value;
  const endInput = document.querySelector("#endDate").value;
  const end = endInput ? new Date(`${endInput}T00:00:00`) : new Date(today);
  const start = startInput ? new Date(`${startInput}T00:00:00`) : new Date(end);
  const spanDays = Math.max(0, Math.round((end - start) / 86400000));
  const movement = spanDays + 1;
  start.setDate(start.getDate() + direction * movement);
  end.setDate(end.getDate() + direction * movement);
  if (end > today) {
    end.setTime(today.getTime());
    start.setTime(today.getTime());
    start.setDate(start.getDate() - spanDays);
  }
  setEventDateRange(start, end);
}

function setEventAutoRefresh(enabled) {
  const button = document.querySelector("#toggleEventAutoRefresh");
  window.clearInterval(eventAutoRefreshTimer);
  eventAutoRefreshTimer = null;
  button.classList.toggle("active", enabled);
  button.setAttribute("aria-pressed", String(enabled));
  button.querySelector("span").textContent = `Auto-refresh ${enabled ? "on" : "off"}`;
  if (enabled) {
    eventAutoRefreshTimer = window.setInterval(() => {
      if (views.events.classList.contains("active")) {
        loadEvents().catch(showEventError);
      }
    }, 30000);
  }
}

function renderEvents(events) {
  const list = document.querySelector("#eventList");
  if (!events.length) {
    list.innerHTML = '<div class="empty-list">No entries match the selected criteria.</div>';
    return;
  }
  list.innerHTML = events.map(item => `
    <article class="event-row ${item.id === selectedEventId ? "selected" : ""}" data-event-id="${item.id}">
      <div><code>${escapeHtml(item.entry_no)}</code><small>${formatDate(item.event_date)}${item.parent_id ? " / Sub-entry" : ""}</small></div>
      <div><strong>${escapeHtml(item.subject)}</strong><small>${escapeHtml(item.observation.slice(0, 115))}${item.observation.length > 115 ? "..." : ""} / ${item.comment_count} comments</small></div>
      <div><code>${escapeHtml(item.kks_code || "-")}</code><small>${escapeHtml(item.asset_description || item.source_logbook_name)}</small></div>
      <span class="state-pill ${escapeHtml(item.state)}">${escapeHtml(item.state)}</span>
      <button class="row-arrow" aria-label="Open entry"><i data-lucide="chevron-right"></i></button>
    </article>
  `).join("");
  list.querySelectorAll("[data-event-id]").forEach(row => {
    row.addEventListener("click", () => selectEvent(Number(row.dataset.eventId)).catch(showEventError));
  });
  lucide.createIcons();
}

async function selectEvent(id) {
  const response = await fetch(`/api/events/${id}`);
  if (!response.ok) throw new Error("Unable to load event details");
  selectedEvent = await response.json();
  selectedEventId = id;
  document.querySelectorAll("[data-event-id]").forEach(row => {
    row.classList.toggle("selected", Number(row.dataset.eventId) === id);
  });
  const sourceLogbook = logbooks.find(item => item.id === selectedEvent.source_logbook_id);
  document.querySelector("#newSubEntry").disabled =
    Boolean(selectedEvent.parent_id) || !sourceLogbook ||
    !canCreateLogbookEntry(sourceLogbook);
  renderEventDetail();
}

function renderEventDetail() {
  const item = selectedEvent;
  const sourceLogbook = logbooks.find(value => value.id === item.source_logbook_id);
  const canChangeState = !item.parent_id && sourceLogbook &&
    canCreateLogbookEntry(sourceLogbook);
  const canEdit = sourceLogbook && canCreateLogbookEntry(sourceLogbook);
  const nextState = item.state === "open" ? "closed" : "open";
  document.querySelector("#eventDetail").innerHTML = `
    <div class="detail-header">
      <div class="detail-title-row"><code>${escapeHtml(item.entry_no)}</code>${renderPrintCommand("event", item.id)}</div>
      <h3>${escapeHtml(item.subject)}</h3>
      <p>${escapeHtml(item.observation)}</p>
    </div>
    <div class="detail-meta">
      <div><span>Logbook</span><strong>${escapeHtml(item.source_logbook_name)}</strong></div>
      <div><span>State</span><strong>${escapeHtml(item.state)}</strong></div>
      <div><span>Asset</span><strong>${escapeHtml(item.kks_code || "No asset")}</strong></div>
      <div><span>Event date</span><strong>${formatDate(item.event_date)}</strong></div>
      <div><span>Informant</span><strong>${escapeHtml(item.informant || "-")}</strong></div>
      <div><span>Created by</span><strong>${escapeHtml(item.created_by)}</strong></div>
    </div>
    <div class="comments-heading"><strong>Sub-entries</strong><span>${item.comments.length} comments</span></div>
    <div class="comment-list">
      ${item.comments.map(comment => `
        <article class="comment">
          <strong>${escapeHtml(comment.entry_no)} / ${escapeHtml(comment.created_by)}</strong>
          <p>${escapeHtml(comment.observation)}</p>
          <small>${formatDate(comment.created_at)}</small>
        </article>
      `).join("") || '<div class="empty-list">No sub-entries recorded.</div>'}
    </div>
    <div class="comments-heading"><strong>State history</strong><span>${item.state_history.length} changes</span></div>
    <div class="comment-list">
      ${item.state_history.map(change => `
        <article class="comment">
          <strong>${escapeHtml(change.previous_state)} to ${escapeHtml(change.new_state)} / ${escapeHtml(change.changed_by)}</strong>
          <p>${escapeHtml(change.reason)}</p>
          <small>${formatDate(change.created_at)}</small>
        </article>
      `).join("") || '<div class="empty-list">No state changes recorded.</div>'}
    </div>
    <div class="comments-heading"><strong>Edit history</strong><span>${item.edit_history.length} revisions</span></div>
    <div class="comment-list">
      ${item.edit_history.map(change => `
        <article class="comment">
          <strong>${escapeHtml(change.changed_by)}</strong>
          <p>${escapeHtml(Object.keys(change.changes).map(field => field.replaceAll("_", " ")).join(", "))}</p>
          <small>${formatDate(change.created_at)}</small>
        </article>
      `).join("") || '<div class="empty-list">No corrections recorded.</div>'}
    </div>
    <div class="comments-heading"><strong>Corrective maintenance</strong><span>${item.work_requests.length} requests</span></div>
    <div class="comment-list">
      ${item.work_requests.map(work => `
        <article class="comment">
          <strong>${escapeHtml(work.request_no)} / ${escapeHtml(work.status)}</strong>
          <p>${escapeHtml(work.name)}</p>
          <small>${escapeHtml(work.main_department)} / Priority ${work.priority}</small>
        </article>
      `).join("") || '<div class="empty-list">No corrective request linked.</div>'}
    </div>
    ${renderAttachmentPanel("event", item.id, item.attachments)}
    ${(canEdit || canChangeState || (!item.parent_id && item.state === "open" && item.asset_id && !item.work_requests.length)) ? `<div class="corrective-actions">
      ${canEdit ? '<button class="button secondary" id="editEventEntry"><i data-lucide="pencil"></i>Edit entry</button>' : ""}
      ${canEdit ? '<button class="button danger-button" id="deleteEventEntry"><i data-lucide="trash-2"></i>Delete entry</button>' : ""}
      ${!item.parent_id && item.state === "open" && item.asset_id && !item.work_requests.length ? '<button class="button secondary" id="createRequestFromEvent"><i data-lucide="wrench"></i>Create work request</button>' : ""}
      ${canChangeState ? `<button class="button ${nextState === "closed" ? "primary" : "secondary"}" id="changeEventState" data-event-state="${nextState}"><i data-lucide="${nextState === "closed" ? "check-circle-2" : "rotate-ccw"}"></i>${nextState === "closed" ? "Close event" : "Reopen event"}</button>` : ""}
    </div>` : ""}
  `;
  document.querySelector("#createRequestFromEvent")?.addEventListener("click", () => {
    openWorkRequestModal(item);
  });
  document.querySelector("#editEventEntry")?.addEventListener("click", () => {
    openEntryModal(null, item);
  });
  document.querySelector("#deleteEventEntry")?.addEventListener("click", openDeleteEventModal);
  document.querySelector("#changeEventState")?.addEventListener("click", () => {
    changeEventState(nextState).catch(showEventError);
  });
  bindAttachmentPanel("event", item.id, () => selectEvent(item.id));
  lucide.createIcons();
}

async function changeEventState(state) {
  const reason = window.prompt(
    state === "closed" ? "Reason for closing this event:" : "Reason for reopening this event:"
  );
  if (!reason?.trim()) return;
  const response = await fetch(`/api/events/${selectedEventId}/state`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ state, reason: reason.trim() })
  });
  const result = await response.json();
  if (!response.ok) throw new Error(result.error || "Unable to change event state");
  selectedEvent = result;
  await Promise.all([loadEvents(), loadDashboard()]);
}

function renderEmptyDetail() {
  document.querySelector("#eventDetail").innerHTML =
    '<div class="empty-detail"><i data-lucide="notebook-tabs"></i><strong>Select an event entry</strong><p>Attributes and sub-entries will appear here.</p></div>';
  document.querySelector("#newSubEntry").disabled = true;
  lucide.createIcons();
}

async function loadShiftHandovers() {
  const status = document.querySelector("#handoverStatusFilter").value;
  const response = await fetch(`/api/shift-handovers${status ? `?status=${encodeURIComponent(status)}` : ""}`);
  if (!response.ok) throw new Error("Unable to load shift handovers");
  const items = await response.json();
  document.querySelector("#newShiftHandover").hidden = !hasRole("Shift Leader");
  document.querySelector("#handoverList").innerHTML = items.map(item => `
    <article class="handover-row ${item.id === selectedHandoverId ? "selected" : ""}" data-handover-id="${item.id}">
      <div><code>${escapeHtml(item.handover_no)}</code><small>${escapeHtml(item.shift_date)}</small></div>
      <div><strong>${escapeHtml(item.shift_name)}</strong><small>${escapeHtml(item.outgoing_name)}${item.incoming_name ? ` to ${escapeHtml(item.incoming_name)}` : ""} / ${item.event_count} entries</small></div>
      <span class="request-pill ${escapeHtml(item.status)}">${escapeHtml(item.status)}</span><i data-lucide="chevron-right"></i>
    </article>`).join("") || '<div class="empty-list">No shift handovers match this state.</div>';
  document.querySelectorAll("[data-handover-id]").forEach(row => row.addEventListener("click", () => selectShiftHandover(Number(row.dataset.handoverId)).catch(showHandoverError)));
  if (!selectedHandoverId && items.length) await selectShiftHandover(items[0].id);
  if (!items.length) {
    selectedHandoverId = null; selectedHandover = null;
    document.querySelector("#handoverDetail").innerHTML = '<div class="empty-detail"><i data-lucide="arrow-left-right"></i><strong>No handover selected</strong><p>Create a handover or change the state filter.</p></div>';
  }
  lucide.createIcons();
}

async function selectShiftHandover(id) {
  const response = await fetch(`/api/shift-handovers/${id}`);
  if (!response.ok) throw new Error("Unable to load shift handover detail");
  selectedHandover = await response.json(); selectedHandoverId = id;
  document.querySelectorAll("[data-handover-id]").forEach(row => row.classList.toggle("selected", Number(row.dataset.handoverId) === id));
  renderShiftHandoverDetail();
}

function renderShiftHandoverDetail() {
  const item = selectedHandover;
  const canSubmit = hasRole("Shift Leader") && item.status === "draft" && item.outgoing_user_id === currentUser.id;
  const canAccept = hasRole("Shift Leader") && item.status === "submitted" && item.outgoing_user_id !== currentUser.id;
  document.querySelector("#handoverDetail").innerHTML = `
    <div class="handover-detail-header"><code>${escapeHtml(item.handover_no)}</code><h3>${escapeHtml(item.shift_name)} / ${escapeHtml(item.shift_date)}</h3><span class="request-pill ${escapeHtml(item.status)}">${escapeHtml(item.status)}</span></div>
    <div class="handover-detail-section handover-detail-grid"><div><span>Outgoing Shift Leader</span><strong>${escapeHtml(item.outgoing_name)}</strong></div><div><span>Incoming Shift Leader</span><strong>${escapeHtml(item.incoming_name || "Awaiting acceptance")}</strong></div><div><span>Submitted</span><strong>${formatDate(item.submitted_at)}</strong></div><div><span>Accepted</span><strong>${formatDate(item.accepted_at)}</strong></div></div>
    <div class="handover-detail-section"><div class="section-title"><strong>Handover summary</strong></div><p>${escapeHtml(item.summary)}</p></div>
    <div class="handover-detail-section handover-detail-grid"><div><span>Operational notes</span><strong>${escapeHtml(item.operational_notes || "None recorded")}</strong></div><div><span>Safety notes</span><strong>${escapeHtml(item.safety_notes || "None recorded")}</strong></div>${item.acceptance_notes ? `<div class="span-2"><span>Acceptance notes</span><strong>${escapeHtml(item.acceptance_notes)}</strong></div>` : ""}</div>
    <div class="handover-detail-section"><div class="section-title"><strong>Event Log entries</strong><span>${item.events.length}</span></div>${item.events.map(entry => `<article class="handover-event"><div><code>${escapeHtml(entry.entry_no)}</code><small>${escapeHtml(entry.state_at_handover)} at handover</small></div><div><strong>${escapeHtml(entry.subject)}</strong><small>${escapeHtml(entry.kks_code || "No KKS")} / ${escapeHtml(entry.logbook_name)}</small></div><span class="request-pill ${escapeHtml(entry.current_state)}">${escapeHtml(entry.current_state)}</span></article>`).join("") || '<div class="empty-compact">No entries selected.</div>'}</div>
    <div class="handover-actions"><a class="button secondary" href="/print/shift-handover/${item.id}" target="_blank" rel="noopener"><i data-lucide="printer"></i> Print</a>${canSubmit ? '<button class="button primary" id="submitShiftHandover"><i data-lucide="send"></i> Submit handover</button>' : ""}${canAccept ? '<button class="button primary" id="acceptShiftHandover"><i data-lucide="check-circle-2"></i> Accept handover</button>' : ""}</div>`;
  document.querySelector("#submitShiftHandover")?.addEventListener("click", () => updateShiftHandover("submit").catch(showHandoverError));
  document.querySelector("#acceptShiftHandover")?.addEventListener("click", () => { const notes = window.prompt("Acceptance notes:"); if (notes?.trim()) updateShiftHandover("accept", notes.trim()).catch(showHandoverError); });
  lucide.createIcons();
}

async function updateShiftHandover(action, acceptanceNotes = "") {
  const response = await fetch(`/api/shift-handovers/${selectedHandoverId}`, { method: "PATCH", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ action, acceptance_notes: acceptanceNotes }) });
  const result = await response.json();
  if (!response.ok) throw new Error(result.error || "Unable to update shift handover");
  selectedHandover = result; await loadShiftHandovers(); renderShiftHandoverDetail();
}

async function openShiftHandoverModal() {
  const form = document.querySelector("#shiftHandoverForm"); form.reset();
  form.elements.shift_date.value = new Date().toISOString().slice(0, 10);
  document.querySelector("#shiftHandoverMessage").textContent = "";
  document.querySelector("#shiftHandoverModal").classList.add("open"); document.querySelector("#shiftHandoverModal").setAttribute("aria-hidden", "false");
  const response = await fetch("/api/events?state=open");
  if (!response.ok) throw new Error("Unable to load open Event Log entries");
  const events = (await response.json()).filter(entry => entry.parent_id === null);
  document.querySelector("#handoverEventChoices").innerHTML = events.map(entry => `<label class="handover-event-choice"><input type="checkbox" name="event_ids" value="${entry.id}" checked><span><strong>${escapeHtml(entry.entry_no)} / ${escapeHtml(entry.subject)}</strong><small>${escapeHtml(entry.kks_code || "No KKS")} / ${formatDate(entry.event_date)} / ${escapeHtml(entry.source_logbook_name)}</small></span></label>`).join("") || '<div class="asset-picker-empty">No open main Event Log entries.</div>';
}

function closeShiftHandoverModal() { document.querySelector("#shiftHandoverModal").classList.remove("open"); document.querySelector("#shiftHandoverModal").setAttribute("aria-hidden", "true"); }

async function saveShiftHandover(event) {
  event.preventDefault(); const form = event.currentTarget; const data = new FormData(form);
  const payload = { shift_date: data.get("shift_date"), shift_name: data.get("shift_name"), summary: data.get("summary"), operational_notes: data.get("operational_notes"), safety_notes: data.get("safety_notes"), event_ids: data.getAll("event_ids").map(Number) };
  const response = await fetch("/api/shift-handovers", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload) }); const result = await response.json();
  if (!response.ok) { document.querySelector("#shiftHandoverMessage").textContent = result.error || "Unable to save handover"; return; }
  selectedHandoverId = result.id; closeShiftHandoverModal(); await loadShiftHandovers();
}

function showHandoverError(error) { document.querySelector("#handoverDetail").innerHTML = `<div class="error">${escapeHtml(error.message)}</div>`; }

async function loadAssetWorkspace() {
  const query = document.querySelector("#assetSearch").value.trim();
  const parameters = new URLSearchParams({ limit: "200" });
  if (query) parameters.set("q", query);
  const exportParameters = new URLSearchParams();
  if (query) exportParameters.set("q", query);
  document.querySelector("#downloadAssetDirectory").href =
    `/api/assets.xlsx${exportParameters.toString() ? `?${exportParameters.toString()}` : ""}`;
  const response = await fetch(`/api/assets?${parameters.toString()}`);
  if (!response.ok) throw new Error("Unable to load KKS hierarchy");
  assetTreeItems = await response.json();
  renderAssetTree(assetTreeItems, Boolean(query));
  if (!selectedAssetId && assetTreeItems.length) {
    await selectAssetWorkspace(assetTreeItems[0].id);
  } else if (selectedAssetId) {
    await selectAssetWorkspace(selectedAssetId);
  }
}

function renderAssetTree(items, searching = false) {
  document.querySelector("#assetList").innerHTML = items.map(item => `
    <button class="asset-tree-row ${item.id === selectedAssetId ? "selected" : ""}" data-asset-workspace-id="${item.id}" style="--level:${searching ? 0 : Math.min(item.level_no, 2)}">
      <span class="asset-tree-icon"><i data-lucide="${item.child_count ? "folder-tree" : "component"}"></i></span>
      <span><code>${escapeHtml(item.kks_code)}</code><small>${escapeHtml(item.description)}${item.responsible_area ? ` / ${escapeHtml(item.responsible_area)}` : ""}</small></span>
      ${item.child_count ? `<span class="tree-count">${item.child_count}</span>` : ""}
      ${item.status !== "active" ? '<span class="offline-dot"></span>' : ""}
    </button>
  `).join("") || '<div class="empty-list">No KKS records match this search.</div>';
  document.querySelectorAll("[data-asset-workspace-id]").forEach(button => {
    button.addEventListener("click", () => selectAssetWorkspace(Number(button.dataset.assetWorkspaceId)).catch(showAssetError));
  });
  lucide.createIcons();
}

async function selectAssetWorkspace(id) {
  const response = await fetch(`/api/assets/${id}`);
  if (!response.ok) throw new Error("Unable to load asset workspace");
  const asset = await response.json();
  selectedAssetId = id;
  document.querySelectorAll("[data-asset-workspace-id]").forEach(button => {
    button.classList.toggle("selected", Number(button.dataset.assetWorkspaceId) === id);
  });
  renderAssetWorkspaceDetail(asset);
}

function renderAssetWorkspaceDetail(asset) {
  const tabs = [
    ["overview", "Overview", "layout-list"],
    ["events", `Events ${asset.counts.events}`, "notebook-tabs"],
    ["corrective", `Corrective ${asset.counts.corrective}`, "wrench"],
    ["preventive", `Preventive ${asset.counts.recurrent}`, "calendar-clock"],
    ["permits", `Permits ${asset.counts.permits}`, "shield-check"]
  ];
  document.querySelector("#assetDetailWorkspace").innerHTML = `
    <div class="asset-workspace-header">
      <div><span class="asset-level">${escapeHtml(asset.hierarchy_level)}</span><code>${escapeHtml(asset.kks_code)}</code><h3>${escapeHtml(asset.description)}</h3><p>${asset.parent_kks_code ? `Parent ${escapeHtml(asset.parent_kks_code)} - ${escapeHtml(asset.parent_description)}` : "Top-level plant unit"}</p></div>
      <div class="asset-header-actions"><span class="state-pill ${asset.status === "active" ? "closed" : "open"}">${escapeHtml(asset.status)}</span>${renderPrintCommand("asset", asset.id)}</div>
    </div>
    <div class="asset-kpis">
      <article><small>Events</small><strong>${asset.counts.events}</strong></article>
      <article><small>Corrective</small><strong>${asset.counts.corrective}</strong></article>
      <article><small>Recurrent</small><strong>${asset.counts.recurrent}</strong></article>
      <article><small>Permits</small><strong>${asset.counts.permits}</strong></article>
    </div>
    <div class="asset-tabs">${tabs.map(tab => `<button class="${assetTab === tab[0] ? "active" : ""}" data-asset-tab="${tab[0]}"><i data-lucide="${tab[2]}"></i>${tab[1]}</button>`).join("")}</div>
    <div class="asset-tab-content" id="assetTabContent">${renderAssetTab(asset)}</div>
  `;
  document.querySelectorAll("[data-asset-tab]").forEach(button => {
    button.addEventListener("click", () => {
      assetTab = button.dataset.assetTab;
      renderAssetWorkspaceDetail(asset);
    });
  });
  document.querySelectorAll("[data-child-asset]").forEach(button => {
    button.addEventListener("click", () => selectAssetWorkspace(Number(button.dataset.childAsset)).catch(showAssetError));
  });
  lucide.createIcons();
}

function renderAssetTab(asset) {
  if (assetTab === "events") {
    return renderAssetRecords(asset.events, item => `
      <article class="asset-linked-record"><span class="record-icon blue"><i data-lucide="notebook-tabs"></i></span><div><code>${escapeHtml(item.entry_no)}</code><strong>${escapeHtml(item.subject)}</strong><small>${formatDate(item.event_date)} / ${escapeHtml(item.state)}</small></div></article>
    `, "No Event Log entries are linked to this asset.");
  }
  if (assetTab === "corrective") {
    return renderAssetRecords(asset.corrective, item => `
      <article class="asset-linked-record"><span class="record-icon amber"><i data-lucide="wrench"></i></span><div><code>${escapeHtml(item.request_no)}${item.order_no ? ` / ${escapeHtml(item.order_no)}` : ""}</code><strong>${escapeHtml(item.name)}</strong><small>Priority ${item.priority} / ${escapeHtml(item.workflow_step || item.status)}</small></div></article>
    `, "No corrective tasks are linked to this asset.");
  }
  if (assetTab === "preventive") {
    return `
      <div class="asset-content-heading"><strong>Recurrent maintenance</strong><span>${asset.recurrent.length} schedules</span></div>
      ${renderAssetRecords(asset.recurrent, item => `<article class="asset-linked-record"><span class="record-icon green"><i data-lucide="repeat-2"></i></span><div><code>${escapeHtml(item.recurrent_no)}</code><strong>${escapeHtml(item.name)}</strong><small>${escapeHtml(item.schedule_type_name)} / Next ${escapeHtml(item.next_target_date)}</small></div></article>`, "No recurrent tasks are linked to this asset.")}
      <div class="asset-content-heading secondary"><strong>Generated preventive work</strong><span>${asset.preventive.length} tasks</span></div>
      ${renderAssetRecords(asset.preventive, item => `<article class="asset-linked-record"><span class="record-icon green"><i data-lucide="calendar-check"></i></span><div><code>${escapeHtml(item.task_no)}</code><strong>${escapeHtml(item.recurrent_name)}</strong><small>Target ${escapeHtml(item.target_date)} / ${escapeHtml(item.status)}</small></div></article>`, "No generated preventive work.")}
    `;
  }
  if (assetTab === "permits") {
    return renderAssetRecords(asset.permits, item => `
      <article class="asset-linked-record"><span class="record-icon red"><i data-lucide="shield-check"></i></span><div><code>${escapeHtml(item.permit_no)}</code><strong>${escapeHtml(item.work_description)}</strong><small>${escapeHtml(permitTypeLabel(item.form_type))} / ${escapeHtml(item.status)}</small></div></article>
    `, "No safety permits are linked to this asset.");
  }
  return `
    <div class="asset-overview-grid">
      <section><div class="asset-content-heading"><strong>Asset identity</strong></div><dl><div><dt>KKS code</dt><dd>${escapeHtml(asset.kks_code)}</dd></div><div><dt>Hierarchy level</dt><dd>${escapeHtml(asset.hierarchy_level)}</dd></div><div><dt>Responsible area</dt><dd>${escapeHtml(asset.responsible_area || "-")}</dd></div><div><dt>Status</dt><dd>${escapeHtml(asset.status)}</dd></div><div><dt>Parent</dt><dd>${escapeHtml(asset.parent_kks_code || "-")}</dd></div></dl></section>
      <section><div class="asset-content-heading"><strong>Child assets</strong><span>${asset.children.length}</span></div>${asset.children.map(child => `<button class="child-asset" data-child-asset="${child.id}"><code>${escapeHtml(child.kks_code)}</code><span>${escapeHtml(child.description)}</span><i data-lucide="chevron-right"></i></button>`).join("") || '<div class="asset-empty">No lower-level assets.</div>'}</section>
    </div>
  `;
}

function renderAssetRecords(items, renderer, emptyText) {
  return items.length ? `<div class="asset-linked-list">${items.map(renderer).join("")}</div>` : `<div class="asset-empty">${emptyText}</div>`;
}

function showAssetError(error) {
  document.querySelector("#assetDetailWorkspace").innerHTML = `<div class="error">${escapeHtml(error.message)}</div>`;
}

function correctiveQueryString() {
  const parameters = new URLSearchParams();
  const search = document.querySelector("#correctiveSearch").value.trim();
  const status = document.querySelector("#correctiveStatus").value;
  const department = document.querySelector("#correctiveDepartment").value;
  if (search) parameters.set("q", search);
  if (status) parameters.set("request_status", status);
  if (department) parameters.set("department", department);
  const query = parameters.toString();
  return query ? `?${query}` : "";
}

async function loadCorrective() {
  const list = document.querySelector("#correctiveList");
  list.innerHTML = '<div class="loading">Loading corrective tasks...</div>';
  const query = correctiveQueryString();
  document.querySelector("#downloadCorrectiveCsv").href = `/api/corrective.csv${query}`;
  const [tasksResponse, summaryResponse] = await Promise.all([
    fetch(`/api/corrective${query}`),
    fetch("/api/corrective/summary")
  ]);
  if (!tasksResponse.ok || !summaryResponse.ok) throw new Error("Unable to load corrective maintenance");
  const tasks = await tasksResponse.json();
  const summary = await summaryResponse.json();
  document.querySelector("#totalRequests").textContent = summary.total_requests || 0;
  document.querySelector("#pendingRequests").textContent = summary.pending_approval || 0;
  document.querySelector("#activeOrders").textContent = summary.active_orders || 0;
  document.querySelector("#awaitingCheck").textContent = summary.awaiting_check || 0;
  document.querySelector("#overdueRequests").textContent = summary.overdue_response || 0;
  document.querySelector("#requestBadge").textContent = summary.pending_approval || 0;
  renderCorrectiveTasks(tasks);
  if (selectedRequestId && tasks.some(item => item.id === selectedRequestId)) {
    await selectCorrective(selectedRequestId);
  } else if (tasks.length) {
    await selectCorrective(tasks[0].id);
  } else {
    selectedRequestId = null;
    selectedCorrective = null;
    renderEmptyCorrectiveDetail();
  }
}

function renderCorrectiveTasks(tasks) {
  const list = document.querySelector("#correctiveList");
  if (!tasks.length) {
    list.innerHTML = '<div class="empty-list">No corrective tasks match the selected filters.</div>';
    return;
  }
  list.innerHTML = tasks.map(item => `
    <article class="corrective-row ${item.id === selectedRequestId ? "selected" : ""}" data-request-id="${item.id}">
      <div><code>${escapeHtml(item.request_no)}</code><small>Priority ${item.priority} / ${item.target_response_at ? `${item.is_response_overdue ? "Overdue" : "Target"} ${formatDate(item.target_response_at)}` : "User-defined target"}</small></div>
      <div><strong>${escapeHtml(item.name)}</strong><small>${escapeHtml(item.kks_code)} / ${escapeHtml(item.asset_description)}</small></div>
      <div><strong>${escapeHtml(item.main_department)}</strong><small>${escapeHtml(item.type_of_work)}</small></div>
      <div><span class="request-pill ${escapeHtml(item.status)}">${escapeHtml(item.status)}</span><small>${escapeHtml(item.order_no || "No work order")}${item.workflow_step ? ` / ${escapeHtml(item.workflow_step.replaceAll("_", " "))}` : ""}</small></div>
      <button class="row-arrow" aria-label="Open work request"><i data-lucide="chevron-right"></i></button>
    </article>
  `).join("");
  list.querySelectorAll("[data-request-id]").forEach(row => {
    row.addEventListener("click", () => selectCorrective(Number(row.dataset.requestId)).catch(showCorrectiveError));
  });
  lucide.createIcons();
}

async function selectCorrective(id) {
  const response = await fetch(`/api/corrective/${id}`);
  if (!response.ok) throw new Error("Unable to load corrective task");
  selectedCorrective = await response.json();
  selectedRequestId = id;
  document.querySelectorAll("[data-request-id]").forEach(row => {
    row.classList.toggle("selected", Number(row.dataset.requestId) === id);
  });
  renderCorrectiveDetail();
}

function workflowActions(item) {
  if (item.status === "submitted") {
    if (!hasRole("Maintenance Approver")) return "";
    return `
      <button class="button secondary" id="editWorkRequest"><i data-lucide="pencil"></i>Edit request</button>
      <button class="button danger-button" data-request-decision="declined">Decline</button>
      <button class="button primary" data-request-decision="approved">Approve request</button>
    `;
  }
  if (!item.work_order_id || item.status === "declined" || item.workflow_step === "closed") return "";
  if (item.workflow_step === "plan_approval" && hasRole("Maintenance Approver")) {
    return '<button class="button danger-button" data-order-action="return_plan">Return to planner</button><button class="button primary" data-order-action="approve_plan">Approve plan</button>';
  }
  const actions = {
    planning: '<button class="button primary" data-order-action="submit_plan">Submit plan</button>',
    permit_decision: '<button class="button primary" data-order-action="confirm_execution">Confirm execution</button>',
    execution: '<button class="button primary" data-order-action="complete_work">Complete work</button>',
    work_check: '<button class="button danger-button" data-order-action="deny_acceptance">Deny acceptance</button><button class="button primary" data-order-action="accept_work">Accept work</button>',
    rework: '<button class="button primary" data-order-action="resubmit_work">Submit revised plan</button>'
  };
  const actionByStep = {
    planning: "submit_plan",
    plan_approval: "approve_plan",
    permit_decision: "confirm_execution",
    execution: "complete_work",
    work_check: "accept_work",
    rework: "resubmit_work"
  };
  const action = actionByStep[item.workflow_step];
  return action && canPerformOrderAction(item, action)
    ? actions[item.workflow_step] || ""
    : "";
}

function renderCorrectiveDetail() {
  const item = selectedCorrective;
  const canEditPlan = item.work_order_id &&
    ["planning", "rework"].includes(item.workflow_step) &&
    hasRole("Maintenance Planner");
  const planDisabled = canEditPlan ? "" : "disabled";
  const activeLinkedPermit = (item.linked_permits || []).find(permit => permit.status !== "cancelled");
  const permitControl = hasRole("Shift Leader") && item.work_order_id && item.workflow_step === "permit_decision" && ["ptw", "loa", "sft"].includes(item.permit_requirement)
    ? activeLinkedPermit
      ? `<button class="button secondary" id="openLinkedPermit"><i data-lucide="shield-check"></i>Open ${escapeHtml(activeLinkedPermit.permit_no)}</button>`
      : `<button class="button secondary" id="preparePermitForOrder"><i data-lucide="shield-plus"></i>Prepare ${item.permit_requirement.toUpperCase()}</button>`
    : "";
  document.querySelector("#correctiveDetail").innerHTML = `
    <div class="corrective-detail-header">
      <div><span><code>${escapeHtml(item.request_no)}</code>${item.order_no ? `<code>${escapeHtml(item.order_no)}</code>` : ""}</span>${renderPrintCommand("corrective", item.id)}</div>
      <h3>${escapeHtml(item.name)}</h3>
      <p>${escapeHtml(item.observation)}</p>
      <div class="detail-statuses"><span class="request-pill ${escapeHtml(item.status)}">${escapeHtml(item.status)}</span>${item.workflow_step ? `<span class="workflow-step">${escapeHtml(item.workflow_step.replaceAll("_", " "))}</span>` : ""}</div>
    </div>
    <div class="detail-meta">
      <div><span>Asset</span><strong>${escapeHtml(item.kks_code)}</strong></div>
      <div><span>Priority</span><strong>${item.priority} - ${priorityLabel(item.priority)}</strong></div>
      <div><span>Response target</span><strong>${item.target_response_at ? `${formatDate(item.target_response_at)}${item.is_response_overdue ? " / Overdue" : ""}` : "User defined"}</strong></div>
      <div><span>Department</span><strong>${escapeHtml(item.main_department)}</strong></div>
      <div><span>Type of work</span><strong>${escapeHtml(item.type_of_work)}</strong></div>
      <div><span>Planned period</span><strong>${formatDate(item.planned_start)} to ${formatDate(item.planned_end)}</strong></div>
      <div><span>Author</span><strong>${escapeHtml(item.author)}</strong></div>
      <div><span>Source event</span><strong>${escapeHtml(item.source_event_no ? `${item.source_event_no} / ${item.source_event_state}` : "Direct request")}</strong></div>
      ${item.execution_started_at ? `<div><span>Execution started</span><strong>${formatDate(item.execution_started_at)} / ${escapeHtml(item.execution_confirmed_by || "-")}</strong></div>` : ""}
      ${item.cmpt_primary ? `<div><span>Primary consequence</span><strong>${escapeHtml(item.cmpt_primary)} - ${escapeHtml(cmptCategoryLabels[item.cmpt_primary] || "")}</strong></div>
      <div><span>CMPT rating</span><strong>Severity ${item.cmpt_severity} / Likelihood ${escapeHtml(item.cmpt_likelihood)}</strong></div>
      <div><span>Impacted areas</span><strong>${(item.cmpt_impacts || []).map(code => escapeHtml(code)).join(", ") || "-"}</strong></div>` : ""}
    </div>
    ${item.status === "declined" ? `<div class="decision-note"><strong>Declined by ${escapeHtml(item.decision_by)}</strong><p>${escapeHtml(item.decision_reason)}</p></div>` : ""}
    ${(item.edit_history || []).length ? `<div class="history-section"><div class="section-title"><strong>Request revisions</strong><span>${item.edit_history.length}</span></div>${item.edit_history.map(entry => `<article class="history-record"><span></span><div><strong>${escapeHtml(Object.keys(entry.changes).map(field => field.replaceAll("_", " ")).join(", "))}</strong><small>${escapeHtml(entry.changed_by)} / ${formatDate(entry.created_at)}</small></div></article>`).join("")}</div>` : ""}
    ${item.work_order_id ? `
      <div class="work-plan">
        <div class="section-title"><strong>Execution plan</strong><span>${escapeHtml(item.permit_requirement)} / ${escapeHtml(item.permit_status)}</span></div>
        <label><span>Description of work</span><textarea id="planDescription" rows="3" ${planDisabled}>${escapeHtml(item.description_of_work || "")}</textarea></label>
        <label><span>Workplace requirements</span><textarea id="planRequirements" rows="2" ${planDisabled}>${escapeHtml(item.workplace_requirements || "")}</textarea></label>
        <div class="plan-grid">
          <label><span>Maintenance code</span><input id="maintenanceCode" maxlength="30" value="${escapeHtml(item.maintenance_code || "")}" placeholder="Approved maintenance code" ${planDisabled}></label>
          <label><span>Equipment condition</span><select id="equipmentCondition" ${planDisabled}><option value="">Select condition</option><option value="Operating" ${item.equipment_condition === "Operating" ? "selected" : ""}>Operating</option><option value="Degraded" ${item.equipment_condition === "Degraded" ? "selected" : ""}>Degraded</option><option value="Failed" ${item.equipment_condition === "Failed" ? "selected" : ""}>Failed</option><option value="Out of service" ${item.equipment_condition === "Out of service" ? "selected" : ""}>Out of service</option></select></label>
          <label><span>Expected man hours</span><input id="planHours" type="number" min="0" step=".5" value="${Number(item.expected_man_hours || 0)}" ${planDisabled}></label>
          <label><span>PTW / LoA / SFT decision</span><select id="permitRequirement" ${planDisabled}><option value="undecided" ${item.permit_requirement === "undecided" ? "selected" : ""}>Undecided</option><option value="none" ${item.permit_requirement === "none" ? "selected" : ""}>No permit required</option><option value="ptw" ${item.permit_requirement === "ptw" ? "selected" : ""}>Permit to Work</option><option value="loa" ${item.permit_requirement === "loa" ? "selected" : ""}>Limitation of Access</option><option value="sft" ${item.permit_requirement === "sft" ? "selected" : ""}>Sanction for Test</option></select></label>
        </div>
      </div>
      <div class="corrective-columns">
        <section><div class="section-title"><strong>Supply</strong><span>${item.supplies.length}${canEditPlan ? ' <button class="mini-icon-button" id="addSupply" title="Add supply" aria-label="Add supply"><i data-lucide="plus"></i></button>' : ""}</span></div>${item.supplies.map(supply => `<article class="compact-record"><div><strong>${escapeHtml(supply.description)}</strong><small>${escapeHtml(supply.supply_type)} / ${Number(supply.quantity || 0)} ${escapeHtml(supply.unit || "")}</small></div>${canEditPlan ? `<button class="mini-icon-button danger-icon" data-delete-supply="${supply.id}" title="Remove supply" aria-label="Remove supply"><i data-lucide="trash-2"></i></button>` : ""}</article>`).join("") || '<div class="empty-compact">No supply recorded.</div>'}</section>
        <section><div class="section-title"><strong>Artisans</strong><span>${item.artisans.length}${canEditPlan ? ' <button class="mini-icon-button" id="addArtisan" title="Add artisan" aria-label="Add artisan"><i data-lucide="plus"></i></button>' : ""}</span></div>${item.artisans.map(person => `<article class="compact-record"><div><strong>${escapeHtml(person.person_name)}</strong><small>${escapeHtml(person.trade)} / Planned ${Number(person.planned_hours)} h${person.actual_hours !== null && person.actual_hours !== undefined ? ` / Actual ${Number(person.actual_hours)} h` : ""}</small></div>${canEditPlan ? `<button class="mini-icon-button danger-icon" data-delete-artisan="${person.id}" title="Remove artisan" aria-label="Remove artisan"><i data-lucide="trash-2"></i></button>` : ""}</article>`).join("") || '<div class="empty-compact">No artisans assigned.</div>'}</section>
      </div>
      ${(item.linked_permits || []).length ? `<div class="history-section"><div class="section-title"><strong>Linked permits</strong><span>${item.linked_permits.length}</span></div>${item.linked_permits.map(permit => `<article class="history-record"><span></span><div><strong>${escapeHtml(permit.permit_no)} / ${escapeHtml(permit.status)}</strong><small>${escapeHtml(permitTypeLabel(permit.form_type))} / ${formatDate(permit.created_at)}</small></div></article>`).join("")}</div>` : ""}
      ${item.completion_summary ? `<div class="decision-note execution-note"><strong>Execution completed by ${escapeHtml(item.execution_completed_by)}</strong><p>${escapeHtml(item.completion_summary)}</p><small>${Number(item.actual_man_hours || 0)} actual man-hours / ${formatDate(item.execution_completed_at)}</small>${item.failure_mode || item.failure_cause ? `<p><strong>Failure analysis:</strong> ${escapeHtml(item.failure_mode || "Unclassified")}${item.failure_cause ? ` / ${escapeHtml(item.failure_cause)}` : ""}</p>` : ""}${item.downtime_hours !== null && item.downtime_hours !== undefined ? `<small>Equipment downtime: ${Number(item.downtime_hours).toFixed(2)} hours / ${formatDate(item.downtime_started_at)} to ${formatDate(item.restored_at)}</small>` : ""}</div>` : ""}
      ${item.acceptance_status !== "pending" ? `<div class="decision-note ${item.acceptance_status === "accepted" ? "acceptance-note" : ""}"><strong>${item.acceptance_status === "accepted" ? "Work accepted" : "Acceptance denied"} by ${escapeHtml(item.acceptance_checked_by)}</strong><p>${escapeHtml(item.acceptance_status === "accepted" ? item.acceptance_note : item.acceptance_reason)}</p><small>${formatDate(item.acceptance_checked_at)}</small></div>` : ""}
      <div class="history-section"><div class="section-title"><strong>Workflow history</strong><span>${item.history.length}</span></div>${item.history.map(entry => `<article class="history-record"><span></span><div><strong>${escapeHtml(entry.action)}</strong><small>${escapeHtml(entry.performed_by)} / ${formatDate(entry.created_at)}</small></div></article>`).join("")}</div>
    ` : ""}
    ${renderAttachmentPanel("corrective", item.id, item.attachments)}
    <div class="corrective-actions">${permitControl}${workflowActions(item)}</div>
  `;
  bindCorrectiveActions();
  bindPlanningResourceActions();
  bindAttachmentPanel("corrective", item.id, () => selectCorrective(item.id));
  lucide.createIcons();
}

function bindPlanningResourceActions() {
  document.querySelector("#addSupply")?.addEventListener("click", () => addPlanningSupply().catch(showCorrectiveError));
  document.querySelector("#addArtisan")?.addEventListener("click", () => addPlanningArtisan().catch(showCorrectiveError));
  document.querySelectorAll("[data-delete-supply]").forEach(button => {
    button.addEventListener("click", () => deletePlanningResource("supplies", button.dataset.deleteSupply).catch(showCorrectiveError));
  });
  document.querySelectorAll("[data-delete-artisan]").forEach(button => {
    button.addEventListener("click", () => deletePlanningResource("artisans", button.dataset.deleteArtisan).catch(showCorrectiveError));
  });
}

async function addPlanningSupply() {
  const description = window.prompt("Material or external service description:");
  if (!description?.trim()) return;
  const quantity = window.prompt("Quantity:", "1");
  if (quantity === null) return;
  const unit = window.prompt("Unit:", "EA");
  if (unit === null) return;
  const response = await fetch(`/api/work-orders/${selectedCorrective.work_order_id}/supplies`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      supply_type: "material",
      description: description.trim(),
      quantity: Number(quantity),
      unit: unit.trim()
    })
  });
  const result = await response.json();
  if (!response.ok) throw new Error(result.error || "Unable to add supply");
  selectedCorrective = result;
  renderCorrectiveDetail();
}

async function addPlanningArtisan() {
  const personName = window.prompt("Artisan name:");
  if (!personName?.trim()) return;
  const trade = window.prompt("Trade or discipline:");
  if (!trade?.trim()) return;
  const plannedHours = window.prompt("Planned hours:", "1");
  if (plannedHours === null) return;
  const response = await fetch(`/api/work-orders/${selectedCorrective.work_order_id}/artisans`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      person_name: personName.trim(),
      trade: trade.trim(),
      planned_hours: Number(plannedHours)
    })
  });
  const result = await response.json();
  if (!response.ok) throw new Error(result.error || "Unable to add artisan");
  selectedCorrective = result;
  renderCorrectiveDetail();
}

async function deletePlanningResource(resource, resourceId) {
  const response = await fetch(
    `/api/work-orders/${selectedCorrective.work_order_id}/${resource}/${resourceId}`,
    { method: "DELETE" }
  );
  const result = await response.json();
  if (!response.ok) throw new Error(result.error || "Unable to remove planning resource");
  selectedCorrective = result;
  renderCorrectiveDetail();
}

function priorityLabel(priority) {
  return {
    1: "Emergency / Immediate", 2: "Urgent / 48 hours",
    3: "Routine / 2 weeks", 4: "Routine / 8 weeks",
    5: "Routine / 6 months", 6: "User defined / over 6 months"
  }[priority] || "";
}

function updateCmptPriority() {
  const form = document.querySelector("#workRequestForm");
  const severity = Number(form.elements.cmpt_severity.value);
  const likelihood = form.elements.cmpt_likelihood.value;
  const priority = cmptMatrix[severity]?.[likelihood] || 6;
  form.elements.priority.value = String(priority);
  document.querySelector("#cmptPriorityBadge").textContent = `Priority ${priority}`;
  document.querySelector("#cmptPriorityText").textContent = `${priority} - ${priorityLabel(priority)}`;
}

function bindCorrectiveActions() {
  document.querySelector("#preparePermitForOrder")?.addEventListener("click", () => {
    openSafetyPermitModal(selectedCorrective).catch(showCorrectiveError);
  });
  document.querySelector("#openLinkedPermit")?.addEventListener("click", () => {
    const permit = (selectedCorrective.linked_permits || []).find(item => item.status !== "cancelled");
    if (!permit) return;
    selectedPermitId = permit.id;
    openView("permits");
  });
  document.querySelector("#editWorkRequest")?.addEventListener("click", () => {
    openWorkRequestModal(null, selectedCorrective);
  });
  document.querySelectorAll("[data-request-decision]").forEach(button => {
    button.addEventListener("click", () => decideRequest(button.dataset.requestDecision).catch(showCorrectiveError));
  });
  document.querySelectorAll("[data-order-action]").forEach(button => {
    button.addEventListener("click", () => {
      if (button.dataset.orderAction === "complete_work") {
        openWorkCompletionModal();
        return;
      }
      advanceWorkOrder(button.dataset.orderAction).catch(showCorrectiveError);
    });
  });
  document.querySelectorAll("[data-permit-action]").forEach(button => {
    button.addEventListener("click", () => updatePermit(button.dataset.permitAction).catch(showCorrectiveError));
  });
}

async function decideRequest(decision) {
  const reason = decision === "declined" ? window.prompt("Reason for declining this request:") : "";
  if (decision === "declined" && !reason) return;
  const response = await fetch(`/api/corrective/${selectedRequestId}/decision`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ decision, reason })
  });
  const result = await response.json();
  if (!response.ok) throw new Error(result.error || "Unable to decide work request");
  await loadCorrective();
}

function openWorkCompletionModal() {
  const form = document.querySelector("#workCompletionForm");
  form.reset();
  document.querySelector("#workCompletionMessage").textContent = "";
  document.querySelector("#workCompletionSummary").innerHTML = `<code>${escapeHtml(selectedCorrective.order_no)}</code><strong>${escapeHtml(selectedCorrective.name)}</strong><small>${escapeHtml(selectedCorrective.kks_code)} / ${escapeHtml(selectedCorrective.main_department)}</small>`;
  const artisans = selectedCorrective.artisans || [];
  const hoursInput = form.elements.actual_man_hours;
  hoursInput.value = Number(selectedCorrective.actual_man_hours ?? selectedCorrective.expected_man_hours ?? 0);
  hoursInput.readOnly = artisans.length > 0;
  document.querySelector("#workCompletionArtisans").innerHTML = artisans.length
    ? artisans.map(person => `<label><span>${escapeHtml(person.person_name)} / ${escapeHtml(person.trade)}</span><input data-artisan-hours="${person.id}" type="number" min="0" step=".25" required value="${Number(person.actual_hours ?? person.planned_hours ?? 0)}"></label>`).join("")
    : '<div class="asset-picker-empty">No artisans assigned. Enter total actual man-hours above.</div>';
  document.querySelectorAll("[data-artisan-hours]").forEach(input => {
    input.addEventListener("input", () => {
      hoursInput.value = Array.from(document.querySelectorAll("[data-artisan-hours]"))
        .reduce((total, item) => total + Number(item.value || 0), 0);
    });
  });
  document.querySelector("#workCompletionModal").classList.add("open");
  document.querySelector("#workCompletionModal").setAttribute("aria-hidden", "false");
  lucide.createIcons();
}

function closeWorkCompletionModal() {
  document.querySelector("#workCompletionModal").classList.remove("open");
  document.querySelector("#workCompletionModal").setAttribute("aria-hidden", "true");
}

async function submitWorkCompletion(event) {
  event.preventDefault();
  const form = event.currentTarget;
  const data = new FormData(form);
  const artisanHours = Array.from(form.querySelectorAll("[data-artisan-hours]")).map(input => ({
    id: Number(input.dataset.artisanHours),
    actual_hours: Number(input.value)
  }));
  const completion = {
    completion_summary: String(data.get("completion_summary") || "").trim(),
    actual_man_hours: Number(data.get("actual_man_hours")),
    artisan_hours: artisanHours,
    failure_mode: String(data.get("failure_mode") || ""),
    failure_cause: String(data.get("failure_cause") || "").trim(),
    downtime_started_at: String(data.get("downtime_started_at") || ""),
    restored_at: String(data.get("restored_at") || "")
  };
  try {
    await advanceWorkOrder("complete_work", completion);
    closeWorkCompletionModal();
  } catch (error) {
    document.querySelector("#workCompletionMessage").textContent = error.message;
  }
}

async function advanceWorkOrder(action, completion = null) {
  let reason = "";
  let completionSummary = "";
  let actualManHours = null;
  let artisanHours = [];
  let acceptanceNote = "";
  if (action === "deny_acceptance") {
    reason = window.prompt("Reason for denying acceptance:");
    if (!reason) return;
  }
  if (action === "return_plan") {
    reason = window.prompt("Reason for returning this plan to the planner:");
    if (!reason?.trim()) return;
  }
  if (action === "resubmit_work") {
    reason = window.prompt("Summarize the revised plan and corrective changes:");
    if (!reason?.trim()) return;
  }
  if (action === "complete_work") {
    if (!completion) return;
    completionSummary = completion.completion_summary;
    actualManHours = completion.actual_man_hours;
    artisanHours = completion.artisan_hours;
  }
  if (action === "accept_work") {
    acceptanceNote = window.prompt("Inspection remarks for accepting this work:");
    if (!acceptanceNote?.trim()) return;
  }
  const payload = {
    action,
    performed_by: currentUser.full_name,
    reason,
    description_of_work: document.querySelector("#planDescription")?.value || "",
    maintenance_code: document.querySelector("#maintenanceCode")?.value || "",
    equipment_condition: document.querySelector("#equipmentCondition")?.value || "",
    workplace_requirements: document.querySelector("#planRequirements")?.value || "",
    expected_man_hours: Number(document.querySelector("#planHours")?.value || 0),
    permit_requirement: document.querySelector("#permitRequirement")?.value || "undecided",
    completion_summary: completionSummary.trim(),
    actual_man_hours: actualManHours,
    artisan_hours: artisanHours,
    failure_mode: completion?.failure_mode || "",
    failure_cause: completion?.failure_cause || "",
    downtime_started_at: completion?.downtime_started_at || "",
    restored_at: completion?.restored_at || "",
    acceptance_note: acceptanceNote.trim()
  };
  const response = await fetch(`/api/work-orders/${selectedCorrective.work_order_id}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload)
  });
  const result = await response.json();
  if (!response.ok) throw new Error(result.error || "Unable to advance work order");
  await loadCorrective();
}

async function updatePermit(status) {
  const response = await fetch(`/api/work-orders/${selectedCorrective.work_order_id}/permit`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ status })
  });
  const result = await response.json();
  if (!response.ok) throw new Error(result.error || "Unable to update permit");
  await loadCorrective();
}

function renderEmptyCorrectiveDetail() {
  document.querySelector("#correctiveDetail").innerHTML =
    '<div class="empty-detail"><i data-lucide="wrench"></i><strong>Select a work request</strong><p>Workflow, planning, supply, and artisans will appear here.</p></div>';
  lucide.createIcons();
}

function openWorkRequestModal(sourceEvent = null, editItem = null) {
  const form = document.querySelector("#workRequestForm");
  form.reset();
  editingWorkRequestId = editItem?.id || null;
  form.elements.author.value = editItem?.author || currentUser.full_name;
  form.elements.show_in_history.checked = true;
  form.elements.source_event_id.value = editItem?.source_event_id || sourceEvent?.id || "";
  document.querySelector("#workRequestModalTitle").textContent =
    editItem ? `Review ${editItem.request_no}` : sourceEvent ? `Create request from ${sourceEvent.entry_no}` : "Create work request";
  if (editItem) {
    form.elements.name.value = editItem.name;
    form.elements.asset_type.value = editItem.asset_type || "";
    form.elements.type_of_work.value = editItem.type_of_work;
    form.elements.main_department.value = editItem.main_department;
    form.elements.planned_start.value = editItem.planned_start || "";
    form.elements.planned_end.value = editItem.planned_end || "";
    form.elements.reminder_days.value = Number(editItem.reminder_days || 0);
    form.elements.show_in_history.checked = Boolean(editItem.show_in_history);
    form.elements.observation.value = editItem.observation;
    form.elements.cmpt_primary.value = editItem.cmpt_primary || "A";
    form.elements.cmpt_severity.value = String(editItem.cmpt_severity ?? 0);
    form.elements.cmpt_likelihood.value = editItem.cmpt_likelihood || "A";
    form.querySelectorAll('[name="cmpt_impacts"]').forEach(input => {
      input.checked = (editItem.cmpt_impacts || []).includes(input.value);
    });
  } else if (sourceEvent) {
    form.elements.name.value = sourceEvent.subject;
    form.elements.observation.value = sourceEvent.observation;
    const sourceLogbook = logbooks.find(item => item.id === sourceEvent.source_logbook_id);
    const department = {
      CI: "Control & Instrumentation",
      ELEC: "Electrical Maintenance",
      MECH: "Mechanical Maintenance",
      OPS: "Operations",
      SHIFT: "Operations"
    }[sourceLogbook?.code];
    if (department) form.elements.main_department.value = department;
    form.elements.type_of_work.value = {
      "Control & Instrumentation": "Control & instrumentation repair",
      "Electrical Maintenance": "Electrical repair",
      "Mechanical Maintenance": "Mechanical repair",
      Operations: "Corrective inspection"
    }[department] || "Corrective inspection";
  }
  const selectedItem = editItem || sourceEvent;
  setAssetPicker("workRequestAsset", selectedItem?.asset_id ? {
    id: selectedItem.asset_id,
    kks_code: selectedItem.kks_code,
    description: selectedItem.asset_description
  } : null, Boolean(sourceEvent) && !editItem);
  updateCmptPriority();
  document.querySelector("#saveWorkRequest").innerHTML = editItem
    ? '<i data-lucide="save"></i> Update request'
    : '<i data-lucide="save"></i> Save request';
  const message = document.querySelector("#workRequestMessage");
  message.textContent = "";
  message.className = "form-message";
  document.querySelector("#workRequestModal").classList.add("open");
  document.querySelector("#workRequestModal").setAttribute("aria-hidden", "false");
  lucide.createIcons();
}

function closeWorkRequestModal() {
  document.querySelector("#workRequestModal").classList.remove("open");
  document.querySelector("#workRequestModal").setAttribute("aria-hidden", "true");
}

async function saveWorkRequest(event) {
  event.preventDefault();
  const form = event.currentTarget;
  const button = document.querySelector("#saveWorkRequest");
  const message = document.querySelector("#workRequestMessage");
  if (!selectedAssetIdFromPicker("workRequestAsset")) {
    message.textContent = "Select an asset from the KKS search results.";
    return;
  }
  const formData = new FormData(form);
  const payload = Object.fromEntries(formData.entries());
  payload.cmpt_impacts = formData.getAll("cmpt_impacts");
  payload.asset_id = Number(payload.asset_id);
  payload.priority = Number(payload.priority);
  payload.reminder_days = Number(payload.reminder_days || 0);
  payload.show_in_history = form.elements.show_in_history.checked;
  button.disabled = true;
  message.textContent = "Saving work request...";
  try {
    const response = await fetch(editingWorkRequestId ? `/api/corrective/${editingWorkRequestId}` : "/api/corrective", {
      method: editingWorkRequestId ? "PATCH" : "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload)
    });
    const result = await response.json();
    if (!response.ok) throw new Error(result.error || "Unable to save work request");
    message.textContent = `${result.request_no} ${editingWorkRequestId ? "updated" : "created"} successfully.`;
    message.className = "form-message success";
    selectedRequestId = result.id;
    await Promise.all([
      loadCorrective(), loadDashboard(),
      selectedEventId ? loadEvents() : Promise.resolve()
    ]);
    setTimeout(closeWorkRequestModal, 450);
  } catch (error) {
    message.textContent = error.message;
    message.className = "form-message";
  } finally {
    button.disabled = false;
  }
}

function showCorrectiveError(error) {
  document.querySelector("#correctiveList").innerHTML = `<div class="error">${escapeHtml(error.message)}</div>`;
}

function preventiveQueryString() {
  const parameters = new URLSearchParams();
  const search = document.querySelector("#preventiveSearch").value.trim();
  const status = document.querySelector("#preventiveStatus").value;
  if (search) parameters.set("q", search);
  if (status) parameters.set("status", status);
  const query = parameters.toString();
  return query ? `?${query}` : "";
}

async function loadPreventive() {
  const [typesResponse, tasksResponse, summaryResponse] = await Promise.all([
    fetch("/api/preventive/schedule-types"),
    fetch(`/api/preventive${preventiveQueryString()}`),
    fetch("/api/preventive/summary")
  ]);
  if (!typesResponse.ok || !tasksResponse.ok || !summaryResponse.ok) throw new Error("Unable to load preventive maintenance");
  scheduleTypes = await typesResponse.json();
  const tasks = await tasksResponse.json();
  const summary = await summaryResponse.json();
  document.querySelector("#activeSchedules").textContent = summary.active_schedules || 0;
  document.querySelector("#preventiveDue").textContent = summary.due || 0;
  document.querySelector("#preventiveOverdue").textContent = summary.overdue || 0;
  document.querySelector("#preventiveCompleted").textContent = summary.completed || 0;
  document.querySelector("#preventiveBadge").textContent = (summary.due || 0) + (summary.overdue || 0);
  renderScheduleTypes();
  renderRecurrentTasks(tasks);
  populatePreventiveForms();
  if (preventiveViewMode === "calendar") await loadPreventiveCalendar();
  if (selectedRecurrentId && tasks.some(item => item.id === selectedRecurrentId)) {
    await selectRecurrentTask(selectedRecurrentId);
  } else if (tasks.length) {
    await selectRecurrentTask(tasks[0].id);
  } else {
    selectedRecurrentId = null;
    selectedRecurrent = null;
    renderEmptyPreventiveDetail();
  }
}

function preventiveMonthValue() {
  const year = preventiveCalendarMonth.getFullYear();
  const month = String(preventiveCalendarMonth.getMonth() + 1).padStart(2, "0");
  return `${year}-${month}`;
}

function preventiveCalendarQueryString() {
  const parameters = new URLSearchParams({ month: preventiveMonthValue() });
  const department = document.querySelector("#preventiveCalendarDepartment").value;
  const status = document.querySelector("#preventiveCalendarStatus").value;
  if (department) parameters.set("department", department);
  if (status) parameters.set("status", status);
  return `?${parameters.toString()}`;
}

async function loadPreventiveCalendar() {
  const query = preventiveCalendarQueryString();
  const response = await fetch(`/api/preventive/calendar${query}`);
  const result = await response.json();
  if (!response.ok) throw new Error(result.error || "Unable to load preventive calendar");
  document.querySelector("#preventiveCalendarTitle").textContent =
    new Intl.DateTimeFormat("en-GB", { month: "long", year: "numeric" })
      .format(preventiveCalendarMonth);
  document.querySelector("#downloadPreventiveCalendar").href =
    `/api/preventive/calendar.csv${query}`;
  document.querySelector("#preventiveCalendarSummary").innerHTML = `
    <span><b>${result.summary.total}</b> total</span>
    <span class="planned"><b>${result.summary.planned}</b> planned</span>
    <span class="due"><b>${result.summary.due}</b> due</span>
    <span class="overdue"><b>${result.summary.overdue}</b> overdue</span>
    <span class="completed"><b>${result.summary.completed}</b> completed</span>
  `;
  renderPreventiveCalendar(result);
}

async function generatePreventiveMonth() {
  const month = preventiveMonthValue();
  const department = document.querySelector("#preventiveCalendarDepartment").value;
  const button = document.querySelector("#generatePreventiveMonth");
  button.disabled = true;
  try {
    const response = await fetch("/api/preventive/calendar/generate", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ month, department })
    });
    const result = await response.json();
    if (!response.ok) throw new Error(result.error || "Unable to generate preventive tasks");
    closePreventiveGenerationPreview();
    await Promise.all([loadPreventiveCalendar(), loadDashboard()]);
    document.querySelector("#preventiveCalendarSummary").insertAdjacentHTML(
      "beforeend",
      `<span><b>${result.generated_count}</b> generated / ${result.skipped_count} skipped</span>`
    );
  } finally {
    button.disabled = false;
  }
}

async function previewPreventiveMonthGeneration() {
  const parameters = new URLSearchParams({ month: preventiveMonthValue() });
  const department = document.querySelector("#preventiveCalendarDepartment").value;
  if (department) parameters.set("department", department);
  const response = await fetch(`/api/preventive/calendar/generate-preview?${parameters}`);
  const result = await response.json();
  if (!response.ok) throw new Error(result.error || "Unable to preview task generation");
  const panel = document.querySelector("#preventiveGenerationPreview");
  panel.hidden = false;
  panel.innerHTML = `
    <div class="generation-preview-header">
      <div><strong>Generation preview</strong><small>${result.ready_count} ready / ${result.blocked_count} blocked</small></div>
      <button class="icon-button" id="closeGenerationPreview" title="Close preview" aria-label="Close preview"><i data-lucide="x"></i></button>
    </div>
    <div class="generation-preview-list">
      ${result.items.map(item => `
        <article class="generation-preview-item ${item.ready ? "ready" : "blocked"}">
          <div><code>${escapeHtml(item.recurrent_no)}</code><strong>${escapeHtml(item.name)}</strong><small>${escapeHtml(item.department)} / ${escapeHtml(item.target_date)}</small></div>
          <span>${item.ready ? "Ready" : escapeHtml(item.reason)}</span>
        </article>
      `).join("") || '<div class="empty-compact">No schedules target this month.</div>'}
    </div>
    <div class="generation-preview-actions">
      <button class="button secondary" id="cancelGenerationPreview">Cancel</button>
      <button class="button primary" id="confirmGenerationPreview" ${result.ready_count ? "" : "disabled"}><i data-lucide="sparkles"></i> Generate ${result.ready_count} task(s)</button>
    </div>
  `;
  document.querySelector("#closeGenerationPreview").addEventListener("click", closePreventiveGenerationPreview);
  document.querySelector("#cancelGenerationPreview").addEventListener("click", closePreventiveGenerationPreview);
  document.querySelector("#confirmGenerationPreview").addEventListener("click", () => {
    generatePreventiveMonth().catch(showPreventiveError);
  });
  lucide.createIcons();
}

function closePreventiveGenerationPreview() {
  const panel = document.querySelector("#preventiveGenerationPreview");
  panel.hidden = true;
  panel.innerHTML = "";
}

function renderPreventiveCalendar(result) {
  const grid = document.querySelector("#preventiveCalendarGrid");
  const firstDay = new Date(
    preventiveCalendarMonth.getFullYear(),
    preventiveCalendarMonth.getMonth(),
    1
  );
  const leadingDays = (firstDay.getDay() + 6) % 7;
  const tasksByDay = new Map();
  result.tasks.forEach(task => {
    const day = Number(task.target_date.slice(8, 10));
    if (!tasksByDay.has(day)) tasksByDay.set(day, []);
    tasksByDay.get(day).push(task);
  });
  const cells = [];
  for (let index = 0; index < leadingDays; index += 1) {
    cells.push('<div class="preventive-calendar-day outside"></div>');
  }
  for (let day = 1; day <= result.days; day += 1) {
    const dateValue = `${result.month}-${String(day).padStart(2, "0")}`;
    const isToday = dateValue === new Date().toLocaleDateString("en-CA");
    const tasks = tasksByDay.get(day) || [];
    cells.push(`
      <div class="preventive-calendar-day ${isToday ? "today" : ""}">
        <span class="calendar-day-number">${day}</span>
        <div class="calendar-day-tasks">
          ${tasks.map(task => `
            <button class="calendar-task ${escapeHtml(task.status)}"
              data-calendar-recurrent="${task.recurrent_task_id}"
              title="${escapeHtml(task.task_no)} / ${escapeHtml(task.name)}">
              <code>${escapeHtml(task.task_no)}</code>
              <span>${escapeHtml(task.name)}</span>
              <small>${escapeHtml(task.kks_code)}</small>
            </button>
          `).join("")}
        </div>
      </div>
    `);
  }
  while (cells.length % 7) {
    cells.push('<div class="preventive-calendar-day outside"></div>');
  }
  grid.innerHTML = cells.join("");
  grid.querySelectorAll("[data-calendar-recurrent]").forEach(button => {
    button.addEventListener("click", () => {
      selectedRecurrentId = Number(button.dataset.calendarRecurrent);
      setPreventiveViewMode("list");
      loadPreventive().catch(showPreventiveError);
    });
  });
}

function setPreventiveViewMode(mode) {
  preventiveViewMode = mode;
  document.querySelector(".preventive-layout").hidden = mode !== "list";
  document.querySelector("#preventiveCalendarPanel").hidden = mode !== "calendar";
  document.querySelectorAll("#preventiveViewMode [data-preventive-mode]").forEach(button => {
    button.classList.toggle("active", button.dataset.preventiveMode === mode);
  });
  if (mode === "calendar") loadPreventiveCalendar().catch(showPreventiveError);
}

function renderScheduleTypes() {
  document.querySelector("#scheduleTypeList").innerHTML = scheduleTypes.map(item => `
    <article class="schedule-type-item">
      <span class="schedule-icon"><i data-lucide="repeat-2"></i></span>
      <div><strong>${escapeHtml(item.name)}</strong><small>Every ${item.interval_count} ${escapeHtml(item.calendar_unit)} / ${escapeHtml(item.strategy.replaceAll("_", " "))}${item.meter_type ? ` / ${Number(item.meter_interval)} ${escapeHtml(item.meter_type)}` : ""}</small></div>
      <b>${item.recurrent_count}</b>
    </article>
  `).join("") || '<div class="empty-list">No schedule types.</div>';
  lucide.createIcons();
}

function renderRecurrentTasks(tasks) {
  const list = document.querySelector("#preventiveList");
  if (!tasks.length) {
    list.innerHTML = '<div class="empty-list">No recurrent tasks match the selected filters.</div>';
    return;
  }
  list.innerHTML = tasks.map(item => `
    <article class="preventive-row ${item.id === selectedRecurrentId ? "selected" : ""}" data-recurrent-id="${item.id}">
      <div><code>${escapeHtml(item.recurrent_no)}</code><strong>${escapeHtml(item.name)}</strong><small>${item.asset_count} assets / ${item.due_count} due</small></div>
      <div><code>${escapeHtml(item.kks_code)}</code><small>${escapeHtml(item.main_department)}</small></div>
      <div><strong>${escapeHtml(item.schedule_type_name)}</strong><small>Every ${item.interval_count} ${escapeHtml(item.calendar_unit)}</small></div>
      <div><strong>${escapeHtml(item.next_target_date)}</strong><small>${escapeHtml(item.status)}</small></div>
      <button class="row-arrow" aria-label="Open recurrent task"><i data-lucide="chevron-right"></i></button>
    </article>
  `).join("");
  list.querySelectorAll("[data-recurrent-id]").forEach(row => {
    row.addEventListener("click", () => selectRecurrentTask(Number(row.dataset.recurrentId)).catch(showPreventiveError));
  });
  lucide.createIcons();
}

async function selectRecurrentTask(id) {
  const response = await fetch(`/api/preventive/${id}`);
  if (!response.ok) throw new Error("Unable to load recurrent task");
  selectedRecurrent = await response.json();
  selectedRecurrentId = id;
  document.querySelectorAll("[data-recurrent-id]").forEach(row => {
    row.classList.toggle("selected", Number(row.dataset.recurrentId) === id);
  });
  renderPreventiveDetail();
}

function renderPreventiveDetail() {
  const item = selectedRecurrent;
  const canManageSchedule = hasRole("Maintenance Planner") &&
    ["active", "suspended"].includes(item.status);
  const canGenerate = canManageSchedule && item.status === "active";
  const canComplete = hasRole(executionRoleForDepartment(item.main_department));
  document.querySelector("#preventiveDetail").innerHTML = `
    <div class="preventive-detail-header">
      <div class="detail-title-row"><code>${escapeHtml(item.recurrent_no)}</code>${renderPrintCommand("preventive", item.id)}</div>
      <h3>${escapeHtml(item.name)}</h3>
      <p>${escapeHtml(item.work_schedule || item.schedule_description)}</p>
      <span class="request-pill approved">${escapeHtml(item.status)}</span>
    </div>
    <div class="detail-meta">
      <div><span>Schedule type</span><strong>${escapeHtml(item.schedule_type_name)}</strong></div>
      <div><span>Generated task type</span><strong>${escapeHtml(item.task_type)}</strong></div>
      <div><span>Strategy</span><strong>${escapeHtml(item.strategy.replaceAll("_", " "))}</strong></div>
      <div><span>Interval</span><strong>Every ${item.interval_count} ${escapeHtml(item.calendar_unit)}</strong></div>
      ${item.meter_type ? `<div><span>Meter interval</span><strong>${Number(item.meter_interval)} ${escapeHtml(item.meter_type)}</strong></div>` : ""}
      <div><span>Tolerance</span><strong>-${item.early_tolerance_days} / +${item.late_tolerance_days} days</strong></div>
      <div><span>Infobox reminder</span><strong>${item.reminder_days} days before target</strong></div>
      <div><span>Next target</span><strong>${escapeHtml(item.next_target_date)}</strong></div>
      <div><span>Generated</span><strong>${item.generated_count}${item.repetitions ? ` / ${item.repetitions}` : ""}</strong></div>
    </div>
    <div class="preventive-section">
      <div class="section-title"><strong>Asset group</strong><span>${item.assets.length} assets</span></div>
      ${item.assets.map(asset => `<article class="asset-group-row"><code>${escapeHtml(asset.kks_code)}</code><strong>${escapeHtml(asset.description)}</strong></article>`).join("")}
    </div>
    <div class="preventive-section">
      <div class="section-title"><strong>Generated tasks</strong><span>${item.generated_tasks.length}</span></div>
      ${item.generated_tasks.map(task => `
        <article class="generated-task">
          <div><code>${escapeHtml(task.task_no)}</code><strong>Target ${escapeHtml(task.target_date)}</strong><small>${task.status === "completed" ? `${escapeHtml(task.feedback)} / ${Number(task.actual_man_hours || 0)} hours / ${escapeHtml(task.completed_by)} / ${formatDate(task.completed_at)}` : `Window ${escapeHtml(task.early_date)} to ${escapeHtml(task.late_date)}`}</small></div>
          <span class="pm-status ${escapeHtml(task.status)}">${escapeHtml(task.status)}</span>
          <div class="generated-task-actions">
            <button class="icon-button compact-action" data-open-pm="${task.id}" title="${task.status === "completed" ? "View completion record" : "Open task"}" aria-label="${task.status === "completed" ? "View completion record" : "Open task"}"><i data-lucide="${task.status === "completed" ? "clipboard-check" : "clipboard-list"}"></i></button>
            ${task.status !== "completed" && canComplete ? `<button class="icon-button compact-action primary-icon" data-complete-pm="${task.id}" title="Complete task" aria-label="Complete task"><i data-lucide="check"></i></button>` : ""}
          </div>
        </article>
      `).join("") || '<div class="empty-compact">No generated tasks.</div>'}
    </div>
    <div class="preventive-section">
      <div class="section-title"><strong>Schedule history</strong><span>${item.status_history.length} changes</span></div>
      ${item.status_history.map(change => `
        <article class="history-record">
          <span></span>
          <div><strong>${escapeHtml(change.previous_status)} to ${escapeHtml(change.new_status)}</strong><small>${escapeHtml(change.changed_by)} / ${formatDate(change.created_at)} / ${escapeHtml(change.reason)}</small></div>
        </article>
      `).join("") || '<div class="empty-compact">No schedule status changes.</div>'}
    </div>
    ${renderAttachmentPanel("preventive", item.id, item.attachments)}
    <div class="corrective-actions">
      ${canManageSchedule ? '<button class="button secondary" id="editRecurrentTask"><i data-lucide="pencil"></i>Edit schedule</button>' : ""}
      ${canManageSchedule ? `<button class="button secondary" id="changePreventiveStatus" data-schedule-status="${item.status === "active" ? "suspended" : "active"}"><i data-lucide="${item.status === "active" ? "pause" : "play"}"></i>${item.status === "active" ? "Suspend schedule" : "Reactivate schedule"}</button>` : ""}
      ${canGenerate ? '<button class="button primary" id="generatePreventiveTask"><i data-lucide="sparkles"></i> Generate next task</button>' : ""}
    </div>
  `;
  document.querySelector("#generatePreventiveTask")?.addEventListener("click", () => generatePreventiveTask().catch(showPreventiveError));
  document.querySelector("#editRecurrentTask")?.addEventListener("click", () => openRecurrentTaskModal(item));
  document.querySelector("#changePreventiveStatus")?.addEventListener("click", () => {
    changePreventiveStatus(
      document.querySelector("#changePreventiveStatus").dataset.scheduleStatus
    ).catch(showPreventiveError);
  });
  document.querySelectorAll("[data-complete-pm]").forEach(button => {
    button.addEventListener("click", () => openPreventiveTaskModal(Number(button.dataset.completePm)));
  });
  document.querySelectorAll("[data-open-pm]").forEach(button => {
    button.addEventListener("click", () => openPreventiveTaskModal(Number(button.dataset.openPm)));
  });
  bindAttachmentPanel("preventive", item.id, () => selectRecurrentTask(item.id));
  lucide.createIcons();
}

async function generatePreventiveTask() {
  const response = await fetch(`/api/preventive/${selectedRecurrentId}/generate`, { method: "POST" });
  const result = await response.json();
  if (!response.ok) throw new Error(result.error || "Unable to generate preventive task");
  await loadPreventive();
}

async function changePreventiveStatus(status) {
  const reason = window.prompt(
    status === "suspended"
      ? "Reason for suspending this schedule:"
      : "Reason for reactivating this schedule:"
  );
  if (!reason?.trim()) return;
  const response = await fetch(`/api/preventive/${selectedRecurrentId}/status`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ status, reason: reason.trim() })
  });
  const result = await response.json();
  if (!response.ok) throw new Error(result.error || "Unable to update schedule status");
  selectedRecurrent = result;
  await Promise.all([loadPreventive(), loadDashboard()]);
}

function localDateTimeValue(value = new Date()) {
  const adjusted = new Date(value);
  adjusted.setMinutes(adjusted.getMinutes() - adjusted.getTimezoneOffset());
  return adjusted.toISOString().slice(0, 16);
}

function openPreventiveTaskModal(taskId) {
  const task = selectedRecurrent.generated_tasks.find(item => item.id === taskId);
  if (!task) return;
  const form = document.querySelector("#preventiveTaskForm");
  const completed = task.status === "completed";
  const canComplete = hasRole(executionRoleForDepartment(selectedRecurrent.main_department));
  form.reset();
  form.elements.task_id.value = task.id;
  form.elements.task_no.value = task.task_no;
  form.elements.status.value = task.status;
  form.elements.target_date.value = task.target_date;
  form.elements.execution_window.value = `${task.early_date} to ${task.late_date}`;
  form.elements.completed_by.value = task.completed_by || currentUser.full_name;
  form.elements.completed_at.value = task.completed_at
    ? localDateTimeValue(task.completed_at)
    : localDateTimeValue();
  form.elements.actual_man_hours.value = completed
    ? Number(task.actual_man_hours || 0)
    : Number(selectedRecurrent.duration_hours || 0);
  form.elements.feedback.value = task.feedback || "";
  ["completed_at", "actual_man_hours", "feedback"].forEach(name => {
    form.elements[name].disabled = completed || !canComplete;
  });
  document.querySelector("#preventiveTaskModalTitle").textContent =
    completed ? "Completion record" : "Complete preventive task";
  document.querySelector("#preventiveTaskSummary").innerHTML = `
    <code>${escapeHtml(selectedRecurrent.recurrent_no)}</code>
    <strong>${escapeHtml(selectedRecurrent.name)}</strong>
    <small>${escapeHtml(selectedRecurrent.main_department)} / ${escapeHtml(selectedRecurrent.kks_code)}</small>
  `;
  document.querySelector("#preventiveTaskMessage").textContent =
    !completed && !canComplete
      ? `Completion requires ${escapeHtml(executionRoleForDepartment(selectedRecurrent.main_department))}.`
      : "";
  document.querySelector("#preventiveTaskMessage").className = "form-message";
  document.querySelector("#savePreventiveCompletion").hidden = completed || !canComplete;
  document.querySelector("#printPreventiveTask").href = `/print/preventive_task/${task.id}`;
  document.querySelector("#preventiveTaskModal").classList.add("open");
  document.querySelector("#preventiveTaskModal").setAttribute("aria-hidden", "false");
  lucide.createIcons();
}

function closePreventiveTaskModal() {
  document.querySelector("#preventiveTaskModal").classList.remove("open");
  document.querySelector("#preventiveTaskModal").setAttribute("aria-hidden", "true");
}

async function completePreventiveTask(event) {
  event.preventDefault();
  const form = event.currentTarget;
  const message = document.querySelector("#preventiveTaskMessage");
  const taskId = Number(form.elements.task_id.value);
  const button = document.querySelector("#savePreventiveCompletion");
  button.disabled = true;
  message.textContent = "Saving completion record...";
  const response = await fetch(`/api/preventive/tasks/${taskId}/complete`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      feedback: form.elements.feedback.value.trim(),
      actual_man_hours: Number(form.elements.actual_man_hours.value),
      completed_at: form.elements.completed_at.value
    })
  });
  const result = await response.json();
  if (!response.ok) {
    message.textContent = result.error || "Unable to complete preventive task";
    button.disabled = false;
    return;
  }
  message.textContent = "Preventive task completed successfully.";
  message.className = "form-message success";
  await Promise.all([loadPreventive(), loadDashboard()]);
  setTimeout(closePreventiveTaskModal, 450);
}

function populatePreventiveForms() {
  document.querySelector("#recurrentScheduleType").innerHTML = scheduleTypes
    .filter(item => item.status === "active")
    .map(item => `<option value="${item.id}">${escapeHtml(item.name)}</option>`).join("");
}

function renderEmptyPreventiveDetail() {
  document.querySelector("#preventiveDetail").innerHTML =
    '<div class="empty-detail"><i data-lucide="calendar-clock"></i><strong>Select a recurrent task</strong><p>Schedule settings, asset group, and generated tasks will appear here.</p></div>';
  lucide.createIcons();
}

function openScheduleTypeModal() {
  document.querySelector("#scheduleTypeForm").reset();
  document.querySelector("#scheduleTypeMessage").textContent = "";
  document.querySelector("#scheduleTypeModal").classList.add("open");
  document.querySelector("#scheduleTypeModal").setAttribute("aria-hidden", "false");
}

function closeScheduleTypeModal() {
  document.querySelector("#scheduleTypeModal").classList.remove("open");
  document.querySelector("#scheduleTypeModal").setAttribute("aria-hidden", "true");
}

function openRecurrentTaskModal(item = null) {
  const form = document.querySelector("#recurrentTaskForm");
  form.reset();
  editingRecurrentId = item?.id || null;
  form.elements.created_by.value = currentUser.full_name;
  form.elements.reminder_days.value = "7";
  form.elements.duration_hours.value = "2";
  form.elements.start_date.value = new Date().toISOString().slice(0, 10);
  recurrentGroupAssets = [];
  setAssetPicker("recurrentPrimaryAsset", item ? {
    id: item.primary_asset_id,
    kks_code: item.kks_code,
    description: item.asset_description
  } : null, Boolean(item));
  setAssetPicker("recurrentGroupAsset");
  populatePreventiveForms();
  if (item) {
    form.elements.name.value = item.name;
    form.elements.schedule_type_id.value = item.schedule_type_id;
    form.elements.schedule_type_id.disabled = true;
    form.elements.type_of_work.value = item.type_of_work;
    form.elements.main_department.value = item.main_department;
    form.elements.start_date.value = item.start_date;
    form.elements.start_date.disabled = true;
    form.elements.end_date.value = item.end_date || "";
    form.elements.repetitions.value = item.repetitions || "";
    form.elements.reminder_days.value = item.reminder_days;
    form.elements.duration_hours.value = item.duration_hours;
    form.elements.work_schedule.value = item.work_schedule || "";
    recurrentGroupAssets = item.assets.filter(asset => asset.id !== item.primary_asset_id);
  } else {
    form.elements.schedule_type_id.disabled = false;
    form.elements.start_date.disabled = false;
  }
  renderRecurrentGroupAssets();
  document.querySelector("#recurrentTaskMessage").textContent = "";
  document.querySelector("#recurrentTaskModalTitle").textContent =
    item ? "Edit recurrent task" : "Create recurrent task";
  document.querySelector("#saveRecurrentTask").innerHTML =
    item ? '<i data-lucide="save"></i> Save changes' : '<i data-lucide="save"></i> Save recurrent task';
  document.querySelector("#recurrentTaskModal").classList.add("open");
  document.querySelector("#recurrentTaskModal").setAttribute("aria-hidden", "false");
  lucide.createIcons();
}

function renderRecurrentGroupAssets() {
  const list = document.querySelector("#recurrentAssetGroupList");
  list.innerHTML = recurrentGroupAssets.map(asset => `
    <article class="recurrent-group-asset">
      <div><code>${escapeHtml(asset.kks_code)}</code><strong>${escapeHtml(asset.description)}</strong></div>
      <button type="button" class="mini-icon-button danger-icon" data-remove-group-asset="${asset.id}" title="Remove asset" aria-label="Remove asset"><i data-lucide="x"></i></button>
    </article>
  `).join("") || '<div class="asset-picker-empty">No additional assets selected.</div>';
  list.querySelectorAll("[data-remove-group-asset]").forEach(button => {
    button.addEventListener("click", () => {
      recurrentGroupAssets = recurrentGroupAssets.filter(
        asset => asset.id !== Number(button.dataset.removeGroupAsset)
      );
      renderRecurrentGroupAssets();
    });
  });
  document.querySelector("#recurrentAssetGroupCount").textContent =
    `${recurrentGroupAssets.length} additional`;
  lucide.createIcons();
}

function addRecurrentGroupAsset() {
  const message = document.querySelector("#recurrentTaskMessage");
  const asset = selectedAssetFromPicker("recurrentGroupAsset");
  if (!asset) {
    message.textContent = "Select an asset from the KKS search results before adding it.";
    return;
  }
  const primaryId = selectedAssetIdFromPicker("recurrentPrimaryAsset");
  if (asset.id === primaryId) {
    message.textContent = "The primary asset is already included in this maintenance plan.";
    return;
  }
  if (recurrentGroupAssets.some(item => item.id === asset.id)) {
    message.textContent = "This asset is already in the maintenance group.";
    return;
  }
  recurrentGroupAssets.push(asset);
  message.textContent = "";
  setAssetPicker("recurrentGroupAsset");
  renderRecurrentGroupAssets();
}

function closeRecurrentTaskModal() {
  document.querySelector("#recurrentTaskModal").classList.remove("open");
  document.querySelector("#recurrentTaskModal").setAttribute("aria-hidden", "true");
}

async function saveScheduleType(event) {
  event.preventDefault();
  const form = event.currentTarget;
  const message = document.querySelector("#scheduleTypeMessage");
  const payload = Object.fromEntries(new FormData(form).entries());
  ["interval_count", "early_tolerance_days", "late_tolerance_days"].forEach(key => payload[key] = Number(payload[key]));
  payload.meter_interval = payload.meter_interval ? Number(payload.meter_interval) : null;
  const response = await fetch("/api/preventive/schedule-types", {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload)
  });
  const result = await response.json();
  if (!response.ok) {
    message.textContent = result.error || "Unable to save schedule type";
    return;
  }
  message.textContent = `${result.name} created successfully.`;
  message.className = "form-message success";
  await loadPreventive();
  setTimeout(closeScheduleTypeModal, 450);
}

async function saveRecurrentTask(event) {
  event.preventDefault();
  const form = event.currentTarget;
  const message = document.querySelector("#recurrentTaskMessage");
  if (!editingRecurrentId && !selectedAssetIdFromPicker("recurrentPrimaryAsset")) {
    message.textContent = "Select a primary asset from the KKS search results.";
    return;
  }
  const payload = Object.fromEntries(new FormData(form).entries());
  if (!editingRecurrentId) {
    payload.schedule_type_id = Number(payload.schedule_type_id);
    payload.primary_asset_id = Number(payload.primary_asset_id);
  }
  payload.duration_hours = Number(payload.duration_hours || 0);
  payload.reminder_days = Number(payload.reminder_days || 0);
  payload.repetitions = payload.repetitions ? Number(payload.repetitions) : null;
  payload.asset_ids = recurrentGroupAssets.map(asset => asset.id);
  const response = await fetch(
    editingRecurrentId ? `/api/preventive/${editingRecurrentId}` : "/api/preventive",
    {
      method: editingRecurrentId ? "PATCH" : "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload)
    }
  );
  const result = await response.json();
  if (!response.ok) {
    message.textContent = result.error || "Unable to save recurrent task";
    return;
  }
  message.textContent = `${result.recurrent_no} ${editingRecurrentId ? "updated" : "created"} successfully.`;
  message.className = "form-message success";
  selectedRecurrentId = result.id;
  await loadPreventive();
  setTimeout(closeRecurrentTaskModal, 450);
}

function showPreventiveError(error) {
  document.querySelector("#preventiveList").innerHTML = `<div class="error">${escapeHtml(error.message)}</div>`;
}

function permitQueryString() {
  const parameters = new URLSearchParams();
  const search = document.querySelector("#permitSearch").value.trim();
  const status = document.querySelector("#permitStatusFilter").value;
  const formType = document.querySelector("#permitTypeFilter").value;
  if (search) parameters.set("q", search);
  if (status) parameters.set("status", status);
  if (formType) parameters.set("form_type", formType);
  const query = parameters.toString();
  return query ? `?${query}` : "";
}

async function loadSafetyPermits() {
  const [permitsResponse, summaryResponse] = await Promise.all([
    fetch(`/api/permits${permitQueryString()}`),
    fetch("/api/permits/summary")
  ]);
  if (!permitsResponse.ok || !summaryResponse.ok) throw new Error("Unable to load safety permits");
  const permits = await permitsResponse.json();
  const summary = await summaryResponse.json();
  document.querySelector("#permitTotal").textContent = summary.total || 0;
  document.querySelector("#permitPrepared").textContent = summary.prepared || 0;
  document.querySelector("#permitActive").textContent = summary.active || 0;
  document.querySelector("#permitAwaitingCancel").textContent = summary.awaiting_cancellation || 0;
  document.querySelector("#permitBadge").textContent = (summary.prepared || 0) + (summary.active || 0) + (summary.awaiting_cancellation || 0);
  renderSafetyPermits(permits);
  if (selectedPermitId && permits.some(item => item.id === selectedPermitId)) {
    await selectSafetyPermit(selectedPermitId);
  } else if (permits.length) {
    await selectSafetyPermit(permits[0].id);
  } else {
    selectedPermitId = null;
    selectedPermit = null;
    renderEmptySafetyPermitDetail();
  }
}

function permitTypeLabel(value) {
  return {
    electrical_ptw: "Electrical PTW",
    mechanical_ptw: "Mechanical PTW",
    electrical_loa: "Electrical LoA",
    mechanical_loa: "Mechanical LoA",
    electrical_sft: "Electrical SFT",
    mechanical_sft: "Mechanical SFT"
  }[value] || value;
}

function renderSafetyPermits(permits) {
  const list = document.querySelector("#permitList");
  if (!permits.length) {
    list.innerHTML = '<div class="empty-list">No permits match the selected filters.</div>';
    return;
  }
  list.innerHTML = permits.map(item => `
    <article class="safety-permit-row ${item.id === selectedPermitId ? "selected" : ""}" data-safety-permit-id="${item.id}">
      <div><code>${escapeHtml(item.permit_no)}</code><small>${escapeHtml(permitTypeLabel(item.form_type))}</small></div>
      <div><strong>${escapeHtml(item.work_description)}</strong><small>${escapeHtml(item.kks_code)} / ${escapeHtml(item.location)}</small></div>
      <div><strong>${escapeHtml(item.issued_to)}</strong><small>${escapeHtml(item.order_no || "No work order")}</small></div>
      <span class="permit-status ${escapeHtml(item.status)}">${escapeHtml(item.status)}</span>
      <button class="row-arrow" aria-label="Open permit"><i data-lucide="chevron-right"></i></button>
    </article>
  `).join("");
  list.querySelectorAll("[data-safety-permit-id]").forEach(row => {
    row.addEventListener("click", () => selectSafetyPermit(Number(row.dataset.safetyPermitId)).catch(showSafetyPermitError));
  });
  lucide.createIcons();
}

async function selectSafetyPermit(id) {
  const response = await fetch(`/api/permits/${id}`);
  if (!response.ok) throw new Error("Unable to load permit details");
  selectedPermit = await response.json();
  selectedPermitId = id;
  document.querySelectorAll("[data-safety-permit-id]").forEach(row => {
    row.classList.toggle("selected", Number(row.dataset.safetyPermitId) === id);
  });
  renderSafetyPermitDetail();
}

function permitNextAction(status) {
  return {
    prepared: ["issue", "Issue permit"],
    issued: ["receive", "Confirm receipt"],
    received: ["clear", "Clear work location"],
    cleared: ["cancel", "Cancel permit"]
  }[status] || null;
}

function renderSafetyPermitDetail() {
  const item = selectedPermit;
  const next = permitNextAction(item.status);
  const selectedPrecautions = item.precautions.filter(value => value.selected);
  document.querySelector("#safetyPermitDetail").innerHTML = `
    <div class="permit-detail-header">
      <div><span><code>${escapeHtml(item.permit_no)}</code><span class="permit-status ${escapeHtml(item.status)}">${escapeHtml(item.status)}</span></span>${renderPrintCommand("permit", item.id)}</div>
      <h3>${escapeHtml(permitTypeLabel(item.form_type))}</h3>
      <p>${escapeHtml(item.work_description)}</p>
    </div>
    <div class="detail-meta">
      <div><span>Asset</span><strong>${escapeHtml(item.kks_code)}</strong></div>
      <div><span>Work order</span><strong>${escapeHtml(item.order_no || "-")}</strong></div>
      <div><span>Location</span><strong>${escapeHtml(item.location)}</strong></div>
      <div><span>Issued to</span><strong>${escapeHtml(item.issued_to)}</strong></div>
      <div><span>Employer</span><strong>${escapeHtml(item.employer)}</strong></div>
      <div><span>Prepared by</span><strong>${escapeHtml(item.prepared_by)}</strong></div>
    </div>
    <div class="permit-detail-section">
      <div class="section-title"><strong>Isolation and access</strong><span>${escapeHtml(item.form_type.includes("loa") ? "LoA" : (item.form_type.includes("sft") ? "SFT" : "PTW"))}</span></div>
      ${item.electrical_isolations ? `<article class="permit-text"><span>Electrical isolations</span><p>${escapeHtml(item.electrical_isolations)}</p></article>` : ""}
      ${item.mechanical_isolations ? `<article class="permit-text"><span>Mechanical isolations</span><p>${escapeHtml(item.mechanical_isolations)}</p></article>` : ""}
      ${item.circuit_main_earths ? `<article class="permit-text"><span>Circuit main earths</span><p>${escapeHtml(item.circuit_main_earths)} / Additional: ${item.additional_earths}</p></article>` : ""}
      ${item.limits_of_access ? `<article class="permit-text"><span>Limits of access</span><p>${escapeHtml(item.limits_of_access)}</p></article>` : ""}
    </div>
    <div class="permit-detail-section">
      <div class="section-title"><strong>Safety precautions</strong><span>${selectedPrecautions.length} selected</span></div>
      <div class="precaution-list">${item.precautions.map(value => `<article class="${value.selected ? "selected" : ""}"><i data-lucide="${value.selected ? "check-square" : "square"}"></i><span>${escapeHtml(value.precaution_text)}</span></article>`).join("")}</div>
    </div>
    <div class="permit-detail-section">
      <div class="section-title"><strong>Special work assessments</strong><span>Yes / No / N/A</span></div>
      <div class="assessment-grid">${item.assessments.map(value => `<div><span>${escapeHtml(value.assessment_type.replaceAll("_", " "))}</span><strong class="${escapeHtml(value.answer)}">${escapeHtml(value.answer)}</strong></div>`).join("")}</div>
    </div>
    <div class="signature-grid">
      <div><span>Issued by</span><strong>${escapeHtml(item.issued_by || "-")}</strong></div>
      <div><span>Controller</span><strong>${escapeHtml(item.controller_name || "-")}</strong></div>
      <div><span>Received by</span><strong>${escapeHtml(item.received_by || "-")}</strong></div>
      <div><span>Cleared by</span><strong>${escapeHtml(item.cleared_by || "-")}</strong></div>
      <div><span>Cancelled by</span><strong>${escapeHtml(item.cancelled_by || "-")}</strong></div>
    </div>
    <div class="permit-detail-section">
      <div class="section-title"><strong>Permit lifecycle</strong><span>${item.transition_history.length} transitions</span></div>
      ${item.transition_history.map(change => `
        <article class="history-record">
          <span></span>
          <div><strong>${escapeHtml(change.previous_status)} to ${escapeHtml(change.new_status)} / ${escapeHtml(change.performed_by)}</strong><small>${formatDate(change.created_at)} / ${escapeHtml(change.remarks)}${change.controller_name ? ` / Controller ${escapeHtml(change.controller_name)}` : ""}</small></div>
        </article>
      `).join("") || '<div class="empty-compact">No permit transitions recorded.</div>'}
    </div>
    ${renderAttachmentPanel("permit", item.id, item.attachments)}
    <div class="corrective-actions">${next && hasRole("Shift Leader") ? `<button class="button primary" id="transitionPermit" data-permit-transition="${next[0]}">${next[1]}</button>` : ""}</div>
  `;
  document.querySelector("#transitionPermit")?.addEventListener("click", () => transitionSafetyPermit(next[0]).catch(showSafetyPermitError));
  bindAttachmentPanel("permit", item.id, () => selectSafetyPermit(item.id));
  lucide.createIcons();
}

async function transitionSafetyPermit(action) {
  let controllerName = "";
  if (action === "issue") {
    controllerName = window.prompt("Controller name:");
    if (!controllerName) return;
  }
  const remarks = window.prompt({
    issue: "Issue remarks:",
    receive: "Receipt confirmation remarks:",
    clear: "Work-location clearance remarks:",
    cancel: "Cancellation remarks:"
  }[action] || "Transition remarks:");
  if (!remarks?.trim()) return;
  const response = await fetch(`/api/permits/${selectedPermitId}/transition`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      action,
      controller_name: controllerName,
      remarks: remarks.trim()
    })
  });
  const result = await response.json();
  if (!response.ok) throw new Error(result.error || "Unable to update permit");
  await Promise.all([loadSafetyPermits(), loadDashboard()]);
}

function renderEmptySafetyPermitDetail() {
  document.querySelector("#safetyPermitDetail").innerHTML =
    '<div class="empty-detail"><i data-lucide="shield-check"></i><strong>Select a permit</strong><p>Isolation, precautions, assessment, and signatures will appear here.</p></div>';
  lucide.createIcons();
}

async function openSafetyPermitModal(workOrder = null) {
  const form = document.querySelector("#safetyPermitForm");
  form.reset();
  form.elements.employer.value = "STEAG Energy Services";
  form.elements.prepared_by.value = currentUser.full_name;
  document.querySelector("#safetyPermitMessage").textContent = "";
  setAssetPicker("safetyPermitAsset");
  const response = await fetch("/api/corrective");
  const corrective = response.ok ? await response.json() : [];
  document.querySelector("#safetyPermitWorkOrder").innerHTML = '<option value="">No linked work order</option>' + corrective
    .filter(item => item.work_order_id && item.workflow_step !== "closed")
    .map(item => `<option value="${item.work_order_id}">${escapeHtml(item.order_no)} - ${escapeHtml(item.name)}</option>`).join("");
  if (workOrder?.work_order_id) {
    form.elements.work_order_id.value = String(workOrder.work_order_id);
    form.elements.form_type.value = `${["Electrical Maintenance", "Control & Instrumentation"].includes(workOrder.main_department) ? "electrical" : "mechanical"}_${workOrder.permit_requirement}`;
    form.elements.work_description.value = workOrder.description_of_work || workOrder.name;
    form.elements.location.value = `${workOrder.kks_code} - ${workOrder.asset_description}`;
    setAssetPicker("safetyPermitAsset", {
      id: workOrder.asset_id,
      kks_code: workOrder.kks_code,
      description: workOrder.asset_description
    }, true);
    document.querySelector("#safetyPermitModalTitle").textContent = `Prepare ${workOrder.permit_requirement.toUpperCase()} for ${workOrder.order_no}`;
  } else {
    document.querySelector("#safetyPermitModalTitle").textContent = "Prepare permit";
  }
  document.querySelector("#safetyPermitModal").classList.add("open");
  document.querySelector("#safetyPermitModal").setAttribute("aria-hidden", "false");
}

function closeSafetyPermitModal() {
  document.querySelector("#safetyPermitModal").classList.remove("open");
  document.querySelector("#safetyPermitModal").setAttribute("aria-hidden", "true");
}

async function saveSafetyPermit(event) {
  event.preventDefault();
  const form = event.currentTarget;
  const message = document.querySelector("#safetyPermitMessage");
  if (!selectedAssetIdFromPicker("safetyPermitAsset")) {
    message.textContent = "Select an asset from the KKS search results.";
    return;
  }
  const data = new FormData(form);
  const payload = Object.fromEntries(data.entries());
  payload.asset_id = Number(payload.asset_id);
  payload.work_order_id = payload.work_order_id ? Number(payload.work_order_id) : null;
  payload.additional_earths = Number(payload.additional_earths || 0);
  payload.identity_wristlets = Number(payload.identity_wristlets || 0);
  payload.precautions_confirmed = form.elements.precautions_confirmed.checked;
  payload.precautions = data.getAll("precautions");
  payload.assessments = {
    hot_work: { answer: payload.hot_work },
    height_work: { answer: payload.height_work },
    confined_space: { answer: payload.confined_space }
  };
  const response = await fetch("/api/permits", {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload)
  });
  const result = await response.json();
  if (!response.ok) {
    message.textContent = result.error || "Unable to save permit";
    return;
  }
  message.textContent = `${result.permit_no} prepared successfully.`;
  message.className = "form-message success";
  selectedPermitId = result.id;
  await Promise.all([
    loadSafetyPermits(),
    selectedRequestId ? loadCorrective() : Promise.resolve()
  ]);
  setTimeout(closeSafetyPermitModal, 450);
}

function showSafetyPermitError(error) {
  document.querySelector("#permitList").innerHTML = `<div class="error">${escapeHtml(error.message)}</div>`;
}

function initializeReportDates() {
  const end = new Date();
  const start = new Date();
  start.setDate(start.getDate() - 30);
  const localValue = value => {
    value.setMinutes(value.getMinutes() - value.getTimezoneOffset());
    return value.toISOString().slice(0, 10);
  };
  if (!document.querySelector("#reportEnd").value) {
    document.querySelector("#reportEnd").value = localValue(end);
  }
  if (!document.querySelector("#reportStart").value) {
    document.querySelector("#reportStart").value = localValue(start);
  }
}

function reportQueryString() {
  const parameters = new URLSearchParams({
    start: document.querySelector("#reportStart").value,
    end: document.querySelector("#reportEnd").value
  });
  return `?${parameters.toString()}`;
}

async function loadReports() {
  const response = await fetch(`/api/reports/summary${reportQueryString()}`);
  const result = await response.json();
  if (!response.ok) throw new Error(result.description || result.error || "Unable to load reports");
  const counts = result.counts;
  document.querySelector("#reportEvents").textContent = counts.events;
  document.querySelector("#reportOpenEvents").textContent = `${counts.open_events} open`;
  document.querySelector("#reportRequests").textContent = counts.work_requests;
  document.querySelector("#reportPendingRequests").textContent = `${counts.pending_requests} pending`;
  document.querySelector("#reportPreventive").textContent = counts.preventive_tasks;
  document.querySelector("#reportOverduePreventive").textContent = `${counts.overdue_preventive} overdue`;
  document.querySelector("#reportPermits").textContent = counts.permits;
  document.querySelector("#reportActivePermits").textContent = `${counts.active_permits} active`;
  const performance = result.performance;
  document.querySelector("#reportCorrectiveCompleted").textContent = performance.completed_corrective;
  document.querySelector("#reportCorrectiveHours").textContent =
    `${Number(performance.corrective_actual_hours).toFixed(1)} / ${Number(performance.corrective_planned_hours).toFixed(1)} hours`;
  document.querySelector("#reportPreventiveCompleted").textContent = performance.completed_preventive;
  document.querySelector("#reportPreventiveHours").textContent =
    `${Number(performance.preventive_actual_hours).toFixed(1)} / ${Number(performance.preventive_planned_hours).toFixed(1)} hours`;
  document.querySelector("#reportAcceptedWork").textContent = performance.accepted_work;
  document.querySelector("#reportDeniedWork").textContent = performance.denied_work;
  const responseCompliance = result.response_compliance;
  document.querySelector("#reportResponseTargeted").textContent = responseCompliance.targeted;
  document.querySelector("#reportResponseMet").textContent = responseCompliance.met;
  document.querySelector("#reportResponseBreached").textContent = responseCompliance.breached;
  document.querySelector("#reportResponseCompliance").textContent =
    responseCompliance.compliance_percent === null ? "-" : `${responseCompliance.compliance_percent}%`;
  document.querySelector("#reportResponsePending").textContent = `${responseCompliance.pending} pending`;
  const reliability = result.reliability;
  document.querySelector("#reportClassifiedFailures").textContent = reliability.classified_failures;
  document.querySelector("#reportDowntimeHours").textContent = `${Number(reliability.total_downtime_hours).toFixed(2)} h`;
  document.querySelector("#reportDowntimeEvents").textContent = `${reliability.downtime_events} recorded events`;
  document.querySelector("#reportMttr").textContent = `${Number(reliability.mttr_hours).toFixed(2)} h`;
  document.querySelector("#reportRepeatFailureAssets").textContent = reliability.repeat_failure_assets;
  const maintenanceKpis = result.maintenance_kpis;
  document.querySelector("#reportPmCompliance").textContent = maintenanceKpis.pm_compliance_percent === null ? "-" : `${maintenanceKpis.pm_compliance_percent}%`;
  document.querySelector("#reportPmComplianceDetail").textContent = `${maintenanceKpis.pm_completed_on_time} of ${maintenanceKpis.pm_due} within window`;
  document.querySelector("#reportCorrectiveSchedule").textContent = maintenanceKpis.corrective_schedule_percent === null ? "-" : `${maintenanceKpis.corrective_schedule_percent}%`;
  document.querySelector("#reportCorrectiveScheduleDetail").textContent = `${maintenanceKpis.corrective_on_schedule} of ${maintenanceKpis.corrective_scheduled_completed} completed`;
  document.querySelector("#reportCorrectiveBacklog").textContent = maintenanceKpis.corrective_backlog;
  document.querySelector("#reportOldBacklog").textContent = `${maintenanceKpis.backlog_over_30_days} older than 30 days`;
  document.querySelector("#reportBacklogAge").textContent = `${Number(maintenanceKpis.average_backlog_age_days).toFixed(1)} days`;
  document.querySelector("#downloadActivityReport").href = `/api/reports/activity.csv${reportQueryString()}`;
  document.querySelector("#printManagementReport").href = `/print/management-report${reportQueryString()}`;
  renderDailyReport(result.daily);
  renderAreaReport(result.areas);
  renderFailureAssets(reliability.top_failure_assets);
  renderStatusReport(result.statuses);
  lucide.createIcons();
}

function renderFailureAssets(items) {
  document.querySelector("#reportFailureAssets").innerHTML = items.length ? `
    <div class="failure-asset-row heading"><span>KKS</span><span>Equipment</span><span>Failures</span><span>Downtime</span></div>
    ${items.map(item => `<article class="failure-asset-row"><code>${escapeHtml(item.kks_code)}</code><strong>${escapeHtml(item.description)}</strong><span>${item.failures}</span><span>${Number(item.downtime_hours).toFixed(2)} h</span></article>`).join("")}
  ` : '<div class="empty-list">No classified equipment failures in this period.</div>';
}

function renderDailyReport(items) {
  const maximum = Math.max(1, ...items.map(item =>
    item.events + item.corrective + item.preventive + item.permits
  ));
  document.querySelector("#reportDailyChart").innerHTML = items.map(item => {
    const total = item.events + item.corrective + item.preventive + item.permits;
    return `
      <article class="daily-chart-row">
        <time>${escapeHtml(item.activity_date)}</time>
        <div class="daily-bar" title="${total} records">
          <span class="events" style="width:${item.events / maximum * 100}%"></span>
          <span class="corrective" style="width:${item.corrective / maximum * 100}%"></span>
          <span class="preventive" style="width:${item.preventive / maximum * 100}%"></span>
          <span class="permits" style="width:${item.permits / maximum * 100}%"></span>
        </div>
        <strong>${total}</strong>
      </article>
    `;
  }).join("") || '<div class="empty-list">No activity was recorded in this period.</div>';
}

function renderAreaReport(items) {
  const maximum = Math.max(1, ...items.map(item => item.total));
  document.querySelector("#reportAreaChart").innerHTML = items.map(item => `
    <article>
      <span>${escapeHtml(item.responsible_area)}</span>
      <div><i style="width:${item.total / maximum * 100}%"></i></div>
      <strong>${item.total}</strong>
    </article>
  `).join("") || '<div class="empty-list">No responsible-area activity.</div>';
}

function renderStatusReport(statuses) {
  const labels = {
    events: ["Event Log", "notebook-tabs"],
    corrective: ["Corrective", "wrench"],
    preventive: ["Preventive", "calendar-clock"],
    permits: ["Permits", "shield-check"]
  };
  document.querySelector("#reportStatuses").innerHTML = Object.entries(statuses).map(([module, items]) => `
    <article>
      <div class="report-status-title"><i data-lucide="${labels[module][1]}"></i><strong>${labels[module][0]}</strong></div>
      ${items.map(item => `<div class="report-status-row"><span>${escapeHtml(item.status)}</span><strong>${item.total}</strong></div>`).join("") || '<div class="asset-empty">No records</div>'}
    </article>
  `).join("");
}

function showReportError(error) {
  document.querySelector("#reportDailyChart").innerHTML = `<div class="error">${escapeHtml(error.message)}</div>`;
}

async function loadUsers() {
  const response = await fetch("/api/users");
  if (!response.ok) throw new Error("Unable to load employee accounts");
  renderUsers(await response.json());
}

function renderUsers(items) {
  document.querySelector("#userAdminList").innerHTML = items.map(user => `
    <article class="user-admin-row ${user.status}">
      <div class="user-admin-identity"><span class="avatar">${escapeHtml(user.initials)}</span><span><strong>${escapeHtml(user.full_name)}</strong><small>${escapeHtml(user.employee_no)}</small></span></div>
      <span>${escapeHtml(user.department)}</span>
      <select data-user-role="${user.id}" aria-label="Role for ${escapeHtml(user.full_name)}">
        ${userRoles.map(role => `<option ${role === user.role_name ? "selected" : ""}>${escapeHtml(role)}</option>`).join("")}
      </select>
      <span class="account-status ${escapeHtml(user.status)}">${escapeHtml(user.status)}</span>
      <div class="user-admin-actions">
        <button class="icon-button compact-action" data-reset-user="${user.id}" title="Reset password" aria-label="Reset password"><i data-lucide="key-round"></i></button>
        <button class="icon-button compact-action" data-toggle-user="${user.id}" data-status="${user.status}" title="${user.status === "active" ? "Deactivate" : "Activate"} account" aria-label="${user.status === "active" ? "Deactivate" : "Activate"} account"><i data-lucide="${user.status === "active" ? "user-x" : "user-check"}"></i></button>
      </div>
    </article>
  `).join("") || '<div class="empty-list">No employee accounts are configured.</div>';
  document.querySelectorAll("[data-user-role]").forEach(select => {
    select.addEventListener("change", () => updateUser(Number(select.dataset.userRole), {
      role_name: select.value
    }).catch(showUserAdminError));
  });
  document.querySelectorAll("[data-toggle-user]").forEach(button => {
    button.addEventListener("click", () => updateUser(Number(button.dataset.toggleUser), {
      status: button.dataset.status === "active" ? "inactive" : "active"
    }).catch(showUserAdminError));
  });
  document.querySelectorAll("[data-reset-user]").forEach(button => {
    button.addEventListener("click", () => resetUserPassword(Number(button.dataset.resetUser)).catch(showUserAdminError));
  });
  lucide.createIcons();
}

function openUserModal() {
  document.querySelector("#userForm").reset();
  document.querySelector("#userFormMessage").textContent = "";
  document.querySelector("#userModal").classList.add("open");
  document.querySelector("#userModal").setAttribute("aria-hidden", "false");
}

function closeUserModal() {
  document.querySelector("#userModal").classList.remove("open");
  document.querySelector("#userModal").setAttribute("aria-hidden", "true");
}

async function saveUser(event) {
  event.preventDefault();
  const message = document.querySelector("#userFormMessage");
  const payload = Object.fromEntries(new FormData(event.currentTarget).entries());
  const response = await fetch("/api/users", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload)
  });
  const result = await response.json();
  if (!response.ok) {
    message.textContent = result.error || "Unable to create account";
    return;
  }
  message.textContent = `${result.full_name} created successfully.`;
  message.className = "form-message success";
  await loadUsers();
  setTimeout(closeUserModal, 450);
}

async function updateUser(userId, payload) {
  const response = await fetch(`/api/users/${userId}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload)
  });
  const result = await response.json();
  if (!response.ok) throw new Error(result.error || "Unable to update account");
  await loadUsers();
}

async function resetUserPassword(userId) {
  const password = window.prompt("Enter a new temporary password with at least 8 characters:");
  if (password === null) return;
  const response = await fetch(`/api/users/${userId}/reset-password`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ password })
  });
  const result = await response.json();
  if (!response.ok) throw new Error(result.error || "Unable to reset password");
}

function showUserAdminError(error) {
  document.querySelector("#userAdminList").innerHTML = `<div class="error">${escapeHtml(error.message)}</div>`;
}

async function loadPublicLogbooks() {
  const response = await fetch("/api/logbooks");
  if (!response.ok) throw new Error("Unable to refresh logbook master data");
  logbooks = await response.json();
  selectedLogbookIds = new Set([...selectedLogbookIds].filter(id => logbooks.some(item => item.id === id)));
  populateMasterData();
}

async function loadAdminLogbooks() {
  const response = await fetch("/api/admin/logbooks");
  if (!response.ok) throw new Error("Unable to load logbook master data");
  adminLogbooks = await response.json();
  renderAdminLogbooks(adminLogbooks);
}

function renderAdminLogbooks(items) {
  document.querySelector("#logbookAdminList").innerHTML = items.map(item => `
    <article class="logbook-admin-row">
      <div><strong>${escapeHtml(item.name)}</strong><small>${escapeHtml(item.code)}${item.is_shift_leader ? " / Shift leader visible" : ""}</small></div>
      <span>${escapeHtml(item.department)}</span>
      <span>${escapeHtml(item.can_create_role)}</span>
      <div><strong>${Number(item.entry_count).toLocaleString()} source entries</strong><small>${Number(item.visible_entry_count).toLocaleString()} visible / ${item.last_activity_at ? formatDate(item.last_activity_at) : "No activity"}</small></div>
      <div class="logbook-admin-actions"><button class="icon-button compact-action" data-edit-logbook="${item.id}" title="Edit logbook" aria-label="Edit logbook"><i data-lucide="pencil"></i></button></div>
    </article>
  `).join("") || '<div class="empty-list">No logbooks are configured.</div>';
  document.querySelectorAll("[data-edit-logbook]").forEach(button => {
    button.addEventListener("click", () => openLogbookModal(adminLogbooks.find(item => item.id === Number(button.dataset.editLogbook))));
  });
  lucide.createIcons();
}

function openLogbookModal(item = null) {
  const form = document.querySelector("#logbookForm");
  const message = document.querySelector("#logbookFormMessage");
  form.reset();
  message.textContent = "";
  message.className = "form-message";
  editingLogbookId = item?.id || null;
  document.querySelector("#logbookModalTitle").textContent = item ? "Edit logbook" : "Create logbook";
  document.querySelector("#saveLogbook").innerHTML = item ? '<i data-lucide="save"></i> Update logbook' : '<i data-lucide="save"></i> Save logbook';
  if (item) {
    form.elements.id.value = item.id;
    form.elements.code.value = item.code;
    form.elements.name.value = item.name;
    form.elements.department.value = item.department;
    form.elements.can_create_role.value = item.can_create_role;
    form.elements.is_shift_leader.checked = Boolean(item.is_shift_leader);
  }
  document.querySelector("#logbookModal").classList.add("open");
  document.querySelector("#logbookModal").setAttribute("aria-hidden", "false");
  lucide.createIcons();
}

function closeLogbookModal() {
  document.querySelector("#logbookModal").classList.remove("open");
  document.querySelector("#logbookModal").setAttribute("aria-hidden", "true");
  editingLogbookId = null;
}

async function saveLogbook(event) {
  event.preventDefault();
  const form = event.currentTarget;
  const message = document.querySelector("#logbookFormMessage");
  const payload = Object.fromEntries(new FormData(form).entries());
  payload.is_shift_leader = form.elements.is_shift_leader.checked;
  delete payload.id;
  const response = await fetch(editingLogbookId ? `/api/admin/logbooks/${editingLogbookId}` : "/api/admin/logbooks", {
    method: editingLogbookId ? "PATCH" : "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload)
  });
  const result = await response.json();
  if (!response.ok) {
    message.textContent = result.error || "Unable to save logbook";
    return;
  }
  message.textContent = editingLogbookId ? "Logbook updated." : "Logbook created.";
  message.className = "form-message success";
  await Promise.all([loadAdminLogbooks(), loadPublicLogbooks(), loadDashboard()]);
  setTimeout(closeLogbookModal, 450);
}

function showLogbookAdminError(error) {
  document.querySelector("#logbookAdminList").innerHTML = `<div class="error">${escapeHtml(error.message)}</div>`;
}

function auditQueryString() {
  const parameters = new URLSearchParams({ limit: "500" });
  const values = {
    q: document.querySelector("#auditSearch").value.trim(),
    action: document.querySelector("#auditAction").value,
    start: document.querySelector("#auditStart").value,
    end: document.querySelector("#auditEnd").value
  };
  Object.entries(values).forEach(([key, value]) => {
    if (value) parameters.set(key, value);
  });
  return `?${parameters.toString()}`;
}

async function loadAuditLogs() {
  const list = document.querySelector("#auditList");
  list.innerHTML = '<div class="loading">Loading audit records...</div>';
  const [logsResponse, actionsResponse] = await Promise.all([
    fetch(`/api/audit-logs${auditQueryString()}`),
    fetch("/api/audit-logs/actions")
  ]);
  if (!logsResponse.ok || !actionsResponse.ok) throw new Error("Unable to load audit trail");
  const selectedAction = document.querySelector("#auditAction").value;
  const actions = await actionsResponse.json();
  document.querySelector("#auditAction").innerHTML =
    '<option value="">All actions</option>' +
    actions.map(action => `<option ${action === selectedAction ? "selected" : ""}>${escapeHtml(action)}</option>`).join("");
  renderAuditLogs(await logsResponse.json());
}

function renderAuditLogs(items) {
  document.querySelector("#auditList").innerHTML = items.map(item => `
    <article class="audit-row">
      <div><strong>${formatDate(item.created_at)}</strong><small>${escapeHtml(item.ip_address || "-")}</small></div>
      <div><strong>${escapeHtml(item.user_name || "Unknown")}</strong><small>${escapeHtml(item.employee_no || "-")} / ${escapeHtml(item.role_name || "-")}</small></div>
      <div><strong>${escapeHtml(item.action)}</strong><small>${escapeHtml(item.method)}</small></div>
      <code>${escapeHtml(item.target)}</code>
      <span class="audit-result">${item.status_code}</span>
      <button class="icon-button compact-action" data-audit-detail="${item.id}" title="View details" aria-label="View details"><i data-lucide="chevron-down"></i></button>
      <pre class="audit-details" id="auditDetail${item.id}">${escapeHtml(item.details || "No request details recorded.")}</pre>
    </article>
  `).join("") || '<div class="empty-list">No audit records match these filters.</div>';
  document.querySelectorAll("[data-audit-detail]").forEach(button => {
    button.addEventListener("click", () => {
      document.querySelector(`#auditDetail${button.dataset.auditDetail}`).classList.toggle("open");
    });
  });
  lucide.createIcons();
}

function showAuditError(error) {
  document.querySelector("#auditList").innerHTML = `<div class="error">${escapeHtml(error.message)}</div>`;
}

function readinessCategoryLabel(category) {
  return {
    application: "Application Readiness",
    data: "Data Readiness",
    access: "Access Readiness",
    process: "Process Readiness",
    training: "Training Readiness",
    support: "Support Readiness",
    open_items: "Open Items"
  }[category] || category;
}

function readinessStatusLabel(status) {
  return {
    pending: "Pending",
    in_progress: "In progress",
    done: "Done",
    blocked: "Blocked",
    deferred: "Deferred"
  }[status] || status;
}

function readinessFilters() {
  return {
    q: document.querySelector("#readinessSearch").value.trim().toLowerCase(),
    category: document.querySelector("#readinessCategory").value,
    status: document.querySelector("#readinessStatus").value
  };
}

async function loadReadiness() {
  const list = document.querySelector("#readinessList");
  list.innerHTML = '<div class="loading">Loading pilot readiness checklist...</div>';
  const response = await fetch("/api/readiness");
  if (!response.ok) throw new Error("Unable to load pilot readiness checklist");
  const result = await response.json();
  readinessItems = result.items;
  document.querySelector("#readinessTotal").textContent = result.summary.total;
  document.querySelector("#readinessDone").textContent = result.summary.done;
  document.querySelector("#readinessPercent").textContent = `${result.summary.completion_percent}% complete`;
  document.querySelector("#readinessOpen").textContent =
    (result.summary.pending + result.summary.in_progress).toLocaleString();
  document.querySelector("#readinessBlocked").textContent = result.summary.blocked;
  const categorySelect = document.querySelector("#readinessCategory");
  const selectedCategory = categorySelect.value;
  const categories = [...new Set(readinessItems.map(item => item.category))];
  categorySelect.innerHTML = '<option value="">All categories</option>' +
    categories.map(category => `<option value="${escapeHtml(category)}">${escapeHtml(readinessCategoryLabel(category))}</option>`).join("");
  categorySelect.value = categories.includes(selectedCategory) ? selectedCategory : "";
  renderReadiness();
}

function renderReadiness() {
  const filters = readinessFilters();
  const items = readinessItems.filter(item => {
    const haystack = `${item.item} ${item.category} ${item.owner || ""} ${item.evidence || ""}`.toLowerCase();
    return (!filters.q || haystack.includes(filters.q)) &&
      (!filters.category || item.category === filters.category) &&
      (!filters.status || item.status === filters.status);
  });
  document.querySelector("#readinessList").innerHTML = items.map(item => `
    <article class="readiness-row status-${escapeHtml(item.status)}" data-readiness-id="${item.id}">
      <div><strong>${escapeHtml(item.item)}</strong><small>${escapeHtml(readinessCategoryLabel(item.category))}</small></div>
      <select data-readiness-field="status" aria-label="Status for ${escapeHtml(item.item)}">
        ${["pending", "in_progress", "done", "blocked", "deferred"].map(status => `<option value="${status}" ${status === item.status ? "selected" : ""}>${escapeHtml(readinessStatusLabel(status))}</option>`).join("")}
      </select>
      <div class="readiness-owner">
        <input data-readiness-field="owner" value="${escapeHtml(item.owner || "")}" placeholder="Owner">
        <input data-readiness-field="target_date" type="date" value="${escapeHtml(item.target_date || "")}">
      </div>
      <textarea data-readiness-field="evidence" rows="2" placeholder="Evidence / notes">${escapeHtml(item.evidence || "")}</textarea>
      <div><strong>${escapeHtml(item.updated_by || "Not updated")}</strong><small>${formatDate(item.updated_at)}</small></div>
      <button class="icon-button compact-action" data-save-readiness="${item.id}" title="Save readiness item" aria-label="Save readiness item"><i data-lucide="save"></i></button>
    </article>
  `).join("") || '<div class="empty-list">No readiness items match the selected filters.</div>';
  document.querySelectorAll("[data-save-readiness]").forEach(button => {
    button.addEventListener("click", () => saveReadinessItem(Number(button.dataset.saveReadiness)).catch(showReadinessError));
  });
  lucide.createIcons();
}

async function saveReadinessItem(itemId) {
  const row = document.querySelector(`[data-readiness-id="${itemId}"]`);
  const payload = {};
  row.querySelectorAll("[data-readiness-field]").forEach(field => {
    payload[field.dataset.readinessField] = field.value;
  });
  const response = await fetch(`/api/readiness/${itemId}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload)
  });
  const result = await response.json();
  if (!response.ok) throw new Error(result.error || "Unable to save readiness item");
  await loadReadiness();
}

function showReadinessError(error) {
  document.querySelector("#readinessList").innerHTML = `<div class="error">${escapeHtml(error.message)}</div>`;
}

function formatStorage(bytes) {
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}

async function loadSystemStatus() {
  const [response, backupsResponse] = await Promise.all([
    fetch("/api/system/status"), fetch("/api/system/backups")
  ]);
  if (!response.ok || !backupsResponse.ok) throw new Error("Unable to load system status");
  const status = await response.json();
  const backups = await backupsResponse.json();
  document.querySelector("#systemDatabaseSize").textContent = formatStorage(status.database_bytes);
  document.querySelector("#systemIntegrity").textContent =
    status.integrity === "ok" ? "Integrity check passed" : `Integrity: ${status.integrity}`;
  document.querySelector("#systemAttachmentSize").textContent = formatStorage(status.upload_bytes);
  document.querySelector("#systemAttachmentCount").textContent = `${status.upload_files} files`;
  document.querySelector("#systemAssetCount").textContent = status.counts.assets.toLocaleString();
  document.querySelector("#systemForeignKeys").textContent = status.foreign_key_issues;
  const countLabels = {
    events: "Event entries",
    work_requests: "Work requests",
    recurrent_tasks: "Recurrent schedules",
    preventive_tasks: "Preventive tasks",
    permits: "PTW / LoA / SFT",
    active_users: "Active users",
    attachments: "Attachment records",
    audit_records: "Audit records"
  };
  document.querySelector("#systemRecordCounts").innerHTML = Object.entries(countLabels).map(([key, label]) => `
    <article><span>${escapeHtml(label)}</span><strong>${Number(status.counts[key] || 0).toLocaleString()}</strong></article>
  `).join("");
  document.querySelector("#systemImportHistory").innerHTML = status.kks_import_runs.map(item => `
    <article>
      <div><strong>${Number(item.unique_assets).toLocaleString()} assets</strong><small>${formatDate(item.imported_at)}</small></div>
      <span>${Number(item.duplicate_rows).toLocaleString()} duplicates / ${Number(item.inferred_parents).toLocaleString()} inferred</span>
    </article>
  `).join("") || '<div class="empty-list">No KKS imports recorded.</div>';
  document.querySelector("#systemBackupRuns").innerHTML = backups.filter(item => item.status === "available").map(item => `
    <article class="backup-run-row">
      <div><strong>${formatDate(item.created_at)}</strong><small>${escapeHtml(item.created_by)}</small></div>
      <div><strong>${escapeHtml(item.filename)}</strong><small>${formatStorage(item.archive_bytes)} / SHA-256 ${escapeHtml(item.sha256.slice(0, 12))}...</small></div>
      <div><strong>${formatStorage(item.database_bytes)} database</strong><small>${item.upload_files} files / ${formatStorage(item.upload_bytes)}</small></div>
      <div><span class="backup-integrity ${escapeHtml(item.integrity)}">${escapeHtml(item.integrity.replaceAll("_", " "))}</span><small>${item.last_verified_at ? formatDate(item.last_verified_at) : "Not yet verified"}</small></div>
      <div class="backup-run-actions"><button class="icon-button compact-action" data-verify-backup="${item.id}" title="Verify backup" aria-label="Verify backup"><i data-lucide="shield-check"></i></button>${item.integrity === "verified" ? `<button class="icon-button compact-action" data-restore-backup="${item.id}" title="Restore backup" aria-label="Restore backup"><i data-lucide="database-backup"></i></button>` : ""}<a class="icon-button compact-action" href="/api/system/backups/${item.id}/download" title="Download backup" aria-label="Download backup"><i data-lucide="download"></i></a><button class="icon-button compact-action danger-icon" data-delete-backup="${item.id}" title="Delete backup" aria-label="Delete backup"><i data-lucide="trash-2"></i></button></div>
    </article>`).join("") || '<div class="empty-list">No retained recovery points. Create a full backup to begin.</div>';
  document.querySelectorAll("[data-verify-backup]").forEach(button => button.addEventListener("click", () => verifySystemBackup(Number(button.dataset.verifyBackup)).catch(showSystemError)));
  document.querySelectorAll("[data-restore-backup]").forEach(button => button.addEventListener("click", () => restoreSystemBackup(Number(button.dataset.restoreBackup)).catch(showSystemError)));
  document.querySelectorAll("[data-delete-backup]").forEach(button => button.addEventListener("click", () => deleteSystemBackup(Number(button.dataset.deleteBackup)).catch(showSystemError)));
  document.querySelector("#systemRestoreHistory").innerHTML = status.restore_runs.map(item => `<article class="restore-run-row"><div><strong>${formatDate(item.restored_at)}</strong><small>${escapeHtml(item.restored_by)}</small></div><div><strong>${escapeHtml(item.source_filename)}</strong><small>Restored recovery point</small></div><div><strong>Safety backup retained</strong><small>${escapeHtml(item.safety_backup_filename)}</small></div></article>`).join("") || '<div class="empty-list">No restore operations recorded.</div>';
  lucide.createIcons();
}

async function createSystemBackup() {
  const button = document.querySelector("#createSystemBackup");
  button.disabled = true;
  try {
    const response = await fetch("/api/system/backup");
    if (!response.ok) throw new Error("Unable to create full backup");
    const blob = await response.blob();
    const disposition = response.headers.get("Content-Disposition") || "";
    const match = disposition.match(/filename\*?=(?:UTF-8''|\")?([^\";]+)/i);
    const link = document.createElement("a");
    link.href = URL.createObjectURL(blob);
    link.download = decodeURIComponent(match?.[1] || "spulse-backup.zip");
    link.click();
    URL.revokeObjectURL(link.href);
    await loadSystemStatus();
  } finally {
    button.disabled = false;
  }
}

async function verifySystemBackup(id) {
  const response = await fetch(`/api/system/backups/${id}/verify`, { method: "POST" });
  const result = await response.json();
  if (!response.ok) throw new Error(result.errors?.join("; ") || result.error || "Backup verification failed");
  await loadSystemStatus();
}

async function restoreSystemBackup(id) {
  const confirmation = window.prompt("Type RESTORE S-PULSE to replace the current database and attachments:");
  if (confirmation !== "RESTORE S-PULSE") return;
  const response = await fetch(`/api/system/backups/${id}/restore`, {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ confirmation })
  });
  const result = await response.json();
  if (!response.ok) throw new Error(result.error || "System restore failed");
  await loadSystemStatus();
}

async function deleteSystemBackup(id) {
  if (!window.confirm("Delete this retained recovery point?")) return;
  const response = await fetch(`/api/system/backups/${id}`, { method: "DELETE" });
  const result = await response.json();
  if (!response.ok) throw new Error(result.error || "Unable to delete backup");
  await loadSystemStatus();
}

function showSystemError(error) {
  document.querySelector("#systemRecordCounts").innerHTML = `<div class="error">${escapeHtml(error.message)}</div>`;
}

async function loadKksImports() {
  const response = await fetch("/api/kks-imports");
  if (!response.ok) throw new Error("Unable to load KKS import history");
  const items = await response.json();
  document.querySelector("#kksImportHistory").innerHTML = items.map(item => `
    <article>
      <div><strong>${escapeHtml(item.original_name)}</strong><small>${formatDate(item.validated_at)} / ${escapeHtml(item.validated_by)}</small></div>
      <div><strong>${Number(item.unique_assets).toLocaleString()} assets</strong><small>${Number(item.duplicate_rows).toLocaleString()} duplicates / ${Number(item.inferred_parents).toLocaleString()} inferred</small></div>
      <span class="account-status ${item.status === "imported" ? "active" : item.status === "failed" ? "inactive" : "validated"}">${escapeHtml(item.status)}</span>
    </article>
  `).join("") || '<div class="empty-list">No web imports have been staged.</div>';
}

async function validateKksWorkbook() {
  const input = document.querySelector("#kksWorkbookFile");
  const message = document.querySelector("#kksValidationMessage");
  if (!input.files.length) {
    message.textContent = "Select an .xlsx workbook.";
    return;
  }
  const form = new FormData();
  form.append("file", input.files[0]);
  message.textContent = "Validating workbook...";
  document.querySelector("#validateKksWorkbook").disabled = true;
  try {
    const response = await fetch("/api/kks-imports/validate", {
      method: "POST",
      body: form
    });
    const result = await response.json();
    if (!response.ok) throw new Error(result.error || "Workbook validation failed");
    validatedKksImportId = result.id;
    message.textContent = "Workbook validation completed.";
    message.className = "form-message success";
    document.querySelector("#kksValidationResult").innerHTML = `
      <div class="kks-validation-grid">
        <article><small>Source rows</small><strong>${Number(result.source_rows).toLocaleString()}</strong></article>
        <article><small>Unique assets</small><strong>${Number(result.unique_assets).toLocaleString()}</strong></article>
        <article><small>New assets</small><strong>${Number(result.new_assets).toLocaleString()}</strong></article>
        <article><small>Matched assets</small><strong>${Number(result.matched_assets).toLocaleString()}</strong></article>
        <article><small>Duplicates</small><strong>${Number(result.duplicate_rows).toLocaleString()}</strong></article>
        <article><small>Inferred parents</small><strong>${Number(result.inferred_parents).toLocaleString()}</strong></article>
      </div>
      <button class="button primary" id="commitKksImport"><i data-lucide="database-zap"></i> Import validated register</button>
    `;
    document.querySelector("#commitKksImport").addEventListener("click", commitKksImport);
    await loadKksImports();
    lucide.createIcons();
  } catch (error) {
    message.textContent = error.message;
    message.className = "form-message";
  } finally {
    document.querySelector("#validateKksWorkbook").disabled = false;
  }
}

async function commitKksImport() {
  if (!validatedKksImportId) return;
  const button = document.querySelector("#commitKksImport");
  const message = document.querySelector("#kksValidationMessage");
  button.disabled = true;
  message.textContent = "Importing validated KKS register...";
  const response = await fetch(`/api/kks-imports/${validatedKksImportId}/commit`, {
    method: "POST"
  });
  const result = await response.json();
  if (!response.ok) {
    message.textContent = result.error || "KKS import failed";
    button.disabled = false;
    return;
  }
  message.textContent = `${Number(result.unique_assets).toLocaleString()} assets imported successfully.`;
  message.className = "form-message success";
  validatedKksImportId = null;
  document.querySelector("#kksValidationResult").innerHTML =
    '<div class="empty-list">Import completed. Select another workbook when required.</div>';
  await Promise.all([loadKksImports(), loadDashboard()]);
}

function showKksImportError(error) {
  document.querySelector("#kksImportHistory").innerHTML = `<div class="error">${escapeHtml(error.message)}</div>`;
}

function openEntryModal(parent = null, editing = null) {
  const form = document.querySelector("#entryForm");
  form.reset();
  editingEventId = editing?.id || null;
  form.elements.created_by.value = currentUser.full_name;
  document.querySelector("#entryFormMessage").textContent = "";
  document.querySelector("#entryFormMessage").className = "form-message";
  document.querySelector("#parentEntryId").value = parent?.id || "";
  document.querySelector("#entryModalTitle").textContent = editing ? "Edit event entry" : parent ? "New sub-entry" : "New main entry";
  document.querySelector("#entrySubject").value = editing?.subject || parent?.subject || "";
  document.querySelector("#entrySubject").disabled = Boolean(parent || editing);
  setAssetPicker(
    "entryAsset",
    (editing || parent)?.asset_id ? {
      id: (editing || parent).asset_id,
      kks_code: (editing || parent).kks_code,
      description: (editing || parent).asset_description
    } : null,
    Boolean(parent || editing?.parent_id)
  );
  document.querySelector("#entryEventDate").value = (editing || parent) ? (editing || parent).event_date.slice(0, 16) : localDateTimeValue();
  document.querySelector("#entryEventDate").disabled = Boolean(parent || editing?.parent_id);
  const writableLogbooks = logbooks.filter(canCreateLogbookEntry);
  const selectedLogbook = (editing || parent)
    ? writableLogbooks.find(item => item.id === (editing || parent).source_logbook_id)
    : writableLogbooks.find(item => item.code === "OPS") || writableLogbooks[0];
  if (!selectedLogbook) return;
  document.querySelector("#entryLogbook").value = selectedLogbook.id;
  document.querySelector("#entryLogbook").disabled = Boolean(parent || editing);
  form.elements.state.value = editing?.state || "open";
  form.elements.state.disabled = Boolean(editing);
  form.elements.informant.value = editing?.informant || "";
  form.elements.observation.value = editing?.observation || "";
  document.querySelector("#saveEntry").innerHTML = editing
    ? '<i data-lucide="save"></i> Save changes'
    : '<i data-lucide="save"></i> Save entry';
  document.querySelector("#entryModal").classList.add("open");
  document.querySelector("#entryModal").setAttribute("aria-hidden", "false");
  lucide.createIcons();
}

function closeEntryModal() {
  document.querySelector("#entryModal").classList.remove("open");
  document.querySelector("#entryModal").setAttribute("aria-hidden", "true");
}

function openDeleteEventModal() {
  document.querySelector("#deleteEventForm").reset();
  document.querySelector("#deleteEventNumber").textContent = selectedEvent.entry_no;
  document.querySelector("#deleteEventMessage").textContent = "";
  document.querySelector("#deleteEventModal").classList.add("open");
  document.querySelector("#deleteEventModal").setAttribute("aria-hidden", "false");
}

function closeDeleteEventModal() {
  document.querySelector("#deleteEventModal").classList.remove("open");
  document.querySelector("#deleteEventModal").setAttribute("aria-hidden", "true");
}

async function deleteEventEntry(event) {
  event.preventDefault();
  const form = event.currentTarget;
  const message = document.querySelector("#deleteEventMessage");
  const button = document.querySelector("#confirmDeleteEvent");
  button.disabled = true;
  message.textContent = "Deleting event entry...";
  try {
    const response = await fetch(`/api/events/${selectedEventId}`, {
      method: "DELETE",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ reason: form.elements.reason.value.trim() })
    });
    const result = await response.json();
    if (!response.ok) throw new Error(result.error || "Unable to delete event entry");
    selectedEventId = null;
    selectedEvent = null;
    closeDeleteEventModal();
    await Promise.all([loadEvents(), loadDashboard()]);
  } catch (error) {
    message.textContent = error.message;
  } finally {
    button.disabled = false;
  }
}

async function saveEntry(event) {
  event.preventDefault();
  const form = event.currentTarget;
  const saveButton = document.querySelector("#saveEntry");
  const message = document.querySelector("#entryFormMessage");
  const payload = Object.fromEntries(new FormData(form).entries());
  if (!editingEventId) payload.logbook_id = Number(payload.logbook_id);
  payload.asset_id = payload.asset_id ? Number(payload.asset_id) : null;
  payload.parent_id = payload.parent_id ? Number(payload.parent_id) : null;
  if (payload.parent_id && selectedEvent) {
    payload.subject = selectedEvent.subject;
    payload.asset_id = selectedEvent.asset_id;
    payload.event_date = selectedEvent.event_date;
  }
  saveButton.disabled = true;
  message.textContent = "Saving entry...";
  try {
    const response = await fetch(editingEventId ? `/api/events/${editingEventId}` : "/api/events", {
      method: editingEventId ? "PATCH" : "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload)
    });
    const result = await response.json();
    if (!response.ok) throw new Error(result.error || "Unable to save entry");
    message.textContent = `${result.entry_no} ${editingEventId ? "updated" : "created"} successfully.`;
    message.className = "form-message success";
    selectedEventId = result.parent_id || result.id;
    await Promise.all([loadEvents(), loadDashboard()]);
    setTimeout(closeEntryModal, 450);
  } catch (error) {
    message.textContent = error.message;
    message.className = "form-message";
  } finally {
    saveButton.disabled = false;
  }
}

function showEventError(error) {
  document.querySelector("#eventList").innerHTML = `<div class="error">${escapeHtml(error.message)}</div>`;
}

function showGlobalError(error) {
  document.querySelector("#recentEvents").innerHTML = `<div class="error">${escapeHtml(error.message)}</div>`;
}

document.querySelectorAll(".nav-item[data-view]").forEach(button => {
  button.addEventListener("click", () => openView(button.dataset.view));
});
window.addEventListener("hashchange", () => {
  openView(window.location.hash.slice(1) || "dashboard", false);
});
document.querySelector("#menuButton").addEventListener("click", () => sidebar.classList.toggle("open"));
document.querySelector("#dashboardNewEntry").addEventListener("click", () => openEntryModal());
document.querySelector("#openReadinessTracker").addEventListener("click", () => openView("readiness"));
document.querySelector("#newMainEntry").addEventListener("click", () => openEntryModal());
document.querySelector("#newShiftHandover").addEventListener("click", () => openShiftHandoverModal().catch(showHandoverError));
document.querySelector("#handoverStatusFilter").addEventListener("change", () => { selectedHandoverId = null; loadShiftHandovers().catch(showHandoverError); });
document.querySelector("#shiftHandoverForm").addEventListener("submit", saveShiftHandover);
document.querySelector("#closeShiftHandoverModal").addEventListener("click", closeShiftHandoverModal);
document.querySelector("#cancelShiftHandover").addEventListener("click", closeShiftHandoverModal);
document.querySelector("#shiftHandoverModal").addEventListener("click", event => { if (event.target.id === "shiftHandoverModal") closeShiftHandoverModal(); });
document.querySelector("#newSubEntry").addEventListener("click", () => openEntryModal(selectedEvent));
document.querySelector("#openAllEvents").addEventListener("click", () => openView("events"));
document.querySelector("#closeEntryModal").addEventListener("click", closeEntryModal);
document.querySelector("#cancelEntry").addEventListener("click", closeEntryModal);
document.querySelector("#entryModal").addEventListener("click", event => {
  if (event.target.id === "entryModal") closeEntryModal();
});
document.querySelector("#deleteEventForm").addEventListener("submit", deleteEventEntry);
document.querySelector("#closeDeleteEventModal").addEventListener("click", closeDeleteEventModal);
document.querySelector("#cancelDeleteEvent").addEventListener("click", closeDeleteEventModal);
document.querySelector("#deleteEventModal").addEventListener("click", event => {
  if (event.target.id === "deleteEventModal") closeDeleteEventModal();
});
document.querySelector("#entryForm").addEventListener("submit", saveEntry);
document.querySelector("#infoboxPriority").addEventListener("change", () => loadInfobox().catch(showInfoboxError));
document.querySelector("#infoboxTiming").addEventListener("change", () => loadInfobox().catch(showInfoboxError));
document.querySelector("#infoboxSearch").addEventListener("input", () => {
  window.clearTimeout(infoboxSearchTimer);
  infoboxSearchTimer = window.setTimeout(() => {
    loadInfobox().catch(showInfoboxError);
  }, 250);
});
document.querySelector("#infoboxGroup").addEventListener("change", event => {
  infoboxGroup = event.target.value;
  loadInfobox().catch(showInfoboxError);
});
document.querySelectorAll("#infoboxScopeFilter [data-scope]").forEach(button => {
  button.addEventListener("click", () => {
    infoboxScope = button.dataset.scope;
    if (infoboxScope === "my") infoboxGroup = "";
    document.querySelectorAll("#infoboxScopeFilter [data-scope]").forEach(item => {
      item.classList.toggle("active", item === button);
    });
    loadInfobox().catch(showInfoboxError);
  });
});
document.querySelectorAll("#infoboxStateFilter [data-state]").forEach(button => {
  button.addEventListener("click", () => {
    infoboxState = button.dataset.state;
    document.querySelectorAll("#infoboxStateFilter [data-state]").forEach(item => {
      item.classList.toggle("active", item === button);
    });
    loadInfobox().catch(showInfoboxError);
  });
});
document.querySelectorAll("#infoboxSourceFilter [data-source]").forEach(button => {
  button.addEventListener("click", () => {
    infoboxSource = button.dataset.source;
    document.querySelectorAll("#infoboxSourceFilter [data-source]").forEach(item => {
      item.classList.toggle("active", item === button);
    });
    loadInfobox().catch(showInfoboxError);
  });
});
document.querySelector("#assetSearch").addEventListener("input", () => {
  window.clearTimeout(assetSearchTimer);
  assetSearchTimer = window.setTimeout(() => {
    loadAssetWorkspace().catch(showAssetError);
  }, 250);
});
document.querySelector("#newWorkRequest").addEventListener("click", () => openWorkRequestModal());
document.querySelector("#closeWorkRequestModal").addEventListener("click", closeWorkRequestModal);
document.querySelector("#cancelWorkRequest").addEventListener("click", closeWorkRequestModal);
document.querySelector("#workRequestModal").addEventListener("click", event => {
  if (event.target.id === "workRequestModal") closeWorkRequestModal();
});
document.querySelector("#workRequestForm").addEventListener("submit", saveWorkRequest);
document.querySelector("#workCompletionForm").addEventListener("submit", submitWorkCompletion);
document.querySelector("#closeWorkCompletionModal").addEventListener("click", closeWorkCompletionModal);
document.querySelector("#cancelWorkCompletion").addEventListener("click", closeWorkCompletionModal);
document.querySelector("#workCompletionModal").addEventListener("click", event => {
  if (event.target.id === "workCompletionModal") closeWorkCompletionModal();
});
document.querySelector("#workRequestForm").elements.cmpt_severity.addEventListener("change", updateCmptPriority);
document.querySelector("#workRequestForm").elements.cmpt_likelihood.addEventListener("change", updateCmptPriority);
document.querySelector("#newScheduleType").addEventListener("click", openScheduleTypeModal);
document.querySelector("#closeScheduleTypeModal").addEventListener("click", closeScheduleTypeModal);
document.querySelector("#cancelScheduleType").addEventListener("click", closeScheduleTypeModal);
document.querySelector("#scheduleTypeForm").addEventListener("submit", saveScheduleType);
document.querySelector("#scheduleTypeModal").addEventListener("click", event => {
  if (event.target.id === "scheduleTypeModal") closeScheduleTypeModal();
});
document.querySelector("#newRecurrentTask").addEventListener("click", openRecurrentTaskModal);
document.querySelector("#closeRecurrentTaskModal").addEventListener("click", closeRecurrentTaskModal);
document.querySelector("#cancelRecurrentTask").addEventListener("click", closeRecurrentTaskModal);
document.querySelector("#recurrentTaskForm").addEventListener("submit", saveRecurrentTask);
document.querySelector("#addRecurrentGroupAsset").addEventListener("click", addRecurrentGroupAsset);
document.querySelector("#recurrentTaskModal").addEventListener("click", event => {
  if (event.target.id === "recurrentTaskModal") closeRecurrentTaskModal();
});
document.querySelector("#preventiveTaskForm").addEventListener("submit", completePreventiveTask);
document.querySelector("#preventiveTaskModal").addEventListener("click", event => {
  if (event.target.id === "preventiveTaskModal") closePreventiveTaskModal();
});
document.querySelector("#closePreventiveTaskModal").addEventListener("click", closePreventiveTaskModal);
document.querySelector("#cancelPreventiveTask").addEventListener("click", closePreventiveTaskModal);
document.querySelector("#newSafetyPermit").addEventListener("click", () => openSafetyPermitModal().catch(showSafetyPermitError));
document.querySelector("#closeSafetyPermitModal").addEventListener("click", closeSafetyPermitModal);
document.querySelector("#cancelSafetyPermit").addEventListener("click", closeSafetyPermitModal);
document.querySelector("#safetyPermitForm").addEventListener("submit", saveSafetyPermit);
document.querySelector("#safetyPermitModal").addEventListener("click", event => {
  if (event.target.id === "safetyPermitModal") closeSafetyPermitModal();
});
document.querySelector("#newUser").addEventListener("click", openUserModal);
document.querySelector("#closeUserModal").addEventListener("click", closeUserModal);
document.querySelector("#cancelUser").addEventListener("click", closeUserModal);
document.querySelector("#userForm").addEventListener("submit", saveUser);
document.querySelector("#userModal").addEventListener("click", event => {
  if (event.target.id === "userModal") closeUserModal();
});
document.querySelector("#newLogbook").addEventListener("click", () => openLogbookModal());
document.querySelector("#closeLogbookModal").addEventListener("click", closeLogbookModal);
document.querySelector("#cancelLogbook").addEventListener("click", closeLogbookModal);
document.querySelector("#logbookForm").addEventListener("submit", saveLogbook);
document.querySelector("#logbookModal").addEventListener("click", event => {
  if (event.target.id === "logbookModal") closeLogbookModal();
});

let auditSearchTimer;
document.querySelector("#auditSearch").addEventListener("input", () => {
  clearTimeout(auditSearchTimer);
  auditSearchTimer = setTimeout(() => loadAuditLogs().catch(showAuditError), 250);
});
["auditAction", "auditStart", "auditEnd"].forEach(id => {
  document.querySelector(`#${id}`).addEventListener("change", () => loadAuditLogs().catch(showAuditError));
});
document.querySelector("#resetAuditFilters").addEventListener("click", () => {
  document.querySelector("#auditSearch").value = "";
  document.querySelector("#auditAction").value = "";
  document.querySelector("#auditStart").value = "";
  document.querySelector("#auditEnd").value = "";
  loadAuditLogs().catch(showAuditError);
});
document.querySelector("#runReport").addEventListener("click", () => loadReports().catch(showReportError));
document.querySelector("#refreshSystemStatus").addEventListener("click", () => loadSystemStatus().catch(showSystemError));
document.querySelector("#createSystemBackup").addEventListener("click", () => createSystemBackup().catch(showSystemError));
document.querySelector("#refreshReadiness").addEventListener("click", () => loadReadiness().catch(showReadinessError));
let readinessSearchTimer;
document.querySelector("#readinessSearch").addEventListener("input", () => {
  clearTimeout(readinessSearchTimer);
  readinessSearchTimer = setTimeout(renderReadiness, 200);
});
["readinessCategory", "readinessStatus"].forEach(id => {
  document.querySelector(`#${id}`).addEventListener("change", renderReadiness);
});
document.querySelector("#validateKksWorkbook").addEventListener("click", validateKksWorkbook);
document.querySelector("#refreshKksImports").addEventListener("click", () => loadKksImports().catch(showKksImportError));

let searchTimer;
document.querySelector("#eventSearch").addEventListener("input", () => {
  clearTimeout(searchTimer);
  searchTimer = setTimeout(() => loadEvents().catch(showEventError), 250);
});
["startDate", "endDate", "stateFilter"].forEach(id => {
  document.querySelector(`#${id}`).addEventListener("change", () => loadEvents().catch(showEventError));
});
document.querySelector("#logbookFilterButton").addEventListener("click", event => {
  event.stopPropagation();
  const menu = document.querySelector("#logbookFilterMenu");
  menu.hidden = !menu.hidden;
  event.currentTarget.setAttribute("aria-expanded", String(!menu.hidden));
});
document.querySelector("#logbookFilterMenu").addEventListener("click", event => event.stopPropagation());
document.addEventListener("click", () => {
  document.querySelector("#logbookFilterMenu").hidden = true;
  document.querySelector("#logbookFilterButton").setAttribute("aria-expanded", "false");
});
document.querySelector("#previousEventRange").addEventListener("click", () => shiftEventDateRange(-1));
document.querySelector("#nextEventRange").addEventListener("click", () => shiftEventDateRange(1));
document.querySelector("#todayEventRange").addEventListener("click", () => {
  const today = new Date();
  setEventDateRange(today, today);
});
document.querySelector("#toggleEventAutoRefresh").addEventListener("click", event => {
  setEventAutoRefresh(event.currentTarget.getAttribute("aria-pressed") !== "true");
});
document.querySelector("#endDate").max = eventDateValue(new Date());
document.querySelector("#resetEventFilters").addEventListener("click", () => {
  document.querySelector("#eventSearch").value = "";
  selectedLogbookIds.clear();
  renderLogbookFilter();
  document.querySelector("#startDate").value = "";
  document.querySelector("#endDate").value = "";
  document.querySelector("#stateFilter").value = "";
  loadEvents().catch(showEventError);
});

let correctiveSearchTimer;
document.querySelector("#correctiveSearch").addEventListener("input", () => {
  clearTimeout(correctiveSearchTimer);
  correctiveSearchTimer = setTimeout(() => loadCorrective().catch(showCorrectiveError), 250);
});
["correctiveStatus", "correctiveDepartment"].forEach(id => {
  document.querySelector(`#${id}`).addEventListener("change", () => loadCorrective().catch(showCorrectiveError));
});
document.querySelector("#resetCorrectiveFilters").addEventListener("click", () => {
  document.querySelector("#correctiveSearch").value = "";
  document.querySelector("#correctiveStatus").value = "";
  document.querySelector("#correctiveDepartment").value = "";
  loadCorrective().catch(showCorrectiveError);
});

let preventiveSearchTimer;
document.querySelector("#preventiveSearch").addEventListener("input", () => {
  clearTimeout(preventiveSearchTimer);
  preventiveSearchTimer = setTimeout(() => loadPreventive().catch(showPreventiveError), 250);
});
document.querySelector("#preventiveStatus").addEventListener("change", () => loadPreventive().catch(showPreventiveError));
document.querySelectorAll("#preventiveViewMode [data-preventive-mode]").forEach(button => {
  button.addEventListener("click", () => setPreventiveViewMode(button.dataset.preventiveMode));
});
document.querySelector("#previousPreventiveMonth").addEventListener("click", () => {
  preventiveCalendarMonth = new Date(
    preventiveCalendarMonth.getFullYear(),
    preventiveCalendarMonth.getMonth() - 1,
    1
  );
  loadPreventiveCalendar().catch(showPreventiveError);
});
document.querySelector("#nextPreventiveMonth").addEventListener("click", () => {
  preventiveCalendarMonth = new Date(
    preventiveCalendarMonth.getFullYear(),
    preventiveCalendarMonth.getMonth() + 1,
    1
  );
  loadPreventiveCalendar().catch(showPreventiveError);
});
document.querySelector("#currentPreventiveMonth").addEventListener("click", () => {
  const now = new Date();
  preventiveCalendarMonth = new Date(now.getFullYear(), now.getMonth(), 1);
  loadPreventiveCalendar().catch(showPreventiveError);
});
document.querySelector("#preventiveCalendarDepartment").addEventListener("change", () => {
  loadPreventiveCalendar().catch(showPreventiveError);
});
document.querySelector("#preventiveCalendarStatus").addEventListener("change", () => {
  loadPreventiveCalendar().catch(showPreventiveError);
});
document.querySelector("#generatePreventiveMonth").addEventListener("click", () => {
  previewPreventiveMonthGeneration().catch(showPreventiveError);
});
document.querySelector("#resetPreventiveFilters").addEventListener("click", () => {
  document.querySelector("#preventiveSearch").value = "";
  document.querySelector("#preventiveStatus").value = "";
  loadPreventive().catch(showPreventiveError);
});

let permitSearchTimer;
document.querySelector("#permitSearch").addEventListener("input", () => {
  clearTimeout(permitSearchTimer);
  permitSearchTimer = setTimeout(() => loadSafetyPermits().catch(showSafetyPermitError), 250);
});
["permitStatusFilter", "permitTypeFilter"].forEach(id => {
  document.querySelector(`#${id}`).addEventListener("change", () => loadSafetyPermits().catch(showSafetyPermitError));
});
document.querySelector("#resetPermitFilters").addEventListener("click", () => {
  document.querySelector("#permitSearch").value = "";
  document.querySelector("#permitStatusFilter").value = "";
  document.querySelector("#permitTypeFilter").value = "";
  loadSafetyPermits().catch(showSafetyPermitError);
});

initializeAssetPickers();
loadFoundation().catch(showGlobalError);
lucide.createIcons();
