import os
import sqlite3
from datetime import datetime, timedelta
from pytz import timezone
import asyncio
import psycopg2 # psycopg2 import 추가
from urllib.parse import urlparse # urlparse import 추가

# ... (DB 연결 설정은 기존과 동일)
DATABASE_URL = os.getenv("DATABASE_URL")
is_postgres = bool(DATABASE_URL)

if is_postgres:
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

async def db_execute(query, params=None, fetch=None):
    def sync_db_call():
        conn = None
        try:
            conn = get_db_connection()
            cursor = conn.cursor()
            cursor.execute(query, params or ())
            if fetch == "one": result = cursor.fetchone()
            elif fetch == "all": result = cursor.fetchall()
            else: result = None
            conn.commit()
            return result
        finally:
            if conn: conn.close()
    return await asyncio.to_thread(sync_db_call)

# ====================================================================================
# ▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼
# [수정] study_sessions 테이블에 multiplier 컬럼 추가
# ====================================================================================
async def initialize_database():
    # ... (users, attendance, wakeup, study, wakeup_pending 테이블은 기존과 동일)
    await db_execute("""CREATE TABLE IF NOT EXISTS users (user_id TEXT PRIMARY KEY, nickname TEXT, exp INTEGER DEFAULT 0)""")
    await db_execute("""CREATE TABLE IF NOT EXISTS attendance (user_id TEXT, date TEXT, UNIQUE(user_id, date))""")
    await db_execute("""CREATE TABLE IF NOT EXISTS wakeup (user_id TEXT, date TEXT, UNIQUE(user_id, date))""")
    await db_execute("""CREATE TABLE IF NOT EXISTS study (user_id TEXT, date TEXT, minutes INTEGER)""")
    await db_execute("""CREATE TABLE IF NOT EXISTS wakeup_pending (user_id TEXT PRIMARY KEY, message_id TEXT NOT NULL)""")
    
    # study_sessions 테이블에 multiplier 컬럼 추가 (기본값 1)
    await db_execute("""
    CREATE TABLE IF NOT EXISTS study_sessions (
        user_id TEXT PRIMARY KEY,
        start_time TEXT NOT NULL,
        message_id TEXT NOT NULL,
        multiplier INTEGER DEFAULT 1 
    )
    """)
    # (SQLite 한정) 이미 테이블이 있을 경우, 컬럼만 추가
    if not is_postgres:
        try:
            await db_execute("ALTER TABLE study_sessions ADD COLUMN multiplier INTEGER DEFAULT 1")
        except sqlite3.OperationalError:
            pass # 이미 컬럼이 존재하면 에러가 나므로 무시

    print("✅ 데이터베이스 테이블 초기화 완료")

# ... (_register_user, save_attendance, get_attendance 등 다른 함수는 기존과 동일)
async def _register_user(user_id: str, nickname: str):
    if is_postgres:
        query = f"""
        INSERT INTO users (user_id, nickname, exp) VALUES ({placeholder}, {placeholder}, 0)
        ON CONFLICT (user_id) DO UPDATE SET nickname = {placeholder};
        """
        await db_execute(query, (user_id, nickname, nickname))
    else:
        user = await db_execute("SELECT 1 FROM users WHERE user_id = ?", (user_id,), fetch="one")
        if not user:
            await db_execute("INSERT INTO users (user_id, nickname, exp) VALUES (?, ?, 0)", (user_id, nickname))
        else:
            await db_execute("UPDATE users SET nickname = ? WHERE user_id = ?", (nickname, user_id))

async def save_attendance(user_id: str, nickname: str) -> bool:
    today = datetime.now(timezone("Asia/Seoul")).strftime("%Y-%m-%d")
    await _register_user(user_id, nickname)
    try:
        await db_execute(f"INSERT INTO attendance (user_id, date) VALUES ({placeholder}, {placeholder})", (user_id, today))
        return True
    except (sqlite3.IntegrityError, psycopg2.IntegrityError):
        return False

async def get_attendance(user_id: str):
    return await db_execute(f"SELECT date FROM attendance WHERE user_id = {placeholder} ORDER BY date DESC", (user_id,), fetch="all")

async def save_wakeup(user_id: str, nickname: str) -> bool:
    today = datetime.now(timezone("Asia/Seoul")).strftime("%Y-%m-%d")
    await _register_user(user_id, nickname)
    try:
        await db_execute(f"INSERT INTO wakeup (user_id, date) VALUES ({placeholder}, {placeholder})", (user_id, today))
        return True
    except (sqlite3.IntegrityError, psycopg2.IntegrityError):
        return False

async def log_study_time(user_id: str, nickname: str, minutes: int):
    today = datetime.now(timezone("Asia/Seoul")).strftime("%Y-%m-%d")
    await _register_user(user_id, nickname)
    row = await db_execute(f"SELECT minutes FROM study WHERE user_id = {placeholder} AND date = {placeholder}", (user_id, today), fetch="one")
    if row:
        total = row[0] + minutes
        await db_execute(f"UPDATE study SET minutes = {placeholder} WHERE user_id = {placeholder} AND date = {placeholder}", (total, user_id, today))
    else:
        await db_execute(f"INSERT INTO study (user_id, date, minutes) VALUES ({placeholder}, {placeholder}, {placeholder})", (user_id, today, minutes))

