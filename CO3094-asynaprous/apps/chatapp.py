"""
apps/chatapp.py — Hybrid Chat Application (Phase 1 + Phase 2)
==============================================================

DM channel naming (fix duplicate + privacy):
  Mỗi user có 2 bucket riêng:
    "dm:alice"  — tin Alice gửi đi (sent) + tin Alice nhận về (received)
  Client chỉ poll /get-dm với username của mình
  → Tom KHÔNG thấy DM của Alice↔Bob
  → Không bị duplicate vì sent và received lưu vào bucket khác nhau
"""

import json
import socket
import threading
import secrets
import time
from concurrent.futures import ThreadPoolExecutor
import multiprocessing
import asyncio
from daemon.asynaprous import AsynapRous
from daemon import backend
# Import trực tiếp HttpAdapter và các biến môi trường
from daemon.httpadapter import ACTIVE_SESSIONS, VALID_USERS, HttpAdapter

app = AsynapRous()

# =========================
# STATE
# =========================
_peers        = {}
_peers_lock   = threading.Lock()

_channels     = {"general": [], "random": []}
_channels_lock = threading.Lock()

_user_channels = {}
_user_lock    = threading.Lock()

_executor = ThreadPoolExecutor(max_workers=30)

MAX_MSG = 200
MAX_LEN = 4096

CORS_HEADERS = {
    "Access-Control-Allow-Origin":  "*",
    "Access-Control-Allow-Methods": "GET, POST, PUT, DELETE, OPTIONS",
    "Access-Control-Allow-Headers": "Content-Type, Authorization, Cookie",
    "Access-Control-Allow-Credentials": "true",
}

# =========================
# LOGGER
# =========================
_C = {
    "reset":  "\033[0m",
    "bold":   "\033[1m",
    "cyan":   "\033[96m",
    "green":  "\033[92m",
    "yellow": "\033[93m",
    "red":    "\033[91m",
    "magenta":"\033[95m",
    "blue":   "\033[94m",
    "gray":   "\033[90m",
}

def _log(tag, color, msg):
    ts = time.strftime("%H:%M:%S")
    print("{gray}[{ts}]{reset} {color}{bold}[{tag:12s}]{reset} {msg}".format(
        gray=_C["gray"], ts=ts, reset=_C["reset"],
        color=_C[color], bold=_C["bold"], tag=tag, msg=msg))

def log_auth(msg):   _log("AUTH",      "cyan",    msg)
def log_peer(msg):   _log("PEER",      "green",   msg)
def log_chan(msg):   _log("CHANNEL",   "yellow",  msg)
def log_bcast(msg):  _log("BROADCAST", "blue",    msg)
def log_dm(msg):     _log("DM",        "magenta", msg)
def log_recv(msg):   _log("RECEIVE",   "green",   msg)
def log_p2p(msg):    _log("P2P-SEND",  "yellow",  msg)
def log_err(msg):    _log("ERROR",     "red",     msg)
def log_api(msg):    _log("API",       "gray",    msg)

def cors(status, body, extra_headers=None):
    h = dict(CORS_HEADERS)
    if extra_headers:
        h.update(extra_headers)
    return status, body, h

def _dm_key(username):
    return "dm:{}".format(username)

# =========================
# P2P CORE SEND (Thuần Socket Đồng Bộ)
# =========================
def _send_p2p(ip, port, payload: dict, retry=2):
    raw = json.dumps(payload).encode()
    req = (
        "POST /receive-message HTTP/1.1\r\n"
        "Host: {}:{}\r\n"
        "Content-Type: application/json\r\n"
        "Content-Length: {}\r\n"
        "Connection: close\r\n\r\n"
    ).format(ip, port, len(raw)).encode() + raw

    for attempt in range(retry):
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.settimeout(3)
                s.connect((ip, int(port)))
                s.sendall(req)
            log_p2p("→ {}:{} type={} ✓".format(ip, port, payload.get("type","?")))
            return True
        except Exception as e:
            log_err("_send_p2p {}:{} attempt={} — {}".format(ip, port, attempt+1, e))
            time.sleep(0.2)
    return False

