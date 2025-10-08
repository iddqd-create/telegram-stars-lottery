# 🎁 Реферальная система

Полное описание реферальной системы Stars Lottery.

## 📋 Обзор

Реферальная система позволяет пользователям приглашать друзей и получать бонусы за их активность. Это увеличивает вовлеченность и помогает расти базе пользователей.

## ✨ Возможности

### Для пользователей:
- 🔗 Уникальная реферальная ссылка
- 📊 Статистика приглашенных друзей
- ⭐ Бонусы за активность рефералов
- 📤 Удобный шаринг в Telegram
- 👥 Список всех рефералов с их активностью

### Для админа:
- 📈 Аналитика реферальной программы
- 💰 Гибкая настройка бонусов
- 🔍 Отслеживание цепочек рефералов
- 📊 Статистика по типам бонусов

## 🏗️ Архитектура

### База данных

#### Таблица `referrals`
```sql
CREATE TABLE referrals (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    referrer_user_id INTEGER,          -- Кто пригласил
    referred_user_id INTEGER UNIQUE,   -- Кого пригласили
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (referrer_user_id) REFERENCES users(user_id),
    FOREIGN KEY (referred_user_id) REFERENCES users(user_id)
);
```

#### Таблица `referral_bonuses`
```sql
CREATE TABLE referral_bonuses (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    referrer_user_id INTEGER,          -- Кто получил бонус
    referred_user_id INTEGER,          -- За кого получен бонус
    bonus_amount INTEGER,              -- Размер бонуса в Stars
    bonus_type TEXT,                   -- Тип бонуса
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (referrer_user_id) REFERENCES users(user_id),
    FOREIGN KEY (referred_user_id) REFERENCES users(user_id)
);
```

### API Endpoints

#### 1. GET /api/referral/link
Получить реферальную ссылку и базовую статистику.

**Request:**
```json
{
  "initData": "telegram_init_data_string"
}
```

**Response:**
```json
{
  "referral_link": "https://t.me/your_bot?start=ref_123456",
  "total_referrals": 5,
  "total_bonuses": 250
}
```

#### 2. POST /api/referral/register
Зарегистрировать нового реферала.

**Request:**
```json
{
  "initData": "telegram_init_data_string",
  "referrerId": 123456
}
```

**Response:**
```json
{
  "success": true,
  "message": "Referral registered successfully"
}
```

**Errors:**
- `400` - Invalid referrer или user already referred
- `404` - Referrer not found

#### 3. POST /api/referral/stats
Получить детальную статистику по рефералам.

**Request:**
```json
{
  "initData": "telegram_init_data_string"
}
```

**Response:**
```json
{
  "referrals": [
    {
      "user_id": 789012,
      "first_name": "John",
      "username": "john_doe",
      "joined_at": "2025-10-01T12:00:00",
      "games_played": 15,
      "wins": 3
    }
  ],
  "bonuses_by_type": {
    "first_game": {
      "total_amount": 50,
      "count": 5
    },
    "active_player": {
      "total_amount": 200,
      "count": 10
    }
  }
}
```

## 🎨 UI Компоненты

### Главный экран
- Кнопка "Invite Friends & Earn Bonuses" с иконкой 🎁
- Расположена после секции "How It Works"

### Реферальный экран

#### Header
- Большая иконка 🎁 с анимацией bounce
- Заголовок "Invite Friends"
- Подзаголовок "Earn bonuses when your friends play!"

#### Статистика (2 карточки)
1. **Friends Invited**
   - Иконка 👥
   - Количество приглашенных друзей
   
2. **Total Bonuses**
   - Иконка ⭐
   - Общая сумма полученных бонусов

#### Реферальная ссылка
- Поле ввода с ссылкой (readonly)
- Кнопка "Copy" с анимацией при копировании
- Кнопка "Share Link" для шаринга в Telegram

#### How It Works
3 шага с иконками:
1. Share your unique referral link with friends
2. They join using your link and start playing
3. You earn bonuses for each active referral!

#### Список рефералов
- Аватар с первой буквой имени
- Имя реферала
- Статистика: количество игр и побед
- Empty state если рефералов нет

