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
const memberSearch = document.querySelector("#member-search");
const memberResults = document.querySelector("#member-results");
const memberList = document.querySelector("#member-list");
const groupDialog = document.querySelector("#group-dialog");
const groupForm = document.querySelector("#group-form");

const LAST_GROUP_KEY = "splitwise-lite:last-group";
const SESSION_KEY = "splitwise-lite:session";

// {token, user} from POST /auth/signin, kept on this device.
let session = loadSession();

function loadSession() {
  try {
    return JSON.parse(localStorage.getItem(SESSION_KEY));
  } catch {
    return null;
  }
}

function saveSession(value) {
  session = value;
  try {
    if (value) localStorage.setItem(SESSION_KEY, JSON.stringify(value));
    else localStorage.removeItem(SESSION_KEY);
  } catch {
    // Without storage the user simply signs in again next visit.
  }
}

// The group currently on screen, as returned by GET /groups/{id}.
let currentGroup = null;
// Expenses on screen by id, so activity buttons can build share messages.
let expensesById = new Map();
let settlementsList = [];
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
    const headers = { "Content-Type": "application/json" };
    if (session) headers.Authorization = `Bearer ${session.token}`;
    response = await fetch(path, { headers, ...options });
  } catch {
    throw new Error("You appear to be offline. Check your connection and try again.");
  }
  if (response.status === 401) {
    showSignIn();
    throw new Error("Please sign in.");
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
  // Activity first: it fills expensesById, which the Settle up rows read.
  renderActivity(expenses, settlements);
  renderBalances(balances);
  renderExpenseForm();
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
      const remind = createButton("Remind", "remind", "", "small-button secondary");
      remind.dataset.from = payment.from_member_id;
      remind.dataset.to = payment.to_member_id;
      remind.dataset.amount = payment.amount;
      row.append(text, amount, remind);

      // Someone has to accept their shares before they can be marked as paid.
      const pending = pendingExpenseIds(payment.from_member_id);
      // A payment marked as paid only counts once the person paid confirms it.
      const sent = settlementsList.find(
        (s) => s.status === "pending" && s.from_member_id === payment.from_member_id && s.to_member_id === payment.to_member_id,
      );
      if (pending.length && payment.from_member_id === currentGroup.my_member_id) {
        const accept = createButton("Accept", "accept-all", "", "small-button");
        accept.dataset.expenses = pending.join(",");
        row.append(accept);
        row.append(createElement("p", "hint settle-note", `${pending.length} expense(s) to accept. Reject one from the Activity tab.`));
      } else if (pending.length) {
        row.append(createElement("p", "hint settle-note", `⏳ Waiting for ${memberName(payment.from_member_id)} to accept`));
      } else if (sent && payment.to_member_id === currentGroup.my_member_id) {
        row.append(
          createButton("Received", "confirm-payment", sent.id, "small-button"),
          createButton("Not received", "reject-payment", sent.id, "small-button secondary"),
          createElement("p", "hint settle-note", `${memberName(sent.from_member_id)} says they paid you ${formatMoney(sent.amount)}.`),
        );
      } else if (sent) {
        row.append(createElement("p", "hint settle-note", `⏳ Waiting for ${memberName(sent.to_member_id)} to confirm ${formatMoney(sent.amount)}`));
      } else {
        const button = createButton("Mark paid", "settle", "", "small-button");
        button.dataset.from = payment.from_member_id;
        button.dataset.to = payment.to_member_id;
        button.dataset.amount = payment.amount;
        row.append(button);
      }
      return row;
    }),
  );
}

// Share a friendly nudge: the phone's share sheet where supported, otherwise WhatsApp.
// WhatsApp needs the number with its country code and no "+"; assume India (+91) for 10-digit numbers.
function whatsappNumber(memberId) {
  const member = currentGroup.members.find((item) => item.id === memberId);
  if (!member || !member.phone) return null;
  const digits = member.phone.replace(/\D/g, "");
  return member.phone.startsWith("+") || digits.length > 10 ? digits : `91${digits}`;
}

// Message one person: straight into their WhatsApp chat when we know their number.
function messageMember(memberId, message) {
  const number = whatsappNumber(memberId);
  if (!number) {
    shareMessage(message);
    return;
  }
  window.open(`https://wa.me/${number}?text=${encodeURIComponent(message)}`, "_blank", "noopener");
}

