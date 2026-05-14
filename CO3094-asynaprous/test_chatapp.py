"""
test_chatapp.py — Script demo kiểm tra Chat Application
=========================================================
Chạy TRƯỚC KHI test:
  Terminal 1:  python start_chatapp.py --server-port 8001  ← Peer 1 (tracker)
  Terminal 2:  python start_chatapp.py --server-port 8002  ← Peer 2

Rồi chạy:
  python test_chatapp.py
"""

import socket
import json
import time

TRACKER_HOST = "127.0.0.1"
TRACKER_PORT = 8001
PEER2_PORT   = 8002

SEP = "=" * 48


# ─────────────────────────────────────────────
# RAW HTTP CLIENT
# ─────────────────────────────────────────────
def request(method, path, body=None, port=None):
    port = port or TRACKER_PORT
    body_bytes = json.dumps(body or {}).encode()

    req = (
        "{} {} HTTP/1.1\r\n"
        "Host: {}:{}\r\n"
        "Content-Type: application/json\r\n"
        "Content-Length: {}\r\n"
        "Connection: close\r\n\r\n"
    ).format(method, path, TRACKER_HOST, port, len(body_bytes)).encode() + body_bytes

    s = socket.socket()
    s.settimeout(5)
    try:
        s.connect((TRACKER_HOST, port))
        s.sendall(req)
        data = b""
        while True:
            chunk = s.recv(4096)
            if not chunk:
                break
            data += chunk
    finally:
        s.close()

    resp = data.decode(errors="ignore")
    # Lấy status code
    try:
        status = int(resp.split(" ")[1])
    except:
        status = 0
    # Lấy body
    try:
        body_str = resp.split("\r\n\r\n", 1)[1]
        return status, json.loads(body_str)
    except:
        return status, {}


def ok(status):
    return "OK!" if 200 <= status < 300 else "❌"


# ─────────────────────────────────────────────
# TEST FLOW
# ─────────────────────────────────────────────
print("\n" + SEP)
print("  CO3094 — Chat Application Test")
print(SEP)

# ── [1] LOGIN ────────────────────────────────
print("\n[1] POST /login — Alice đăng nhập (Client → Tracker)")
st, r = request("POST", "/login", {"username": "alice", "password": "any"})
print("   {} Status: {} | {}".format(ok(st), st, r))
assert 200 <= st < 300, "LOGIN THẤT BẠI"

print("\n[2] POST /login — Bob đăng nhập")
st, r = request("POST", "/login", {"username": "bob", "password": "any"})
print("   {} Status: {} | {}".format(ok(st), st, r))
assert 200 <= st < 300

# ── [2] SUBMIT INFO ──────────────────────────
print("\n[3] POST /submit-info — Alice đăng ký địa chỉ P2P (port 8001)")
st, r = request("POST", "/submit-info", {
    "username": "alice", "ip": "127.0.0.1", "port": TRACKER_PORT
})
print("   {} Status: {} | {}".format(ok(st), st, r))
assert 200 <= st < 300

print("\n[4] POST /submit-info — Bob đăng ký địa chỉ P2P (port 8002)")
st, r = request("POST", "/submit-info", {
    "username": "bob", "ip": "127.0.0.1", "port": PEER2_PORT
})
print("   {} Status: {} | {}".format(ok(st), st, r))
assert 200 <= st < 300

# ── [3] GET LIST ─────────────────────────────
print("\n[5] GET /get-list — Lấy danh sách peers online (Peer Discovery)")
st, r = request("GET", "/get-list")
print("   {} Status: {} | Peers: {}".format(ok(st), st, r.get("peers", [])))
assert 200 <= st < 300
assert len(r.get("peers", [])) >= 2, "Phải có ít nhất 2 peers"
print("   → {} peers đang online".format(len(r["peers"])))

# ── [4] JOIN CHANNEL ─────────────────────────
print("\n[6] POST /join-channel — Alice join channel 'random'")
st, r = request("POST", "/join-channel", {"username": "alice", "channel": "random"})
print("   {} Status: {} | {}".format(ok(st), st, r))

