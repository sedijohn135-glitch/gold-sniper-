"""Njoftime ne Telegram dhe komanda /status (vetem lexim, pa tregtim nga Telegram-i).

Mesazhet dergohen ne nje thread me vete, qe nje problem me Telegram-in
te mos e ndaloje kurre tregtimin.
"""
import json
import logging
import queue
import threading
import time
import urllib.error
import urllib.request

log = logging.getLogger("telegram")
API = "https://api.telegram.org/bot{token}/{method}"


class Telegram:
    def __init__(self, token: str, chat_id: str):
        self.token = (token or "").strip()
        self.chat_id = str(chat_id or "").strip()
        self.enabled = bool(self.token and self.chat_id)
        self._queue = queue.Queue()
        self._commands = {}
        if self.enabled:
            threading.Thread(target=self._sender, daemon=True).start()
            log.info("Telegram aktiv (chat %s)", self.chat_id)
        else:
            log.info("Telegram joaktiv: vendos TELEGRAM_TOKEN dhe TELEGRAM_CHAT_ID")

    # ------------------------------------------------------------ dergimi
    def send(self, text: str):
        if self.enabled:
            self._queue.put(text[:4000])

    def _call(self, method, payload, timeout=20):
        req = urllib.request.Request(
            API.format(token=self.token, method=method),
            json.dumps(payload).encode(), {"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode())

    def _sender(self):
        while True:
            text = self._queue.get()
            for attempt in range(3):
                try:
                    self._call("sendMessage", {"chat_id": self.chat_id, "text": text,
                                               "disable_web_page_preview": True})
                    break
                except urllib.error.HTTPError as e:
                    body = e.read().decode()[:200]
                    log.warning("Telegram HTTP %s: %s", e.code, body)
                    if e.code in (400, 401, 403, 404):
                        break  # token/chat i gabuar: s'ka kuptim te riprovohet
                    time.sleep(3 * (attempt + 1))
                except Exception as e:
                    log.warning("Telegram: %s", e)
                    time.sleep(3 * (attempt + 1))

    # ------------------------------------------------------------ komandat
    def on_command(self, name: str, handler):
        """handler() kthen tekstin e pergjigjes."""
        self._commands[name] = handler

    def start_commands(self):
        if self.enabled and self._commands:
            threading.Thread(target=self._poll, daemon=True).start()

    def _poll(self):
        offset = None
        conflicts = 0
        while True:
            try:
                args = {"timeout": 50, "allowed_updates": ["message"]}
                if offset is not None:
                    args["offset"] = offset
                res = self._call("getUpdates", args, timeout=60)
                for upd in res.get("result", []):
                    offset = upd["update_id"] + 1
                    msg = upd.get("message") or {}
                    # vetem nga chat-i yt; te tjeret injorohen
                    if str(msg.get("chat", {}).get("id")) != self.chat_id:
                        continue
                    cmd = (msg.get("text") or "").strip().split()[0].split("@")[0].lower() if msg.get("text") else ""
                    handler = self._commands.get(cmd)
                    if handler:
                        try:
                            self.send(handler())
                        except Exception as e:
                            self.send(f"Gabim ne {cmd}: {e}")
                conflicts = 0
            except urllib.error.HTTPError as e:
                if e.code != 409:
                    log.warning("Telegram getUpdates: %s", e)
                    time.sleep(10)
                    continue
                # 409: nje program tjeter lexon mesazhet e ketij boti (deployment i dyte, webhook,
                # ose nje aplikacion tjeter me te njejtin token). Njoftimet dergohen gjithsesi.
                conflicts += 1
                if conflicts in (1, 20):
                    body = e.read().decode(errors="replace")[:200]
                    log.warning("Telegram 409: %s. Nje program tjeter po perdor kete token per komandat; "
                                "njoftimet vazhdojne, /status mund te mos pergjigjet. Provohet me rralle.", body)
                time.sleep(min(300, 15 * conflicts))
            except Exception as e:
                log.warning("Telegram getUpdates: %s", e)
                time.sleep(10)
