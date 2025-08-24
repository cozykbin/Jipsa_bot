import discord
from discord.ext import commands, tasks
from discord.ui import View, Button
from discord import app_commands
from datetime import datetime, timedelta
from pytz import timezone
import db 
import random
import os
import ahttp
import asyncio
import logging

# ... (상단 설정은 기존과 동일)
TOKEN = os.getenv("DISCORD_TOKEN")
GSHEET_WEBHOOK = os.getenv("GSHEET_WEBHOOK")
intents = discord.Intents.default()
intents.message_content = True
intents.voice_states = True
intents.messages = True
intents.members = True
bot = commands.Bot(command_prefix="!", intents=intents)
logging.basicConfig(level=logging.INFO, format='%(asctime)s:%(levelname)s:%(name)s: %(message)s')
logger = logging.getLogger(__name__)

# [추가] 캠스터디 채널 이름 상수
CAM_STUDY_CHANNEL = "🎥｜캠스터디"
CAM_BONUS_MULTIPLIER = 2

# ... (append_to_sheet, get_embed_footer, AttendanceRankingView, LEVELS 등 기존과 동일)
async def append_to_sheet(session: aiohttp.ClientSession, sheet_name: str, data: list) -> bool:
    if not GSHEET_WEBHOOK:
        logger.error("Google Sheet Webhook URL이 설정되어 있지 않습니다.")
        return False
    payload = {"sheet": sheet_name, "data": data}
    try:
        async with session.post(GSHEET_WEBHOOK, json=payload, timeout=10) as resp:
            if resp.status != 200:
                logger.warning(f"Google Sheet API 비정상 응답: 상태코드 {resp.status}")
                return False
            return True
    except Exception as e:
        logger.error(f"Google Sheet API 요청 실패: {str(e)}")
        return False

def get_embed_footer(user: discord.User, dt: datetime):
    kst = timezone('Asia/Seoul')
    now = dt.astimezone(kst)
    if now.date() == datetime.now(kst).date(): label = "오늘"
    elif now.date() == (datetime.now(kst).date() - timedelta(days=1)): label = "어제"
    else: label = now.strftime("%y/%m/%d")
    time_label = now.strftime("%H:%M")
    display_name = user.display_name
    avatar_url = user.display_avatar.url if user.display_avatar else user.avatar.url
    return {"text": f"{display_name} | {label}, {time_label}", "icon_url": avatar_url}

class AttendanceRankingView(View):
    def __init__(self):
        super().__init__(timeout=None)
        self.add_item(Button(label="🔥 연속 출석 랭킹", style=discord.ButtonStyle.primary, custom_id="streak_rank"))
        self.add_item(Button(label="📅 누적 출석 랭킹", style=discord.ButtonStyle.secondary, custom_id="total_rank"))

