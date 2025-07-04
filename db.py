import os
import sqlite3
from datetime import datetime, timedelta
from pytz import timezone

# === DB Connection ===
DATABASE_URL = os.getenv("DATABASE_URL")
if DATABASE_URL:
    import psycopg2
    from urllib.parse import urlparse

    url = urlparse(DATABASE_URL)
    conn = psycopg2.connect(
        dbname=url.path[1:], user=url.username,
        password=url.password, host=url.hostname, port=url.port
    )
    cursor = conn.cursor()
    placeholder = "%s"
else:
    conn = sqlite3.connect("princess.db", check_same_thread=False)
    cursor = conn.cursor()
    placeholder = "?"

# === Table Creation ===
cursor.execute("""
CREATE TABLE IF NOT EXISTS users (
    user_id   TEXT PRIMARY KEY,
    nickname  TEXT,
    exp       INTEGER DEFAULT 0
)
""")
cursor.execute("""
CREATE TABLE IF NOT EXISTS attendance (
    user_id TEXT,
    date    TEXT
)
""")
cursor.execute("""
CREATE TABLE IF NOT EXISTS wakeup (
    user_id TEXT,
    date    TEXT
)
""")
cursor.execute("""
CREATE TABLE IF NOT EXISTS study (
    user_id TEXT,
    date    TEXT,
    minutes INTEGER
)
""")
conn.commit()

# === Internal: Register or Update User ===
def _register_user(user_id: str, nickname: str):
    # 1) 동일한 user_id가 있는지 확인
    cursor.execute(
        f"SELECT 1 FROM users WHERE user_id = {placeholder}",
        (user_id,)
    )
    if not cursor.fetchone():
        # 2-1) 없으면 INSERT
        cursor.execute(
            f"INSERT INTO users (user_id, nickname, exp) VALUES ({placeholder}, {placeholder}, 0)",
            (user_id, nickname)
        )
    else:
        # 2-2) 있으면 nickname만 UPDATE (새 닉네임 반영)
        cursor.execute(
            f"UPDATE users SET nickname = {placeholder} WHERE user_id = {placeholder}",
            (nickname, user_id)
        )
    conn.commit()

# === Save Attendance (KST date) ===
def save_attendance(user_id: str, nickname: str) -> bool:
    today = datetime.now(timezone("Asia/Seoul")).strftime("%Y-%m-%d")
    _register_user(user_id, nickname)
    cursor.execute(
        f"SELECT 1 FROM attendance WHERE user_id = {placeholder} AND date = {placeholder}",
        (user_id, today)
    )
    if cursor.fetchone():
        return False

    cursor.execute(
        f"INSERT INTO attendance (user_id, date) VALUES ({placeholder}, {placeholder})",
        (user_id, today)
    )
    conn.commit()
    return True

# === Get Attendance Records ===
def get_attendance(user_id: str):
    cursor.execute(
        f"SELECT date FROM attendance WHERE user_id = {placeholder} ORDER BY date DESC",
        (user_id,)
    )
    return cursor.fetchall()

# === Save Wakeup (KST date) ===
def save_wakeup(user_id: str, nickname: str) -> bool:
    today = datetime.now(timezone("Asia/Seoul")).strftime("%Y-%m-%d")
    _register_user(user_id, nickname)
    cursor.execute(
        f"SELECT 1 FROM wakeup WHERE user_id = {placeholder} AND date = {placeholder}",
        (user_id, today)
    )
    if cursor.fetchone():
        return False

    cursor.execute(
        f"INSERT INTO wakeup (user_id, date) VALUES ({placeholder}, {placeholder})",
        (user_id, today)
    )
    conn.commit()
    return True

# === Log Study Time (accumulate) ===
def log_study_time(user_id: str, minutes: int):
    today = datetime.now(timezone("Asia/Seoul")).strftime("%Y-%m-%d")
    # study는 nickname 불필요하니 Unknown 고정
    _register_user(user_id, "Unknown")
    cursor.execute(
        f"SELECT minutes FROM study WHERE user_id = {placeholder} AND date = {placeholder}",
        (user_id, today)
    )
    row = cursor.fetchone()
    if row:
        total = row[0] + minutes
        cursor.execute(
            f"UPDATE study SET minutes = {placeholder} WHERE user_id = {placeholder} AND date = {placeholder}",
            (total, user_id, today)
        )
    else:
        cursor.execute(
            f"INSERT INTO study (user_id, date, minutes) VALUES ({placeholder}, {placeholder}, {placeholder})",
            (user_id, today, minutes)
        )
    conn.commit()

# === Get Today's Study Time ===
def get_today_study_time(user_id: str) -> int:
    today = datetime.now(timezone("Asia/Seoul")).strftime("%Y-%m-%d")
    cursor.execute(
        f"SELECT minutes FROM study WHERE user_id = {placeholder} AND date = {placeholder}",
        (user_id, today)
    )
    row = cursor.fetchone()
    return row[0] if row else 0

# === Experience Management ===
def add_exp(user_id: str, nickname: str, amount: int):
    # 1) 매번 사용자 등록 또는 닉네임 업데이트
    _register_user(user_id, nickname)
    # 2) exp 누적
    cursor.execute(
        f"UPDATE users SET exp = exp + {placeholder} WHERE user_id = {placeholder}",
        (amount, user_id)
    )
    conn.commit()

def remove_exp(user_id: str, amount: int):
    current = get_exp(user_id)
    new_exp = max(0, current - amount)
    cursor.execute(
        f"UPDATE users SET exp = {placeholder} WHERE user_id = {placeholder}",
        (new_exp, user_id)
    )
    conn.commit()