async def get_today_study_time(user_id: str) -> int:
    today = datetime.now(timezone("Asia/Seoul")).strftime("%Y-%m-%d")
    row = await db_execute(f"SELECT minutes FROM study WHERE user_id = {placeholder} AND date = {placeholder}", (user_id, today), fetch="one")
    return row[0] if row else 0

async def add_exp(user_id: str, nickname: str, amount: int):
    await _register_user(user_id, nickname)
    await db_execute(f"UPDATE users SET exp = exp + {placeholder} WHERE user_id = {placeholder}", (amount, user_id))

async def remove_exp(user_id: str, amount: int):
    current = await get_exp(user_id)
    new_exp = max(0, current - amount)
    await db_execute(f"UPDATE users SET exp = {placeholder} WHERE user_id = {placeholder}", (new_exp, user_id))

async def set_exp(user_id: str, nickname: str, new_exp: int):
    await _register_user(user_id, nickname)
    await db_execute(f"UPDATE users SET exp = {placeholder} WHERE user_id = {placeholder}", (new_exp, user_id))

async def get_exp(user_id: str) -> int:
    row = await db_execute(f"SELECT exp FROM users WHERE user_id = {placeholder}", (user_id,), fetch="one")
    return row[0] if row else 0

async def get_top_users_by_exp(limit: int = 10):
    query = f"SELECT nickname, exp FROM users ORDER BY exp DESC LIMIT {placeholder if is_postgres else limit}"
    params = (limit,) if is_postgres else ()
    return await db_execute(query, params, fetch="all")

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

def _calculate_streak_from_dates(date_list):
    if not date_list: return 0
    today = datetime.now(timezone("Asia/Seoul")).date()
    streak = 0
    unique_dates = sorted(list(set(d[0] for d in date_list)), reverse=True)
    if not unique_dates or datetime.strptime(unique_dates[0], "%Y-%m-%d").date() not in [today, today - timedelta(days=1)]:
        if not unique_dates or datetime.strptime(unique_dates[0], "%Y-%m-%d").date() != today - timedelta(days=1):
            return 0
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

# ====================================================================================
# ▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼
# [수정/신규] 휘발성 상태 관리 함수들 (multiplier 지원)
# ====================================================================================
async def start_study_session(user_id: str, start_time: datetime, message_id: int):
    # ON CONFLICT 구문은 PostgreSQL과 SQLite 3.24.0+ 에서만 지원됩니다.
    # 이전 버전의 SQLite를 사용한다면 SELECT 후 INSERT/UPDATE 하는 방식으로 변경해야 합니다.
    query = f"""
    INSERT INTO study_sessions (user_id, start_time, message_id, multiplier) VALUES ({placeholder}, {placeholder}, {placeholder}, 1)
    ON CONFLICT(user_id) DO UPDATE SET start_time = EXCLUDED.start_time, message_id = EXCLUDED.message_id, multiplier = 1
    """
    await db_execute(query, (user_id, start_time.isoformat(), str(message_id)))

async def end_study_session(user_id: str):
    session = await db_execute(
        f"SELECT start_time, message_id, multiplier FROM study_sessions WHERE user_id = {placeholder}",
        (user_id,),
        fetch="one"
    )
    if session:
        await db_execute(f"DELETE FROM study_sessions WHERE user_id = {placeholder}", (user_id,))
        start_time = datetime.fromisoformat(session[0])
        message_id = int(session[1])
        multiplier = int(session[2])
        return {'start': start_time, 'msg_id': message_id, 'multiplier': multiplier}
    return None

# [신규] 공부 세션 전체 정보 조회
async def get_study_session(user_id: str):
    session = await db_execute(
        f"SELECT start_time, message_id, multiplier FROM study_sessions WHERE user_id = {placeholder}",
        (user_id,),
        fetch="one"
    )
    if session:
        return {'start': datetime.fromisoformat(session[0]), 'msg_id': int(session[1]), 'multiplier': int(session[2])}
    return None

# [신규] 공부 세션 경험치 배율 업데이트
async def update_study_multiplier(user_id: str, multiplier: int):
    await db_execute(
        f"UPDATE study_sessions SET multiplier = {placeholder} WHERE user_id = {placeholder}",
        (multiplier, user_id)
    )

# [신규] 공부 세션 강제 삭제 (강퇴 시 사용)
async def delete_study_session(user_id: str):
    await db_execute(f"DELETE FROM study_sessions WHERE user_id = {placeholder}", (user_id,))


async def add_wakeup_pending(user_id: str, message_id: int):
    query = f"""
    INSERT INTO wakeup_pending (user_id, message_id) VALUES ({placeholder}, {placeholder})
    ON CONFLICT(user_id) DO UPDATE SET message_id = EXCLUDED.message_id
    """
    await db_execute(query, (user_id, str(message_id)))

async def get_and_remove_wakeup_pending(user_id: str):
    pending = await db_execute(f"SELECT message_id FROM wakeup_pending WHERE user_id = {placeholder}", (user_id,), fetch="one")
    if pending:
        await db_execute(f"DELETE FROM wakeup_pending WHERE user_id = {placeholder}", (user_id,))
        return int(pending[0])
    return None

async def get_streak_rankings(limit: int = 10):
    all_users = await db_execute("SELECT DISTINCT user_id FROM attendance", fetch="all")
    streaks = []
    for (user_id,) in all_users:
        s = await get_streak_attendance(user_id)
        if s > 0: streaks.append((user_id, s))
    streaks.sort(key=lambda x: x[1], reverse=True)
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