LEVELS = {
    1: {"emoji": "🪴", "name": "궁전문 앞 새싹", "desc": "드디어 궁전문을 똑똑 두드리는 우리 새싹 공듀🌱\n아직은 설렘과 긴장이 함께 찾아오지만,\n햇살이 좋은 날엔 ‘나도 뭔가 해낼 수 있을 것 같아’\n가만히 마음속 다짐이 싹 트기 시작해요."},
    2: {"emoji": "🏰", "name": "왕실 입문생", "desc": "한 걸음 더 내딛으면, 새로운 세계가 펼쳐져요!\n궁전 안에서 길을 잃기도 하고,\n간식 코너에서 몰래 쉬다 들키기도 하지만🐻‍❄️\n조금씩 나만의 리듬으로 살아가는 연습이 시작돼요.\n‘이게 바로 갓생의 첫걸음?’"},
    3: {"emoji": "🎀", "name": "공듀 준비생", "desc": "조금 더 익숙해진 궁전 생활,\n공듀 선배들의 응원도 받고,\n‘오늘은 전보다 1분이라도 더 집중해볼까?’\n조그만 성취에도 스스로 토닥여주는\n진짜 갓생 연습생이 되어가는 중이에요🐹"},
    4: {"emoji": "🍼", "name": "초보 공듀", "desc": "이제는 티아라도 살짝 써보고,\n도서관 입장도 조금은 자연스러워졌어요.\n가끔 집중이 풀리더라도,\n오늘 하루 나를 칭찬하며\n조용히 다시 책상 앞에 앉아요✨\n작은 습관들이 하나씩 쌓여가요."},
    5: {"emoji": "🍀", "name": "레어 공듀", "desc": "레어템처럼 불시에 터지는 집중력!\n자기 효능감이 잔뜩 쌓이기 시작한 레어 공듀!\n오늘은 어제보다 더 멋진 나를 발견해요.\n딴짓도, 공부도, 휴식도 다 내 갓생 루틴의 일부!"},
    6: {"emoji": "🔮", "name": "에픽 공듀", "desc": "이젠 모두가 아는 에픽 공듀!\n계획표도 더욱 멋있어지고\n나만의 리듬이 더 단단해지는 시기를 보내고 있어요❤️‍🔥\n이 작은 성장들이 모여,\n나만의 갓생을 완성해간답니다."},
    7: {"emoji": "🌈", "name": "레전더리 공듀", "desc": "집중력이 슬금슬금 전설이 되고 있어요!\n공부하다 멈췄을 때,\n‘이 정도면 나 진짜 레전드 아냐?’ 하는\n괜한 뿌듯함이 마음을 채워줘요.\n더 이상 남과 비교하지 않고,\n매일의 기록을 즐겁게 채워가는 중🌟"},
    8: {"emoji": "🦄", "name": "비스트 공듀", "desc": "집중 비스트 모드, 오늘도 ON!\n가끔은 흔들리더라도,\n작은 루틴을 지켜내는 나를 대견히 바라봐요🦄\n공부도, 웃음도, 간식도\n모두 ‘나만의 갓생’이 되어가는 중!"},
    9: {"emoji": "💎", "name": "공주(진)", "desc": "이제 모두가 인정하는 진짜 공주!\n따뜻한 응원과 작은 배려로,\n서버 친구들에게 힘을 주는 존재가 되었어요👸\n공부, 성장, 휴식 모두가\n나만의 소중한 루틴이란 걸 알게 됐어요."},
    10: {"emoji": "👑", "name": "QUEEN", "desc": "궁전의 왕좌에 앉은 우리 왕국의 QUEEN!\n어떤 하루도 멋지게 완성할 수 있다는 걸\n작은 실천들이 알려줬어요💖\n이제는 모두의 롤모델이 되어,\n다른 공듀들에게도 ‘나만의 갓생’을 응원할 수 있답니다.\n오늘도 함께라서 참 든든해요!"},
}
LEVEL_THRESHOLDS = [0, 200, 600, 1500, 3000, 5000, 7500, 10000, 14000, 18500, 25000]
TRACKED_VOICE_CHANNELS = ["🎥｜캠스터디", "📖｜1인실 (A)", "📖｜1인실 (B)", "📓｜도서관", "🌆｜워크스페이스"]
RANKING_CHANNEL_ID = 1378863730741219458
HONOR_CHANNEL_ID = 1378863861863682102
MYINFO_CHANNEL_ID = 1378952514702938182
ATTENDANCE_CHANNEL_ID = 1378862713484218489
WAKEUP_CHANNEL_ID = 1378862771214745690
ranking_message_id = None
user_info_channel_msgs = {}

def get_level_from_exp(exp):
    for i in range(1, len(LEVEL_THRESHOLDS)):
        if exp < LEVEL_THRESHOLDS[i]: return i
    return 10

async def get_user_exp(user_id):
    return await db.get_exp(str(user_id))

# ... (send_levelup_embed, create_or_update_user_info, add_exp_and_check_level 등 기존과 동일)
async def send_levelup_embed(member, new_level):
    honor_channel = bot.get_channel(HONOR_CHANNEL_ID)
    if honor_channel is None: return
    data = LEVELS[new_level]
    embed = discord.Embed(
        title=f"{data['emoji']} 레벨업! {data['name']} 달성",
        description=(f"{member.mention} 공듀님, {data['name']}에 도달했어요!\n\n{data['desc']}"),
        color=discord.Color.purple()
    )
    footer = get_embed_footer(member, datetime.now(timezone('Asia/Seoul')))
    embed.set_footer(text=footer["text"], icon_url=footer["icon_url"])
    await honor_channel.send(embed=embed)

