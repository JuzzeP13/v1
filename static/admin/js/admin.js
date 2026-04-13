// Автообновление каждые 10 секунд
setInterval(() => location.reload(), 10000);

function viewUser(userId) {
  alert(`Просмотр пользователя ID: ${userId}\n\nВ полной версии здесь будет детальная информация о пользователе`);
}

function setPriority(userId) {
  const priority = prompt(`Установить приоритет для пользователя ID: ${userId}\n\n1 - Low\n2 - Normal\n3 - High\n4 - VIP\n\nВведите число (1-4):`, '2');
  if (priority && priority >= 1 && priority <= 4) {
    fetch(`/admin/api/set-priority`, {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({user_id: userId, priority: parseInt(priority)})
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
