import os
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
    import sqlite3
    conn = sqlite3.connect("princess.db", check_same_thread=False)
    cursor = conn.cursor()
    placeholder = "?"

# === 테이블 생성 (두 DB 모두 호환) ===
cursor.execute("""
CREATE TABLE IF NOT EXISTS users (
    user_id TEXT PRIMARY KEY,
    nickname TEXT,
    exp INTEGER DEFAULT 0
)
""")
cursor.execute("""
CREATE TABLE IF NOT EXISTS attendance (
    user_id TEXT,
    date TEXT
)
""")
cursor.execute("""
CREATE TABLE IF NOT EXISTS wakeup (
    user_id TEXT,
    date TEXT
)
""")
cursor.execute("""
CREATE TABLE IF NOT EXISTS study (
    user_id TEXT,
    date TEXT,
    minutes INTEGER
)
""")
conn.commit()

# === 내부: 사용자 등록 ===
def _register_user(user_id: str, nickname: str):
    cursor.execute(
        f"SELECT 1 FROM users WHERE user_id = {placeholder}",
        (user_id,)
    )
    if not cursor.fetchone():
        cursor.execute(
            f"INSERT INTO users (user_id, nickname, exp) VALUES ({placeholder}, {placeholder}, 0)",
            (user_id, nickname)
        )
        conn.commit()

# === 출석 저장 ===
def save_attendance(user_id: str, nickname: str) -> bool:
    today = datetime.now(timezone("Asia/Seoul")).strftime("%Y-%m-%d")
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
    _register_user(user_id, nickname)
    conn.commit()
    return True

# === 출석 기록 조회 ===
def get_attendance(user_id: str):
    cursor.execute(
        f"SELECT date FROM attendance WHERE user_id = {placeholder} ORDER BY date DESC",
        (user_id,)
    )
    return cursor.fetchall()

# === 기상 인증 저장 ===
def save_wakeup(user_id: str, nickname: str) -> bool:
    today = datetime.now(timezone("Asia/Seoul")).strftime("%Y-%m-%d")
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
    _register_user(user_id, nickname)
    conn.commit()
    return True

# === 공부 시간 기록 ===
def log_study_time(user_id: str, minutes: int):
    today = datetime.now(timezone("Asia/Seoul")).strftime("%Y-%m-%d")
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

# === 오늘 공부 시간 조회 ===
def get_today_study_time(user_id: str) -> int:
    today = datetime.now(timezone("Asia/Seoul")).strftime("%Y-%m-%d")
    cursor.execute(
        f"SELECT minutes FROM study WHERE user_id = {placeholder} AND date = {placeholder}",
        (user_id, today)
    )
    row = cursor.fetchone()
    return row[0] if row else 0

# === 경험치 추가/제거 ===
def add_exp(user_id: str, amount: int):
    cursor.execute(
        f"SELECT exp FROM users WHERE user_id = {placeholder}",
        (user_id,)
    )
    row = cursor.fetchone()
    if row:
        new_exp = row[0] + amount
        cursor.execute(
            f"UPDATE users SET exp = {placeholder} WHERE user_id = {placeholder}",
            (new_exp, user_id)
        )
    else:
        cursor.execute(
            f"INSERT INTO users (user_id, nickname, exp) VALUES ({placeholder}, {placeholder}, {placeholder})",
            (user_id, "Unknown", amount)
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

# === 상위 유저 조회 ===
def get_top_users_by_exp(limit: int = 10):
    cursor.execute(
        f"SELECT nickname, exp FROM users ORDER BY exp DESC LIMIT {placeholder}",
        (limit,)
    )
    return cursor.fetchall()

# === 월간/주간 통계 ===
def get_monthly_stats(user_id: str):
    now = datetime.now(timezone("Asia/Seoul"))
    month_start = now.replace(day=1).strftime("%Y-%m-%d")
    next_month = (now.replace(day=28) + timedelta(days=4)).replace(day=1)
    month_end = (next_month - timedelta(days=1)).strftime("%Y-%m-%d")

    cursor.execute(
        f"SELECT COUNT(DISTINCT date) FROM attendance WHERE user_id = {placeholder} 
         AND date BETWEEN {placeholder} AND {placeholder}",
        (user_id, month_start, month_end)
    )
    attendance = cursor.fetchone()[0]

    cursor.execute(
        f"SELECT COUNT(DISTINCT date) FROM wakeup WHERE user_id = {placeholder} 
         AND date BETWEEN {placeholder} AND {placeholder}",
        (user_id, month_start, month_end)
    )
    wakeup = cursor.fetchone()[0]

    cursor.execute(
        f"SELECT COUNT(DISTINCT date) FROM study WHERE user_id = {placeholder} 
         AND date BETWEEN {placeholder} AND {placeholder} AND minutes >= 10",
        (user_id, month_start, month_end)
    )
    study_days = cursor.fetchone()[0]

    cursor.execute(
        f"SELECT COALESCE(SUM(minutes), 0) FROM study WHERE user_id = {placeholder} 
         AND date BETWEEN {placeholder} AND {placeholder}",
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

def get_weekly_stats(user_id: str):
    now = datetime.now(timezone("Asia/Seoul"))
    week_start = (now - timedelta(days=now.weekday())).strftime("%Y-%m-%d")
    week_end = (now + timedelta(days=6 - now.weekday())).strftime("%Y-%m-%d")

    cursor.execute(
        f"SELECT COUNT(DISTINCT date) FROM attendance WHERE user_id = {placeholder} 
         AND date BETWEEN {placeholder} AND {placeholder}",
        (user_id, week_start, week_end)
    )
    attendance = cursor.fetchone()[0]

    cursor.execute(
        f"SELECT COUNT(DISTINCT date) FROM wakeup WHERE user_id = {placeholder} 
         AND date BETWEEN {placeholder} AND {placeholder}",
        (user_id, week_start, week_end)
    )
    wakeup = cursor.fetchone()[0]

    cursor.execute(
        f"SELECT COUNT(DISTINCT date) FROM study WHERE user_id = {placeholder} 
         AND date BETWEEN {placeholder} AND {placeholder} AND minutes >= 10",
        (user_id, week_start, week_end)
    )
    study_days = cursor.fetchone()[0]

    cursor.execute(
        f"SELECT COALESCE(SUM(minutes), 0) FROM study WHERE user_id = {placeholder} 
         AND date BETWEEN {placeholder} AND {placeholder}",
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

# === 연속 기록 계산 ===
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
