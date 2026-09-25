"""Klient i vogel per serverin cTrader Trading MCP (https://mcp.ctrader.com/trading/mcp).

Perdor vetem librarine standarde te Python-it. Rilidhet automatikisht kur
serveri e humb sesionin (404 / "No valid session").
"""
import json
import logging
import time
import urllib.error
import urllib.request

log = logging.getLogger("mcp")

PRICE_SCALE = 100_000  # cmimet nga get_trendbars / get_spot_prices jane ne 1/100000


class McpError(Exception):
    def __init__(self, msg, rejected=False):
        super().__init__(msg)
        self.rejected = rejected  # True = serveri e pa dhe e refuzoi kerkesen


class McpClient:
    def __init__(self, url: str, bearer: str, timeout: int = 30):
        self.url = url
        self.bearer = bearer
        self.timeout = timeout
        self.session_id = None
        self._next_id = 1

    # ------------------------------------------------------------ transport
    def _post(self, body: dict):
        headers = {
            "Authorization": "Bearer " + self.bearer,
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
        }
        if self.session_id:
            headers["Mcp-Session-Id"] = self.session_id
        req = urllib.request.Request(self.url, json.dumps(body).encode(), headers)
        with urllib.request.urlopen(req, timeout=self.timeout) as resp:
            sid = resp.headers.get("mcp-session-id")
            if sid:
                self.session_id = sid
            text = resp.read().decode()
        for line in text.splitlines():
            if line.startswith("data: "):
                return json.loads(line[6:])
        return json.loads(text) if text.strip() else None

    def connect(self):
        self.session_id = None
        self._post({
            "jsonrpc": "2.0", "id": 0, "method": "initialize",
            "params": {
                "protocolVersion": "2025-06-18",
                "capabilities": {},
                "clientInfo": {"name": "gold-sniper", "version": "1.0"},
            },
        })
        self._post({"jsonrpc": "2.0", "method": "notifications/initialized"})
        log.info("U lidh me cTrader MCP (sesioni %s)", (self.session_id or "?")[:8])

    # ------------------------------------------------------------ tools
    def call(self, name: str, args: dict | None = None, retries: int = 3):
        """Therret nje tool dhe kthen JSON-in e rezultatit.

        Per veprimet qe ndryshojne llogarine (create_order etj.) perdor retries=1
        qe te mos dergohet i njejti urdher dy here.
        """
        last_err = None
        for attempt in range(retries):
            try:
                if not self.session_id:
                    self.connect()
                self._next_id += 1
                msg = self._post({
                    "jsonrpc": "2.0", "id": self._next_id, "method": "tools/call",
                    "params": {"name": name, "arguments": args or {}},
                })
                if msg is None:
                    raise McpError("pergjigje bosh")
                if "error" in msg:
                    raise McpError(f"{name}: {msg['error']}")
                result = msg["result"]
                text = "".join(c.get("text", "") for c in result.get("content", []))
                if result.get("isError"):
                    raise McpError(f"{name}: {text}", rejected=True)
                try:
                    return json.loads(text)
                except json.JSONDecodeError:
                    return {"text": text}
            except urllib.error.HTTPError as e:
                last_err = e
                # sesioni ka skaduar -> rilidhu
                if e.code in (400, 404):
                    self.session_id = None
                log.warning("%s: HTTP %s (prova %d/%d)", name, e.code, attempt + 1, retries)
            except (urllib.error.URLError, TimeoutError, ConnectionError) as e:
                last_err = e
                self.session_id = None
                log.warning("%s: rrjeti deshtoi: %s (prova %d/%d)", name, e, attempt + 1, retries)
            if attempt + 1 < retries:
                time.sleep(2 * (attempt + 1))
        raise McpError(f"{name} deshtoi: {last_err}")