# =========================
# OPTIONS preflight
# =========================
@app.route("/login",          methods=["OPTIONS"])
@app.route("/submit-info",    methods=["OPTIONS"])
@app.route("/get-list",       methods=["OPTIONS"])
@app.route("/send-peer",      methods=["OPTIONS"])
@app.route("/broadcast-peer", methods=["OPTIONS"])
@app.route("/get-messages",   methods=["OPTIONS"])
@app.route("/receive-message",methods=["OPTIONS"])
@app.route("/get-channels",   methods=["OPTIONS"])
@app.route("/join-channel",   methods=["OPTIONS"])
@app.route("/connect-peer",   methods=["OPTIONS"])
@app.route("/add-list",       methods=["OPTIONS"])
@app.route("/logout",         methods=["OPTIONS"])
@app.route("/get-dm",         methods=["OPTIONS"])
def options_handler(headers="", body=""):
    return cors(200, b"")

# =========================
# LOGIN
# =========================
# @app.route("/login", methods=["POST"])
# def login(headers="", body=""):
#     data = json.loads(body or "{}")
#     username = data.get("username", "").strip()
#     password = data.get("password", "")

#     if not username or VALID_USERS.get(username) != password:
#         log_err("LOGIN failed — invalid credentials for '{}'".format(username))
#         return cors(401, b'{"error":"Sai username hoac password"}')

#     token = secrets.token_hex(16)
#     ACTIVE_SESSIONS[token] = username

#     with _user_lock:
#         _user_channels.setdefault(username, set())
#         _user_channels[username].add("general")

#     log_auth("LOGIN  user='{}' session={}...".format(username, token[:8]))
#     return cors(200,
#         json.dumps({"message": "ok", "username": username}).encode(),
#         {"session": token})
# ###
@app.route("/login", methods=["POST"])
def login(headers="", body=""):
    data = json.loads(body or "{}")
    username = data.get("username", "").strip()
    password = data.get("password", "")

    if not username or VALID_USERS.get(username) != password:
        log_err("LOGIN failed — invalid credentials for '{}'".format(username))
        return cors(401, b'{"error":"Sai username hoac password"}')

    token = secrets.token_hex(16)
    ACTIVE_SESSIONS[token] = username

    with _user_lock:
        _user_channels.setdefault(username, set()).add("general")

    log_auth("LOGIN  user='{}' session={}...".format(username, token[:8]))
    # THÊM "token": token vào JSON trả về
    return cors(200,
        json.dumps({"message": "ok", "username": username, "token": token}).encode(),
        {"session": token})

@app.route("/sync-auth", methods=["POST", "OPTIONS"])
def sync_auth(headers="", body=""):
    if not body: return cors(200, b"") # Xử lý OPTIONS
    data = json.loads(body or "{}")
    user = data.get("username")
    token = data.get("token")
    
    # Local Node nhận token từ Tracker và tự lưu vào bộ nhớ của mình
    ACTIVE_SESSIONS[token] = user
    with _user_lock:
        _user_channels.setdefault(user, set()).add("general")
    log_auth("SYNC-AUTH user='{}' nhận lệnh từ Tracker!".format(user))
    
    return cors(200, b'{"ok":true}', {"session": token})
###
# =========================
# SUBMIT INFO
# =========================
@app.route("/submit-info", methods=["POST"])
def submit_info(headers="", body=""):
    data = json.loads(body or "{}")
    user = data.get("username")
    ip   = data.get("ip")
    try:
        port = int(data.get("port"))
    except Exception:
        return cors(400, b'{"error":"invalid port"}')

    with _peers_lock:
        _peers[user] = {"username": user, "ip": ip, "port": port,
                        "online": True, "last_seen": time.time()}
    with _user_lock:
        _user_channels.setdefault(user, set())
        _user_channels[user].add("general")

    log_peer("REGISTER user='{}' addr={}:{}".format(user, ip, port))
    return cors(200, b'{"ok":true}')

# =========================
# GET LIST
# =========================
@app.route("/get-list", methods=["GET"])
def get_list(headers="", body=""):
    with _peers_lock:
        peers = [{"username": u, "ip": v["ip"], "port": v["port"]}
                 for u, v in _peers.items() if v["ip"] and v["online"]]
    log_peer("GET-LIST → {} peers: {}".format(
        len(peers), [p["username"] for p in peers]))
    return cors(200, json.dumps({"peers": peers}).encode())

# =========================
# ADD LIST
# =========================
@app.route("/add-list", methods=["POST"])
def add_list(headers="", body=""):
    data = json.loads(body or "{}")
    ch = data.get("channel", "general")
    with _channels_lock:
        if ch not in _channels:
            _channels[ch] = []
    with _user_lock:
        for u in _peers.keys():
            _user_channels.setdefault(u, set()).add(ch)
    return cors(200, json.dumps({"channel": ch}).encode())

