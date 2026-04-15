let isGithubUpdateBusy = false;

// Автообновление страницы каждые 10 секунд (пауза во время git-обновления)
setInterval(() => {
  if (!isGithubUpdateBusy) {
    location.reload();
  }
}, 10000);

function setGithubUpdateBusy(busy) {
  isGithubUpdateBusy = !!busy;
  const checkBtn = document.getElementById("github-check-btn");
  const updateBtn = document.getElementById("github-update-btn");
  if (checkBtn) checkBtn.disabled = isGithubUpdateBusy;
  if (updateBtn) updateBtn.disabled = isGithubUpdateBusy;
}

function setGithubUpdateLog(text, append = false) {
  const logEl = document.getElementById("github-update-log");
  if (!logEl) return;

  const nextText = (text || "").toString().trim() || "Нет дополнительного лога.";
  if (append && logEl.textContent) {
    logEl.textContent = `${logEl.textContent}\n\n${nextText}`;
  } else {
    logEl.textContent = nextText;
  }
}

function shortCommit(value) {
  const commit = (value || "").trim();
  if (!commit) return "—";
  return commit.length > 12 ? commit.slice(0, 12) : commit;
}

function applyGithubStatusToUi(payload) {
  const status = payload?.status || {};
  const statusEl = document.getElementById("github-update-status");
  const sourceEl = document.getElementById("github-source");
  const gitPathEl = document.getElementById("github-git-path");
  const branchEl = document.getElementById("github-branch");
  const targetBranchEl = document.getElementById("github-target-branch");
  const localEl = document.getElementById("github-local");
  const remoteEl = document.getElementById("github-remote");
  const divergenceEl = document.getElementById("github-divergence");
  const dirtyEl = document.getElementById("github-dirty");
  const updateBtn = document.getElementById("github-update-btn");

  if (!statusEl || !branchEl || !targetBranchEl || !localEl || !remoteEl || !divergenceEl || !dirtyEl || !updateBtn) {
    return;
  }

  const ready = !!status.ready;
  const behind = parseInt(status.behind || 0, 10);
  const ahead = parseInt(status.ahead || 0, 10);
  const dirty = !!status.dirty;

  if (sourceEl) {
    const repoUrl = status.repo_url || "https://github.com/JuzzeP13/v1";
    sourceEl.href = repoUrl;
    sourceEl.textContent = repoUrl;
  }
  if (gitPathEl) {
    gitPathEl.textContent = status.git_path || "не найден";
  }

  branchEl.textContent = status.branch || "—";
  targetBranchEl.textContent = status.target_branch || "—";
  localEl.textContent = shortCommit(status.local_commit);
  remoteEl.textContent = shortCommit(status.remote_commit);
  divergenceEl.textContent = `${behind} / ${ahead}`;
  dirtyEl.textContent = dirty ? "Да" : "Нет";

  let color = "var(--text2)";
  if (!ready) color = "var(--red)";
  else if (dirty) color = "var(--red)";
  else if (behind > 0) color = "var(--amber)";
  else color = "var(--green)";

  statusEl.style.color = color;
  statusEl.textContent = status.message || "Статус получен";

  updateBtn.disabled = isGithubUpdateBusy || !ready || dirty || behind <= 0;
}

async function checkGithubUpdate(refresh = true) {
  const suffix = refresh ? "?refresh=1" : "";
  setGithubUpdateBusy(true);
  try {
    const response = await fetch(`/admin/api/github-update/status${suffix}`);
    const data = await response.json();
    applyGithubStatusToUi(data);
    if (data?.status?.message) {
      setGithubUpdateLog(data.status.message);
    }
  } catch (error) {
    setGithubUpdateLog(`Ошибка проверки обновлений: ${error}`);
  } finally {
    setGithubUpdateBusy(false);
  }
}

async function runGithubUpdate() {
  const source = document.getElementById("github-source")?.textContent?.trim() || "https://github.com/JuzzeP13/v1";
  const confirmed = confirm(
    "Запустить автообновление с GitHub?\n\n" +
    `Источник: ${source}\n` +
    "Будет выполнено: git fetch + git merge --ff-only FETCH_HEAD.\n" +
    "При локальных несохранённых изменениях обновление будет заблокировано."
  );
  if (!confirmed) return;

  setGithubUpdateBusy(true);
  setGithubUpdateLog("Запускаю обновление с GitHub...");

  try {
    const response = await fetch("/admin/api/github-update", { method: "POST" });
    const data = await response.json();

    applyGithubStatusToUi(data);

    const parts = [];
    if (data?.message) parts.push(data.message);
    if (data?.pull_output) parts.push(data.pull_output);
    setGithubUpdateLog(parts.join("\n\n") || "Операция завершена.");

    if (!response.ok || data.success === false) {
      alert(`❌ Обновление не выполнено: ${data.message || data.error || "unknown_error"}`);
      return;
    }

    if (data.updated) {
      alert("✅ Обновление применено. Рекомендуется перезапустить сервис, если это production.");
    } else {
      alert("ℹ️ Обновлений не найдено, локальная версия уже актуальна.");
    }

    await checkGithubUpdate(true);
  } catch (error) {
    setGithubUpdateLog(`Ошибка обновления: ${error}`);
    alert(`❌ Ошибка обновления: ${error}`);
  } finally {
    setGithubUpdateBusy(false);
  }
}

function viewUser(userId) {
  alert(`Просмотр пользователя ID: ${userId}\n\nВ полной версии здесь будет детальная информация о пользователе`);
}

function setPriority(userId) {
  const priority = prompt(`Установить приоритет для пользователя ID: ${userId}\n\n1 - Low\n2 - Normal\n3 - High\n4 - VIP\n\nВведите число (1-4):`, '2');
  if (priority && priority >= 1 && priority <= 4) {
    fetch(`/admin/api/set-priority`, {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({user_id: userId, priority: parseInt(priority, 10)})
    })
    .then(r => r.json())
    .then(data => {
      if (data.success) {
        alert(`✅ Приоритет установлен: ${priority}`);
        location.reload();
      } else {
        alert(`❌ Ошибка: ${data.error}`);
      }
    });
  }
}

function banUser(userId) {
  if (confirm(`Вы уверены что хотите заблокировать пользователя ID: ${userId}?`)) {
    fetch(`/admin/api/ban-user`, {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({user_id: userId})
    })
    .then(r => r.json())
    .then(data => {
      if (data.success) {
        alert(`✅ Пользователь заблокирован`);
        location.reload();
      } else {
        alert(`❌ Ошибка: ${data.error}`);
      }
    });
  }
}

document.addEventListener("DOMContentLoaded", () => {
  checkGithubUpdate(true);
});
