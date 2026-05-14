#
# Copyright (C) 2026 pdnguyen of HCMC University of Technology VNU-HCM.
# All rights reserved.
# This file is part of the CO3093/CO3094 course.
#
# AsynapRous release
#
# The authors hereby grant to Licensee personal permission to use
# and modify the Licensed Source Code for the sole purpose of studying
# while attending the course
#

"""
daemon.backend
~~~~~~~~~~~~~~~~~

This module provides a backend object to manage and persist backend daemon. 
It implements a basic backend server using Python's socket and threading libraries.
It supports handling multiple client connections concurrently and routing requests using a
custom HTTP adapter.

Requirements:
--------------
- socket: provide socket networking interface.
- threading: Enables concurrent client handling via threads.
- response: response utilities.
- httpadapter: the class for handling HTTP requests.
- CaseInsensitiveDict: provides dictionary for managing headers or routes.


Notes:
------
- The server create daemon threads for client handling.
- The current implementation error handling is minimal, socket errors are printed to the console.
- The actual request processing is delegated to the HttpAdapter class.

Usage Example:
--------------
>>> create_backend("127.0.0.1", 9000, routes={})

"""

import socket
import threading
import argparse

import asyncio
import inspect

from .response import *
from .httpadapter import HttpAdapter
from .dictionary import CaseInsensitiveDict

import selectors
sel = selectors.DefaultSelector()

#mode_async = "callback"
#mode_async = "coroutine"
mode_async = "threading"

def handle_client(ip, port, conn, addr, routes):
    
    print("[Backend] Invoke handle_client accepted connection from {}".format(addr))
    daemon = HttpAdapter(ip, port, conn, addr, routes)

    # Handle client
    daemon.handle_client(conn, addr, routes)


# Callback for handling new client (itself run in sync mode)
def handle_client_callback(server, ip, port,conn, addr, routes):
    
    print("[Backend] Invoke handle_client_callback accepted connection from {}".format(addr))

    daemon = HttpAdapter(ip, port, conn, addr, routes)

    # Handle client
    daemon.handle_client(conn, addr, routes)

# comment lại 2 hàm của thầy, code lại thành closure để cái routes xác định
# # Coroutine async/await for handling new client
# async def handle_client_coroutine(reader, writer):
    
#     addr = writer.get_extra_info("peername")
#     print("[Backend] Invoke handle_client_coroutine accepted connection from {}".format(addr))

#     # Handle client in asynchronous mode
#     while True:
#           daemon = HttpAdapter(None, None, None, None, None)
#           await daemon.handle_client_coroutine(reader, writer)

# async def async_server(ip="0.0.0.0", port=7000, routes={}):
#     print("[Backend] async_server **ASYNC** listening on port {}".format(port))
#     if routes != {}:
#         print("[Backend] route settings")
#         for key, value in routes.items():
#             isCoFunc = ""
#             if inspect.iscoroutinefunction(value):
#                isCoFunc += "**ASYNC** "
#             print("   + ('{}', '{}'): {}{}".format(key[0], key[1], isCoFunc, str(value)))

#     async_server = await asyncio.start_server(handle_client_coroutine, ip, port)
#     async with async_server:
#         await async_server.serve_forever()
#     return
async def async_server(ip="0.0.0.0", port=7000, routes={}):
    print("[Backend] async_server **ASYNC** listening on port {}".format(port))
    if routes != {}:
        print("[Backend] route settings")
        for key, value in routes.items():
            isCoFunc = ""
            if inspect.iscoroutinefunction(value):
               isCoFunc += "**ASYNC** "
            print("   + ('{}', '{}'): {}{}".format(key[0], key[1], isCoFunc, str(value)))
 
    # dùng closure để routes từ async_server truyền vào được handler
    # hồi trước handle_client_coroutine là hàm ngoài nên routes bị None
    async def handle_client_coroutine(reader, writer):
        addr = writer.get_extra_info("peername")
        print("[Backend] Invoke handle_client_coroutine accepted connection from {}".format(addr))
        daemon = HttpAdapter(None, None, None, None, routes)
        await daemon.handle_client_coroutine(reader, writer)
 
    server = await asyncio.start_server(handle_client_coroutine, ip, port)
    async with server:
        await server.serve_forever()
    return


