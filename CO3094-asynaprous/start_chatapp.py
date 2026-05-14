"""
start_chatapp.py — Entry point để chạy Hybrid Chat Application
===============================================================

Cách chạy:
  # Peer 1 (làm tracker luôn) — cổng 8001
  python start_chatapp.py --server-ip 0.0.0.0 --server-port 8001

  # Peer 2 — cổng 8002
  python start_chatapp.py --server-ip 0.0.0.0 --server-port 8002

  # Peer 3 — cổng 8003
  python start_chatapp.py --server-ip 0.0.0.0 --server-port 8003
"""

import argparse
from apps.chatapp import create_chatapp

PORT = 8001

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        prog="ChatApp",
        description="Hybrid P2P Chat Application — CO3094 Assignment 1",
    )
    parser.add_argument("--server-ip",   default="0.0.0.0")
    parser.add_argument("--server-port", type=int, default=PORT)
    parser.add_argument("--mode", choices=["thread", "callback", "async"], default="thread", 
                        help="Chọn cơ chế: thread, callback (selector), async (coroutine)")
    args = parser.parse_args()
    create_chatapp(args.server_ip, args.server_port, args.mode)