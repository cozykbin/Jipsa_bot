import discord
from discord.ext import commands, tasks
from discord.ui import View, Button
from discord import app_commands
from datetime import datetime, timedelta
from pytz import timezone
from db import (
    save_attendance, get_attendance, add_exp, remove_exp, get_exp, set_exp,
    save_wakeup, log_study_time, get_today_study_time,
    get_top_users_by_exp, get_monthly_stats, get_weekly_stats,
    get_streak_attendance, get_streak_wakeup, get_streak_study,
    cursor  # DB 커서를 직접 사용
)
import random
import os
import aiohttp
import asyncio
import logging

TOKEN = os.getenv("DISCORD_TOKEN")
GSHEET_WEBHOOK = os.getenv("GSHEET_WEBHOOK")

intents = discord.Intents.default()
intents.message_content = True
intents.voice_states = True
intents.messages = True
intents.members = True
bot = commands.Bot(command_prefix="!", intents=intents)

logger = logging.getLogger(__name__)

async def append_to_sheet(session: aiohttp.ClientSession, sheet_name: str, data: list) -> bool:
    if not GSHEET_WEBHOOK:
        logger.error("Google Sheet Webhook URL이 설정되어 있지 않습니다.")
        return False

    payload = {
        "sheet": sheet_name,
        "data": data
    }

    try:
        async with session.post(GSHEET_WEBHOOK, json=payload, timeout=5) as resp:
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

    if now.date() == datetime.now(kst).date():
        label = "오늘"
    elif now.date() == (datetime.now(kst).date() - timedelta(days=1)):
        label = "어제"
    else:
        label = now.strftime("%y/%m/%d")

    time_label = now.strftime("%H:%M")
    display_name = user.display_name
    avatar_url = user.display_avatar.url if hasattr(user, "display_avatar") else user.avatar.url

    return {
        "text": f"{display_name} | {label}, {time_label}",
        "icon_url": avatar_url
    }

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

def get_level_from_exp(exp):
    for i in range(1, len(LEVEL_THRESHOLDS)):
        if exp < LEVEL_THRESHOLDS[i]:
            return i
    return 10

def get_user_exp(user_id):
    return get_exp(str(user_id))