async function shareMessage(message) {
  if (navigator.share) {
    try {
      await navigator.share({ text: message });
      return;
    } catch (error) {
      // The user closed the share sheet; nothing else to do.
      if (error.name === "AbortError") return;
    }
  }
  window.open(`https://wa.me/?text=${encodeURIComponent(message)}`, "_blank", "noopener");
}

function sendReminder(button) {
  const debtor = memberName(Number(button.dataset.from));
  const creditor = memberName(Number(button.dataset.to));
  messageMember(
    Number(button.dataset.from),
    `Hi ${debtor}, a reminder that you owe ${creditor} ${formatMoney(Number(button.dataset.amount))} for "${currentGroup.name}". Thanks!`,
  );
}

function pendingExpenseIds(memberId) {
  return [...expensesById.values()]
    .filter((expense) => expense.shares.some((share) => share.member_id === memberId && share.status === "pending"))
    .map((expense) => expense.id);
}

async function acceptAll(button) {
  button.disabled = true;
  try {
    for (const expenseId of button.dataset.expenses.split(",")) {
      await api(`/groups/${currentGroup.id}/expenses/${expenseId}/respond`, {
        method: "POST",
        body: JSON.stringify({ decision: "accept" }),
      });
    }
    showToast("Accepted. You can now mark it paid.");
    await refresh();
  } catch (error) {
    showError(error.message);
    button.disabled = false;
  }
}

// The person who was paid says whether the money arrived. "Not received" removes the payment.
async function answerPayment(button) {
  const received = button.dataset.action === "confirm-payment";
  if (!received && !confirm("Mark this payment as not received? It will be removed and the amount stays owed.")) return;
  button.disabled = true;
  try {
    const path = `/groups/${currentGroup.id}/settlements/${button.dataset.id}`;
    await api(received ? `${path}/confirm` : path, { method: received ? "POST" : "DELETE" });
    showToast(received ? "Payment confirmed" : "Payment removed");
    await refresh();
  } catch (error) {
    showError(error.message);
    button.disabled = false;
  }
}

settleList.addEventListener("click", async (event) => {
  const answerButton = event.target.closest("button[data-action='confirm-payment'], button[data-action='reject-payment']");
  if (answerButton) {
    answerPayment(answerButton);
    return;
  }
  const acceptButton = event.target.closest("button[data-action='accept-all']");
  if (acceptButton) {
    acceptAll(acceptButton);
    return;
  }
  const remindButton = event.target.closest("button[data-action='remind']");
  if (remindButton) {
    sendReminder(remindButton);
    return;
  }
  const button = event.target.closest("button[data-action='settle']");
  if (!button) return;
  button.disabled = true;
  const to = Number(button.dataset.to);
  try {
    await api(`/groups/${currentGroup.id}/settlements`, {
      method: "POST",
      body: JSON.stringify({
        from_member_id: Number(button.dataset.from),
        to_member_id: Number(button.dataset.to),
        amount: button.dataset.amount,
      }),
    });
    showToast(to === currentGroup.my_member_id ? "Payment recorded" : `Sent to ${memberName(to)} to confirm`);
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
  // Default the payer to you; keep a different choice when the form re-renders.
  expensePaidBy.value = members.some((member) => member.id === previousPayer) ? previousPayer : currentGroup.my_member_id;

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
  expensesById = new Map(expenses.map((expense) => [expense.id, expense]));
  settlementsList = settlements;
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
      let splitMembers = null;
      if (type === "expense") {
        const included = data.shares.filter((share) => share.status !== "rejected");
        details.append(
          createElement("p", "row-title", data.description),
          createElement(
            "p",
            "hint",
            `${memberName(data.paid_by_id)} paid · split ${included.length} ways · ${formatDate(date)}`,
          ),
        );
        action = "delete-expense";
        splitMembers = createSplitMembers(data);
      } else {
        const waiting = data.status === "pending" ? ` · ⏳ Waiting for ${memberName(data.to_member_id)} to confirm` : "";
        details.append(
          createElement("p", "row-title", `${memberName(data.from_member_id)} paid ${memberName(data.to_member_id)}`),
          createElement("p", "hint", `Repayment · ${formatDate(date)}${waiting}`),
        );
        action = "delete-settlement";
      }
      row.append(
        details,
        createElement("span", "amount", formatMoney(data.amount)),
        createButton("✕", action, data.id, "icon-button"),
      );
      row.lastChild.setAttribute("aria-label", "Delete");
      if (splitMembers) row.append(splitMembers);
      if (type === "settlement" && data.status === "pending" && data.to_member_id === currentGroup.my_member_id) {
        row.append(createButton("Received", "confirm-payment", data.id, "small-button"));
      }
      return row;
    }),
  );
}

