import os
import sqlite3
from datetime import datetime, timedelta
from pytz import timezone
import asyncio

# === DB Connection ===
DATABASE_URL = os.getenv("DATABASE_URL")
is_postgres = bool(DATABASE_URL)

if is_postgres:
    import psycopg2
    from urllib.parse import urlparse
    url = urlparse(DATABASE_URL)
    
    def get_db_connection():
        return psycopg2.connect(
            dbname=url.path[1:], user=url.username,
            password=url.password, host=url.hostname, port=url.port
        )
    placeholder = "%s"
else:
    def get_db_connection():
        return sqlite3.connect("princess.db", check_same_thread=False)
    placeholder = "?"

# --- 비동기 DB 실행을 위한 래퍼 ---
# 동기적인 DB 작업을 별도의 스레드에서 실행하여, 봇의 메인 루프를 막지 않습니다.
async def db_execute(query, params=None, fetch=None):
    def sync_db_call():
        conn = None
        try:
            conn = get_db_connection()
            cursor = conn.cursor()
            cursor.execute(query, params or ())
            
            if fetch == "one":
                result = cursor.fetchone()
            elif fetch == "all":
                result = cursor.fetchall()
            else:
                result = None
            
            conn.commit()
            return result
        finally:
            if conn:
                conn.close()

    return await asyncio.to_thread(sync_db_call)


# === Table Creation ===
# 봇 시작 시 한 번만 실행될 초기화 함수
async def initialize_database():
    # users, attendance, wakeup, study 테이블은 기존과 동일
    await db_execute("""
    CREATE TABLE IF NOT EXISTS users (
        user_id TEXT PRIMARY KEY,
        nickname TEXT,
        exp INTEGER DEFAULT 0
    )
    """)
    await db_execute("""
    CREATE TABLE IF NOT EXISTS attendance (
        user_id TEXT,
        date TEXT,
        UNIQUE(user_id, date)
    )
    """)
    await db_execute("""
    CREATE TABLE IF NOT EXISTS wakeup (
        user_id TEXT,
        date TEXT,
        UNIQUE(user_id, date)
    )
    """)
    await db_execute("""
    CREATE TABLE IF NOT EXISTS study (
        user_id TEXT,
        date TEXT,
        minutes INTEGER
    )
    """)
    # [추가] 휘발성 상태 저장을 위한 테이블
    await db_execute("""
    CREATE TABLE IF NOT EXISTS study_sessions (
        user_id TEXT PRIMARY KEY,
        start_time TEXT NOT NULL,
        message_id TEXT NOT NULL
    )
    """)
    await db_execute("""
    CREATE TABLE IF NOT EXISTS wakeup_pending (
        user_id TEXT PRIMARY KEY,
        message_id TEXT NOT NULL
    )
    """)
    print("✅ 데이터베이스 테이블 초기화 완료")


# === Internal: Register or Update User ===
async def _register_user(user_id: str, nickname: str):
    # PostgreSQL의 경우 ON CONFLICT를 사용하여 더 효율적으로 처리
    if is_postgres:
        query = f"""
        INSERT INTO users (user_id, nickname, exp) VALUES ({placeholder}, {placeholder}, 0)
        ON CONFLICT (user_id) DO UPDATE SET nickname = {placeholder};
        """
        await db_execute(query, (user_id, nickname, nickname))
    else: # SQLite
        user = await db_execute("SELECT 1 FROM users WHERE user_id = ?", (user_id,), fetch="one")
        if not user:
            await db_execute("INSERT INTO users (user_id, nickname, exp) VALUES (?, ?, 0)", (user_id, nickname))
        else:
            await db_execute("UPDATE users SET nickname = ? WHERE user_id = ?", (nickname, user_id))


# === Save Attendance (KST date) ===
async def save_attendance(user_id: str, nickname: str) -> bool:
    today = datetime.now(timezone("Asia/Seoul")).strftime("%Y-%m-%d")
    await _register_user(user_id, nickname)
    try:
        await db_execute(
            f"INSERT INTO attendance (user_id, date) VALUES ({placeholder}, {placeholder})",
            (user_id, today)
        )
        return True
    except (sqlite3.IntegrityError, psycopg2.IntegrityError): # 중복 시 에러 발생
        return False

# === Get Attendance Records ===
async def get_attendance(user_id: str):
    return await db_execute(
        f"SELECT date FROM attendance WHERE user_id = {placeholder} ORDER BY date DESC",
        (user_id,),
        fetch="all"
    )

# === Save Wakeup (KST date) ===
async def save_wakeup(user_id: str, nickname: str) -> bool:
    today = datetime.now(timezone("Asia/Seoul")).strftime("%Y-%m-%d")
    await _register_user(user_id, nickname)
    try:
        await db_execute(
            f"INSERT INTO wakeup (user_id, date) VALUES ({placeholder}, {placeholder})",
            (user_id, today)
        )
        return True
    except (sqlite3.IntegrityError, psycopg2.IntegrityError):
        return False