TRACKED_VOICE_CHANNELS = ["🎥｜캠스터디", "📖｜1인실 (A)", "📖｜1인실 (B)", "📓｜도서관
", "🌆｜워크스페이스"]
study_sessions = {}

RANKING_CHANNEL_ID = 1378863730741219458   # 👑｜랭킹
HONOR_CHANNEL_ID = 1378863861863682102     # 🏆｜명예기록
MYINFO_CHANNEL_ID = 1378952514702938182    # 🏠｜내정보
ATTENDANCE_CHANNEL_ID = 1378862713484218489  # 🍀｜출석체크
WAKEUP_CHANNEL_ID = 1378862771214745690       # 🌅｜기상인증

ranking_message_id = None
wakeup_pending = {}
user_info_channel_msgs = {}

async def send_levelup_embed(member, new_level):
    honor_channel = bot.get_channel(HONOR_CHANNEL_ID)
    if honor_channel is None:
        return
    data = LEVELS[new_level]
    embed = discord.Embed(
        title=f"{data['emoji']} 레벨업! {data['name']} 달성",
        description=(
            f"{member.mention} 공듀님, {data['name']}에 도달했어요!\n\n"
            f"{data['desc']}"
        ),
        color=discord.Color.purple()
    )
    footer = get_embed_footer(member, datetime.now(timezone('Asia/Seoul')))
    embed.set_footer(text=footer["text"], icon_url=footer["icon_url"])
    await honor_channel.send(embed=embed)

async def create_or_update_user_info(member):
    user_id = str(member.id)
    exp = get_user_exp(user_id)
    level = get_level_from_exp(exp)
    leveldata = LEVELS[level]

    if level < len(LEVEL_THRESHOLDS) - 1:
        next_exp = LEVEL_THRESHOLDS[level]
    else:
        next_exp = exp + 100
    exp_required = next_exp - exp

    if level == 1:
        current_exp = exp
        progress_total = LEVEL_THRESHOLDS[1]
    elif level < len(LEVEL_THRESHOLDS) - 1:
        current_exp = exp - LEVEL_THRESHOLDS[level - 1]
        progress_total = LEVEL_THRESHOLDS[level] - LEVEL_THRESHOLDS[level - 1]
    else:
        current_exp = exp - LEVEL_THRESHOLDS[-2]
        progress_total = 100

    progress_bar_length = 20
    filled_length = int(progress_bar_length * current_exp / progress_total) if progress_total else 0
    bar = "■" * filled_length + "□" * (progress_bar_length - filled_length)

    now = datetime.now(timezone('Asia/Seoul'))
    embed = discord.Embed(
        title=f"{member.display_name}님의 내정보",
        description=(
            f"{member.mention} 공듀님의 최신 정보예요.\n"
            f"변동이 있을 때마다 자동으로 업데이트됩니다! 😊"
        ),
        color=member.color
    )
    embed.add_field(
        name="👑 레벨",
        value=f"{leveldata['emoji']} Lv.{level} {leveldata['name']}",
        inline=False
    )
    embed.add_field(
        name="📊 총 경험치",
        value=f"{exp} Exp (다음 레벨까지 {exp_required} Exp 남음)",
        inline=False
    )
    embed.add_field(
        name="📈 진행도",
        value=f"`{bar}`",
        inline=False
    )

    stats_month = get_monthly_stats(user_id)
    embed.add_field(
        name="📅 이번달 통계",
        value=(
            f"출석: {stats_month['attendance']}일\n"
            f"기상: {stats_month['wakeup']}일\n"
            f"공부일수: {stats_month['study_days']}일\n"
            f"공부시간: {stats_month['study_minutes']}분"
        ),
        inline=False
    )

    stats_week = get_weekly_stats(user_id)
    embed.add_field(
        name="📆 이번주 통계",
        value=(
            f"출석: {stats_week['attendance']}일\n"
            f"기상: {stats_week['wakeup']}일\n"
            f"공부일수: {stats_week['study_days']}일\n"
            f"공부시간: {stats_week['study_minutes']}분"
        ),
        inline=False
    )

    footer = get_embed_footer(member, now)
    embed.set_footer(text=footer["text"], icon_url=footer["icon_url"])

    channel = bot.get_channel(MYINFO_CHANNEL_ID)
    if channel is None:
        return

    if user_id in user_info_channel_msgs:
        try:
            msg_id = user_info_channel_msgs[user_id]
            existing = await channel.fetch_message(msg_id)
            await existing.edit(embed=embed)
            return
        except Exception:
            pass

    new_msg = await channel.send(embed=embed)
    user_info_channel_msgs[user_id] = new_msg.id

async def add_exp_and_check_level(member, exp_gained):
    user_id = str(member.id)
    exp_before = get_user_exp(user_id)
    old_level = get_level_from_exp(exp_before)

    add_exp(user_id, member.display_name, exp_gained)
    exp_after = exp_before + exp_gained
    new_level = get_level_from_exp(exp_after)

    if new_level > old_level:
        await send_levelup_embed(member, new_level)

    async with aiohttp.ClientSession() as session:
        await append_to_sheet(session, "users", [
            user_id,
            member.display_name,
            exp_after,
            new_level
        ])

    await create_or_update_user_info(member)
    return new_level, exp_after

def make_ranking_embed():
    now = datetime.now(timezone('Asia/Seoul'))
    today_str = now.strftime("%Y년 %m월 %d일")
    ranking = get_top_users_by_exp()
    embed = discord.Embed(
        title="🏆 경험치 랭킹 TOP 10",
        color=discord.Color.gold()
    )
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
    embed.set_footer(text=today_str)
    return embed

@tasks.loop(minutes=1)
async def update_ranking():
    global ranking_message_id
    channel = bot.get_channel(RANKING_CHANNEL_ID)
    if channel is None:
        return

    if ranking_message_id is None:
        await setup_ranking_message()
        return

    try:
        msg = await channel.fetch_message(ranking_message_id)
    except discord.NotFound:
        ranking_message_id = None
        await setup_ranking_message()
        return
    except discord.Forbidden:
        return
    except Exception:
        return

    embed = make_ranking_embed()
    await msg.edit(embed=embed)

@bot.event
async def on_ready():
    await bot.tree.sync()
    await setup_ranking_message()
    update_ranking.start()
    print(f"✅ {bot.user} 로그인 완료")

async def setup_ranking_message():
    global ranking_message_id
    channel = bot.get_channel(RANKING_CHANNEL_ID)
    if channel is None:
        return

    async for msg in channel.history(limit=20):
        if (
            msg.author == bot.user
            and msg.embeds
            and msg.embeds[0].title
            and "경험치 랭킹" in msg.embeds[0].title
        ):
            ranking_message_id = msg.id
            break
    else:
        embed = make_ranking_embed()
        msg = await channel.send(embed=embed)
        await msg.pin()
        ranking_message_id = msg.id

@bot.command(name="출석")
async def checkin(ctx):
    now = datetime.now(timezone('Asia/Seoul'))
    nickname = ctx.author.display_name
    embed_color = ctx.author.color
    
    saved_db = save_attendance(str(ctx.author.id), nickname)
    
    async with aiohttp.ClientSession() as session:
        saved_sheet = await append_to_sheet(
            session,
            "attendance",
            [str(ctx.author.id), now.strftime("%Y-%m-%d"), nickname]
        )

    # 출석 데이터에서 연속출석, 총 출석 횟수 조회
    attendance_rows = get_attendance(str(ctx.author.id))
    streak = get_streak_attendance(str(ctx.author.id))
    total = len(attendance_rows) if attendance_rows else 0

    embed = discord.Embed(color=embed_color)
    if not saved_db:
        embed.title = "👑 출석 실패"
        embed.description = f"{ctx.author.mention} 공듀님, 오늘은 이미 출석하셨어요! 🐣"
    else:
        exp_gained = 50
        level, exp_after = await add_exp_and_check_level(ctx.author, exp_gained)
        leveldata = LEVELS[level]
        embed.title = "✅ 출석체크 완료!"
        embed.description = (
            f"출석체크 보상으로 **{exp_gained} EXP**를 획득하였습니다.\n\n"
            f"❤️‍🔥 **현재 연속 출석**\n**{streak}일**\n\n"
            f"📅 **총 출석 횟수**\n**{total}회**"
        )
        embed.add_field(
            name="🎁 현재 레벨",
            value=f"{leveldata['emoji']} Lv.{level} {leveldata['name']}",
            inline=False
        )

    footer = get_embed_footer(ctx.author, now)
    embed.set_footer(text=footer["text"], icon_url=footer["icon_url"])
    await ctx.send(embed=embed, view=AttendanceRankingView())

@bot.event
async def on_interaction(interaction: discord.Interaction):
    custom_id = interaction.data.get("custom_id")
    guild = interaction.guild

    if custom_id == "streak_rank":
        cursor.execute("SELECT DISTINCT user_id FROM attendance")
        users = [row[0] for row in cursor.fetchall()]

        streaks = []
        for uid in users:
            s = get_streak_attendance(uid)
            streaks.append((uid, s))
        streaks.sort(key=lambda x: x[1], reverse=True)
        top = streaks[:10]

        description = ""
        for i, (uid, s) in enumerate(top, start=1):
            member_obj = guild.get_member(int(uid)) if guild else None
            if member_obj:
                name = member_obj.display_name
            else:
                try:
                    user_obj = await bot.fetch_user(int(uid))
                    name = user_obj.name
                except:
                    name = "알 수 없는 유저"
            description += f"{i}위 🔥 **{name}** — {s}일\n"

        embed = discord.Embed(
            title="🔥 연속 출석 랭킹 TOP 10",
            description=description if description else "출석 기록이 없습니다.",
            color=discord.Color.orange()
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)

    elif custom_id == "total_rank":
        cursor.execute(
            "SELECT user_id, COUNT(*) as cnt FROM attendance GROUP BY user_id ORDER BY cnt DESC LIMIT 10"
        )
        rows = cursor.fetchall()

        description = ""
        for i, (uid, cnt) in enumerate(rows, start=1):
            member_obj = guild.get_member(int(uid)) if guild else None
            if member_obj:
                name = member_obj.display_name
            else:
                try:
                    user_obj = await bot.fetch_user(int(uid))
                    name = user_obj.name
                except:
                    name = "알 수 없는 유저"
            description += f"{i}위 📅 **{name}** — {cnt}회\n"

        embed = discord.Embed(
            title="📅 누적 출석 랭킹 TOP 10",
            description=description if description else "출석 기록이 없습니다.",
            color=discord.Color.green()
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)

@bot.command(name="기상")
async def wakeup(ctx):
    now = datetime.now(timezone('Asia/Seoul'))
    nickname = ctx.author.display_name
    embed_color = ctx.author.color
    user_id = str(ctx.author.id)
    today = now.strftime("%Y-%m-%d")

    already_db = save_wakeup(user_id, nickname) 

    async with aiohttp.ClientSession() as session:
        already = await append_to_sheet(session, "wakeup", [user_id, today, nickname])

    footer = get_embed_footer(ctx.author, now)

    if not already_db:
        embed = discord.Embed(
            title="☀️ 기상 실패",
            description=f"{ctx.author.mention} 공듀님, 오늘은 이미 기상 인증했어요! ☀️",
            color=embed_color
        )
        embed.set_footer(text=footer["text"], icon_url=footer["icon_url"])
        await ctx.send(embed=embed)
        return

    embed = discord.Embed(
        title="📷 기상 인증 요청",
        description=(
            f"{ctx.author.mention} 공듀님, 기상 인증 사진을 올려주세요!\n"
            "카메라로 아침 인증샷(책상, 시계 등) 첨부 필수 📸"
        ),
        color=embed_color
    )
    embed.set_footer(text=footer["text"], icon_url=footer["icon_url"])
    msg = await ctx.send(embed=embed)
    wakeup_pending[str(ctx.author.id)] = msg.id

@bot.event
async def on_message(message):
    if message.author.bot:
        return
    await bot.process_commands(message)

    user_id = str(message.author.id)
    if user_id in wakeup_pending and message.attachments:
        msg_id = wakeup_pending[user_id]
        channel = message.channel

        try:
            req_msg = await channel.fetch_message(msg_id)
        except Exception:
            wakeup_pending.pop(user_id, None)
            return

        now = datetime.now(timezone('Asia/Seoul'))
        footer = get_embed_footer(message.author, now)
        hour = now.hour
        exp_gained = 200 if hour < 9 else 100
        level, exp_after = await add_exp_and_check_level(message.author, exp_gained)
        leveldata = LEVELS[level]
        photo_url = message.attachments[0].url

        try:
            await message.delete()
        except discord.Forbidden:
            pass
        except Exception:
            pass

        embed = discord.Embed(
            title=f"{leveldata['emoji']} 기상 인증 완료!",
            description=(
                f"{message.author.mention} 공듀님, 기상 인증 완료! 오늘 하루 멋지게 시작해요 🌞 (+{exp_gained} Exp)"
            ),
            color=message.author.color
        )
        embed.set_image(url=photo_url)
        embed.add_field(
            name="🎁 현재 레벨",
            value=f"{leveldata['emoji']} Lv.{level} {leveldata['name']}"
        )
        embed.set_footer(text=footer["text"], icon_url=footer["icon_url"])

        await req_msg.edit(embed=embed)
        wakeup_pending.pop(user_id, None)

@bot.event
async def on_voice_state_update(member, before, after):
    now = datetime.now(timezone('Asia/Seoul'))
    footer = get_embed_footer(member, now)
    before_channel = before.channel.name if before.channel else None
    after_channel = after.channel.name if after.channel else None

    study_channel = discord.utils.get(member.guild.text_channels, name="📕｜공부기록")
    if study_channel is None:
        return

    if after.channel and after_channel in TRACKED_VOICE_CHANNELS and (not before.channel or before_channel != after_channel):
        embed = discord.Embed(
            title="🎀 공듀 스터디룸 입장 🎀",
            description=(
                f"{member.mention} 공듀님이 도서관에 나타났어요!\n"
                f"오늘도 집중모드 발동✨\n공부 시작 시간: {now.strftime('%H:%M:%S')}"
            ),
            color=member.color
        )
        embed.set_footer(text=footer["text"], icon_url=footer["icon_url"])
        msg = await study_channel.send(embed=embed)
        study_sessions[str(member.id)] = {
            'start': now,
            'msg_id': msg.id
        }

    if before.channel and before_channel in TRACKED_VOICE_CHANNELS and (not after.channel or after_channel not in TRACKED_VOICE_CHANNELS):
        session = study_sessions.pop(str(member.id), None)
        if session:
            end_time = datetime.now(timezone('Asia/Seoul'))
            footer_end = get_embed_footer(member, end_time)
            duration = (end_time - session['start']).total_seconds() / 60
            try:
                msg = await study_channel.fetch_message(session['msg_id'])
            except Exception:
                msg = None

            if duration < 10:
                embed = discord.Embed(
                    title="⏰ 집중 실패! (10분 미만)",
                    description=(f"{member.mention} 공듀님, 10분 미만은 집중 인정 불가에요!\n다시 도전해볼까요?"),
                    color=member.color
                )
                embed.set_footer(text=footer_end["text"], icon_url=footer_end["icon_url"])
                if msg:
                    await msg.edit(embed=embed)
                else:
                    await study_channel.send(embed=embed)
                return

            log_study_time(str(member.id), int(duration))
            exp = int(duration)

            async with aiohttp.ClientSession() as session_http:
                await append_to_sheet(session_http, "study", [
                    str(member.id),
                    member.display_name,
                    end_time.strftime("%Y-%m-%d"),
                    int(duration)
                ])

            level, exp_after = await add_exp_and_check_level(member, exp)
            leveldata = LEVELS[level]
            today_total = get_today_study_time(str(member.id))

            h = int(duration) // 60
            m = int(duration) % 60
            time_str = f"{h}시간 {m}분" if h else f"{m}분"

            embed = discord.Embed(
                title=f"{leveldata['emoji']} 집중 완료! 공듀 퇴장 ✨",
                description=(f"{member.mention} 공듀님 오늘도 대단해요!\n공부박스 도착🎁"),
                color=member.color
            )
            embed.add_field(name="⏳ 공부한 시간", value=f"**{time_str}**⏳", inline=False)
            embed.add_field(name="🌹 획득 Exp", value=f"**{exp} Exp**", inline=True)
            embed.add_field(name="👑 오늘 누적", value=f"**{today_total}분**", inline=True)
            embed.add_field(
                name="🏅 현재 레벨",
                value=f"{leveldata['emoji']} Lv.{level} {leveldata['name']}",
                inline=True
            )
            embed.set_footer(text=footer_end["text"], icon_url=footer_end["icon_url"])

            if msg:
                await msg.edit(embed=embed)
            else:
                await study_channel.send(embed=embed)

@bot.command(name="통계")
async def show_stats(ctx):
    user_id = str(ctx.author.id)
    now = datetime.now(timezone('Asia/Seoul'))
    footer = get_embed_footer(ctx.author, now)

    exp = get_user_exp(user_id)
    level = get_level_from_exp(exp)
    leveldata = LEVELS[level]
    embed_color = ctx.author.color

    stats_month = get_monthly_stats(user_id)
    stats_week = get_weekly_stats(user_id)

    total_attendance = len(get_attendance(user_id))
    total_wakeup = 0
    total_study_days = 0
    total_study_minutes = 0
    try:
        cursor.execute("SELECT COUNT(*) FROM wakeup WHERE user_id = ?", (user_id,))
        total_wakeup = cursor.fetchone()[0]
        cursor.execute("SELECT COUNT(DISTINCT date) FROM study WHERE user_id = ? AND minutes >= 10", (user_id,))
        total_study_days = cursor.fetchone()[0]
        cursor.execute("SELECT COALESCE(SUM(minutes), 0) FROM study WHERE user_id = ?", (user_id,))
        total_study_minutes = cursor.fetchone()[0]
    except:
        pass

    embed = discord.Embed(
        title=f"{leveldata['emoji']} 통계 정보",
        color=embed_color
    )
    embed.add_field(
        name="👑 레벨·경험치",
        value=f"{leveldata['emoji']} Lv.{level} ({exp} Exp)",
        inline=False
    )
    embed.add_field(
        name="📅 이번달 통계",
        value=(
            f"출석: {stats_month['attendance']}일\n"
            f"기상: {stats_month['wakeup']}일\n"
            f"공부일수: {stats_month['study_days']}일\n"
            f"공부시간: {stats_month['study_minutes']}분"
        ),
        inline=False
    )
    embed.add_field(
        name="📆 이번주 통계",
        value=(
            f"출석: {stats_week['attendance']}일\n"
            f"기상: {stats_week['wakeup']}일\n"
            f"공부일수: {stats_week['study_days']}일\n"
            f"공부시간: {stats_week['study_minutes']}분"
        ),
        inline=False
    )
    embed.add_field(
        name="🔢 전체 통계",
        value=(
            f"총 출석: {total_attendance}회\n"
            f"총 기상: {total_wakeup}회\n"
            f"총 공부일수: {total_study_days}일\n"
            f"총 공부시간: {total_study_minutes}분"
        ),
        inline=False
    )
    embed.set_footer(text=footer["text"], icon_url=footer["icon_url"])
    await ctx.send(embed=embed)

@bot.command(name="기록")
async def show_records(ctx):
    user_id = str(ctx.author.id)
    now = datetime.now(timezone('Asia/Seoul'))
    footer = get_embed_footer(ctx.author, now)

    exp = get_user_exp(user_id)
    level = get_level_from_exp(exp)
    leveldata = LEVELS[level]
    embed_color = ctx.author.color

    rows = get_attendance(user_id)
    if rows:
        dates = [row[0] for row in rows]
        attendance_list = "\n".join(f"✅ {d}" for d in dates[:20])
        if len(dates) > 20:
            attendance_list += "\n…"
    else:
        attendance_list = "아직 출석 기록이 없습니다."

    streak_att = get_streak_attendance(user_id)
    streak_wup = get_streak_wakeup(user_id)
    streak_std = get_streak_study(user_id)

    embed = discord.Embed(
        title=f"{leveldata['emoji']} 기록 정보",
        color=embed_color
    )
    embed.add_field(
        name="🗓️ 출석 날짜 (최대 최근 20개)",
        value=attendance_list,
        inline=False
    )
    embed.add_field(
        name="🔥 연속 기록",
        value=(
            f"연속 출석: {streak_att}일\n"
            f"연속 기상: {streak_wup}일\n"
            f"연속 공부: {streak_std}일"
        ),
        inline=False
    )
    embed.set_footer(text=footer["text"], icon_url=footer["icon_url"])
    await ctx.send(embed=embed)

@bot.command(name="명령어")
async def command_list(ctx):
    now = datetime.now(timezone('Asia/Seoul'))
    footer = get_embed_footer(ctx.author, now)

    exp = get_user_exp(str(ctx.author.id))
    level = get_level_from_exp(exp)
    leveldata = LEVELS[level]
    embed_color = ctx.author.color

    embed = discord.Embed(
        title=f"{leveldata['emoji']} 사용 가능한 명령어 모음",
        description="각 채널에서 명령어를 입력해보세요!\n아래 채널명 클릭 시 바로 이동됩니다.",
        color=embed_color
    )
    embed.add_field(
        name="👑 랭킹",
        value=f"<#{RANKING_CHANNEL_ID}> 에서 자동 갱신됨",
        inline=False
    )
    embed.add_field(
        name="🍀 출석",
        value=f"<#{ATTENDANCE_CHANNEL_ID}> 에서 사용\n!출석 - 오늘 출석 체크",
        inline=False
    )
    embed.add_field(
        name="🌅 기상",
        value=f"<#{WAKEUP_CHANNEL_ID}> 에서 사용\n!기상 - 오늘 기상 인증(사진 첨부 필수)",
        inline=False
    )
    embed.add_field(
        name="📊 통계",
        value="!통계 - 월간/주간/전체 통계를 한 번에 확인",
        inline=False
    )
    embed.add_field(
        name="📜 기록",
        value="!기록 - 출석 날짜 및 연속 기록 확인",
        inline=False
    )
    embed.add_field(
        name="🏠 내정보",
        value=f"<#{MYINFO_CHANNEL_ID}> 에서 사용자별 내정보를 자동으로 업데이트",
        inline=False
    )
    embed.add_field(
        name="🎥 캠스터디 자동 기록",
        value="- 🎥｜캠스터디 입퇴장 시 공부시간 자동 기록",
        inline=False
    )
    embed.set_footer(text=footer["text"], icon_url=footer["icon_url"])
    await ctx.send(embed=embed)

@bot.command(name="내정보")
async def my_info(ctx):
    await create_or_update_user_info(ctx.author)
    await ctx.send(f"{ctx.author.mention}님의 내정보를 <#{MYINFO_CHANNEL_ID}> 채널에 업데이트했어요!")

@bot.tree.command(name="경험치추가", description="지정한 유저에게 원하는 양의 경험치를 지급합니다.")
@app_commands.describe(user="경험치를 받을 사용자", amount="지급할 경험치 양(정수)")
async def slash_add_exp(interaction: discord.Interaction, user: discord.Member, amount: int):
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("❌ 관리자 권한이 필요합니다.", ephemeral=True)
        return
    if amount <= 0:
        await interaction.response.send_message("❌ 올바른 양을 입력해주세요 (양수).", ephemeral=True)
        return

    add_exp(str(user.id), user.display_name, amount)
    await create_or_update_user_info(user)
    await interaction.response.send_message(f"✅ {user.mention}님에게 {amount} Exp를 추가했습니다.", ephemeral=True)

@bot.tree.command(name="경험치제거", description="지정한 유저의 경험치를 원하는 만큼 제거합니다.")
@app_commands.describe(user="대상 유저", amount="제거할 Exp 양(정수, 0 이상)")
async def slash_remove_exp(interaction: discord.Interaction, user: discord.Member, amount: int):
    if not interaction.user.guild_permissions.administrator:
        return await interaction.response.send_message("❌ 관리자 권한이 필요합니다.", ephemeral=True)
    if amount < 0:
        return await interaction.response.send_message("❌ 0 이상의 값을 입력해주세요.", ephemeral=True)

    current = get_exp(str(user.id))
    removed = min(amount, current)
    remove_exp(str(user.id), removed)

    new_total = get_exp(str(user.id))
    await create_or_update_user_info(user)
    await interaction.response.send_message(
        f"✅ {user.mention}님에게서 **{removed} Exp**를 제거했습니다. (총 Exp: **{new_total}**)",
        ephemeral=True
    )

@bot.tree.command(name="역할경험치추가", description="지정한 역할을 가진 모든 유저에게 원하는 양의 경험치를 지급합니다.")
@app_commands.describe(role="대상 역할", amount="지급할 경험치 양(정수)")
async def slash_role_add_exp(interaction: discord.Interaction, role: discord.Role, amount: int):
    if not interaction.user.guild_permissions.administrator:
        return await interaction.response.send_message("❌ 관리자 권한이 필요합니다.", ephemeral=True)
    if amount <= 0:
        return await interaction.response.send_message("❌ 올바른 양을 입력해주세요 (양수).", ephemeral=True)

    members = [m for m in interaction.guild.members if role in m.roles and not m.bot]
    if not members:
        return await interaction.response.send_message("❌ 해당 역할을 가진 사용자가 없습니다.", ephemeral=True)

    for m in members:
        add_exp(str(m.id), m.display_name, amount)
        await create_or_update_user_info(m)

    await interaction.response.send_message(
        f"✅ 역할 `{role.name}`을(를) 가진 {len(members)}명에게 각각 {amount} Exp를 지급했습니다.",
        ephemeral=True
    )

@bot.tree.command(name="추첨", description="원하는 양의 경험치에 대한 추첨 이벤트를 진행합니다.")
@app_commands.describe(amount="추첨하여 지급할 경험치 양(정수)")
async def slash_raffle(interaction: discord.Interaction, amount: int):
    if not interaction.user.guild_permissions.administrator:
        return await interaction.response.send_message("❌ 관리자 권한이 필요합니다.", ephemeral=True)
    if amount <= 0:
        return await interaction.response.send_message("❌ 올바른 양을 입력해주세요 (양수).", ephemeral=True)

    members = [m for m in interaction.guild.members if not m.bot and m.status != discord.Status.offline]
    if not members:
        return await interaction.response.send_message("❌ 추첨할 사용자 후보가 없습니다.", ephemeral=True)

    winner = random.choice(members)
    add_exp(str(winner.id), winner.display_name, amount)
    await create_or_update_user_info(winner)

    await interaction.response.send_message(
        f"🎉 축하합니다! {winner.mention} 님이 {amount} Exp를 당첨되셨습니다!",
        ephemeral=False
    )

@bot.tree.command(name="경험치설정", description="지정한 유저의 경험치를 정확히 설정합니다.")
@app_commands.describe(user="대상 유저", amount="설정할 Exp 값(정수, 0 이상)")
async def slash_set_exp(interaction: discord.Interaction, user: discord.Member, amount: int):
    if not interaction.user.guild_permissions.administrator:
        return await interaction.response.send_message("❌ 관리자 권한이 필요합니다.", ephemeral=True)
    if amount < 0:
        return await interaction.response.send_message("❌ 0 이상의 값을 입력해주세요.", ephemeral=True)

    set_exp(str(user.id), amount)
    await create_or_update_user_info(user)
    await interaction.response.send_message(
        f"✅ {user.mention}님의 Exp를 **{amount}**으로 설정했습니다.",
        ephemeral=True
    )

@bot.tree.command(
    name="공부추가",
    description="관리자가 지정한 유저의 오늘 공부 시간을 수동으로 추가합니다."
)
@app_commands.describe(
    user="공부 시간을 추가할 사용자",
    minutes="추가할 공부 시간 (분 단위, 양수)"
)
async def slash_add_study(
    interaction: discord.Interaction,
    user: discord.Member,
    minutes: int
):
    # 1) 관리자 권한 검사
    if not interaction.user.guild_permissions.administrator:
        return await interaction.response.send_message(
            "❌ 관리자 권한이 필요합니다.",
            ephemeral=True
        )
    # 2) 파라미터 검증
    if minutes <= 0:
        return await interaction.response.send_message(
            "❌ 1분 이상의 양수를 입력해주세요.",
            ephemeral=True
        )

    # 3) DB에 공부시간 기록
    #    -- db.py 에 정의된 log_study_time 함수는 '오늘(Asia/Seoul)' 기준으로 누적해 줍니다.
    log_study_time(str(user.id), minutes)

    # 4) 경험치(=분 단위) 추가 및 레벨업 처리
    #    -- add_exp_and_check_level 은 내부적으로 add_exp 호출 후
    #       레벨업 알림, 내정보 업데이트까지 알아서 해 줍니다.
    level, exp_after = await add_exp_and_check_level(user, minutes)

    # 5) 오늘 총 공부시간 조회
    total_today = get_today_study_time(str(user.id))

    # 6) 피드백 전송
    await interaction.response.send_message(
        f"✅ {user.mention}님의 오늘 공부 시간으로 **{minutes}분**을 추가했습니다.\n"
        f"⏳ 오늘 누적 공부 시간: **{total_today}분**\n"
        f"🌹 **{minutes} Exp**를 획득했어요!",
        ephemeral=True
    )

bot.run(TOKEN)
