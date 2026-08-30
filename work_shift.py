"""
桥桥排班计算模块。
固定三天周期：早班、晚班、晚班。
基准日 2026-08-30 = 晚班（cycle index 2，即周期里的第二个晚班）。
纯函数，无 IO，无数据库。
"""
from __future__ import annotations

from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

LOCAL_TZ = ZoneInfo("Asia/Shanghai")

# 周期定义 —— index 0/1/2
_CYCLE = [
    {"name": "早班", "start": "06:45", "end": "14:30"},
    {"name": "晚班", "start": "14:00", "end": "21:30"},
    {"name": "晚班", "start": "14:00", "end": "21:30"},
]
_CYCLE_LEN = len(_CYCLE)

# 基准日和它在周期里的 index
_ANCHOR_DATE = date(2026, 8, 30)
_ANCHOR_INDEX = 2  # 晚班（周期里第二个晚班）


def shift_for_date(d: date) -> dict:
    """返回某一天的班次信息。"""
    delta_days = (d - _ANCHOR_DATE).days
    idx = (_ANCHOR_INDEX + delta_days) % _CYCLE_LEN
    entry = _CYCLE[idx]
    return {
        "date": d.isoformat(),
        "shift": entry["name"],
        "start": entry["start"],
        "end": entry["end"],
    }


def shift_range(start: date, days: int = 7) -> list[dict]:
    """返回连续多天的班次。"""
    return [shift_for_date(start + timedelta(days=i)) for i in range(days)]


def today_shift_summary() -> str:
    """给 gateway 注入用的一行摘要：今天+明天的排班。"""
    now = datetime.now(LOCAL_TZ)
    today = now.date()
    tomorrow = today + timedelta(days=1)
    t = shift_for_date(today)
    m = shift_for_date(tomorrow)
    weekday_names = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]
    today_wd = weekday_names[today.weekday()]
    tomorrow_wd = weekday_names[tomorrow.weekday()]

    # 判断桥桥当前状态
    hour_min = now.hour * 60 + now.minute
    t_start = int(t["start"].split(":")[0]) * 60 + int(t["start"].split(":")[1])
    t_end = int(t["end"].split(":")[0]) * 60 + int(t["end"].split(":")[1])

    if t_start <= hour_min <= t_end:
        status = f"桥桥现在正在上{t['shift']}（{t['start']}–{t['end']}）"
    elif hour_min < t_start:
        status = f"桥桥今天{t['shift']}，还没到上班时间（{t['start']}–{t['end']}）"
    else:
        status = f"桥桥今天{t['shift']}已下班（{t['start']}–{t['end']}）"

    return (
        f"桥桥排班｜今天 {today.isoformat()}（{today_wd}）{t['shift']} {t['start']}–{t['end']}，"
        f"明天 {tomorrow.isoformat()}（{tomorrow_wd}）{m['shift']} {m['start']}–{m['end']}。"
        f"{status}。"
    )


if __name__ == "__main__":
    # 自检：8/30=晚, 8/31=早, 9/1=晚, 9/2=晚, 9/3=早
    assert shift_for_date(date(2026, 8, 30))["shift"] == "晚班"
    assert shift_for_date(date(2026, 8, 31))["shift"] == "早班"
    assert shift_for_date(date(2026, 9, 1))["shift"] == "晚班"
    assert shift_for_date(date(2026, 9, 2))["shift"] == "晚班"
    assert shift_for_date(date(2026, 9, 3))["shift"] == "早班"
    # 往回
    assert shift_for_date(date(2026, 8, 29))["shift"] == "晚班"
    assert shift_for_date(date(2026, 8, 28))["shift"] == "早班"
    print("ALL OK")
    print(today_shift_summary())
    for info in shift_range(date(2026, 8, 28), 10):
        print(info)
