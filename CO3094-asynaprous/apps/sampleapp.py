#
# Copyright (C) 2026 pdnguyen of HCMC University of Technology VNU-HCM.
# All rights reserved.
# This file is part of the CO3093/CO3094 course,
# and is released under the "MIT License Agreement". Please see the LICENSE
# file that should have been included as part of this package.
#
# AsynapRous release
#
# The authors hereby grant to Licensee personal permission to use
# and modify the Licensed Source Code for the sole purpose of studying
# while attending the course
#


"""
apps/sampleapp.py — ví dụ dùng Basic Auth + Cookie session

Flow:
  1. GET  /login.html  → trả trang login (không cần auth)
  2. POST /login       → verify user/pass, nếu đúng thì set-cookie session
  3. GET  /form.html   → cần auth, httpadapter tự check cookie/basic auth
"""

import json
import os
import sys
import importlib
import secrets  # dùng để tạo token ngẫu nhiên

# import VALID_USERS và ACTIVE_SESSIONS từ httpadapter để dùng chung
# tránh duplicate dữ liệu ở 2 chỗ
from daemon.httpadapter import VALID_USERS, ACTIVE_SESSIONS
from daemon.asynaprous import AsynapRous

app = AsynapRous()


@app.route('/login', methods=['POST'])
def login(headers="", body=""):
    """
    Nhận POST /login với body dạng "username=admin&password=admin123"
    Nếu đúng thì tạo session token, lưu vào ACTIVE_SESSIONS, trả Set-Cookie.
    """
    # parse body dạng form urlencoded
    params = {}
    for pair in body.split("&"):
        if "=" in pair:
            k, v = pair.split("=", 1)
            params[k.strip()] = v.strip()

    username = params.get("username", "")
    password = params.get("password", "")

    if VALID_USERS.get(username) != password:
        # sai thông tin đăng nhập
        return 401, json.dumps({"error": "Sai username hoặc password"})

    # tạo token ngẫu nhiên 32 ký tự hex
    token = secrets.token_hex(16)
    ACTIVE_SESSIONS[token] = username
    print("[SampleApp] login OK user={} token={}".format(username, token))

    # trả response kèm Set-Cookie — response.py sẽ đọc resp.cookies để ghi header
    # cách đơn giản: nhúng Set-Cookie thẳng vào body response không được
    # nên ta trả tuple (status, body) + phụ thuộc vào response build header
    # workaround: trả token trong body, client tự set cookie qua JS
    # hoặc implement Set-Cookie trong response.py (xem ghi chú bên dưới)
    # result = {
    #     "message": "Đăng nhập thành công",
    #     "username": username,
    #     # token trả về để client dùng, browser cần JS để set cookie thủ công
    #     # nếu muốn server set cookie: cần thêm Set-Cookie vào response header
    #     "session": token,
    # }
    # return 200, json.dumps(result)
    # trả tuple 3 phần tử, phần tử 3 là cookies cần set
    return 200, json.dumps({"message": "OK", "username": username}), {"session": token}


@app.route('/hello', methods=['PUT'])
def hello(headers="", body=""):
    """Route demo không cần auth."""
    return 200, json.dumps({"message": "Hello từ SampleApp"})


def create_sampleapp(ip, port):
    app.prepare_address(ip, port)
    app.run()