async def create_or_update_user_info(member):
    user_id = str(member.id)
    exp = await get_user_exp(user_id)
    level = get_level_from_exp(exp)
    leveldata = LEVELS[level]
    if level < len(LEVEL_THRESHOLDS) - 1: next_exp = LEVEL_THRESHOLDS[level]
    else: next_exp = exp + 100
    exp_required = next_exp - exp
    if level == 1:
        current_exp = exp
        progress_total = LEVEL_THRESHOLDS[1]
    elif level < len(LEVEL_THRESHOLDS) - 1:
        current_exp = exp - LEVEL_THRESHOLDS[level - 1]
        progress_total = LEVEL_THRESHOLDS[level] - LEVEL_THRESHOLDS[level - 1]
    else:
        current_exp = exp - LEVEL_THRESHOLDS[-2]
        progress_total = LEVEL_THRESHOLDS[-1] - LEVEL_THRESHOLDS[-2]
    progress_bar_length = 20
    filled_length = int(progress_bar_length * current_exp / progress_total) if progress_total else 0
    bar = "■" * filled_length + "□" * (progress_bar_length - filled_length)
    now = datetime.now(timezone('Asia/Seoul'))
    embed = discord.Embed(
        title=f"{member.display_name}님의 내정보",
        description=(f"{member.mention} 공듀님의 최신 정보예요.\n변동이 있을 때마다 자동으로 업데이트됩니다! 😊"),
        color=member.color
    )
    embed.add_field(name="👑 레벨", value=f"{leveldata['emoji']} Lv.{level} {leveldata['name']}", inline=False)
    embed.add_field(name="📊 총 경험치", value=f"{exp} Exp (다음 레벨까지 {exp_required} Exp 남음)", inline=False)
    embed.add_field(name="📈 진행도", value=f"`{bar}`", inline=False)
    stats_month = await db.get_monthly_stats(user_id)
    embed.add_field(
        name="📅 이번달 통계",
        value=(f"출석: {stats_month['attendance']}일\n기상: {stats_month['wakeup']}일\n공부일수: {stats_month['study_days']}일\n공부시간: {stats_month['study_minutes']}분"),
        inline=True
    )
    stats_week = await db.get_weekly_stats(user_id)
    embed.add_field(
        name="📆 이번주 통계",
        value=(f"출석: {stats_week['attendance']}일\n기상: {stats_week['wakeup']}일\n공부일수: {stats_week['study_days']}일\n공부시간: {stats_week['study_minutes']}분"),
        inline=True
    )
    footer = get_embed_footer(member, now)
    embed.set_footer(text=footer["text"], icon_url=footer["icon_url"])
    channel = bot.get_channel(MYINFO_CHANNEL_ID)
    if channel is None: return
    if user_id in user_info_channel_msgs:
        try:
            msg_id = user_info_channel_msgs[user_id]
            existing = await channel.fetch_message(msg_id)
            await existing.edit(embed=embed)
            return
        except Exception:
            user_info_channel_msgs.pop(user_id, None)
    new_msg = await channel.send(embed=embed)
    user_info_channel_msgs[user_id] = new_msg.id

async def add_exp_and_check_level(member, exp_gained):
    user_id = str(member.id)
    exp_before = await get_user_exp(user_id)
    old_level = get_level_from_exp(exp_before)
    await db.add_exp(user_id, member.display_name, exp_gained)
    exp_after = exp_before + exp_gained
    new_level = get_level_from_exp(exp_after)
    if new_level > old_level:
        await send_levelup_embed(member, new_level)
    async with aiohttp.ClientSession() as session:
        await append_to_sheet(session, "users", [user_id, member.display_name, exp_after, new_level])
    await create_or_update_user_info(member)
    return new_level, exp_after

# ... (make_ranking_embed, update_ranking, on_ready, setup_ranking_message 등 기존과 동일)
async def make_ranking_embed():
    now = datetime.now(timezone('Asia/Seoul'))
    today_str = now.strftime("%Y년 %m월 %d일 %H:%M 기준")
    ranking = await db.get_top_users_by_exp()
    embed = discord.Embed(title="🏆 경험치 랭킹 TOP 10", color=discord.Color.gold())
    if not ranking:
        embed.description = "아직 아무도 경험치를 쌓지 않았어요! 🌱"
    else:
        lines = []
        for i, (name, exp) in enumerate(ranking, start=1):
            level = get_level_from_exp(exp)
            emoji = LEVELS[level]["emoji"]
            levelname = LEVELS[level]["name"]
            lines.append(f"{i}위 {emoji} **{name}** ({levelname}) - Lv.{level} / {exp} Exp")
        embed.description = "\n".join(lines)
    embed.set_footer(text=f"마지막 업데이트: {today_str}")
    return embed

@tasks.loop(minutes=1)
async def update_ranking():
    global ranking_message_id
    channel = bot.get_channel(RANKING_CHANNEL_ID)
    if channel is None: return
    if ranking_message_id is None:
        await setup_ranking_message()
        if ranking_message_id is None: return
    try:
        msg = await channel.fetch_message(ranking_message_id)
        embed = await make_ranking_embed()
        await msg.edit(embed=embed)
    except discord.NotFound:
        ranking_message_id = None
    except Exception as e:
        logger.error(f"랭킹 업데이트 중 오류: {e}")

@bot.event
async def on_ready():
    await db.initialize_database()
    bot.add_view(AttendanceRankingView())
    await bot.tree.sync()
    await setup_ranking_message()
    update_ranking.start()
    print(f"✅ {bot.user} 로그인 완료")

async def setup_ranking_message():
    global ranking_message_id
    channel = bot.get_channel(RANKING_CHANNEL_ID)
    if channel is None: return
    async for msg in channel.history(limit=20):
        if (msg.author == bot.user and msg.embeds and msg.embeds[0].title and "경험치 랭킹" in msg.embeds[0].title):
            ranking_message_id = msg.id
            break
    else:
        embed = await make_ranking_embed()
        msg = await channel.send(embed=embed)
        await msg.pin()
        ranking_message_id = msg.id

