"""Репостер каналов.

  python main.py add @channel      — запомнить канал-источник (и подписаться на него)
  python main.py list              — показать запомненные каналы
  python main.py remove @channel   — забыть канал
  python main.py run               — запустить репост в TARGET_CHANNEL
"""
import argparse
import asyncio
import logging

from telethon import TelegramClient, utils
from telethon.tl.functions.channels import JoinChannelRequest

import settings
from core import Reposter, TelegramSender
from storage import ChannelStore


def parse_ref(ref: str):
    ref = ref.strip()
    return int(ref) if ref.lstrip("-").isdigit() else ref


async def resolve(client, ref):
    ent = await client.get_entity(parse_ref(ref))
    return utils.get_peer_id(ent), ent


async def cmd_add(client, store, ref):
    chat_id, ent = await resolve(client, ref)
    if not getattr(ent, "broadcast", False):
        print("Это не канал (broadcast). Нужен именно канал.")
        return
    try:  # чтобы получать обновления, аккаунт должен быть подписан
        await client(JoinChannelRequest(ent))
    except Exception as e:
        print(f"(не удалось подписаться автоматически: {e})")
    added = store.add(chat_id, ent.title, getattr(ent, "username", None))
    print(("Добавлен: " if added else "Уже в списке: ") + f"{ent.title} ({chat_id})")


async def cmd_remove(client, store, ref):
    chat_id, ent = await resolve(client, ref)
    print("Удалён" if store.remove(chat_id) else "Такого канала нет в списке")


async def cmd_run(client, store):
    if not settings.TARGET:
        raise SystemExit("Укажите TARGET_CHANNEL в .env")
    target = await client.get_entity(parse_ref(settings.TARGET))
    Reposter(store, TelegramSender(client, target), settings.OPTS).register(client)
    names = ", ".join(c["title"] for c in store.channels) or "— пока пусто, добавьте: main.py add @channel"
    print(f"Работаю. Источники: {names}\nЦель: {getattr(target, 'title', target)}\nCtrl+C — выход")
    await client.run_until_disconnected()


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("command", choices=["add", "list", "remove", "run"])
    ap.add_argument("channel", nargs="?", help="@username, ссылка t.me/... или id")
    args = ap.parse_args()

    store = ChannelStore()
    if args.command == "list":
        for c in store.channels:
            print(f"{c['id']}\t{c['title']}\t@{c['username'] or '-'}")
        if not store.channels:
            print("Список пуст")
        return
    if args.command in ("add", "remove") and not args.channel:
        ap.error("укажите канал")

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s", datefmt="%H:%M:%S")
    logging.getLogger("telethon").setLevel(logging.WARNING)

    async def runner():
        async with TelegramClient(settings.SESSION, settings.API_ID, settings.API_HASH) as client:
            # при первом запуске Telethon спросит телефон и код в терминале
            if args.command == "add":
                await cmd_add(client, store, args.channel)
            elif args.command == "remove":
                await cmd_remove(client, store, args.channel)
            else:
                await cmd_run(client, store)

    try:
        asyncio.run(runner())
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