# ── [5] GET CHANNELS ─────────────────────────
print("\n[7] GET /get-channels — Lấy danh sách channels")
st, r = request("GET", "/get-channels")
print("   {} Status: {} | Channels: {}".format(ok(st), st, r.get("channels", [])))
assert 200 <= st < 300

# ── [6] CONNECT PEER ─────────────────────────
print("\n[8] POST /connect-peer — Alice hỏi địa chỉ P2P của Bob (Connection Setup)")
# Key đúng là "to" (không phải "target_username")
st, r = request("POST", "/connect-peer", {"to": "bob"})
print("   {} Status: {} | {}".format(ok(st), st, r))
assert 200 <= st < 300
peer_info = r.get("peer", {})
print("   → Bob đang ở {}:{}".format(peer_info.get("ip"), peer_info.get("port")))

# ── [7] BROADCAST ────────────────────────────
print("\n[9] POST /broadcast-peer — Alice broadcast đến tất cả (P2P)")
st, r = request("POST", "/broadcast-peer", {
    "from": "alice",
    "channel": "general",
    "message": "Hello everyone! Đây là P2P broadcast."
})
print("   {} Status: {} | {}".format(ok(st), st, r))
assert 200 <= st < 300
time.sleep(0.5)

# ── [8] GET MESSAGES ─────────────────────────
print("\n[10] POST /get-messages — Lấy tin nhắn channel 'general'")
st, r = request("POST", "/get-messages", {"channel": "general"})
print("   {} Status: {} | {} tin nhắn".format(ok(st), st, len(r.get("messages", []))))
for m in r.get("messages", []):
    print("     [{}] {}: {}".format(m.get("time",""), m.get("from",""), m.get("message","")))
assert 200 <= st < 300

# ── [9] SEND PEER (Direct P2P) ───────────────
print("\n[11] POST /send-peer — Alice gửi DM trực tiếp đến Bob (P2P Direct)")
st, r = request("POST", "/send-peer", {
    "from": "alice",
    "to": "bob",
    "message": "Này Bob, đây là tin nhắn riêng!"
})
print("   {} Status: {} | {}".format(ok(st), st, r))
# 200 = bob đang chạy ở port 8002, 404 = bob chưa đăng ký
if st == 200:
    print("   → Gửi thành công, Peer 2 (port 8002) đã nhận")
else:
    print("   → {} (bình thường nếu Peer 2 chưa chạy)".format(r))

# ── [10] RECEIVE MESSAGE (simulate) ──────────
print("\n[12] POST /receive-message — Simulate nhận tin từ peer khác")
st, r = request("POST", "/receive-message", {
    "type": "direct",
    "from": "charlie",
    "to": "alice",
    "message": "Tin nhắn test từ charlie",
    "time": time.strftime("%H:%M:%S"),
    "channel": "direct"
})
print("   {} Status: {} | {}".format(ok(st), st, r))
assert 200 <= st < 300

# ── [11] ADD LIST ────────────────────────────
print("\n[13] POST /add-list — Thêm channel 'announcements'")
st, r = request("POST", "/add-list", {"channel": "announcements"})
print("   {} Status: {} | {}".format(ok(st), st, r))

# ── [12] LOGOUT ──────────────────────────────
print("\n[14] POST /logout — Alice đăng xuất")
st, r = request("POST", "/logout", {"username": "alice"})
print("   {} Status: {} | {}".format(ok(st), st, r))
assert 200 <= st < 300

# Kiểm tra alice offline
print("\n[15] GET /get-list — Kiểm tra Alice đã offline")
st, r = request("GET", "/get-list")
names = [p["username"] for p in r.get("peers", [])]
print("   {} Peers còn online: {}".format(ok(st), names))
assert "alice" not in names, "Alice phải offline sau logout!"
print("   → Alice đã offline")

# ── DONE ─────────────────────────────────────
print("\n" + SEP)
print("TẤT CẢ TEST PASSED!")
print(SEP)
print()
print("Ghi chú:")
print("  - [11] send-peer: 200 nếu Peer 2 (port 8002) đang chạy")
print("  - Kiểm tra terminal Peer 2 để thấy tin nhắn P2P nhận được")
print()