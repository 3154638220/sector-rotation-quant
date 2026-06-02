from __future__ import annotations

import csv
import json
import time
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any, Callable

from .models import PriceData


SW_LEVEL1_INDICES = [
    ("801010", "农林牧渔"),
    ("801030", "基础化工"),
    ("801040", "钢铁"),
    ("801050", "有色金属"),
    ("801080", "电子"),
    ("801110", "家用电器"),
    ("801120", "食品饮料"),
    ("801130", "纺织服饰"),
    ("801140", "轻工制造"),
    ("801150", "医药生物"),
    ("801160", "公用事业"),
    ("801170", "交通运输"),
    ("801180", "房地产"),
    ("801200", "商贸零售"),
    ("801210", "社会服务"),
    ("801230", "综合"),
    ("801710", "建筑材料"),
    ("801720", "建筑装饰"),
    ("801730", "电力设备"),
    ("801740", "国防军工"),
    ("801750", "计算机"),
    ("801760", "传媒"),
    ("801770", "通信"),
    ("801780", "银行"),
    ("801790", "非银金融"),
    ("801880", "汽车"),
    ("801890", "机械设备"),
    ("801950", "煤炭"),
    ("801960", "石油石化"),
    ("801970", "环保"),
    ("801980", "美容护理"),
]


@dataclass(frozen=True)
class IndexInfo:
    code: str
    name: str


@dataclass(frozen=True)
class RealDataSummary:
    output_dir: Path
    industry_close_path: Path
    industry_amount_path: Path | None
    benchmark_close_path: Path
    manifest_path: Path
    start: date
    end: date
    rows: int
    industries: int
    benchmark_symbol: str


@dataclass(frozen=True)
class IndustryMarketData:
    close: PriceData
    amount: PriceData | None


ProgressCallback = Callable[[str], None]


def parse_date(value: str | date | datetime) -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value

    raw = value.strip()
    if len(raw) == 8 and raw.isdigit():
        return date(int(raw[:4]), int(raw[4:6]), int(raw[6:8]))
    return date.fromisoformat(raw)


def compact_date(value: date) -> str:
    return value.strftime("%Y%m%d")


def _require_akshare() -> Any:
    try:
        import akshare as ak
    except ModuleNotFoundError as exc:
        raise RuntimeError(
            "AKShare is required for real data. Install it with "
            "`python -m pip install -e .[real-data]` or `python -m pip install akshare`."
        ) from exc
    return ak


def _records(frame: Any) -> list[dict[str, Any]]:
    if frame is None:
        return []
    if hasattr(frame, "to_dict"):
        return list(frame.to_dict("records"))
    return list(frame)


def _cell(row: dict[str, Any], *names: str) -> Any:
    for name in names:
        if name in row:
            return row[name]
    return None


def _cell_date(value: Any) -> date:
    if value is None:
        raise ValueError("Missing date value")
    if hasattr(value, "date") and not isinstance(value, date):
        return value.date()
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return parse_date(str(value)[:10])


def _cell_float(value: Any) -> float:
    if value is None:
        raise ValueError("Missing numeric value")
    if isinstance(value, str):
        value = value.replace(",", "").strip()
    return float(value)


def sw_level1_index_infos(ak: Any | None = None) -> list[IndexInfo]:
    ak = ak or _require_akshare()
    fallback = [IndexInfo(code, name) for code, name in SW_LEVEL1_INDICES]

    try:
        frame = ak.index_realtime_sw(symbol="一级行业")
    except Exception:
        return fallback

    infos: list[IndexInfo] = []
    for row in _records(frame):
        code = str(_cell(row, "指数代码", "代码", "symbol") or "").strip()
        name = str(_cell(row, "指数名称", "名称", "name") or "").strip()
        if code and name:
            infos.append(IndexInfo(code, name))

    return infos if len(infos) >= 25 else fallback


def fetch_sw_level1_close_data(
    start: date,
    end: date,
    *,
    ak: Any | None = None,
    progress: ProgressCallback | None = None,
    request_interval: float = 0.0,
) -> PriceData:
    return fetch_sw_level1_market_data(
        start,
        end,
        ak=ak,
        progress=progress,
        request_interval=request_interval,
        require_amount=False,
    ).close