# ====================================================================================
# ▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼
# [신규] 캠스터디 10분 유예시간 체크 및 자동 강퇴 함수
# ====================================================================================
async def check_and_kick(member: discord.Member):
    """10분(600초) 후에 멤버의 카메라 상태를 확인하고, 꺼져있으면 강퇴시키는 함수"""
    await asyncio.sleep(600)

    user_id = str(member.id)
    
    # 10분 후, 멤버가 서버에 없거나 다른 채널로 이동했다면 함수 종료
    if not member.guild or not member.voice or member.voice.channel.name != CAM_STUDY_CHANNEL:
        return

    # 10분 후, DB에서 세션 정보를 가져옴
    session = await db.get_study_session(user_id)
    
    # 세션이 없거나(이미 퇴장 처리됨) 배율이 1이 아니면(이미 캠을 켬) 함수 종료
    if not session or session.get('multiplier', 1) != 1:
        return

    # 위의 모든 조건을 통과했다면 -> 10분 동안 캠을 켜지 않은 유저
    try:
        study_channel = discord.utils.get(member.guild.text_channels, name="📕｜공부기록")
        if study_channel:
            msg = await study_channel.fetch_message(session['msg_id'])
            embed = msg.embeds[0]
            embed.title = "🚫 캠스터디 규칙 위반"
            embed.description = f"{member.mention} 공듀님, 10분 내에 카메라를 켜지 않아 채널에서 이동되었어요."
            embed.color = discord.Color.red()
            await msg.edit(embed=embed)

        await member.move_to(None, reason="캠스터디 10분 내 카메라 미사용")
    except Exception as e:
        logger.error(f"{member.display_name}님 강퇴 처리 중 오류: {e}")
    finally:
        # 강퇴 후에는 공부 세션 기록을 완전히 삭제 (경험치 지급 방지)
        await db.delete_study_session(user_id)

# ====================================================================================
# ▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼
# [수정] on_voice_state_update: 캠스터디 채널 관련 로직 대폭 수정
# ====================================================================================
@bot.event
async def on_voice_state_update(member, before, after):
    now_kst = datetime.now(timezone('Asia/Seoul'))
    user_id = str(member.id)
    
    study_channel = discord.utils.get(member.guild.text_channels, name="📕｜공부기록")
    if study_channel is None: return

    # 채널 상태 정의
    before_channel_name = before.channel.name if before.channel else None
    after_channel_name = after.channel.name if after.channel else None
    is_before_study = before_channel_name in TRACKED_VOICE_CHANNELS
    is_after_study = after_channel_name in TRACKED_VOICE_CHANNELS

    # --- 시나리오 1: 공부 시작 (스터디 채널 입장) ---
    if is_after_study and not is_before_study:
        footer = get_embed_footer(member, now_kst)
        
        # 캠스터디 채널에 입장한 경우
        if after_channel_name == CAM_STUDY_CHANNEL:
            embed = discord.Embed(title="📸 캠스터디 입장!", color=member.color)
            embed.description = (
                f"{member.mention} 공듀님, 캠스터디에 오신 것을 환영해요!\n\n"
                f"**10분 내에 카메라나 화면 공유를 켜주세요.**\n"
                f"규칙을 지키지 않으면 자동으로 채널에서 내보내져요! 😥"
            )
            embed.set_footer(text=footer["text"], icon_url=footer["icon_url"])
            msg = await study_channel.send(embed=embed)
            await db.start_study_session(user_id, now_kst, msg.id)
            # 10분 타이머 시작
            bot.loop.create_task(check_and_kick(member))
        
        # 일반 스터디 채널에 입장한 경우
        else:
            embed = discord.Embed(title="🎀 공듀 스터디룸 입장 🎀", color=member.color)
            embed.description = (
                f"{member.mention} 공듀님이 도서관에 나타났어요!\n"
                f"오늘도 집중모드 발동✨\n공부 시작 시간: {now_kst.strftime('%H:%M:%S')}"
            )
            embed.set_footer(text=footer["text"], icon_url=footer["icon_url"])
            msg = await study_channel.send(embed=embed)
            await db.start_study_session(user_id, now_kst, msg.id)

    # --- 시나리오 2: 공부 종료 (스터디 채널 퇴장) ---
    elif is_before_study and not is_after_study:
        session = await db.end_study_session(user_id)
        if not session: return

        end_time = now_kst
        duration_minutes = (end_time - session['start']).total_seconds() / 60
        
        try: msg = await study_channel.fetch_message(session['msg_id'])
        except Exception: msg = None

        if duration_minutes < 10:
            embed = discord.Embed(title="⏰ 집중 실패! (10분 미만)", description=f"{member.mention} 공듀님, 10분 미만은 집중 인정 불가에요!", color=member.color)
            embed.set_footer(text=get_embed_footer(member, end_time)["text"], icon_url=get_embed_footer(member, end_time)["icon_url"])
            if msg: await msg.edit(embed=embed)
            return

        duration_int = int(duration_minutes)
        # [수정] 경험치 계산 시 배율 적용
        multiplier = session.get('multiplier', 1)
        exp_gained = duration_int * multiplier

        await db.log_study_time(user_id, member.display_name, duration_int)
        level, exp_after = await add_exp_and_check_level(member, exp_gained)
        leveldata = LEVELS[level]
        today_total = await db.get_today_study_time(user_id)
        h, m = divmod(duration_int, 60)
        time_str = f"{h}시간 {m}분" if h else f"{m}분"

        embed = discord.Embed(title=f"{leveldata['emoji']} 집중 완료! 공듀 퇴장 ✨", description=f"{member.mention} 공듀님 오늘도 대단해요!\n공부박스 도착🎁", color=member.color)
        embed.add_field(name="⏳ 공부한 시간", value=f"**{time_str}**", inline=False)
        embed.add_field(name="🌹 획득 Exp", value=f"**{exp_gained} Exp**{' (🔥 2배 보너스!)' if multiplier > 1 else ''}", inline=True)
        embed.add_field(name="👑 오늘 누적", value=f"**{today_total}분**", inline=True)
        embed.add_field(name="🏅 현재 레벨", value=f"{leveldata['emoji']} Lv.{level} {leveldata['name']}", inline=False)
        embed.set_footer(text=get_embed_footer(member, end_time)["text"], icon_url=get_embed_footer(member, end_time)["icon_url"])

        if msg: await msg.edit(embed=embed)
        else: await study_channel.send(embed=embed)

    # --- 시나리오 3: 채널 내 상태 변경 (카메라 On/Off 등) ---
    elif is_after_study and after_channel_name == CAM_STUDY_CHANNEL:
        session = await db.get_study_session(user_id)
        if not session: return

        is_cam_on = after.self_video or after.self_stream
        current_multiplier = session.get('multiplier', 1)
        
        try:
            msg = await study_channel.fetch_message(session['msg_id'])
            embed = msg.embeds[0]

            # 카메라/방송을 켰고, 현재 보너스를 받고 있지 않다면 -> 보너스 적용
            if is_cam_on and current_multiplier == 1:
                await db.update_study_multiplier(user_id, CAM_BONUS_MULTIPLIER)
                embed.title = "열공 모드 ON 🔥"
                embed.description = f"{member.mention} 공듀님, 집중하는 모습이 멋져요!\n**지금부터 경험치가 2배로 적용됩니다!**"
                embed.color = discord.Color.green()
                await msg.edit(embed=embed)

            # 카메라/방송을 껐고, 현재 보너스를 받고 있다면 -> 보너스 해제
            elif not is_cam_on and current_multiplier > 1:
                await db.update_study_multiplier(user_id, 1)
                embed.title = "📸 캠스터디 (일반 모드)"
                embed.description = f"{member.mention} 공듀님, 휴식이 필요하신가요?\n카메라나 화면 공유를 다시 켜면 경험치 2배가 적용돼요!"
                embed.color = member.color
                await msg.edit(embed=embed)

        except Exception as e:
            logger.error(f"캠스터디 상태 업데이트 중 오류: {e}")

