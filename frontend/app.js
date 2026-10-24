const groupSelect = document.querySelector("#group-select");
const errorBanner = document.querySelector("#error-banner");
const toast = document.querySelector("#toast");
const totalSpent = document.querySelector("#total-spent");
const balanceList = document.querySelector("#balance-list");
const settleList = document.querySelector("#settle-list");
const expenseForm = document.querySelector("#expense-form");
const expensePaidBy = document.querySelector("#expense-paid-by");
const expenseAmount = document.querySelector("#expense-amount");
const splitOptions = document.querySelector("#split-options");
const splitPreview = document.querySelector("#split-preview");
const activityList = document.querySelector("#activity-list");
const memberForm = document.querySelector("#member-form");
const memberList = document.querySelector("#member-list");
const groupDialog = document.querySelector("#group-dialog");
const groupForm = document.querySelector("#group-form");

const LAST_GROUP_KEY = "splitwise-lite:last-group";

// The group currently on screen, as returned by GET /groups/{id}.
let currentGroup = null;
let toastTimer = null;

function showError(message) {
  errorBanner.textContent = message;
}

function clearError() {
  errorBanner.textContent = "";
}

function showToast(message) {
  toast.textContent = message;
  toast.classList.add("visible");
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => toast.classList.remove("visible"), 2500);
}

async function getErrorMessage(response) {
  try {
    const data = await response.json();
    // FastAPI validation errors (422) return detail as a list of {msg, ...} objects.
    if (Array.isArray(data.detail)) {
      return data.detail.map((item) => item.msg).join("; ");
    }
    return data.detail || "The request could not be completed.";
  } catch {
    return "The request could not be completed.";
  }
}

// Fetch JSON from the API; throws an Error with a readable message on failure.
async function api(path, options = {}) {
  let response;
  try {
    response = await fetch(path, {
      headers: { "Content-Type": "application/json" },
      ...options,
    });
  } catch {
    throw new Error("You appear to be offline. Check your connection and try again.");
  }
  if (!response.ok) {
    throw new Error(await getErrorMessage(response));
  }
  return response.status === 204 ? null : response.json();
}

function rememberGroup(groupId) {
  try {
    localStorage.setItem(LAST_GROUP_KEY, String(groupId));
  } catch {
    // Storage can be unavailable (private mode); remembering the group is optional.
  }
}

function recallGroup() {
  try {
    return Number(localStorage.getItem(LAST_GROUP_KEY)) || null;
  } catch {
    return null;
  }
}

function formatMoney(amount) {
  const value = Math.abs(amount).toLocaleString("en-IN", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  });
  return `${currentGroup ? currentGroup.currency : ""}${value}`;
}

function memberName(memberId) {
  const member = currentGroup.members.find((item) => item.id === memberId);
  return member ? member.name : "Someone";
}

function formatDate(isoString) {
  return new Date(isoString).toLocaleDateString(undefined, { day: "numeric", month: "short" });
}

function createElement(tag, className, text) {
  const element = document.createElement(tag);
  if (className) element.className = className;
  if (text !== undefined) element.textContent = text;
  return element;
}

function createButton(label, action, id, className = "") {
  const button = createElement("button", className, label);
  button.type = "button";
  button.dataset.action = action;
  button.dataset.id = id;
  return button;
}

function showEmpty(list, message) {
  list.replaceChildren(createElement("li", "empty-state", message));
}

// Tabs

function showTab(name) {
  document.querySelectorAll(".tab-panel").forEach((panel) => {
    panel.hidden = panel.id !== `tab-${name}`;
  });
  document.querySelectorAll(".tab-button").forEach((button) => {
    const active = button.dataset.tab === name;
    button.classList.toggle("active", active);
    button.setAttribute("aria-current", active ? "page" : "false");
  });
  window.scrollTo(0, 0);
}

document.querySelectorAll(".tab-button").forEach((button) => {
  button.addEventListener("click", () => showTab(button.dataset.tab));
});

// Groups

async function loadGroups(selectId = null) {
  const groups = await api("/groups/");
  groupSelect.replaceChildren(
    ...groups.map((group) => {
      const option = createElement("option", "", group.name);
      option.value = group.id;
      return option;
    }),
  );

  if (groups.length === 0) {
    currentGroup = null;
    renderNoGroup();
    return;
  }

  const wanted = selectId || recallGroup();
  const chosen = groups.find((group) => group.id === wanted) || groups[0];
  groupSelect.value = chosen.id;
  await loadGroup(chosen.id);
}

async function loadGroup(groupId) {
  clearError();
  const [group, balances, expenses, settlements] = await Promise.all([
    api(`/groups/${groupId}`),
    api(`/groups/${groupId}/balances`),
    api(`/groups/${groupId}/expenses`),
    api(`/groups/${groupId}/settlements`),
  ]);
  currentGroup = group;
  rememberGroup(groupId);
  renderBalances(balances);
  renderExpenseForm();
  renderActivity(expenses, settlements);
  renderMembers();
}