# =========================
# CONNECT PEER
# =========================
@app.route("/connect-peer", methods=["POST"])
def connect_peer(headers="", body=""):
    data = json.loads(body or "{}")
    target = data.get("to")
    with _peers_lock:
        p = _peers.get(target)
    if not p:
        return cors(404, b'{"error":"peer not found"}')
    return cors(200, json.dumps(
        {"peer": {"username": target, "ip": p["ip"], "port": p["port"]}}
    ).encode())

# =========================
# SEND DIRECT P2P
# =========================
@app.route("/send-peer", methods=["POST"])
def send_peer(headers="", body=""):
    data   = json.loads(body or "{}")
    sender = data.get("from")
    target = data.get("to")
    msg    = data.get("message", "")[:MAX_LEN]
    ts     = time.strftime("%H:%M:%S")

    with _peers_lock:
        p = _peers.get(target)
    if not p:
        return cors(404, b'{"error":"peer not found"}')

    sent_key = _dm_key(sender)
    with _channels_lock:
        _channels.setdefault(sent_key, [])
        _channels[sent_key].append({
            "from": sender, "to": target,
            "message": msg, "time": ts,
            "direction": "sent",
        })
        _channels[sent_key] = _channels[sent_key][-MAX_MSG:]

    payload = {"type": "direct", "from": sender, "to": target,
               "message": msg, "time": ts}
    ok = _send_p2p(p["ip"], p["port"], payload)
    print("[DM] {} -> {} ok={}".format(sender, target, ok))

    return cors(200, json.dumps({"sent": ok}).encode())

# =========================
# BROADCAST
# =========================
@app.route("/broadcast-peer", methods=["POST"])
def broadcast_peer(headers="", body=""):
    data    = json.loads(body or "{}")
    sender  = data.get("from")
    msg     = data.get("message", "")
    channel = data.get("channel", "general")
    ts      = time.strftime("%H:%M:%S")

    with _channels_lock:
        _channels.setdefault(channel, [])
        _channels[channel].append(
            {"from": sender, "message": msg, "time": ts, "channel": channel})
        _channels[channel] = _channels[channel][-MAX_MSG:]

    with _peers_lock:
        peers = [v for u, v in _peers.items() if u != sender and v["online"]]

    payload = {"type": "broadcast", "from": sender,
               "message": msg, "channel": channel, "time": ts}

    def job():
        for p in peers:
            uname = p.get("username")
            if not p.get("ip") or not p.get("port"):
                continue
            with _user_lock:
                user_chs = _user_channels.get(uname, set()).copy()
            if channel in user_chs:
                _send_p2p(p["ip"], p["port"], payload)

    _executor.submit(job)
    print("[BROADCAST] {} -> {}".format(sender, channel))
    return cors(200, json.dumps({"status": "ok"}).encode())

# =========================
# RECEIVE MESSAGE (Đã Fix lỗi lưu nhầm hòm thư)
# =========================
@app.route("/receive-message", methods=["POST"])
def receive_message(headers="", body=""):
    try:
        data = json.loads(body or "{}")
    except Exception:
        return cors(400, b'{"error":"invalid json"}')

    msg_type = data.get("type", "broadcast")

    if msg_type == "direct":
        sender = data.get("from")
        target = data.get("to")
        
        # FIX 1: Tôn trọng cái direction do trình duyệt gửi lên (nếu không có thì mới là received)
        direction = data.get("direction", "received")
        
        # FIX 2: Phân loại hòm thư. Gửi đi thì cất tủ người gửi, Nhận về thì cất tủ người nhận.
        inbox_owner = sender if direction == "sent" else target
        inbox_key = _dm_key(inbox_owner)
        
        with _channels_lock:
            _channels.setdefault(inbox_key, [])
            _channels[inbox_key].append({
                "from": sender, "to": target,
                "message": data.get("message"),
                "time": data.get("time", time.strftime("%H:%M:%S")),
                "direction": direction,
            })
        print("[DM-LOG] {} -> {} (dir: {})".format(sender, target, direction))
    else:
        print("[BCAST-RECV] from={} ch={}".format(
            data.get("from"), data.get("channel")))

    return cors(200, b'{"ok":true}')

# =========================
# GET DM
# =========================
@app.route("/get-dm", methods=["POST", "GET"])
def get_dm(headers="", body=""):
    try:
        data = json.loads(body) if body and body.strip() else {}
    except Exception:
        data = {}
    username = data.get("username", "")
    key = _dm_key(username)
    with _channels_lock:
        msgs = list(_channels.get(key, []))
    return cors(200, json.dumps(
        {"username": username, "messages": msgs[-MAX_MSG:]}
    ).encode())

