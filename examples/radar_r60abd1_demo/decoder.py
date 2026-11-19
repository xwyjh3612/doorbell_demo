"""R60ABD1 passive report decoder. No radar configuration or serial writes."""


ENUMS = {
    (0x07, 0x07): ("range", {0: "范围外", 1: "范围内"}),
    (0x80, 0x01): ("presence", {0: "无人", 1: "有人"}),
    (0x80, 0x02): ("activity", {0: "无活动目标", 1: "静止", 2: "活跃"}),
    (0x81, 0x01): ("breath_status", {1: "正常", 2: "呼吸过高", 3: "呼吸过低", 4: "无"}),
    (0x84, 0x01): ("bed", {0: "离床", 1: "入床", 2: "无 / 实时模式"}),
    (0x84, 0x02): ("sleep", {0: "深睡", 1: "浅睡", 2: "清醒", 3: "无 / 离床或实时模式"}),
}


def result(name, value, label=None, unit="", quality="valid"):
    return dict(name=name, value=value, label=str(value) if label is None else label,
                unit=unit, quality=quality)


def decode(raw):
    """Validate the entire packet; reject corrupt frames before changing any state."""
    packet = bytes.fromhex(raw)
    if (len(packet) < 9 or packet[:2] != b"\x53\x59" or packet[-2:] != b"\x54\x43"
            or int.from_bytes(packet[4:6], "big") + 9 != len(packet)
            or sum(packet[:-3]) % 256 != packet[-3]):
        raise ValueError("Invalid radar packet")
    pair, data = (packet[2], packet[3]), packet[6:-3]
    if pair == (5, 1) and data == b"\x0f":
        return result("init", True, "初始化完成")
    if pair in ENUMS:
        name, values = ENUMS[pair]
        if len(data) != 1 or data[0] not in values:
            raise ValueError("Unknown enum value or payload length")
        label = values[data[0]]
        if name == "sleep":
            return result(name, data[0], f"原始状态 {data[0]}（版本待确认）", quality="raw_only")
        return result(name, data[0], label)
    if pair in ((0x80, 3), (0x81, 2), (0x85, 2), (0x84, 6)):
        if len(data) != 1:
            raise ValueError("Invalid numeric payload length")
        name, minimum, maximum, unit = {
            (0x80, 3): ("motion", 0, 100, "/ 100"),
            (0x81, 2): ("breath", 1, 35, "次/分"),
            (0x85, 2): ("heart", 60, 120, "次/分"),
            (0x84, 6): ("sleep_score", 0, 100, "分"),
        }[pair]
        value = data[0]
        quality = "valid" if minimum <= value <= maximum else "out_of_range"
        if name in ("breath", "heart") and value == 0:
            quality = "no_measurement"
        label = str(value) if quality == "valid" else (
            "尚无有效测量" if quality == "no_measurement" else "超出手册范围")
        return result(name, value, label, unit, quality)
    if pair in ((0x80, 4), (0x84, 3), (0x84, 4), (0x84, 5)):
        if len(data) != 2:
            raise ValueError("Invalid two-byte payload")
        name = {(0x80, 4): "distance", (0x84, 3): "awake_minutes",
                (0x84, 4): "light_minutes", (0x84, 5): "deep_minutes"}[pair]
        value = int.from_bytes(data, "big")
        quality = "no_measurement" if name == "distance" and value == 0 else "valid"
        return result(name, value, "尚无有效距离" if quality != "valid" else None,
                      "cm" if name == "distance" else "分钟", quality)
    if pair == (0x80, 5):
        # V0220 reports four bytes; V3.6 specifies six. Do not invent XYZ/signs.
        return result("coordinates", list(data), f"{len(data)} 字节：{data.hex(' ').upper()}",
                      quality="raw_only")
    if pair in ((0x81, 5), (0x85, 5)):
        if len(data) != 5:
            raise ValueError("Invalid waveform payload")
        return result("breath_wave" if pair[0] == 0x81 else "heart_wave",
                      [value - 128 for value in data], "收到 5 个波形点")
    if pair == (0x84, 0x0C):
        if len(data) != 8:
            raise ValueError("Invalid sleep summary payload")
        # Keep raw values; this firmware's sleep enum revision is not read back.
        return result("sleep_summary", dict(zip(
            ("presence", "sleep_raw", "average_breath", "average_heart", "turns",
             "large_motion_percent", "small_motion_percent", "apnea_raw"), data)),
            "收到睡眠综合报文（保留原始值）", quality="raw_only")
    return None
