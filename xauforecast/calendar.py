"""経済イベントの組み込みカレンダー。

FOMC の政策決定日（2 日間会合の 2 日目、発表は 14:00 米東部時間）。
出典: 2026 年は複数の公開カレンダーで一致を確認（Fed の公式ページ
https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm が一次情報）。
2024・2025 年は公開スケジュールに基づく。利用前に公式ページでの確認を推奨。
臨時会合は含まない。これより前の期間や他の指標（雇用統計・CPI 等）は --events で CSV を指定する。
"""
from __future__ import annotations

import pandas as pd

FOMC_DECISION_DATES = [
    # 2024
    "2024-01-31", "2024-03-20", "2024-05-01", "2024-06-12", "2024-07-31", "2024-09-18", "2024-11-07", "2024-12-18",
    # 2025
    "2025-01-29", "2025-03-19", "2025-05-07", "2025-06-18", "2025-07-30", "2025-09-17", "2025-10-29", "2025-12-10",
    # 2026
    "2026-01-28", "2026-03-18", "2026-04-29", "2026-06-17", "2026-07-29", "2026-09-16", "2026-10-28", "2026-12-09",
]


def fomc_times() -> pd.DatetimeIndex:
    """FOMC 声明の発表時刻（UTC）。"""
    t = pd.DatetimeIndex([pd.Timestamp(d + " 14:00") for d in FOMC_DECISION_DATES])
    return t.tz_localize("America/New_York").tz_convert("UTC")