def run_backend(ip, port, routes):
    # This global variable to configure the asynchrnous mode or not
    global mode_async

    print("[Backend] run_backend with routes={}".format(routes))
    # Process async stream for registering the service and terminate
    if mode_async == "coroutine":

       asyncio.run(async_server(ip, port, routes))
       return

    # Process socket object
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    # fix callback
    try:
        server.bind((ip, port))
        server.listen(50)
        print("[Backend] Listening on port {}".format(port))
        
        # --- CHẾ ĐỘ MULTI-THREADING ---
        if mode_async == "threading":
            while True:
                conn, addr = server.accept()
                client_thread = threading.Thread(target=handle_client, args=(ip, port, conn, addr, routes))
                client_thread.daemon = True 
                client_thread.start()

        # --- CHẾ ĐỘ CALLBACK (SELECTOR CHUẨN) ---
        elif mode_async == "callback":
            print("[Backend] Chạy chế độ EVENT-DRIVEN (Selector chuẩn)")
            server.setblocking(False) # Cửa chính không bao giờ bị kẹt
            # Đăng ký cửa chính cho ông Bảo vệ (sel) theo dõi
            sel.register(server, selectors.EVENT_READ, data="CUA_CHINH")

            while True:
                # Ông bảo vệ ngồi chờ (chỉ chặn ở đây), cửa nào có biến ổng báo
                events = sel.select(timeout=None)
                for key, mask in events:
                    if key.data == "CUA_CHINH":
                        # Khách mới tới! Chấp nhận và giao cửa phụ cho bảo vệ canh tiếp
                        conn, addr = server.accept()
                        conn.setblocking(False)
                        print("[Backend] Selector bắt được kết nối mới từ:", addr)
                        sel.register(conn, selectors.EVENT_READ, data=addr)
                    else:
                        # Khách cũ gửi tin nhắn!
                        conn = key.fileobj
                        addr = key.data
                        # Phải gỡ đăng ký ra trước khi đọc để khỏi bị lặp
                        sel.unregister(conn)
                        # Gọi callback xử lý
                        handle_client_callback(server, ip, port, conn, addr, routes)
                        
    except socket.error as e:
        print("Socket error: {}".format(e))
    # try:
    #     server.bind((ip, port))
    #     server.listen(50)

    #     print("[Backend] Listening on port {}".format(port))
    #     if routes != {}:
    #         print("[Backend] route settings")
    #         for key, value in routes.items():
    #            isCoFunc = ""
    #            if inspect.iscoroutinefunction(value):
    #               isCoFunc += "**ASYNC** "
    #            print("   + ('{}', '{}'): {}{}".format(key[0], key[1], isCoFunc, str(value)))

    #     if mode_async == "callback":
    #         sel.register(server, selectors.EVENT_READ, (handle_client_callback, ip, port, routes))

    #     while True:
    #         # Accept connection
    #         conn, addr = server.accept()
    #         if mode_async == "callback":
    #            # Callback implementation - Event driven architecture
    #            server.setblocking(False)

    #            events = sel.select(timeout=None)
    #            for key, mask in events:
    #                callback, ip, port, routes = key.data
    #                callback(key.fileobj, ip, port, conn, addr, routes)

    #         else:
    #             client_thread = threading.Thread(
    #                target=handle_client, 
    #                args=(ip, port, conn, addr, routes)
    #            )
    #             client_thread.daemon = True 
    #             client_thread.start()

    # except socket.error as e:
    #   print("Socket error: {}".format(e))

def create_backend(ip, port, routes={}):
    run_backend(ip, port, routes)