const STATUS_LABELS = { accepted: "✓ Accepted", rejected: "✕ Rejected" };

// Who is in a split, what each owes, and Accept/Reject on your own share if you haven't answered.
function createSplitMembers(expense) {
  const list = createElement("ul", "split-members");
  for (const share of expense.shares) {
    const item = createElement("li", `split-member ${share.status}`);
    item.append(
      createElement("span", "split-name", memberName(share.member_id)),
      createElement("span", "split-amount", share.status === "rejected" ? "-" : formatMoney(share.amount)),
    );
    // Pending rows show their Accept/Reject buttons instead of a badge, so they fit on one line.
    if (share.status !== "pending") {
      item.append(createElement("span", `status-badge ${share.status}`, STATUS_LABELS[share.status]));
    } else if (share.member_id !== currentGroup.my_member_id) {
      item.append(createElement("span", "status-badge pending", "⏳ Waiting"));
    } else {
      for (const [label, decision] of [["Accept", "accept"], ["Reject", "reject"]]) {
        const button = createButton(label, "respond", expense.id, `mini-button ${decision}`);
        button.dataset.member = share.member_id;
        button.dataset.decision = decision;
        item.append(button);
      }
    }
    list.append(item);
  }
  const notify = createButton("📣 Notify members", "notify-expense", expense.id, "text-button");
  list.append(notify);
  return list;
}

function expenseMessage(expense) {
  const lines = expense.shares
    .filter((share) => share.status !== "rejected")
    .map((share) => `• ${memberName(share.member_id)}: ${formatMoney(share.amount)}`);
  return `New expense in "${currentGroup.name}": ${expense.description} ${formatMoney(expense.amount)}, paid by ${memberName(expense.paid_by_id)}.\n${lines.join("\n")}\nAccept or reject your share here: ${inviteLink()}`;
}

async function respondToShare(button) {
  const expense = expensesById.get(Number(button.dataset.id));
  const memberId = Number(button.dataset.member);
  const rejecting = button.dataset.decision === "reject";
  if (rejecting && !confirm(`Leave "${expense.description}"? The cost will be split between the others.`)) {
    return;
  }
  try {
    const updated = await api(`/groups/${currentGroup.id}/expenses/${expense.id}/respond`, {
      method: "POST",
      body: JSON.stringify({ decision: button.dataset.decision }),
    });
    showToast(rejecting ? "Rejected, cost re-split" : "Share accepted");
    await refresh();
    if (rejecting) {
      // Tell the payer on WhatsApp, in their own chat when we have their number.
      const remaining = updated.shares
        .filter((share) => share.status !== "rejected")
        .map((share) => `${memberName(share.member_id)} ${formatMoney(share.amount)}`);
      messageMember(
        updated.paid_by_id,
        `Hi ${memberName(updated.paid_by_id)}, ${memberName(memberId)} rejected "${updated.description}" in "${currentGroup.name}". It is now split as: ${remaining.join(", ")}.`,
      );
    }
  } catch (error) {
    showError(error.message);
  }
}

activityList.addEventListener("click", async (event) => {
  const button = event.target.closest("button[data-action]");
  if (!button) return;
  if (button.dataset.action === "respond") {
    respondToShare(button);
    return;
  }
  if (button.dataset.action === "confirm-payment" || button.dataset.action === "reject-payment") {
    answerPayment(button);
    return;
  }
  if (button.dataset.action === "notify-expense") {
    shareMessage(expenseMessage(expensesById.get(Number(button.dataset.id))));
    return;
  }
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
      const isMe = member.id === currentGroup.my_member_id;
      row.append(
        createElement("span", "avatar", member.name.charAt(0).toUpperCase()),
        createElement("span", "row-title", isMe ? `${member.name} (you)` : member.name),
        createElement("span", `status-badge ${member.joined ? "accepted" : "pending"}`, member.joined ? "Joined" : "Invited"),
      );
      if (!isMe) row.append(createButton("Remove", "remove-member", member.id, "small-button secondary"));
      return row;
    }),
  );
}