async function refresh() {
  try {
    await loadGroup(currentGroup.id);
  } catch (error) {
    showError(error.message);
  }
}

function renderNoGroup() {
  totalSpent.textContent = "-";
  showEmpty(balanceList, "Create a group to get started.");
  settleList.replaceChildren();
  showEmpty(activityList, "No group yet.");
  memberList.replaceChildren();
  expensePaidBy.replaceChildren();
  splitOptions.replaceChildren();
  groupDialog.showModal();
}

// Balances

function renderBalances(data) {
  totalSpent.textContent = formatMoney(data.total_spent);

  if (data.balances.length === 0) {
    showEmpty(balanceList, "Add members in the Members tab.");
  } else {
    balanceList.replaceChildren(
      ...data.balances.map((item) => {
        const row = createElement("li", "card balance-row");
        let label = "settled up";
        let tone = "neutral";
        if (item.balance > 0) {
          label = `gets back ${formatMoney(item.balance)}`;
          tone = "positive";
        } else if (item.balance < 0) {
          label = `owes ${formatMoney(item.balance)}`;
          tone = "negative";
        }
        row.append(createElement("span", "avatar", item.name.charAt(0).toUpperCase()));
        row.append(createElement("span", "row-title", item.name));
        row.append(createElement("span", `amount ${tone}`, label));
        return row;
      }),
    );
  }

  if (data.settle_up.length === 0) {
    showEmpty(settleList, "Everyone is settled up. 🎉");
    return;
  }
  settleList.replaceChildren(
    ...data.settle_up.map((payment) => {
      const row = createElement("li", "card settle-row");
      const text = createElement("p", "row-title");
      text.append(
        createElement("strong", "", memberName(payment.from_member_id)),
        " pays ",
        createElement("strong", "", memberName(payment.to_member_id)),
      );
      const amount = createElement("p", "amount", formatMoney(payment.amount));
      const button = createButton("Mark paid", "settle", "", "small-button");
      button.dataset.from = payment.from_member_id;
      button.dataset.to = payment.to_member_id;
      button.dataset.amount = payment.amount;
      row.append(text, amount, button);
      return row;
    }),
  );
}

settleList.addEventListener("click", async (event) => {
  const button = event.target.closest("button[data-action='settle']");
  if (!button) return;
  button.disabled = true;
  try {
    await api(`/groups/${currentGroup.id}/settlements`, {
      method: "POST",
      body: JSON.stringify({
        from_member_id: Number(button.dataset.from),
        to_member_id: Number(button.dataset.to),
        amount: button.dataset.amount,
      }),
    });
    showToast("Payment recorded");
    await refresh();
  } catch (error) {
    showError(error.message);
    button.disabled = false;
  }
});

// Add expense

function renderExpenseForm() {
  const members = currentGroup.members;
  const previousPayer = Number(expensePaidBy.value);
  expensePaidBy.replaceChildren(
    ...members.map((member) => {
      const option = createElement("option", "", member.name);
      option.value = member.id;
      return option;
    }),
  );
  if (members.some((member) => member.id === previousPayer)) {
    expensePaidBy.value = previousPayer;
  }

  splitOptions.replaceChildren(
    ...members.map((member) => {
      const label = createElement("label", "chip-checkbox");
      const checkbox = document.createElement("input");
      checkbox.type = "checkbox";
      checkbox.value = member.id;
      checkbox.checked = true;
      label.append(checkbox, createElement("span", "", member.name));
      return label;
    }),
  );
  updateSplitPreview();
}

function selectedSplitIds() {
  return [...splitOptions.querySelectorAll("input:checked")].map((input) => Number(input.value));
}

function updateSplitPreview() {
  const count = selectedSplitIds().length;
  const amount = Number(expenseAmount.value);
  if (!currentGroup || count === 0 || !amount) {
    splitPreview.textContent = count === 0 ? "Pick at least one person." : "";
    return;
  }
  splitPreview.textContent = `${formatMoney(amount / count)} each between ${count} ${count === 1 ? "person" : "people"}`;
}

expenseAmount.addEventListener("input", updateSplitPreview);
splitOptions.addEventListener("change", updateSplitPreview);

expenseForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  clearError();
  if (!currentGroup || currentGroup.members.length === 0) {
    showError("Add members in the Members tab first.");
    return;
  }
  const splitBetween = selectedSplitIds();
  if (splitBetween.length === 0) {
    showError("Pick at least one person to split with.");
    return;
  }

  const submitButton = expenseForm.querySelector("button[type='submit']");
  submitButton.disabled = true;
  try {
    await api(`/groups/${currentGroup.id}/expenses`, {
      method: "POST",
      body: JSON.stringify({
        description: document.querySelector("#expense-description").value,
        // Send the typed text so the server validates exact decimals, not a float.
        amount: expenseAmount.value,
        paid_by_id: Number(expensePaidBy.value),
        split_between: splitBetween,
      }),
    });
    expenseForm.reset();
    showToast("Expense added");
    await refresh();
    showTab("balances");
  } catch (error) {
    showError(error.message);
  } finally {
    submitButton.disabled = false;
  }
});

