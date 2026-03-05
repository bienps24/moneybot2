"""
Telegram Bot — Auto Send Videos on Join Request
=================================================
Flow:
  User nag-request na sumali → Bot DM promo → Bot agad nagse-send ng videos + buttons

Railway env vars:
  BOT_TOKEN, ADMIN_ID, CHANNEL_ID, CHANNEL_LINK,
  PAYMENT_LINK, VIDEO_1_ID, VIDEO_2_ID, EXTRA_VIDEO_IDS
"""
import asyncio
import logging
import os
from urllib.parse import quote

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    ChatJoinRequestHandler,
    MessageHandler,
    filters,
    ContextTypes,
)

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

# ── ENV VARS ──────────────────────────────────────────────────────────────────
BOT_TOKEN       = os.environ["BOT_TOKEN"]
ADMIN_ID         = int(os.environ.get("ADMIN_ID", "0"))
CHANNEL_ID      = int(os.environ["CHANNEL_ID"])
CHANNEL_LINK     = os.environ.get("CHANNEL_LINK", "https://t.me/+YLDFGnamQXRjODll")
PAYMENT_LINK    = os.environ.get("PAYMENT_LINK", "https://t.me/your_payment_bot")
VIDEO_1_ID      = os.environ.get("VIDEO_1_ID", "")
VIDEO_2_ID      = os.environ.get("VIDEO_2_ID", "")
EXTRA_VIDEO_IDS = os.environ.get("EXTRA_VIDEO_IDS", "").split(",")

VIDEO_DELETE_DELAY = 20    # 20 seconds
CHAT_DELETE_DELAY  = 1200  # 20 minutes

# ── STATE ─────────────────────────────────────────────────────────────────────
user_states: dict[int, dict] = {}

def get_state(uid: int) -> dict:
    if uid not in user_states:
        user_states[uid] = {"messages": [], "more_shares": 0}
    return user_states[uid]

def share_url() -> str:
    return f"https://t.me/share/url?url={quote(CHANNEL_LINK)}&text={quote('join our exclusive group')}"

# ── HELPERS ───────────────────────────────────────────────────────────────────
async def schedule_delete(bot, chat_id: int, message_ids: list, delay: int):
    await asyncio.sleep(delay)
    for mid in message_ids:
        try:
            await bot.delete_message(chat_id=chat_id, message_id=mid)
        except Exception:
            pass

# ── SEND VIDEOS + BUTTONS ─────────────────────────────────────────────────────
async def send_content(bot, chat_id: int, uid: int, state: dict):
    video_msgs = []

    for label, vid_id in [("VIDEO_1_ID", VIDEO_1_ID), ("VIDEO_2_ID", VIDEO_2_ID)]:
        if not vid_id:
            logger.warning(f"{label} is empty")
            await bot.send_message(chat_id=ADMIN_ID, text=f"⚠️ {label} not set in Railway Variables!")
            continue
        try:
            msg = await bot.send_video(
                chat_id=chat_id,
                video=vid_id,
                protect_content=True,
                supports_streaming=True,
            )
            video_msgs.append(msg.message_id)
            state["messages"].append(msg.message_id)
            logger.info(f"✅ Sent {label} to {chat_id}")
        except Exception as e:
            err = f"Video send error {label}: {e}"
            logger.error(err)
            await bot.send_message(chat_id=ADMIN_ID, text=f"❌ {err}")

    # Description text + buttons — sent SEPARATELY from videos
    info_msg = await bot.send_message(
        chat_id=chat_id,
        text=(
            "🚫 *CHANNEL IS PRIVATE*\n\n"
            "🍌💦 *SHARE = CONTENT*\n\n"
            "0 / 2 JOIN\n\n"
            "(SHARE) CHANNEL — 55,568 VIDEOS\n\n"
            "SHARE TO 2 GROUPS TO UNLOCK more free videos\n\n"
            "Verification is automatic ❤️"
        ),
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("📤  SHARE FOR MORE", url=share_url())],
            [InlineKeyboardButton("💳  PAY FOR ACCESS — ₱999", url=PAYMENT_LINK)],
        ])
    )
    state["messages"].append(info_msg.message_id)

    # 🗑 Videos delete after 1 minute
    asyncio.create_task(schedule_delete(bot, chat_id, video_msgs, VIDEO_DELETE_DELAY))
    # 🗑 Full chat wipe after 20 minutes
    asyncio.create_task(schedule_delete(bot, chat_id, list(state["messages"]), CHAT_DELETE_DELAY))


# ── JOIN REQUEST HANDLER ──────────────────────────────────────────────────────
async def handle_join_request(update: Update, context: ContextTypes.DEFAULT_TYPE):
    join_req = update.chat_join_request
    user     = join_req.from_user

    if join_req.chat.id != CHANNEL_ID:
        return

    logger.info(f"Join request: {user.id} ({user.full_name})")

    state = get_state(user.id)
    state["messages"]    = []
    state["more_shares"] = 0

    # Send videos + buttons directly to user
    await send_content(context.bot, user.id, user.id, state)





# ── AUTO REPLY "SHARE!" TO ANY USER MESSAGE ───────────────────────────────────
async def auto_reply_share(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or update.effective_user.id == ADMIN_ID:
        return
    # Only reply to users who came through channel join request
    if update.effective_user.id not in user_states:
        return
    state = get_state(update.effective_user.id)
    msg = await update.message.reply_text("SHARE!")
    state["messages"].append(update.message.message_id)
    state["messages"].append(msg.message_id)


# ── /testvideo (admin only) ───────────────────────────────────────────────────
async def test_video(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    await update.message.reply_text("🧪 Testing videos...")
    for label, vid_id in [("VIDEO_1_ID", VIDEO_1_ID), ("VIDEO_2_ID", VIDEO_2_ID)]:
        if not vid_id:
            await update.message.reply_text(f"❌ {label} is EMPTY in Railway Variables!")
            continue
        try:
            await context.bot.send_video(
                chat_id=update.effective_chat.id,
                video=vid_id,
                protect_content=True,
                supports_streaming=True,
            )
            await update.message.reply_text(f"✅ {label} — OK!")
        except Exception as e:
            await update.message.reply_text(f"❌ {label} FAILED:\n{e}")


# ── MAIN ──────────────────────────────────────────────────────────────────────
def main():
    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("testvideo", test_video))
    app.add_handler(ChatJoinRequestHandler(handle_join_request))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, auto_reply_share))

    logger.info("Bot running.")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
