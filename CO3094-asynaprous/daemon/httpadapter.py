"""
daemon.httpadapter
~~~~~~~~~~~~~~~~~
"""
import inspect
import base64
from .request import Request
from .response import Response

VALID_USERS = {
    "admin": "admin123",
    "user1": "pass1",
    "user2": "pass2",
    "user3": "pass3"
}
ACTIVE_SESSIONS = {}
PROTECTED_PATHS = ["/chat.html"]

class HttpAdapter:
    __attrs__ = ["ip", "port", "conn", "connaddr", "routes", "request", "response"]

    def __init__(self, ip, port, conn, connaddr, routes):
        self.ip = ip
        self.port = port
        self.conn = conn
        self.connaddr = connaddr
        self.routes = routes
        self.request = Request()
        self.response = Response()

    def _error_response(self, status_code, message):
        self.response.status_code = status_code
        return self.response.build_response(self.request, envelop_content=str(message))

    # ── AUTH helpers ──
    def check_basic_auth(self, req):
        auth_header = req.headers.get("authorization", "") if req.headers else ""
        if not auth_header.startswith("Basic "): return False, None
        try:
            encoded = auth_header[6:] 
            decoded = base64.b64decode(encoded).decode("utf-8")
            username, password = decoded.split(":", 1)
            if VALID_USERS.get(username) == password: return True, username
        except: pass
        return False, None

    def check_cookie_session(self, req):
        cookie_header = req.headers.get("cookie", "") if req.headers else ""
        for pair in cookie_header.split(";"):
            pair = pair.strip()
            if pair.startswith("session="):
                token = pair[len("session="):]
                if token in ACTIVE_SESSIONS: return True, ACTIVE_SESSIONS[token]
        return False, None

    def is_authenticated(self, req):
        ok, username = self.check_cookie_session(req)
        if ok: return True, username
        ok, username = self.check_basic_auth(req)
        if ok: return True, username
        return False, None

    def build_401_response(self, req):
        self.response.status_code = 401
        self.response.headers["WWW-Authenticate"] = 'Basic realm="MyServer"'
        return self.response.build_response(req, envelop_content="Unauthorized")

    # ── SYNC HANDLER (Dùng cho Thread và Callback) ──
    def handle_client(self, conn, addr, routes):
        self.conn = conn        
        self.connaddr = addr
        req = self.request
        resp = self.response

        try:
            raw = conn.recv(4096)
            if not raw:
                conn.close()
                return
            msg = raw.decode("utf-8", errors="replace")
        except:
            conn.close()
            return

        req.prepare(msg, routes)

        if req.method is None:
            response = self._error_response(400, "Bad Request")
        elif req.path in PROTECTED_PATHS:
            ok, username = self.is_authenticated(req)
            if not ok: response = self.build_401_response(req)
            else:
                resp.status_code = 200
                response = resp.build_response(req)
        elif req.hook:
            try:
                result = req.hook(headers=req.headers, body=req.body or "")
                set_cookies = {}
                if isinstance(result, tuple) and len(result) == 3:
                    status_code, body_bytes, set_cookies = result
                elif isinstance(result, tuple):
                    status_code, body_bytes = result
                else:
                    status_code, body_bytes = 200, result

                if not isinstance(body_bytes, bytes): body_bytes = body_bytes.encode("utf-8")
                if set_cookies: resp.cookies.update(set_cookies)

                resp.status_code = status_code
                response = resp.build_response(req, envelop_content=body_bytes)
            except Exception as e:
                response = self._error_response(500, str(e))
        else:
            resp.status_code = 200
            response = resp.build_response(req)

        try: conn.sendall(response)
        except: pass
        finally: conn.close()

    # ── ASYNC HANDLER (Dùng cho Coroutine) ──
    async def handle_client_coroutine(self, reader, writer):
        req = self.request
        resp = self.response
        msg = await reader.read(4096)

        if not msg:
            writer.close()
            await writer.wait_closed()
            return

        req.prepare(msg.decode("utf-8", errors="replace"), self.routes or {})

        if req.method is None:
            response = self._error_response(400, "Bad Request")
        elif req.path in PROTECTED_PATHS:
            ok, username = self.is_authenticated(req)
            if not ok: response = self.build_401_response(req)
            else:
                resp.status_code = 200
                response = resp.build_response(req)
        elif req.hook:
            try:
                # Kiểm tra xem cái hàm API (hook) là async hay đồng bộ bình thường
                if inspect.iscoroutinefunction(req.hook):
                    result = await req.hook(headers=req.headers, body=req.body or "")
                else:
                    result = req.hook(headers=req.headers, body=req.body or "")
                set_cookies = {}
                if isinstance(result, tuple) and len(result) == 3:
                    status_code, body_bytes, set_cookies = result
                elif isinstance(result, tuple):
                    status_code, body_bytes = result
                else:
                    status_code, body_bytes = 200, result

                if not isinstance(body_bytes, bytes): body_bytes = body_bytes.encode("utf-8")
                if set_cookies: resp.cookies.update(set_cookies)

                resp.status_code = status_code
                response = resp.build_response(req, envelop_content=body_bytes)
            except Exception as e:
                response = self._error_response(500, str(e))
        else:
            resp.status_code = 200
            response = resp.build_response(req)

        writer.write(response)
        await writer.drain()
        writer.close()
        await writer.wait_closed()

    @property
    def extract_cookies(self):
        req = self.request
        cookies = {}
        if not req or not req.headers: return cookies
        cookie_str = req.headers.get("cookie", "") or req.headers.get("Cookie", "")
        if not cookie_str: return cookies
        for pair in cookie_str.split(";"):
            pair = pair.strip()
            if "=" in pair:
                key, value = pair.split("=", 1)
                cookies[key.strip()] = value.strip()
        return cookies

    def build_response(self, req, resp):
        response = Response()
        response.raw = resp
        response.url = req.url.decode("utf-8") if isinstance(req.url, bytes) else req.url
        response.cookies = self.extract_cookies
        response.request = req
        response.connection = self
        return response

    def build_json_response(self, req, resp):
        response = Response(req)
        response.raw = resp
        response.url = req.url.decode("utf-8") if isinstance(req.url, bytes) else req.url
        response.request = req
        response.connection = self
        return response

    def add_headers(self, request): pass
    def build_proxy_headers(self, proxy): return {}