# ... (이하 !출석, !기상, !통계, !기록, !명령어, 슬래시 커맨드 등 기존 코드와 동일)
@bot.command(name="출석")
async def checkin(ctx):
    now = datetime.now(timezone('Asia/Seoul'))
    saved_db = await db.save_attendance(str(ctx.author.id), ctx.author.display_name)
    async with aiohttp.ClientSession() as session:
        await append_to_sheet(session, "attendance", [str(ctx.author.id), now.strftime("%Y-%m-%d"), ctx.author.display_name])
    streak = await db.get_streak_attendance(str(ctx.author.id))
    attendance_rows = await db.get_attendance(str(ctx.author.id))
    total = len(attendance_rows) if attendance_rows else 0
    embed = discord.Embed(color=ctx.author.color)
    if not saved_db:
        embed.title = "👑 출석 실패"
        embed.description = f"{ctx.author.mention} 공듀님, 오늘은 이미 출석하셨어요! 🐣"
    else:
        exp_gained = 50
        level, exp_after = await add_exp_and_check_level(ctx.author, exp_gained)
        leveldata = LEVELS[level]
        embed.title = "✅ 출석체크 완료!"
        embed.description = (f"출석체크 보상으로 **{exp_gained} EXP**를 획득하였습니다.\n\n"
                           f"❤️‍🔥 **현재 연속 출석**\n**{streak}일**\n\n"
                           f"📅 **총 출석 횟수**\n**{total}회**")
        embed.add_field(name="🎁 현재 레벨", value=f"{leveldata['emoji']} Lv.{level} {leveldata['name']}", inline=False)
    footer = get_embed_footer(ctx.author, now)
    embed.set_footer(text=footer["text"], icon_url=footer["icon_url"])
    await ctx.send(embed=embed, view=AttendanceRankingView())

