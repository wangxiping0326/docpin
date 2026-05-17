# 二进制帧协议 - 帧结构: 0xA5 | LEN | CMD | DATA(N) | CRC16(2B) | 0x5A
# CRC-16/MODBUS 查表法，大端序

# 命令码
CMD_HEART = 0x01       # 心跳
CMD_HEART_ACK = 0x02   # 心跳应答
CMD_START = 0x10       # 启动注射
CMD_STOP = 0x11        # 停止注射
CMD_PARAM = 0x12       # 参数设置
CMD_STATUS_QUERY = 0x20  # 状态查询
CMD_STATUS_REPORT = 0x21 # 状态上报
CMD_ACK = 0xFF         # ACK/NAK
CMD_NAK = 0xFE         # NAK 专用（也可用 ACK+data=0x01）

FRAME_HEAD = 0xA5
FRAME_TAIL = 0x5A

# CRC-16/MODBUS 查找表（预计算256个值）
_CRC_TABLE = [
    0x0000, 0xC0C1, 0xC181, 0x0140, 0xC301, 0x03C0, 0x0280, 0xC241,
    0xC601, 0x06C0, 0x0780, 0xC741, 0x0500, 0xC5C1, 0xC481, 0x0440,
    0xCC01, 0x0CC0, 0x0D80, 0xCD41, 0x0F00, 0xCFC1, 0xCE81, 0x0E40,
    0x0A00, 0xCAC1, 0xCB81, 0x0B40, 0xC901, 0x09C0, 0x0880, 0xC841,
    0xD801, 0x18C0, 0x1980, 0xD941, 0x1B00, 0xDBC1, 0xDA81, 0x1A40,
    0x1E00, 0xDEC1, 0xDF81, 0x1F40, 0xDD01, 0x1DC0, 0x1C80, 0xDC41,
    0x1400, 0xD4C1, 0xD581, 0x1540, 0xD701, 0x17C0, 0x1680, 0xD641,
    0xD201, 0x12C0, 0x1380, 0xD341, 0x1100, 0xD1C1, 0xD081, 0x1040,
    0xF001, 0x30C0, 0x3180, 0xF141, 0x3300, 0xF3C1, 0xF281, 0x3240,
    0x3600, 0xF6C1, 0xF781, 0x3740, 0xF501, 0x35C0, 0x3480, 0xF441,
    0x3C00, 0xFCC1, 0xFD81, 0x3D40, 0xFF01, 0x3FC0, 0x3E80, 0xFE41,
    0xFA01, 0x3AC0, 0x3B80, 0xFB41, 0x3900, 0xF9C1, 0xF881, 0x3840,
    0x2800, 0xE8C1, 0xE981, 0x2940, 0xEB01, 0x2BC0, 0x2A80, 0xEA41,
    0xEE01, 0x2EC0, 0x2F80, 0xEF41, 0x2D00, 0xEDC1, 0xEC81, 0x2C40,
    0xE401, 0x24C0, 0x2580, 0xE541, 0x2700, 0xE7C1, 0xE681, 0x2640,
    0x2200, 0xE2C1, 0xE381, 0x2340, 0xE101, 0x21C0, 0x2080, 0xE041,
    0xA001, 0x60C0, 0x6180, 0xA141, 0x6300, 0xA3C1, 0xA281, 0x6240,
    0x6600, 0xA6C1, 0xA781, 0x6740, 0xA501, 0x65C0, 0x6480, 0xA441,
    0x6C00, 0xACC1, 0xAD81, 0x6D40, 0xAF01, 0x6FC0, 0x6E80, 0xAE41,
    0xAA01, 0x6AC0, 0x6B80, 0xAB41, 0x6900, 0xA9C1, 0xA881, 0x6840,
    0x7800, 0xB8C1, 0xB981, 0x7940, 0xBB01, 0x7BC0, 0x7A80, 0xBA41,
    0xBE01, 0x7EC0, 0x7F80, 0xBF41, 0x7D00, 0xBDC1, 0xBC81, 0x7C40,
    0xB401, 0x74C0, 0x7580, 0xB541, 0x7700, 0xB7C1, 0xB681, 0x7640,
    0x7200, 0xB2C1, 0xB381, 0x7340, 0xB101, 0x71C0, 0x7080, 0xB041,
    0x5000, 0x90C1, 0x9181, 0x5140, 0x9301, 0x53C0, 0x5280, 0x9241,
    0x9601, 0x56C0, 0x5780, 0x9741, 0x5500, 0x95C1, 0x9481, 0x5440,
    0x9C01, 0x5CC0, 0x5D80, 0x9D41, 0x5F00, 0x9FC1, 0x9E81, 0x5E40,
    0x5A00, 0x9AC1, 0x9B81, 0x5B40, 0x9901, 0x59C0, 0x5880, 0x9841,
    0x8801, 0x48C0, 0x4980, 0x8941, 0x4B00, 0x8BC1, 0x8A81, 0x4A40,
    0x4E00, 0x8EC1, 0x8F81, 0x4F40, 0x8D01, 0x4DC0, 0x4C80, 0x8C41,
    0x4400, 0x84C1, 0x8581, 0x4540, 0x8701, 0x47C0, 0x4680, 0x8641,
    0x8201, 0x42C0, 0x4380, 0x8341, 0x4100, 0x81C1, 0x8081, 0x4040,
]