# === Log Study Time (accumulate) ===
async def log_study_time(user_id: str, nickname: str, minutes: int):
    today = datetime.now(timezone("Asia/Seoul")).strftime("%Y-%m-%d")
    await _register_user(user_id, nickname)
    
    row = await db_execute(
        f"SELECT minutes FROM study WHERE user_id = {placeholder} AND date = {placeholder}",
        (user_id, today),
        fetch="one"
    )
    
    if row:
        total = row[0] + minutes
        await db_execute(
            f"UPDATE study SET minutes = {placeholder} WHERE user_id = {placeholder} AND date = {placeholder}",
            (total, user_id, today)
        )
    else:
        await db_execute(
            f"INSERT INTO study (user_id, date, minutes) VALUES ({placeholder}, {placeholder}, {placeholder})",
            (user_id, today, minutes)
        )

# === Get Today's Study Time ===
async def get_today_study_time(user_id: str) -> int:
    today = datetime.now(timezone("Asia/Seoul")).strftime("%Y-%m-%d")
    row = await db_execute(
        f"SELECT minutes FROM study WHERE user_id = {placeholder} AND date = {placeholder}",
        (user_id, today),
        fetch="one"
    )
    return row[0] if row else 0

# === Experience Management ===
async def add_exp(user_id: str, nickname: str, amount: int):
    await _register_user(user_id, nickname)
    await db_execute(
        f"UPDATE users SET exp = exp + {placeholder} WHERE user_id = {placeholder}",
        (amount, user_id)
    )

async def remove_exp(user_id: str, amount: int):
    current = await get_exp(user_id)
    new_exp = max(0, current - amount)
    await db_execute(
        f"UPDATE users SET exp = {placeholder} WHERE user_id = {placeholder}",
        (new_exp, user_id)
    )

async def set_exp(user_id: str, nickname: str, new_exp: int):
    await _register_user(user_id, nickname)
    await db_execute(
        f"UPDATE users SET exp = {placeholder} WHERE user_id = {placeholder}",
        (new_exp, user_id)
    )

async def get_exp(user_id: str) -> int:
    row = await db_execute(
        f"SELECT exp FROM users WHERE user_id = {placeholder}",
        (user_id,),
        fetch="one"
    )
    return row[0] if row else 0

# === Top Users by Exp ===
async def get_top_users_by_exp(limit: int = 10):
    query = f"SELECT nickname, exp FROM users ORDER BY exp DESC LIMIT {placeholder if is_postgres else limit}"
    params = (limit,) if is_postgres else ()
    return await db_execute(query, params, fetch="all")

# === Stats ===
async def get_monthly_stats(user_id: str):
    now = datetime.now(timezone("Asia/Seoul"))
    month_start = now.replace(day=1).strftime("%Y-%m-%d")
    
    query_params = (user_id, month_start, now.strftime("%Y-%m-%d"))
    
    attendance = (await db_execute(f"SELECT COUNT(DISTINCT date) FROM attendance WHERE user_id = {placeholder} AND date >= {placeholder} AND date <= {placeholder}", query_params, fetch="one"))[0]
    wakeup = (await db_execute(f"SELECT COUNT(DISTINCT date) FROM wakeup WHERE user_id = {placeholder} AND date >= {placeholder} AND date <= {placeholder}", query_params, fetch="one"))[0]
    study_days = (await db_execute(f"SELECT COUNT(DISTINCT date) FROM study WHERE user_id = {placeholder} AND minutes >= 10 AND date >= {placeholder} AND date <= {placeholder}", query_params, fetch="one"))[0]
    study_minutes = (await db_execute(f"SELECT COALESCE(SUM(minutes), 0) FROM study WHERE user_id = {placeholder} AND date >= {placeholder} AND date <= {placeholder}", query_params, fetch="one"))[0]
    
    return { "attendance": attendance, "wakeup": wakeup, "study_days": study_days, "study_minutes": study_minutes }

async def get_weekly_stats(user_id: str):
    now = datetime.now(timezone("Asia/Seoul"))
    week_start = (now - timedelta(days=now.weekday())).strftime("%Y-%m-%d")

    query_params = (user_id, week_start, now.strftime("%Y-%m-%d"))

    attendance = (await db_execute(f"SELECT COUNT(DISTINCT date) FROM attendance WHERE user_id = {placeholder} AND date >= {placeholder} AND date <= {placeholder}", query_params, fetch="one"))[0]
    wakeup = (await db_execute(f"SELECT COUNT(DISTINCT date) FROM wakeup WHERE user_id = {placeholder} AND date >= {placeholder} AND date <= {placeholder}", query_params, fetch="one"))[0]
    study_days = (await db_execute(f"SELECT COUNT(DISTINCT date) FROM study WHERE user_id = {placeholder} AND minutes >= 10 AND date >= {placeholder} AND date <= {placeholder}", query_params, fetch="one"))[0]
    study_minutes = (await db_execute(f"SELECT COALESCE(SUM(minutes), 0) FROM study WHERE user_id = {placeholder} AND date >= {placeholder} AND date <= {placeholder}", query_params, fetch="one"))[0]

    return { "attendance": attendance, "wakeup": wakeup, "study_days": study_days, "study_minutes": study_minutes }