def set_exp(user_id: str, new_exp: int):
    _register_user(user_id, "Unknown")
    cursor.execute(
        f"UPDATE users SET exp = {placeholder} WHERE user_id = {placeholder}",
        (new_exp, user_id)
    )
    conn.commit()

def get_exp(user_id: str) -> int:
    cursor.execute(
        f"SELECT exp FROM users WHERE user_id = {placeholder}",
        (user_id,)
    )
    row = cursor.fetchone()
    return row[0] if row else 0

# === Top Users by Exp ===
def get_top_users_by_exp(limit: int = 10):
    if placeholder == "?":  # SQLite
        cursor.execute(
            f"SELECT nickname, exp FROM users ORDER BY exp DESC LIMIT {limit}"
        )
    else:  # Postgres
        cursor.execute(
            f"SELECT nickname, exp FROM users ORDER BY exp DESC LIMIT {placeholder}",
            (limit,)
        )
    return cursor.fetchall()

# === Monthly Stats ===
def get_monthly_stats(user_id: str):
    now = datetime.now(timezone("Asia/Seoul"))
    month_start = now.replace(day=1).strftime("%Y-%m-%d")
    next_month = (now.replace(day=28) + timedelta(days=4)).replace(day=1)
    month_end = (next_month - timedelta(days=1)).strftime("%Y-%m-%d")

    cursor.execute(
        f"SELECT COUNT(DISTINCT date) FROM attendance WHERE user_id = {placeholder} AND date BETWEEN {placeholder} AND {placeholder}",
        (user_id, month_start, month_end)
    )
    attendance = cursor.fetchone()[0]
    cursor.execute(
        f"SELECT COUNT(DISTINCT date) FROM wakeup WHERE user_id = {placeholder} AND date BETWEEN {placeholder} AND {placeholder}",
        (user_id, month_start, month_end)
    )
    wakeup = cursor.fetchone()[0]
    cursor.execute(
        f"SELECT COUNT(DISTINCT date) FROM study WHERE user_id = {placeholder} AND date BETWEEN {placeholder} AND {placeholder} AND minutes >= 10",
        (user_id, month_start, month_end)
    )
    study_days = cursor.fetchone()[0]
    cursor.execute(
        f"SELECT COALESCE(SUM(minutes), 0) FROM study WHERE user_id = {placeholder} AND date BETWEEN {placeholder} AND {placeholder}",
        (user_id, month_start, month_end)
    )
    study_minutes = cursor.fetchone()[0]
    return {
        "attendance": attendance,
        "wakeup": wakeup,
        "study_days": study_days,
        "study_minutes": study_minutes,
        "exp": get_exp(user_id)
    }

# === Weekly Stats ===
def get_weekly_stats(user_id: str):
    now = datetime.now(timezone("Asia/Seoul"))
    week_start = (now - timedelta(days=now.weekday())).strftime("%Y-%m-%d")
    week_end = (now + timedelta(days=6 - now.weekday())).strftime("%Y-%m-%d")
    cursor.execute(
        f"SELECT COUNT(DISTINCT date) FROM attendance WHERE user_id = {placeholder} AND date BETWEEN {placeholder} AND {placeholder}",
        (user_id, week_start, week_end)
    )
    attendance = cursor.fetchone()[0]
    cursor.execute(
        f"SELECT COUNT(DISTINCT date) FROM wakeup WHERE user_id = {placeholder} AND date BETWEEN {placeholder} AND {placeholder}",
        (user_id, week_start, week_end)
    )
    wakeup = cursor.fetchone()[0]
    cursor.execute(
        f"SELECT COUNT(DISTINCT date) FROM study WHERE user_id = {placeholder} AND date BETWEEN {placeholder} AND {placeholder} AND minutes >= 10",
        (user_id, week_start, week_end)
    )
    study_days = cursor.fetchone()[0]
    cursor.execute(
        f"SELECT COALESCE(SUM(minutes), 0) FROM study WHERE user_id = {placeholder} AND date BETWEEN {placeholder} AND {placeholder}",
        (user_id, week_start, week_end)
    )
    study_minutes = cursor.fetchone()[0]
    return {
        "attendance": attendance,
        "wakeup": wakeup,
        "study_days": study_days,
        "study_minutes": study_minutes,
        "exp": get_exp(user_id)
    }

# === Streak Calculation ===
def _calculate_streak_from_dates(date_list):
    if not date_list:
        return 0
    today = datetime.now(timezone("Asia/Seoul")).date()
    streak = 0
    for d in date_list:
        try:
            d_date = datetime.strptime(d, "%Y-%m-%d").date()
        except:
            continue
        if (today - d_date).days == streak:
            streak += 1
        else:
            break
    return streak

def _get_streak_days(table: str, user_id: str):
    cursor.execute(
        f"SELECT date FROM {table} WHERE user_id = {placeholder} ORDER BY date DESC",
        (user_id,)
    )
    rows = [r[0] for r in cursor.fetchall()]
    return _calculate_streak_from_dates(rows)

def get_streak_attendance(user_id: str):
    return _get_streak_days("attendance", user_id)

def get_streak_wakeup(user_id: str):
    return _get_streak_days("wakeup", user_id)

def get_streak_study(user_id: str):
    cursor.execute(
        f"SELECT date FROM study WHERE user_id = {placeholder} AND minutes >= 10 ORDER BY date DESC",
        (user_id,)
    )
    rows = [r[0] for r in cursor.fetchall()]
    return _calculate_streak_from_dates(rows)