def calc_crc(data: bytes) -> int:
    """CRC-16/MODBUS"""
    crc = 0xFFFF
    for b in data:
        idx = (crc ^ b) & 0xFF
        crc = (crc >> 8) ^ _CRC_TABLE[idx]
    return crc & 0xFFFF

class ProtocolError(Exception):
    pass

class ChecksumError(ProtocolError):
    pass

class FrameFormatError(ProtocolError):
    pass

def pack(cmd: int, data_bytes: bytes = b"") -> bytes:
    """组帧: HEAD + LEN + CMD + DATA + CRC16 + TAIL"""
    if not (0 <= cmd <= 255):
        raise ProtocolError(f"cmd {cmd} 超出范围")
    data_len = len(data_bytes)
    if data_len > 255:
        raise ProtocolError(f"数据太长 {data_len} > 255")

    # 帧头 + 长度 + 命令码 + 数据
    pre_crc = bytes([FRAME_HEAD, data_len, cmd]) + data_bytes
    crc_val = calc_crc(pre_crc)
    crc_bytes = crc_val.to_bytes(2, byteorder="big")

    return pre_crc + crc_bytes + bytes([FRAME_TAIL])

def unpack(raw_bytes: bytes) -> dict:
    """解帧，成功返回 {"cmd": int, "data": bytes}，失败抛异常"""
    if not raw_bytes or len(raw_bytes) < 6:
        raise FrameFormatError("帧太短")

    if raw_bytes[0] != FRAME_HEAD:
        raise FrameFormatError(f"帧头错: 0x{raw_bytes[0]:02X}")
    if raw_bytes[-1] != FRAME_TAIL:
        raise FrameFormatError("帧尾错")

    data_len = raw_bytes[1]
    cmd = raw_bytes[2]
    expected_len = 3 + data_len + 2 + 1  # head+len+cmd + data + crc + tail
    if len(raw_bytes) != expected_len:
        raise FrameFormatError(f"长度不对: 实际{len(raw_bytes)} 期望{expected_len}")

    data_bytes = raw_bytes[3:3 + data_len]

    # CRC 校验（覆盖: head + len + cmd + data）
    crc_received = int.from_bytes(raw_bytes[3 + data_len:3 + data_len + 2], byteorder="big")
    pre_crc = raw_bytes[:3 + data_len]
    crc_calc = calc_crc(pre_crc)

    if crc_received != crc_calc:
        raise ChecksumError(f"CRC错: 收到0x{crc_received:04X} 计算0x{crc_calc:04X}")

    return {"cmd": cmd, "data": data_bytes}

def pack_status_report(elapsed: int, remaining: int, yali: float, yao: float, running: bool) -> bytes:
    """封装 0x21 状态上报帧"""
    import struct
    data = struct.pack(">IIffB", elapsed, remaining, yali, yao, 1 if running else 0)
    return pack(CMD_STATUS_REPORT, data)

def parse_status_report(data: bytes) -> dict:
    """解析 0x21 状态上报"""
    import struct
    elapsed, remaining, yali, yao, running = struct.unpack(">IIffB", data)
    return {
        "elapsed": elapsed,
        "remaining": remaining,
        "yali": yali,
        "yao": yao,
        "running": bool(running),
    }

def pack_start_cmd(mode: int, su_lv: float, ji_liang: float, total_t: int) -> bytes:
    """封装 0x10 启动指令
    mode: 0=cont, 1=jianxie, 2=tui, 3=custom
    """
    import struct
    mode_map = {"cont": 0, "jianxie": 1, "tui": 2, "custom": 3}
    m = mode_map.get(mode, 0) if isinstance(mode, str) else mode
    data = struct.pack(">BffI", m, su_lv, ji_liang, total_t)
    return pack(CMD_START, data)

def pack_stop_cmd() -> bytes:
    """封装 0x11 停止指令"""
    return pack(CMD_STOP, b"")

def pack_heart() -> bytes:
    return pack(CMD_HEART, b"")

def pack_heart_ack() -> bytes:
    return pack(CMD_HEART_ACK, b"")

def pack_ack(orig_cmd: int, ok: bool = True) -> bytes:
    """封装 ACK 帧: data[0]=原始cmd, data[1]=0x00成功/0x01失败"""
    flag = b"\x00" if ok else b"\x01"
    return pack(CMD_ACK, bytes([orig_cmd]) + flag)

def pack_status_query() -> bytes:
    return pack(CMD_STATUS_QUERY, b"")
