import socket, threading, time

HOST, PORT = "127.0.0.1", 8001
# Server phải đang chạy: python start_chatapp.py --server-port 8001

t0 = None
send_time = {}  # lưu thời điểm gửi của mỗi client (từ t0)
recv_time = {}  # lưu thời điểm nhận response

def slow_client():
    global send_time, recv_time
    s = socket.socket()
    s.connect((HOST, PORT))
    connect_done = time.time() - t0
    print(f"[SLOW ] kết nối xong tại t={connect_done:.2f}s, giữ im 3 giây...")
    time.sleep(3)
    # Gửi request
    send_t = time.time() - t0
    send_time['SLOW'] = send_t
    s.sendall(b"GET /get-list HTTP/1.1\r\nHost: localhost\r\n\r\n")
    print(f"[SLOW ] gửi request tại t={send_t:.2f}s")
    try:
        resp = s.recv(4096)
        recv_t = time.time() - t0
        recv_time['SLOW'] = recv_t
        print(f"[SLOW ] nhận response tại t={recv_t:.2f}s")
    except Exception as e:
        print(f"[SLOW ] lỗi: {e}")
    finally:
        s.close()

def fast_client(label, delay):
    global send_time, recv_time
    time.sleep(delay)  # chờ đến thời điểm bắt đầu kết nối
    start_conn = time.time() - t0
    s = socket.socket()
    s.settimeout(5)
    try:
        s.connect((HOST, PORT))
        # Gửi request
        send_t = time.time() - t0
        send_time[label] = send_t
        s.sendall(b"GET /get-list HTTP/1.1\r\nHost: localhost\r\n\r\n")
        print(f"[{label}] gửi request tại t={send_t:.2f}s")
        resp = s.recv(4096)
        recv_t = time.time() - t0
        recv_time[label] = recv_t
        print(f"[{label}] nhận response tại t={recv_t:.2f}s")
        # Kiểm tra non-blocking dựa trên thứ tự hoàn thành
    except Exception as e:
        print(f"[{label}] lỗi: {e}")
    finally:
        s.close()

if __name__ == "__main__":
    t0 = time.time()
    print(f"Bắt đầu test tại t0 = {t0}")
    slow_thread = threading.Thread(target=slow_client)
    fast_threads = [
        threading.Thread(target=fast_client, args=("FAST-1", 0.5)),
        threading.Thread(target=fast_client, args=("FAST-2", 0.5)),
        threading.Thread(target=fast_client, args=("FAST-3", 0.5))
    ]
    slow_thread.start()
    for t in fast_threads:
        t.start()
    slow_thread.join()
    for t in fast_threads:
        t.join()
    
    print("\n=== TỔNG KẾT THỜI ĐIỂM ===")
    for label in ['FAST-1', 'FAST-2', 'FAST-3', 'SLOW']:
        if label in send_time:
            print(f"{label:8} - gửi request: {send_time[label]:.2f}s, nhận response: {recv_time[label]:.2f}s")
    # So sánh thời điểm nhận response
    fast_recv_max = max(recv_time.get('FAST-1',0), recv_time.get('FAST-2',0), recv_time.get('FAST-3',0))
    slow_recv = recv_time.get('SLOW', 0)
    if fast_recv_max < slow_recv:
        print(f"\nKẾT LUẬN: Non-blocking thành công (fast cuối cùng hoàn thành lúc {fast_recv_max:.2f}s < slow hoàn thành lúc {slow_recv:.2f}s)")
    else:
        print(f"\nKẾT LUẬN: Có thể bị blocking (fast cuối cùng {fast_recv_max:.2f}s >= slow {slow_recv:.2f}s)")