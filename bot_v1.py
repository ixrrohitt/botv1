import os
import re
import asyncio
import logging
import time
from telethon import TelegramClient, events
from telethon.sessions import StringSession
from telethon.errors import (
    SessionPasswordNeededError, PhoneCodeInvalidError, PhoneCodeExpiredError,
    PasswordHashInvalidError, PhoneNumberInvalidError, ApiIdInvalidError,
    FloodWaitError,
)

logging.getLogger("telethon").setLevel(logging.CRITICAL)

BOT_API_ID = int(os.environ["API_ID"])
BOT_API_HASH = os.environ["API_HASH"]
BOT_TOKEN = os.environ["BOT_TOKEN"]

TIMEOUT = 600
bot = TelegramClient(StringSession(), BOT_API_ID, BOT_API_HASH)
states = {}  # sirf RAM me


async def cleanup(uid):
    st = states.pop(uid, None)
    if st and st.get("client"):
        try:
            await st["client"].disconnect()
        except Exception:
            pass


async def expire(uid, started):
    await asyncio.sleep(TIMEOUT)
    st = states.get(uid)
    if st and st["t"] == started:
        await cleanup(uid)
        await bot.send_message(uid, "⏰ Time out. /gen se dobara shuru karo.")


async def wipe_msg(event):
    try:
        await event.delete()
    except Exception:
        pass


@bot.on(events.NewMessage(incoming=True, func=lambda e: e.is_private))
async def handler(event):
    uid = event.sender_id
    text = (event.raw_text or "").strip()

    if text.startswith("/start"):
        return await event.reply("👋 Session Generator\n\n/gen - naya session\n/cancel - band karo")

    if text.startswith("/cancel"):
        await cleanup(uid)
        return await event.reply("❌ Cancel ho gaya, memory clear.")

    if text.startswith("/gen"):
        await cleanup(uid)
        t = time.time()
        states[uid] = {"step": "api_id", "t": t, "client": None}
        asyncio.create_task(expire(uid, t))
        return await event.reply("1️⃣ Apna *api_id* bhejo:")

    st = states.get(uid)
    if not st:
        return

    step = st["step"]
    try:
        if step == "api_id":
            if not text.isdigit():
                return await event.reply("Sirf number. Dobara bhejo:")
            st["api_id"] = int(text)
            st["step"] = "api_hash"
            await event.reply("2️⃣ Ab *api_hash* bhejo:")

        elif step == "api_hash":
            await wipe_msg(event)
            if not re.fullmatch(r"[0-9a-fA-F]{32}", text):
                return await bot.send_message(uid, "api_hash 32-char hota hai. Dobara bhejo:")
            st["api_hash"] = text
            st["step"] = "phone"
            await bot.send_message(uid, "3️⃣ Phone (+91XXXXXXXXXX):")

        elif step == "phone":
            await wipe_msg(event)
            phone = text.replace(" ", "")
            client = TelegramClient(StringSession(), st["api_id"], st["api_hash"])
            await client.connect()
            st["client"] = client
            sent = await client.send_code_request(phone)
            st.update(phone=phone, hash=sent.phone_code_hash, step="code")
            await bot.send_message(
                uid,
                "4️⃣ Code aaya hoga. **Spaces ke saath bhejo**, jaise `1 2 3 4 5`.",
            )

        elif step == "code":
            await wipe_msg(event)
            code = re.sub(r"\D", "", text)
            try:
                await st["client"].sign_in(st["phone"], code, phone_code_hash=st["hash"])
            except SessionPasswordNeededError:
                st["step"] = "password"
                return await bot.send_message(uid, "5️⃣ 2-Step password bhejo:")
            await finish(uid)

        elif step == "password":
            await wipe_msg(event)
            await st["client"].sign_in(password=text)
            await finish(uid)

    except ApiIdInvalidError:
        await cleanup(uid)
        await bot.send_message(uid, "❌ api_id/api_hash galat. /gen dobara.")
    except PhoneNumberInvalidError:
        await cleanup(uid)
        await bot.send_message(uid, "❌ Number galat. /gen dobara.")
    except PhoneCodeInvalidError:
        await bot.send_message(uid, "❌ Code galat. Dobara bhejo (spaces ke saath):")
    except PhoneCodeExpiredError:
        await cleanup(uid)
        await bot.send_message(uid, "❌ Code expire. /gen dobara.")
    except PasswordHashInvalidError:
        await bot.send_message(uid, "❌ Password galat. Dobara bhejo:")
    except FloodWaitError as e:
        await cleanup(uid)
        await bot.send_message(uid, f"⏳ {e.seconds}s baad try karo.")
    except Exception:
        await cleanup(uid)
        await bot.send_message(uid, "❌ Kuch galat hua. /gen se dobara try karo.")


async def finish(uid):
    st = states[uid]
    session = st["client"].session.save()
    await bot.send_message(
        uid,
        "✅ *Tumhari StringSession:*\n\n"
        f"`{session}`\n\n"
        "⚠️ Copy karte hi ye message delete kar dena.",
    )
    await cleanup(uid)


async def main():
    await bot.start(bot_token=BOT_TOKEN)
    print("Bot chalu hai...")
    await bot.run_until_disconnected()


if __name__ == "__main__":
    asyncio.run(main())
