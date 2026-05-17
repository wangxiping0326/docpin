# 硬件模拟器 - 完整协议栈的虚拟注射器
import threading
import time
import random
import math
import struct
from collections import deque
from services.protocol import (
    CMD_HEART, CMD_HEART_ACK, CMD_START, CMD_STOP,
    CMD_STATUS_QUERY, CMD_STATUS_REPORT,
    CMD_ACK, FRAME_HEAD, FRAME_TAIL,
    pack, unpack, calc_crc, pack_status_report,
    pack_heart_ack, pack_ack, ProtocolError, ChecksumError, FrameFormatError,
)

class VirtualInjector:
    """模拟一台真实的注射器硬件"""

    def __init__(self):
        self.running = False
        self.mode = 0
        self.su_lv = 5.0
        self.ji_liang = 10.0
        self.total_time = 60
        self.elapsed = 0
        self.yali_now = 50.0
        self.yao_left = 10.0
        self._lock = threading.Lock()
        self._sim_thread = None

        # 错误注入开关
        self.no_response = False
        self.bad_crc = False
        self.send_nak = False
        self.skip_heartbeat = False
        self.heartbeat_missed = 0

        self._tx_queue = deque()
        self._rx_callback = None

    def set_rx_callback(self, cb):
        self._rx_callback = cb

    def feed_bytes(self, raw: bytes):
        i = 0
        while i < len(raw):
            if raw[i] == FRAME_HEAD and i + 5 < len(raw):
                data_len = raw[i + 1] if i + 1 < len(raw) else 0
                frame_end = i + 3 + data_len + 2 + 1
                if frame_end <= len(raw) and raw[frame_end - 1] == FRAME_TAIL:
                    frame = raw[i:frame_end]
                    self._handle_frame(frame)
                    i = frame_end
                    continue
            i += 1

    def _handle_frame(self, frame: bytes):
        if self.no_response:
            return
        try:
            parsed = unpack(frame)
        except ProtocolError:
            return
        cmd = parsed["cmd"]
        data = parsed["data"]

        if cmd == CMD_HEART:
            if not self.skip_heartbeat:
                self._enqueue_tx(pack_heart_ack())
            else:
                self.heartbeat_missed += 1
            return

        elif cmd == CMD_START:
            ok = self._do_start(data)
            flag = b"\x00" if ok else b"\x01"
            if self.send_nak:
                flag = b"\x01"
            self._enqueue_tx(pack(CMD_ACK, bytes([CMD_START]) + flag))

        elif cmd == CMD_STOP:
            self._do_stop()
            flag = b"\x01" if self.send_nak else b"\x00"
            self._enqueue_tx(pack(CMD_ACK, bytes([CMD_STOP]) + flag))

        elif cmd == CMD_STATUS_QUERY:
            self._send_status()

        else:
            self._enqueue_tx(pack_ack(cmd, True))

    def _do_start(self, data: bytes) -> bool:
        try:
            m, su_lv, ji_liang, total_t = struct.unpack(">BffI", data)
        except struct.error:
            return False
        with self._lock:
            self.mode = m
            self.su_lv = su_lv
            self.ji_liang = ji_liang
            self.total_time = total_t
            self.elapsed = 0
            self.yao_left = ji_liang
            self.yali_now = 50.0
            self.running = True
        if self._sim_thread is None or not self._sim_thread.is_alive():
            self._sim_thread = threading.Thread(target=self._sim_run, daemon=True)
            self._sim_thread.start()
        return True

    def _do_stop(self):
        with self._lock:
            self.running = False

    def _send_status(self):
        with self._lock:
            frame = pack_status_report(
                self.elapsed,
                max(0, self.total_time - self.elapsed),
                self.yali_now,
                self.yao_left,
                self.running,
            )
        if self.bad_crc:
            frame = frame[:-3] + b'\xFF\xFF' + bytes([FRAME_TAIL])
        self._enqueue_tx(frame)

    def _sim_run(self):
        last_report = 0
        while self.running:
            time.sleep(0.5)
            with self._lock:
                if not self.running:
                    break
                self.elapsed += 0.5
                if self.elapsed >= self.total_time:
                    self.elapsed = self.total_time
                    self.running = False
                decay = (self.su_lv / 3600.0) * 0.5
                self.yao_left = max(0, self.yao_left - decay)
                self.yali_now += random.uniform(-1.0, 2.0) + math.sin(self.elapsed * 0.15) * 1.2
                self.yali_now = max(0, self.yali_now)
                last_report += 0.5
                if last_report >= 1.0:
                    last_report = 0
                    self._send_status()

    def _enqueue_tx(self, frame: bytes):
        self._tx_queue.append(frame)
        if self._rx_callback:
            self._rx_callback(frame)

    def pop_tx(self) -> bytes:
        if self._tx_queue:
            return self._tx_queue.popleft()
        return b""

    def has_tx(self) -> bool:
        return len(self._tx_queue) > 0

    def get_state(self) -> dict:
        with self._lock:
            return {
                "running": self.running,
                "mode": self.mode,
                "su_lv": self.su_lv,
                "ji_liang": self.ji_liang,
                "total_time": self.total_time,
                "elapsed": self.elapsed,
                "yali_now": self.yali_now,
                "yao_left": self.yao_left,
            }

_virtual_dev = None

def get_virtual_device() -> VirtualInjector:
    global _virtual_dev
    if _virtual_dev is None:
        _virtual_dev = VirtualInjector()
    return _virtual_dev