# =========================
# JOIN CHANNEL
# =========================
@app.route("/join-channel", methods=["POST"])
def join_channel(headers="", body=""):
    data    = json.loads(body or "{}")
    user    = data.get("username")
    channel = data.get("channel", "general")
    with _user_lock:
        _user_channels.setdefault(user, set())
        _user_channels[user].add(channel)
    with _channels_lock:
        _channels.setdefault(channel, [])
    print("[JOIN] {} -> {}".format(user, channel))
    return cors(200, json.dumps({"joined": channel}).encode())

# =========================
# GET MESSAGES
# =========================
@app.route("/get-messages", methods=["GET", "POST"])
def get_messages(headers="", body=""):
    try:
        data = json.loads(body) if body and body.strip() else {}
    except Exception:
        data = {}
    channel = data.get("channel", "general")
    with _channels_lock:
        msgs = list(_channels.get(channel, []))
    return cors(200, json.dumps(
        {"channel": channel, "messages": msgs[-MAX_MSG:]}
    ).encode())

# =========================
# GET CHANNELS
# =========================
@app.route("/get-channels", methods=["GET"])
def get_channels(headers="", body=""):
    with _channels_lock:
        channels = [ch for ch in _channels.keys() if not ch.startswith("dm:")]
    return cors(200, json.dumps({"channels": channels or ["general"]}).encode())

# =========================
# LIST CHANNELS
# =========================
@app.route("/list-channels", methods=["GET"])
def list_channels(headers="", body=""):
    with _channels_lock:
        channels = list(_channels.keys())
    return cors(200, json.dumps({"channels": channels}).encode())

# =========================
# LOGOUT
# =========================
@app.route("/logout", methods=["POST"])
def logout(headers="", body=""):
    try:
        data     = json.loads(body)
        username = data.get("username", "")
        with _peers_lock:
            if username in _peers:
                _peers[username]["online"] = False
        print("[LOGOUT] {}".format(username))
        return cors(200, json.dumps({"message": "logged out"}).encode())
    except Exception as e:
        return cors(400, json.dumps({"error": str(e)}).encode())

# =========================
# =========================
# def create_chatapp(ip, port):
#     print("[P2P CHAT] running {}:{} (MULTI-THREADING MODE)".format(ip, port))
#     print("[P2P CHAT] Routes:")
#     for (method, path) in app.routes.keys():
#         print("   [{:6s}] {}".format(method, path))
    
#     # Khởi tạo Socket thuần chủng TCP
#     server_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
#     server_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
#     server_sock.bind((ip, port))
#     server_sock.listen(100) # Lắng nghe đồng thời
    
#     print("[*] Server đang lắng nghe tại port {} (Cơ chế Multithreading)".format(port))

#     # Vòng lặp vĩnh cửu để Accept kết nối (Blocking I/O)
#     while True:
#         try:
#             conn, addr = server_sock.accept()
            
#             # Tạo Adapter và đẩy vào một Thread riêng biệt
#             adapter = HttpAdapter(ip=ip, port=port, conn=conn, connaddr=addr, routes=app.routes)
#             t = threading.Thread(target=adapter.handle_client, args=(conn, addr, app.routes))
#             t.daemon = True # Thread sẽ tự tắt khi Server chính tắt
#             t.start()
            
#         except KeyboardInterrupt:
#             print("\n[!] Đang tắt Server...")
#             server_sock.close()
#             break
#         except Exception as e:
#             print("[!] Lỗi vòng lặp accept: {}".format(e))
# =========================
# START (HỖ TRỢ 3 CHẾ ĐỘ)
# =========================
def create_chatapp(ip, port, mode="thread"):
    print("[P2P CHAT] running {}:{} | Chế độ: {}".format(ip, port, mode.upper()))
    print("[P2P CHAT] Routes:")
    for (method, path) in app.routes.keys():
        print("   [{:6s}] {}".format(method, path))
    
    # 1. BẬT CÔNG TẮC CỦA THẦY TỪ BÊN NGOÀI
    if mode == "async":
        backend.mode_async = "coroutine"
    elif mode == "callback":
        backend.mode_async = "callback"
    else:
        backend.mode_async = "threading"

    print("[*] Đã set cờ backend.mode_async = '{}'".format(backend.mode_async))

    # 2. CHẠY APP BÌNH THƯỜNG
    app.prepare_address(ip, port)
    app.run()