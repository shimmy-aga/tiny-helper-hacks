import time
from typing import Set, Iterable
import requests

# Notifications
from plyer import notification

# RCON
from mcrcon import MCRcon

# Query / status
from mcstatus import JavaServer

# ------------- CONFIG -------------
HOST = "203.16.163.153"   # domain or IP (no scheme)
PORT = 28736                # your server's *game* port (very important!)
POLL_SECONDS = 5

# Add the exact usernames (IGNs) you care about. Case-insensitive matching.
FRIENDS: Set[str] = {"BosnianRocket", "Friend1", "Friend2"}

# If you enabled RCON (recommended)
USE_RCON = False
RCON_HOST = HOST
RCON_PORT = 25575           # match server.properties rcon.port
RCON_PASSWORD = "your_rcon_password"

# If you enabled Query (optional but helpful)
USE_QUERY = True

# Public status API fallback (no config needed)
STATUS_API_URL = f"https://api.mcsrvstat.us/3/{HOST}:{PORT}"
HTTP_TIMEOUT = 8
# ----------------------------------

def norm_set(names: Iterable[str]) -> Set[str]:
    return {n.strip().lower() for n in names if isinstance(n, str) and n.strip()}

def notify_local(msg: str):
    try:
        notification.notify(title="Minecraft Watcher", message=msg, timeout=5)
    except Exception as e:
        print(f"[notify] desktop notification failed: {e}")

def players_via_rcon() -> Set[str]:
    try:
        with MCRcon(RCON_HOST, RCON_PASSWORD, port=RCON_PORT) as r:
            resp = r.command("list") or ""
        # Typical formats:
        # "There are 1 of a max of 20 players online: Alice"
        # "There are 0 of a max of 20 players online"
        if ":" in resp:
            names_part = resp.split(":", 1)[1]
            names = [n.strip() for n in names_part.split(",") if n.strip()]
            return norm_set(names)
        return set()
    except Exception as e:
        print(f"[rcon] {e}")
        return set()

def players_via_query() -> Set[str]:
    try:
        server = JavaServer(HOST, PORT)
        q = server.query()  # requires enable-query=true
        return norm_set(q.players.names or [])
    except Exception as e:
        print(f"[query] {e}")
        return set()

def players_via_status_api() -> Set[str]:
    try:
        r = requests.get(STATUS_API_URL, timeout=HTTP_TIMEOUT)
        data = r.json()
        players = data.get("players", {})
        names = players.get("list") or []
        return norm_set(names)
    except Exception as e:
        print(f"[api] {e}")
        return set()

def get_online_players() -> Set[str]:
    # Try strongest -> weakest
    if USE_RCON:
        names = players_via_rcon()
        if names:
            return names
    if USE_QUERY:
        names = players_via_query()
        if names:
            return names
    return players_via_status_api()

def main():
    watch_names = norm_set(FRIENDS)
    print(f"Watching {HOST}:{PORT} … every {POLL_SECONDS}s. Ctrl+C to stop.")
    last_seen: Set[str] = set()

    while True:
        current = get_online_players()

        # If you want to see raw list each tick:
        print(f"[now online] {', '.join(sorted(current)) if current else '(none)'}")

        joined = current - last_seen
        left = last_seen - current

        if watch_names:
            joined = {p for p in joined if p in watch_names}
            left = {p for p in left if p in watch_names}

        for p in sorted(joined):
            msg = f"{p} just joined {HOST}:{PORT}"
            print("🟢", msg)
            notify_local(msg)

        # If you also want leave alerts, uncomment:
        # for p in sorted(left):
        #     msg = f"{p} left {HOST}:{PORT}"
        #     print("🔴", msg)
        #     notify_local(msg)

        last_seen = current
        time.sleep(POLL_SECONDS)

if __name__ == "__main__":
    main()