## 💰 Система бонусов

### Типы бонусов

#### 1. First Game Bonus
**Условие:** Реферал сыграл первую игру  
**Размер:** 10 Stars  
**Код:**
```python
def award_first_game_bonus(referrer_id, referred_id):
    bonus_amount = 10
    bonus_type = 'first_game'
    # Сохранить в referral_bonuses
```

#### 2. Active Player Bonus
**Условие:** Реферал сыграл 10 игр  
**Размер:** 50 Stars  
**Код:**
```python
def award_active_player_bonus(referrer_id, referred_id):
    bonus_amount = 50
    bonus_type = 'active_player'
    # Сохранить в referral_bonuses
```

#### 3. Winner Bonus
**Условие:** Реферал выиграл игру  
**Размер:** 5% от выигрыша реферала  
**Код:**
```python
def award_winner_bonus(referrer_id, referred_id, win_amount):
    bonus_amount = int(win_amount * 0.05)
    bonus_type = 'winner'
    # Сохранить в referral_bonuses
```

### Реализация начисления бонусов

Добавьте в `lottery_engine.py`:

```python
def award_referral_bonuses(winner_user_id, win_amount, db_path):
    """Начислить бонусы рефереру победителя"""
    conn = sqlite3.connect(db_path)
    c = conn.cursor()
    
    # Найти реферера победителя
    c.execute('SELECT referrer_user_id FROM referrals WHERE referred_user_id = ?', 
              (winner_user_id,))
    result = c.fetchone()
    
    if result:
        referrer_id = result[0]
        bonus_amount = int(win_amount * 0.05)  # 5% от выигрыша
        
        # Сохранить бонус
        c.execute('''INSERT INTO referral_bonuses 
                     (referrer_user_id, referred_user_id, bonus_amount, bonus_type)
                     VALUES (?, ?, ?, ?)''',
                  (referrer_id, winner_user_id, bonus_amount, 'winner'))
        
        conn.commit()
        logger.info(f"Awarded {bonus_amount} Stars to referrer {referrer_id}")
    
    conn.close()
```

## 🔄 Поток работы

### 1. Пользователь открывает реферальный экран
```javascript
// app.js
document.getElementById('open-referral-btn').addEventListener('click', async () => {
    await loadReferralData();
    showScreen('referral-screen');
});
```

### 2. Загрузка данных
```javascript
async function loadReferralData() {
    const response = await fetch(`${API_BASE_URL}/api/referral/link`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ initData: tg.initData })
    });
    
    const data = await response.json();
    // Обновить UI
}
```

### 3. Копирование ссылки
```javascript
document.getElementById('copy-referral-link').addEventListener('click', async () => {
    await navigator.clipboard.writeText(referralLink);
    // Показать анимацию успеха
});
```

### 4. Шаринг ссылки
```javascript
document.getElementById('share-referral-link').addEventListener('click', () => {
    const shareUrl = `https://t.me/share/url?url=${encodeURIComponent(link)}`;
    tg.openTelegramLink(shareUrl);
});
```

### 5. Новый пользователь переходит по ссылке
- URL содержит параметр `start=ref_123456`
- При инициализации приложения проверяется `tg.initDataUnsafe.start_parameter`
- Если найден `ref_`, вызывается `registerReferral(referrerId)`

### 6. Регистрация реферала
```javascript
async function registerReferral(referrerId) {
    const response = await fetch(`${API_BASE_URL}/api/referral/register`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ 
            initData: tg.initData,
            referrerId: parseInt(referrerId)
        })
    });
    
    if (response.ok) {
        tg.showPopup({
            title: '🎁 Welcome!',
            message: 'You were invited by a friend!'
        });
    }
}
```

## 📊 Аналитика

### SQL запросы для статистики

#### Топ рефереров
```sql
SELECT 
    u.user_id,
    u.first_name,
    COUNT(r.id) as total_referrals,
    COALESCE(SUM(rb.bonus_amount), 0) as total_bonuses