@bot.event
async def on_interaction(interaction: discord.Interaction):
    if not interaction.data or "custom_id" not in interaction.data: return
    custom_id = interaction.data.get("custom_id")
    if custom_id == "streak_rank":
        top_users = await db.get_streak_rankings()
        description = ""
        for i, user_data in enumerate(top_users, start=1):
            description += f"{i}위 🔥 **{user_data['nickname']}** — {user_data['streak']}일\n"
        embed = discord.Embed(title="🔥 연속 출석 랭킹 TOP 10", description=description or "출석 기록이 없습니다.", color=discord.Color.orange())
        await interaction.response.send_message(embed=embed, ephemeral=True)
    elif custom_id == "total_rank":
        top_users = await db.get_total_attendance_rankings()
        description = ""
        for i, user_data in enumerate(top_users, start=1):
            description += f"{i}위 📅 **{user_data['nickname']}** — {user_data['count']}회\n"
        embed = discord.Embed(title="📅 누적 출석 랭킹 TOP 10", description=description or "출석 기록이 없습니다.", color=discord.Color.green())
        await interaction.response.send_message(embed=embed, ephemeral=True)

@bot.command(name="기상")
async def wakeup(ctx):
    now = datetime.now(timezone('Asia/Seoul'))
    user_id = str(ctx.author.id)
    is_first_wakeup = await db.save_wakeup(user_id, ctx.author.display_name) 
    footer = get_embed_footer(ctx.author, now)
    if not is_first_wakeup:
        embed = discord.Embed(title="☀️ 기상 실패", description=f"{ctx.author.mention} 공듀님, 오늘은 이미 기상 인증했어요! ☀️", color=ctx.author.color)
        embed.set_footer(text=footer["text"], icon_url=footer["icon_url"])
        await ctx.send(embed=embed)
        return
    async with aiohttp.ClientSession() as session:
        await append_to_sheet(session, "wakeup", [user_id, now.strftime("%Y-%m-%d"), ctx.author.display_name])
    embed = discord.Embed(title="📷 기상 인증 요청", description=(f"{ctx.author.mention} 공듀님, 기상 인증 사진을 올려주세요!\n카메라로 아침 인증샷(책상, 시계 등) 첨부 필수 📸"), color=ctx.author.color)
    embed.set_footer(text=footer["text"], icon_url=footer["icon_url"])
    msg = await ctx.send(embed=embed)
    await db.add_wakeup_pending(user_id, msg.id)

@bot.event
async def on_message(message):
    if message.author.bot: return
    await bot.process_commands(message)
    user_id = str(message.author.id)
    pending_msg_id = await db.get_and_remove_wakeup_pending(user_id)
    if pending_msg_id and message.attachments:
        try:
            req_msg = await message.channel.fetch_message(pending_msg_id)
        except Exception:
            return
        now = datetime.now(timezone('Asia/Seoul'))
        footer = get_embed_footer(message.author, now)
        hour = now.hour
        exp_gained = 200 if hour < 9 else 100
        level, exp_after = await add_exp_and_check_level(message.author, exp_gained)
        leveldata = LEVELS[level]
        photo_url = message.attachments[0].url
        try: await message.delete()
        except Exception: pass
        embed = discord.Embed(title=f"{leveldata['emoji']} 기상 인증 완료!", description=(f"{message.author.mention} 공듀님, 기상 인증 완료! 오늘 하루 멋지게 시작해요 🌞 (+{exp_gained} Exp)"), color=message.author.color)
        embed.set_image(url=photo_url)
        embed.add_field(name="🎁 현재 레벨", value=f"{leveldata['emoji']} Lv.{level} {leveldata['name']}")
        embed.set_footer(text=footer["text"], icon_url=footer["icon_url"])
        await req_msg.edit(embed=embed)

@bot.command(name="통계")
async def show_stats(ctx):
    user_id = str(ctx.author.id)
    now = datetime.now(timezone('Asia/Seoul'))
    footer = get_embed_footer(ctx.author, now)
    exp = await get_user_exp(user_id)
    level = get_level_from_exp(exp)
    leveldata = LEVELS[level]
    stats_month = await db.get_monthly_stats(user_id)
    stats_week = await db.get_weekly_stats(user_id)
    total_attendance = len(await db.get_attendance(user_id))
    total_wakeup = (await db.db_execute(f"SELECT COUNT(*) FROM wakeup WHERE user_id = {db.placeholder}", (user_id,), fetch="one"))[0]
    total_study_days = (await db.db_execute(f"SELECT COUNT(DISTINCT date) FROM study WHERE user_id = {db.placeholder} AND minutes >= 10", (user_id,), fetch="one"))[0]
    total_study_minutes = (await db.db_execute(f"SELECT COALESCE(SUM(minutes), 0) FROM study WHERE user_id = {db.placeholder}", (user_id,), fetch="one"))[0]
    embed = discord.Embed(title=f"{ctx.author.display_name}님의 통계 정보", color=ctx.author.color)
    embed.add_field(name="👑 레벨·경험치", value=f"{leveldata['emoji']} Lv.{level} ({exp} Exp)", inline=False)
    embed.add_field(name="📅 이번달 통계", value=(f"출석: {stats_month['attendance']}일\n기상: {stats_month['wakeup']}일\n공부일수: {stats_month['study_days']}일\n공부시간: {stats_month['study_minutes']}분"), inline=True)
    embed.add_field(name="📆 이번주 통계", value=(f"출석: {stats_week['attendance']}일\n기상: {stats_week['wakeup']}일\n공부일수: {stats_week['study_days']}일\n공부시간: {stats_week['study_minutes']}분"), inline=True)
    embed.add_field(name="🔢 전체 누적 통계", value=(f"총 출석: {total_attendance}회\n총 기상: {total_wakeup}회\n총 공부일수: {total_study_days}일\n총 공부시간: {total_study_minutes}분"), inline=False)
    embed.set_footer(text=footer["text"], icon_url=footer["icon_url"])
    await ctx.send(embed=embed)