def fetch_sw_level1_market_data(
    start: date,
    end: date,
    *,
    ak: Any | None = None,
    progress: ProgressCallback | None = None,
    request_interval: float = 0.0,
    require_amount: bool = True,
) -> IndustryMarketData:
    if start > end:
        raise ValueError("start must be earlier than or equal to end")

    ak = ak or _require_akshare()
    infos = sw_level1_index_infos(ak)
    closes_by_asset: dict[str, dict[date, float]] = {}
    amounts_by_asset: dict[str, dict[date, float]] = {}

    for number, info in enumerate(infos, start=1):
        if progress:
            progress(f"Fetching SW index {number}/{len(infos)}: {info.code} {info.name}")
        frame = ak.index_hist_sw(symbol=info.code, period="day")
        rows = _records(frame)
        asset_closes: dict[date, float] = {}
        asset_amounts: dict[date, float] = {}
        for row in rows:
            day = _cell_date(_cell(row, "日期", "date"))
            if start <= day <= end:
                close = _cell_float(_cell(row, "收盘", "close"))
                asset_closes[day] = close
                raw_amount = _cell(
                    row,
                    "成交额",
                    "成交金额",
                    "amount",
                    "成交量",
                    "volume",
                    "vol",
                )
                if raw_amount is not None:
                    asset_amounts[day] = _cell_float(raw_amount)
        if not asset_closes:
            raise ValueError(f"No SW index data returned for {info.code} {info.name}")
        closes_by_asset[info.name] = asset_closes
        if asset_amounts:
            amounts_by_asset[info.name] = asset_amounts
        elif require_amount:
            raise ValueError(
                f"No SW index amount or volume data returned for {info.code} {info.name}"
            )
        if request_interval > 0 and number < len(infos):
            time.sleep(request_interval)

    common_dates = sorted(set.intersection(*(set(values) for values in closes_by_asset.values())))
    if not common_dates:
        raise ValueError("No common trading dates found across SW level-1 indices")

    amount_data = None
    if amounts_by_asset:
        if len(amounts_by_asset) != len(closes_by_asset):
            if require_amount:
                raise ValueError("Amount data is missing for one or more SW indices")
        else:
            amount_common_dates = sorted(
                set(common_dates)
                & set.intersection(*(set(values) for values in amounts_by_asset.values()))
            )
            if not amount_common_dates:
                if require_amount:
                    raise ValueError("No common amount dates found across SW level-1 indices")
            else:
                common_dates = amount_common_dates
                amounts = {
                    asset: [values[day] for day in common_dates]
                    for asset, values in amounts_by_asset.items()
                }
                amount_data = PriceData(dates=common_dates, closes=amounts)

    closes = {
        asset: [values[day] for day in common_dates]
        for asset, values in closes_by_asset.items()
    }
    return IndustryMarketData(
        close=PriceData(dates=common_dates, closes=closes),
        amount=amount_data,
    )


def fetch_benchmark_close_data(
    symbol: str,
    start: date,
    end: date,
    *,
    ak: Any | None = None,
) -> dict[date, float]:
    if start > end:
        raise ValueError("start must be earlier than or equal to end")

    ak = ak or _require_akshare()
    frame = ak.stock_zh_index_daily_tx(
        symbol=symbol,
        start_date=compact_date(start),
        end_date=compact_date(end),
    )
    closes: dict[date, float] = {}
    for row in _records(frame):
        day = _cell_date(_cell(row, "date", "日期"))
        if start <= day <= end:
            closes[day] = _cell_float(_cell(row, "close", "收盘"))
    if not closes:
        raise ValueError(f"No benchmark data returned for {symbol}")
    return closes


def _write_industry_close(path: Path, data: PriceData) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.writer(handle)
        assets = data.assets
        writer.writerow(["date", *assets])
        for row_index, day in enumerate(data.dates):
            writer.writerow(
                [
                    day.isoformat(),
                    *[f"{data.closes[asset][row_index]:.4f}" for asset in assets],
                ]
            )