FROM users u
LEFT JOIN referrals r ON u.user_id = r.referrer_user_id
LEFT JOIN referral_bonuses rb ON u.user_id = rb.referrer_user_id
GROUP BY u.user_id, u.first_name
ORDER BY total_referrals DESC
LIMIT 10;
```

#### Конверсия рефералов
```sql
SELECT 
    COUNT(DISTINCT r.referred_user_id) as total_referrals,
    COUNT(DISTINCT rp.user_id) as active_referrals,
    ROUND(COUNT(DISTINCT rp.user_id) * 100.0 / COUNT(DISTINCT r.referred_user_id), 2) as conversion_rate
FROM referrals r
LEFT JOIN room_participants rp ON r.referred_user_id = rp.user_id;
```

#### Средний доход с реферала
```sql
SELECT 
    AVG(bonus_per_referral) as avg_bonus_per_referral
FROM (
    SELECT 
        r.referrer_user_id,
        COUNT(rb.id) as bonuses_count,
        COALESCE(SUM(rb.bonus_amount), 0) as bonus_per_referral
    FROM referrals r
    LEFT JOIN referral_bonuses rb ON r.referred_user_id = rb.referred_user_id
    GROUP BY r.referrer_user_id, r.referred_user_id
);
```

## 🎯 Лучшие практики

### 1. Предотвращение злоупотреблений

**Проблема:** Пользователь создает несколько аккаунтов  
**Решение:**
- Ограничение 5 регистраций в час (уже реализовано через rate limiting)
- Проверка активности реферала перед начислением бонусов
- Минимальный порог игр для получения бонусов

### 2. Мотивация рефереров

**Стратегии:**
- Прогрессивные бонусы (больше рефералов = больше бонусов)
- Специальные награды за активных рефералов
- Таблица лидеров рефереров

### 3. Вовлечение рефералов

**Приветственное сообщение:**
```javascript
tg.showPopup({
    title: '🎁 Welcome Bonus!',
    message: 'Your friend invited you! Play your first game and both of you get bonuses!',
    buttons: [{type: 'ok'}]
});
```

### 4. Уведомления

**Когда уведомлять:**
- Новый реферал зарегистрировался
- Реферал сыграл первую игру
- Получен бонус
- Реферал выиграл

**Реализация через bot.py:**
```python
def notify_referrer(referrer_id, message):
    bot.send_message(
        chat_id=referrer_id,
        text=message,
        parse_mode='HTML'
    )
```

## 🚀 Будущие улучшения

### 1. Многоуровневая реферальная система
- Уровень 1: Прямые рефералы (текущая реализация)
- Уровень 2: Рефералы ваших рефералов (5% от бонусов)
- Уровень 3: И так далее (2% от бонусов)

### 2. Реферальные коды
- Кастомные коды вместо числовых ID
- Легче запоминать и делиться

### 3. Временные акции
- Удвоенные бонусы в выходные
- Специальные события с повышенными бонусами

### 4. Достижения
- "Первый реферал" - бонус 20 Stars
- "10 рефералов" - бонус 100 Stars
- "100 рефералов" - бонус 1000 Stars

### 5. Реферальные турниры
- Соревнование между рефереррами
- Призы за топ-3 места

## 📱 Тестирование

### Unit тесты

```python
# tests/test_referral_system.py
def test_register_referral():
    # Тест регистрации реферала
    pass

def test_duplicate_referral():
    # Тест предотвращения дубликатов
    pass

def test_self_referral():
    # Тест предотвращения самореферала
    pass

def test_bonus_calculation():
    # Тест расчета бонусов
    pass
```

### Интеграционные тесты

```python
def test_referral_flow():
    # 1. Пользователь A получает ссылку
    # 2. Пользователь B переходит по ссылке
    # 3. Пользователь B регистрируется
    # 4. Проверить, что связь создана
    pass
```

## 📝 Заключение

Реферальная система - мощный инструмент для роста пользовательской базы. Она:
- ✅ Увеличивает вовлеченность
- ✅ Снижает стоимость привлечения
- ✅ Создает сообщество
- ✅ Мотивирует пользователей

**Следующие шаги:**
1. Запустить базовую реферальную систему
2. Собрать данные и аналитику
3. Оптимизировать размеры бонусов
4. Добавить дополнительные функции

---

**Удачи с реферальной программой! 🎁⭐**