@bot.command(name="기록")
async def show_records(ctx):
    user_id = str(ctx.author.id)
    now = datetime.now(timezone('Asia/Seoul'))
    footer = get_embed_footer(ctx.author, now)
    exp = await get_user_exp(user_id)
    level = get_level_from_exp(exp)
    leveldata = LEVELS[level]
    rows = await db.get_attendance(user_id)
    attendance_list = "\n".join(f"✅ {row[0]}" for row in rows[:20]) if rows else "아직 출석 기록이 없습니다."
    if len(rows) > 20: attendance_list += "\n… (이하 생략)"
    streak_att = await db.get_streak_attendance(user_id)
    streak_wup = await db.get_streak_wakeup(user_id)
    streak_std = await db.get_streak_study(user_id)
    embed = discord.Embed(title=f"{ctx.author.display_name}님의 기록 정보", color=ctx.author.color)
    embed.add_field(name="🔥 연속 기록", value=(f"연속 출석: {streak_att}일\n연속 기상: {streak_wup}일\n연속 공부: {streak_std}일"), inline=False)
    embed.add_field(name="🗓️ 출석 날짜 (최근 20개)", value=attendance_list, inline=False)
    embed.set_footer(text=footer["text"], icon_url=footer["icon_url"])
    await ctx.send(embed=embed)

@bot.command(name="명령어")
async def command_list(ctx):
    now = datetime.now(timezone('Asia/Seoul'))
    footer = get_embed_footer(ctx.author, now)
    embed = discord.Embed(title="👑 공듀봇 명령어 모음", description="각 채널에서 명령어를 입력해보세요!\n아래 채널명 클릭 시 바로 이동됩니다.", color=ctx.author.color)
    embed.add_field(name=f"🍀 출석 (`!출석`)", value=f"매일 <#{ATTENDANCE_CHANNEL_ID}> 채널에서 출석하고 경험치를 얻으세요.", inline=False)
    embed.add_field(name=f"🌅 기상 (`!기상`)", value=f"<#{WAKEUP_CHANNEL_ID}> 채널에서 기상 인증 사진을 올려주세요.", inline=False)
    embed.add_field(name="📊 통계 (`!통계`)", value="나의 월간/주간/전체 통계를 한 번에 확인합니다.", inline=False)
    embed.add_field(name="📜 기록 (`!기록`)", value="나의 출석 날짜 및 연속 기록을 확인합니다.", inline=False)
    embed.add_field(name=f"🏠 내정보 (`!내정보`)", value=f"<#{MYINFO_CHANNEL_ID}> 채널에서 나의 레벨, 경험치, 통계를 확인하고 업데이트합니다.", inline=False)
    embed.add_field(name="🎥 캠스터디 자동 기록", value=f"음성 채널 <#{TRACKED_VOICE_CHANNELS[0]}> 등에 입장 시 공부시간이 자동 기록됩니다.", inline=False)
    embed.set_footer(text=footer["text"], icon_url=footer["icon_url"])
    await ctx.send(embed=embed)

@bot.command(name="내정보")
async def my_info(ctx):
    await create_or_update_user_info(ctx.author)
    await ctx.send(f"{ctx.author.mention}님의 내정보를 <#{MYINFO_CHANNEL_ID}> 채널에 생성 또는 업데이트했어요!", ephemeral=True)

# --- Slash Commands ---
@bot.tree.command(name="경험치추가", description="지정한 유저에게 원하는 양의 경험치를 지급합니다.")
@app_commands.describe(user="경험치를 받을 사용자", amount="지급할 경험치 양(정수)")
@app_commands.default_permissions(administrator=True)
async def slash_add_exp(interaction: discord.Interaction, user: discord.Member, amount: int):
    if amount <= 0: return await interaction.response.send_message("❌ 올바른 양을 입력해주세요 (양수).", ephemeral=True)
    await add_exp_and_check_level(user, amount)
    await interaction.response.send_message(f"✅ {user.mention}님에게 {amount} Exp를 추가했습니다.", ephemeral=True)