// Search signed-in people as you type; wait briefly so each keystroke isn't a request.
let searchTimer = null;

memberSearch.addEventListener("input", () => {
  clearTimeout(searchTimer);
  const query = memberSearch.value.trim();
  if (!query) {
    memberResults.hidden = true;
    return;
  }
  searchTimer = setTimeout(async () => {
    try {
      const users = await api(`/users/search?q=${encodeURIComponent(query)}`);
      if (memberSearch.value.trim() !== query) return;
      const memberNames = new Set(currentGroup.members.filter((m) => m.joined).map((m) => m.name.toLowerCase()));
      const items = users.map((user) => {
        const alreadyIn = memberNames.has(user.name.toLowerCase());
        const item = createButton(alreadyIn ? `${user.name} · in group` : user.name, "add-user", user.id, "search-result");
        item.disabled = alreadyIn;
        const row = createElement("li");
        row.append(item);
        return row;
      });
      if (items.length === 0) {
        items.push(createElement("li", "empty-state", "No one found. Share the invite link instead."));
      }
      memberResults.replaceChildren(...items);
      memberResults.hidden = false;
    } catch (error) {
      showError(error.message);
    }
  }, 250);
});

memberResults.addEventListener("click", async (event) => {
  const button = event.target.closest("button[data-action='add-user']");
  if (!button) return;
  clearError();
  try {
    await api(`/groups/${currentGroup.id}/members`, {
      method: "POST",
      body: JSON.stringify({ user_id: Number(button.dataset.id) }),
    });
    memberSearch.value = "";
    memberResults.hidden = true;
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

document.querySelector("#copy-link-btn").addEventListener("click", async () => {
  if (!currentGroup) return;
  try {
    await navigator.clipboard.writeText(inviteLink());
    showToast("Invite link copied");
  } catch {
    // Clipboard access needs HTTPS (or localhost); let the user copy it by hand instead.
    prompt("Copy this invite link:", inviteLink());
  }
});

document.querySelector("#share-group-btn").addEventListener("click", () => {
  if (!currentGroup) return;
  const names = currentGroup.members.map((member) => member.name).join(", ");
  shareMessage(
    `You've been added to "${currentGroup.name}" on Splitwise Lite with ${names}. Join here: ${inviteLink()}`,
  );
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
  try {
    const group = await api("/groups/", {
      method: "POST",
      body: JSON.stringify({
        name: document.querySelector("#group-name").value,
        currency: document.querySelector("#group-currency").value.trim(),
      }),
    });
    groupForm.reset();
    groupDialog.close();
    showToast("Group created");
    await loadGroups(group.id);
    showTab("members");
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

// Sign in and invite links

const signinScreen = document.querySelector("#signin-screen");
const signinError = document.querySelector("#signin-error");

function inviteLink() {
  return `${location.origin}/?join=${currentGroup.invite_code}`;
}

function showSignIn() {
  saveSession(null);
  signinScreen.hidden = false;
}

document.querySelector("#signin-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  signinError.textContent = "";
  try {
    saveSession(
      await api("/auth/signin", {
        method: "POST",
        body: JSON.stringify({
          name: document.querySelector("#signin-name").value,
          phone: document.querySelector("#signin-phone").value,
        }),
      }),
    );
    signinScreen.hidden = true;
    await start();
  } catch (error) {
    signinError.textContent = error.message;
  }
});

document.querySelector("#signout-btn").addEventListener("click", () => {
  if (confirm("Sign out of Splitwise Lite on this device?")) showSignIn();
});

async function start() {
  document.querySelector("#user-name").textContent = session.user.name;
  const inviteCode = new URLSearchParams(location.search).get("join");
  let joinedGroupId = null;
  if (inviteCode) {
    // Drop ?join= from the address bar so a refresh does not try to join again.
    history.replaceState(null, "", "/");
    try {
      const group = await api(`/groups/join/${encodeURIComponent(inviteCode)}`, { method: "POST" });
      joinedGroupId = group.id;
      showToast(`Joined ${group.name}`);
    } catch (error) {
      showError(error.message);
    }
  }
  await loadGroups(joinedGroupId);
}

// Start up

if ("serviceWorker" in navigator) {
  navigator.serviceWorker.register("service-worker.js").catch(() => {
    // The app still works without offline caching.
  });
}

if (session) {
  start().catch((error) => showError(error.message));
} else {
  signinScreen.hidden = false;
}