def _write_benchmark_close(path: Path, dates: list[date], closes: dict[date, float]) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["date", "close"])
        for day in dates:
            writer.writerow([day.isoformat(), f"{closes[day]:.4f}"])


def _write_industry_amount(path: Path, data: PriceData) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.writer(handle)
        assets = data.assets
        writer.writerow(["date", *assets])
        for row_index, day in enumerate(data.dates):
            writer.writerow(
                [
                    day.isoformat(),
                    *[f"{data.closes[asset][row_index]:.2f}" for asset in assets],
                ]
            )


def _slice_price_data(data: PriceData, dates: list[date]) -> PriceData:
    position_by_date = {day: index for index, day in enumerate(data.dates)}
    closes = {
        asset: [values[position_by_date[day]] for day in dates]
        for asset, values in data.closes.items()
    }
    return PriceData(dates=dates, closes=closes)


def write_real_data_files(
    output_dir: str | Path,
    industry_data: PriceData,
    benchmark_closes: dict[date, float],
    *,
    amount_data: PriceData | None = None,
    benchmark_symbol: str,
    provider: str = "akshare",
) -> RealDataSummary:
    if amount_data is not None and amount_data.assets != industry_data.assets:
        raise ValueError("Amount data assets must match industry data assets")

    common_dates = sorted(set(industry_data.dates) & set(benchmark_closes))
    if amount_data is not None:
        common_dates = sorted(set(common_dates) & set(amount_data.dates))
    if not common_dates:
        raise ValueError("No common dates found across industry, benchmark, and amount data")

    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    aligned_industry_data = _slice_price_data(industry_data, common_dates)
    aligned_amount_data = _slice_price_data(amount_data, common_dates) if amount_data else None

    industry_path = output_path / "industry_close.csv"
    amount_path = output_path / "industry_amount.csv" if aligned_amount_data else None
    benchmark_path = output_path / "benchmark_close.csv"
    manifest_path = output_path / "manifest.json"

    _write_industry_close(industry_path, aligned_industry_data)
    if aligned_amount_data and amount_path:
        _write_industry_amount(amount_path, aligned_amount_data)
    _write_benchmark_close(benchmark_path, common_dates, benchmark_closes)

    manifest = {
        "provider": provider,
        "industry_source": "sw_level1_index",
        "benchmark_symbol": benchmark_symbol,
        "start": common_dates[0].isoformat(),
        "end": common_dates[-1].isoformat(),
        "rows": len(common_dates),
        "industries": len(aligned_industry_data.assets),
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "files": {
            "industry_close": industry_path.name,
            "industry_amount": amount_path.name if amount_path else None,
            "benchmark_close": benchmark_path.name,
        },
    }
    with manifest_path.open("w", encoding="utf-8") as handle:
        json.dump(manifest, handle, ensure_ascii=False, indent=2)

    return RealDataSummary(
        output_dir=output_path,
        industry_close_path=industry_path,
        industry_amount_path=amount_path,
        benchmark_close_path=benchmark_path,
        manifest_path=manifest_path,
        start=common_dates[0],
        end=common_dates[-1],
        rows=len(common_dates),
        industries=len(aligned_industry_data.assets),
        benchmark_symbol=benchmark_symbol,
    )


def fetch_and_write_real_data(
    output_dir: str | Path,
    start: date,
    end: date,
    *,
    benchmark_symbol: str = "sh000300",
    progress: ProgressCallback | None = None,
    request_interval: float = 0.0,
) -> RealDataSummary:
    ak = _require_akshare()
    market_data = fetch_sw_level1_market_data(
        start,
        end,
        ak=ak,
        progress=progress,
        request_interval=request_interval,
        require_amount=False,
    )
    if progress:
        progress(f"Fetching benchmark: {benchmark_symbol}")
    benchmark_closes = fetch_benchmark_close_data(
        benchmark_symbol,
        start,
        end,
        ak=ak,
    )
    return write_real_data_files(
        output_dir,
        market_data.close,
        benchmark_closes,
        amount_data=market_data.amount,
        benchmark_symbol=benchmark_symbol,
    )