// Activity

function renderActivity(expenses, settlements) {
  const items = [
    ...expenses.map((expense) => ({ type: "expense", date: expense.created_at, data: expense })),
    ...settlements.map((settlement) => ({ type: "settlement", date: settlement.created_at, data: settlement })),
  ].sort((a, b) => new Date(b.date) - new Date(a.date));

  if (items.length === 0) {
    showEmpty(activityList, "No expenses yet. Add one from the Add tab.");
    return;
  }

  activityList.replaceChildren(
    ...items.map(({ type, date, data }) => {
      const row = createElement("li", `card activity-row ${type}`);
      const details = createElement("div", "activity-details");
      let action;
      if (type === "expense") {
        details.append(
          createElement("p", "row-title", data.description),
          createElement(
            "p",
            "hint",
            `${memberName(data.paid_by_id)} paid · split ${data.shares.length} ways · ${formatDate(date)}`,
          ),
        );
        action = "delete-expense";
      } else {
        details.append(
          createElement("p", "row-title", `${memberName(data.from_member_id)} paid ${memberName(data.to_member_id)}`),
          createElement("p", "hint", `Repayment · ${formatDate(date)}`),
        );
        action = "delete-settlement";
      }
      row.append(
        details,
        createElement("span", "amount", formatMoney(data.amount)),
        createButton("✕", action, data.id, "icon-button"),
      );
      row.lastChild.setAttribute("aria-label", "Delete");
      return row;
    }),
  );
}

activityList.addEventListener("click", async (event) => {
  const button = event.target.closest("button[data-action]");
  if (!button) return;
  const path = button.dataset.action === "delete-expense" ? "expenses" : "settlements";
  if (!confirm("Delete this entry? Balances will be recalculated.")) return;
  try {
    await api(`/groups/${currentGroup.id}/${path}/${button.dataset.id}`, { method: "DELETE" });
    showToast("Deleted");
    await refresh();
  } catch (error) {
    showError(error.message);
  }
});

// Members

function renderMembers() {
  if (currentGroup.members.length === 0) {
    showEmpty(memberList, "No members yet.");
    return;
  }
  memberList.replaceChildren(
    ...currentGroup.members.map((member) => {
      const row = createElement("li", "card member-row");
      row.append(
        createElement("span", "avatar", member.name.charAt(0).toUpperCase()),
        createElement("span", "row-title", member.name),
        createButton("Remove", "remove-member", member.id, "small-button secondary"),
      );
      return row;
    }),
  );
}

memberForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  clearError();
  const input = document.querySelector("#member-name");
  try {
    await api(`/groups/${currentGroup.id}/members`, {
      method: "POST",
      body: JSON.stringify({ name: input.value }),
    });
    input.value = "";
    showToast("Member added");
    await refresh();
  } catch (error) {
    showError(error.message);
  }
});

memberList.addEventListener("click", async (event) => {
  const button = event.target.closest("button[data-action='remove-member']");
  if (!button) return;
  clearError();
  try {
    await api(`/groups/${currentGroup.id}/members/${button.dataset.id}`, { method: "DELETE" });
    showToast("Member removed");
    await refresh();
  } catch (error) {
    showError(error.message);
  }
});

document.querySelector("#delete-group-btn").addEventListener("click", async () => {
  if (!currentGroup) return;
  if (!confirm(`Delete "${currentGroup.name}" and all its expenses? This cannot be undone.`)) return;
  try {
    await api(`/groups/${currentGroup.id}`, { method: "DELETE" });
    showToast("Group deleted");
    await loadGroups();
    showTab("balances");
  } catch (error) {
    showError(error.message);
  }
});

// New group dialog

document.querySelector("#new-group-btn").addEventListener("click", () => groupDialog.showModal());
document.querySelector("#group-cancel").addEventListener("click", () => groupDialog.close());

groupForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  clearError();
  const members = document
    .querySelector("#group-members")
    .value.split(",")
    .map((name) => name.trim())
    .filter(Boolean);
  try {
    const group = await api("/groups/", {
      method: "POST",
      body: JSON.stringify({
        name: document.querySelector("#group-name").value,
        currency: document.querySelector("#group-currency").value.trim(),
        members,
      }),
    });
    groupForm.reset();
    groupDialog.close();
    showToast("Group created");
    await loadGroups(group.id);
    showTab(members.length ? "add" : "members");
  } catch (error) {
    showError(error.message);
    groupDialog.close();
  }
});

groupSelect.addEventListener("change", async () => {
  try {
    await loadGroup(Number(groupSelect.value));
  } catch (error) {
    showError(error.message);
  }
});

// Start up

if ("serviceWorker" in navigator) {
  navigator.serviceWorker.register("service-worker.js").catch(() => {
    // The app still works without offline caching.
  });
}

loadGroups().catch((error) => showError(error.message));