@bot.tree.command(name="경험치제거", description="지정한 유저의 경험치를 원하는 만큼 제거합니다.")
@app_commands.describe(user="대상 유저", amount="제거할 Exp 양(정수, 0 이상)")
@app_commands.default_permissions(administrator=True)
async def slash_remove_exp(interaction: discord.Interaction, user: discord.Member, amount: int):
    if amount < 0: return await interaction.response.send_message("❌ 0 이상의 값을 입력해주세요.", ephemeral=True)
    current = await db.get_exp(str(user.id))
    removed = min(amount, current)
    await db.remove_exp(str(user.id), removed)
    new_total = await db.get_exp(str(user.id))
    await create_or_update_user_info(user)
    await interaction.response.send_message(f"✅ {user.mention}님에게서 **{removed} Exp**를 제거했습니다. (총 Exp: **{new_total}**)", ephemeral=True)

@bot.tree.command(name="역할경험치추가", description="지정한 역할을 가진 모든 유저에게 원하는 양의 경험치를 지급합니다.")
@app_commands.describe(role="대상 역할", amount="지급할 경험치 양(정수)")
@app_commands.default_permissions(administrator=True)
async def slash_role_add_exp(interaction: discord.Interaction, role: discord.Role, amount: int):
    if amount <= 0: return await interaction.response.send_message("❌ 올바른 양을 입력해주세요 (양수).", ephemeral=True)
    members = [m for m in role.members if not m.bot]
    if not members: return await interaction.response.send_message("❌ 해당 역할을 가진 사용자가 없습니다.", ephemeral=True)
    await interaction.response.defer(ephemeral=True)
    for m in members:
        await add_exp_and_check_level(m, amount)
    await interaction.followup.send(f"✅ 역할 `{role.name}`을(를) 가진 {len(members)}명에게 각각 {amount} Exp를 지급했습니다.")

@bot.tree.command(name="추첨", description="온라인 상태인 유저 중 한 명을 추첨해 경험치를 지급합니다.")
@app_commands.describe(amount="추첨하여 지급할 경험치 양(정수)")
@app_commands.default_permissions(administrator=True)
async def slash_raffle(interaction: discord.Interaction, amount: int):
    if amount <= 0: return await interaction.response.send_message("❌ 올바른 양을 입력해주세요 (양수).", ephemeral=True)
    members = [m for m in interaction.guild.members if not m.bot and m.status != discord.Status.offline]
    if not members: return await interaction.response.send_message("❌ 추첨할 사용자 후보가 없습니다.", ephemeral=True)
    winner = random.choice(members)
    await add_exp_and_check_level(winner, amount)
    await interaction.response.send_message(f"🎉 축하합니다! {winner.mention} 님이 **{amount} Exp**에 당첨되셨습니다!", ephemeral=False)

@bot.tree.command(name="경험치설정", description="지정한 유저의 경험치를 정확히 설정합니다.")
@app_commands.describe(user="대상 유저", amount="설정할 Exp 값(정수, 0 이상)")
@app_commands.default_permissions(administrator=True)
async def slash_set_exp(interaction: discord.Interaction, user: discord.Member, amount: int):
    if amount < 0: return await interaction.response.send_message("❌ 0 이상의 값을 입력해주세요.", ephemeral=True)
    await db.set_exp(str(user.id), user.display_name, amount)
    await create_or_update_user_info(user)
    await interaction.response.send_message(f"✅ {user.mention}님의 Exp를 **{amount}**으로 설정했습니다.", ephemeral=True)

@bot.tree.command(name="공부추가", description="관리자가 지정한 유저의 오늘 공부 시간을 수동으로 추가합니다.")
@app_commands.describe(user="공부 시간을 추가할 사용자", minutes="추가할 공부 시간 (분 단위, 양수)")
@app_commands.default_permissions(administrator=True)
async def slash_add_study(interaction: discord.Interaction, user: discord.Member, minutes: int):
    if minutes <= 0: return await interaction.response.send_message("❌ 1분 이상의 양수를 입력해주세요.", ephemeral=True)
    await db.log_study_time(str(user.id), user.display_name, minutes)
    await add_exp_and_check_level(user, minutes)
    total_today = await db.get_today_study_time(str(user.id))
    await interaction.response.send_message(f"✅ {user.mention}님의 오늘 공부 시간으로 **{minutes}분**을 추가했습니다.\n⏳ 오늘 누적 공부 시간: **{total_today}분**\n🌹 **{minutes} Exp**를 획득했어요!", ephemeral=True)

if TOKEN:
    bot.run(TOKEN)
else:
    logger.critical("DISCORD_TOKEN 환경변수가 설정되지 않았습니다.")