# === Streak Calculation ===
def _calculate_streak_from_dates(date_list):
    if not date_list:
        return 0
    today = datetime.now(timezone("Asia/Seoul")).date()
    streak = 0
    
    # 중복 날짜 제거
    unique_dates = sorted(list(set(d[0] for d in date_list)), reverse=True)

    # 오늘 출석했는지 확인
    if not unique_dates or datetime.strptime(unique_dates[0], "%Y-%m-%d").date() not in [today, today - timedelta(days=1)]:
         # 어제 출석 기록도 없으면 연속 출석은 0
        if not unique_dates or datetime.strptime(unique_dates[0], "%Y-%m-%d").date() != today - timedelta(days=1):
            return 0
    
    # 오늘 출석 안했으면 어제부터 카운트
    current_date = today if unique_dates and datetime.strptime(unique_dates[0], "%Y-%m-%d").date() == today else today - timedelta(days=1)

    for d_str in unique_dates:
        d_date = datetime.strptime(d_str, "%Y-%m-%d").date()
        if d_date == current_date:
            streak += 1
            current_date -= timedelta(days=1)
        else:
            break
            
    return streak

async def get_streak_attendance(user_id: str):
    rows = await db_execute(f"SELECT date FROM attendance WHERE user_id = {placeholder} ORDER BY date DESC", (user_id,), fetch="all")
    return _calculate_streak_from_dates(rows)

async def get_streak_wakeup(user_id: str):
    rows = await db_execute(f"SELECT date FROM wakeup WHERE user_id = {placeholder} ORDER BY date DESC", (user_id,), fetch="all")
    return _calculate_streak_from_dates(rows)

async def get_streak_study(user_id: str):
    rows = await db_execute(f"SELECT date FROM study WHERE user_id = {placeholder} AND minutes >= 10 ORDER BY date DESC", (user_id,), fetch="all")
    return _calculate_streak_from_dates(rows)

# === [신규] 휘발성 상태 관리 함수 ===
async def start_study_session(user_id: str, start_time: datetime, message_id: int):
    await db_execute(
        f"INSERT INTO study_sessions (user_id, start_time, message_id) VALUES ({placeholder}, {placeholder}, {placeholder}) ON CONFLICT(user_id) DO UPDATE SET start_time = EXCLUDED.start_time, message_id = EXCLUDED.message_id",
        (user_id, start_time.isoformat(), str(message_id))
    )

async def end_study_session(user_id: str):
    session = await db_execute(
        f"SELECT start_time, message_id FROM study_sessions WHERE user_id = {placeholder}",
        (user_id,),
        fetch="one"
    )
    if session:
        await db_execute(f"DELETE FROM study_sessions WHERE user_id = {placeholder}", (user_id,))
        start_time = datetime.fromisoformat(session[0])
        message_id = int(session[1])
        return {'start': start_time, 'msg_id': message_id}
    return None

async def add_wakeup_pending(user_id: str, message_id: int):
    await db_execute(
        f"INSERT INTO wakeup_pending (user_id, message_id) VALUES ({placeholder}, {placeholder}) ON CONFLICT(user_id) DO UPDATE SET message_id = EXCLUDED.message_id",
        (user_id, str(message_id))
    )

async def get_and_remove_wakeup_pending(user_id: str):
    pending = await db_execute(
        f"SELECT message_id FROM wakeup_pending WHERE user_id = {placeholder}",
        (user_id,),
        fetch="one"
    )
    if pending:
        await db_execute(f"DELETE FROM wakeup_pending WHERE user_id = {placeholder}", (user_id,))
        return int(pending[0])
    return None

# === [신규] 랭킹 조회 함수 (추상화) ===
async def get_streak_rankings(limit: int = 10):
    # 이 쿼리는 복잡하므로 Python에서 처리
    all_users = await db_execute("SELECT DISTINCT user_id FROM attendance", fetch="all")
    streaks = []
    for (user_id,) in all_users:
        s = await get_streak_attendance(user_id)
        if s > 0:
            streaks.append((user_id, s))
    
    streaks.sort(key=lambda x: x[1], reverse=True)
    
    # 닉네임 가져오기
    top_users = []
    for user_id, streak_count in streaks[:limit]:
        nickname = await db_execute(f"SELECT nickname FROM users WHERE user_id = {placeholder}", (user_id,), fetch="one")
        top_users.append({'user_id': user_id, 'nickname': nickname[0] if nickname else '알 수 없는 유저', 'streak': streak_count})
        
    return top_users

async def get_total_attendance_rankings(limit: int = 10):
    query = f"""
    SELECT t1.user_id, t2.nickname, t1.cnt
    FROM (SELECT user_id, COUNT(*) as cnt FROM attendance GROUP BY user_id) as t1
    LEFT JOIN users as t2 ON t1.user_id = t2.user_id
    ORDER BY t1.cnt DESC
    LIMIT {placeholder if is_postgres else limit}
    """
    params = (limit,) if is_postgres else ()
    rows = await db_execute(query, params, fetch="all")
    return [{'user_id': r[0], 'nickname': r[1] or '알 수 없는 유저', 'count': r[2]} for r in rows]
