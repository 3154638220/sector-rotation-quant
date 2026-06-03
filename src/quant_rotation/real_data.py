from __future__ import annotations

import csv
import json
import time
from dataclasses import dataclass
from datetime import date, datetime, timedelta
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


DEFAULT_MARKET_INDICES = [
    IndexInfo("sh000300", "CSI300"),
    IndexInfo("sh000985", "CSIAll"),
    IndexInfo("sz399006", "ChiNext"),
]


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
    market_close_path: Path | None = None
    market_symbols: dict[str, str] | None = None


@dataclass(frozen=True)
class BreadthDataSummary:
    output_dir: Path
    breadth_paths: dict[int, Path]
    manifest_path: Path
    start: date
    end: date
    rows: int
    industries: int
    windows: tuple[int, ...]
    min_stocks: int
    current_constituents: bool = True


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


def fetch_market_close_data(
    symbols: list[IndexInfo],
    start: date,
    end: date,
    *,
    ak: Any | None = None,
    progress: ProgressCallback | None = None,
) -> PriceData:
    if start > end:
        raise ValueError("start must be earlier than or equal to end")
    if not symbols:
        raise ValueError("symbols must contain at least one market index")

    ak = ak or _require_akshare()
    closes_by_asset: dict[str, dict[date, float]] = {}
    for number, info in enumerate(symbols, start=1):
        if progress:
            progress(
                f"Fetching market index {number}/{len(symbols)}: "
                f"{info.code} {info.name}"
            )
        closes_by_asset[info.name] = fetch_benchmark_close_data(
            info.code,
            start,
            end,
            ak=ak,
        )

    common_dates = sorted(set.intersection(*(set(values) for values in closes_by_asset.values())))
    if not common_dates:
        raise ValueError("No common trading dates found across market indices")

    closes = {
        asset: [values[day] for day in common_dates]
        for asset, values in closes_by_asset.items()
    }
    return PriceData(dates=common_dates, closes=closes)


def _normalize_stock_code(value: Any) -> str:
    raw = str(value).strip()
    if not raw:
        return ""
    raw = raw.split(".", 1)[0]
    if raw.endswith(".0"):
        raw = raw[:-2]
    digits = "".join(ch for ch in raw if ch.isdigit())
    return digits.zfill(6) if digits else raw


def fetch_sw_level1_constituents(
    *,
    ak: Any | None = None,
    industries: list[IndexInfo] | None = None,
    progress: ProgressCallback | None = None,
    request_interval: float = 0.0,
) -> dict[str, list[str]]:
    ak = ak or _require_akshare()
    infos = industries if industries is not None else sw_level1_index_infos(ak)
    if not infos:
        raise ValueError("industries must contain at least one SW index")

    result: dict[str, list[str]] = {}
    for number, info in enumerate(infos, start=1):
        if progress:
            progress(
                f"Fetching SW constituents {number}/{len(infos)}: "
                f"{info.code} {info.name}"
            )
        frame = ak.index_component_sw(symbol=info.code)
        stocks: list[str] = []
        for row in _records(frame):
            code = _normalize_stock_code(
                _cell(row, "证券代码", "股票代码", "成分券代码", "code", "symbol")
            )
            if code:
                stocks.append(code)
        deduped = list(dict.fromkeys(stocks))
        if not deduped:
            raise ValueError(f"No constituents returned for {info.code} {info.name}")
        result[info.name] = deduped
        if request_interval > 0 and number < len(infos):
            time.sleep(request_interval)
    return result


def fetch_stock_close_data(
    symbol: str,
    start: date,
    end: date,
    *,
    ak: Any | None = None,
    adjust: str = "",
) -> dict[date, float]:
    if start > end:
        raise ValueError("start must be earlier than or equal to end")

    ak = ak or _require_akshare()
    frame = ak.stock_zh_a_hist(
        symbol=_normalize_stock_code(symbol),
        period="daily",
        start_date=compact_date(start),
        end_date=compact_date(end),
        adjust=adjust,
    )
    closes: dict[date, float] = {}
    for row in _records(frame):
        day = _cell_date(_cell(row, "日期", "date"))
        if start <= day <= end:
            closes[day] = _cell_float(_cell(row, "收盘", "close"))
    return closes


def compute_industry_breadth(
    constituents_by_industry: dict[str, list[str]],
    stock_closes: dict[str, dict[date, float]],
    start: date,
    end: date,
    *,
    windows: tuple[int, ...] = (20, 60),
    min_stocks: int = 1,
) -> dict[int, PriceData]:
    if start > end:
        raise ValueError("start must be earlier than or equal to end")
    if not constituents_by_industry:
        raise ValueError("constituents_by_industry must not be empty")
    if not windows:
        raise ValueError("windows must contain at least one value")
    if any(window <= 0 for window in windows):
        raise ValueError("breadth windows must be positive")
    if min_stocks <= 0:
        raise ValueError("min_stocks must be positive")

    sorted_windows = tuple(sorted(dict.fromkeys(windows)))
    values_by_window: dict[int, dict[str, dict[date, float]]] = {
        window: {} for window in sorted_windows
    }

    for industry, stocks in constituents_by_industry.items():
        unique_stocks = list(dict.fromkeys(stocks))
        if not unique_stocks:
            raise ValueError(f"No constituents configured for industry {industry!r}")
        for window in sorted_windows:
            above_by_day: dict[date, int] = {}
            eligible_by_day: dict[date, int] = {}
            for stock in unique_stocks:
                series = stock_closes.get(stock)
                if not series:
                    continue
                ordered = sorted(series.items(), key=lambda item: item[0])
                for index, (day, close) in enumerate(ordered):
                    if day < start or day > end or index + 1 < window:
                        continue
                    trailing = [value for _, value in ordered[index + 1 - window : index + 1]]
                    moving_average = sum(trailing) / window
                    eligible_by_day[day] = eligible_by_day.get(day, 0) + 1
                    if close > moving_average:
                        above_by_day[day] = above_by_day.get(day, 0) + 1

            industry_values = {
                day: above_by_day.get(day, 0) / eligible
                for day, eligible in eligible_by_day.items()
                if eligible >= min_stocks
            }
            if not industry_values:
                raise ValueError(
                    f"No breadth values for {industry!r} with MA{window}; "
                    "check constituent stock data and min_stocks"
                )
            values_by_window[window][industry] = industry_values

    result: dict[int, PriceData] = {}
    for window, values_by_industry in values_by_window.items():
        common_dates = sorted(
            set.intersection(*(set(values) for values in values_by_industry.values()))
        )
        if not common_dates:
            raise ValueError(f"No common breadth dates found for MA{window}")
        closes = {
            industry: [values[day] for day in common_dates]
            for industry, values in values_by_industry.items()
        }
        result[window] = PriceData(dates=common_dates, closes=closes)
    return result


def fetch_sw_level1_breadth_data(
    start: date,
    end: date,
    *,
    ak: Any | None = None,
    industries: list[IndexInfo] | None = None,
    windows: tuple[int, ...] = (20, 60),
    min_stocks: int = 1,
    adjust: str = "",
    lookback_days: int | None = None,
    progress: ProgressCallback | None = None,
    request_interval: float = 0.0,
) -> dict[int, PriceData]:
    if start > end:
        raise ValueError("start must be earlier than or equal to end")
    if not windows:
        raise ValueError("windows must contain at least one value")

    ak = ak or _require_akshare()
    resolved_windows = tuple(sorted(dict.fromkeys(windows)))
    history_start = start - timedelta(
        days=lookback_days if lookback_days is not None else max(resolved_windows) * 3
    )
    constituents = fetch_sw_level1_constituents(
        ak=ak,
        industries=industries,
        progress=progress,
        request_interval=request_interval,
    )
    all_stocks = sorted({stock for stocks in constituents.values() for stock in stocks})
    stock_closes: dict[str, dict[date, float]] = {}
    for number, stock in enumerate(all_stocks, start=1):
        if progress:
            progress(f"Fetching stock {number}/{len(all_stocks)}: {stock}")
        closes = fetch_stock_close_data(
            stock,
            history_start,
            end,
            ak=ak,
            adjust=adjust,
        )
        if closes:
            stock_closes[stock] = closes
        if request_interval > 0 and number < len(all_stocks):
            time.sleep(request_interval)
    if not stock_closes:
        raise ValueError("No constituent stock close data returned")

    return compute_industry_breadth(
        constituents,
        stock_closes,
        start,
        end,
        windows=resolved_windows,
        min_stocks=min_stocks,
    )


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


def _write_market_close(path: Path, data: PriceData) -> None:
    _write_industry_close(path, data)


def _write_breadth(path: Path, data: PriceData) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.writer(handle)
        assets = data.assets
        writer.writerow(["date", *assets])
        for row_index, day in enumerate(data.dates):
            writer.writerow(
                [
                    day.isoformat(),
                    *[f"{data.closes[asset][row_index]:.6f}" for asset in assets],
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
    market_data: PriceData | None = None,
    benchmark_symbol: str,
    market_symbols: dict[str, str] | None = None,
    provider: str = "akshare",
) -> RealDataSummary:
    if amount_data is not None and amount_data.assets != industry_data.assets:
        raise ValueError("Amount data assets must match industry data assets")

    common_dates = sorted(set(industry_data.dates) & set(benchmark_closes))
    if amount_data is not None:
        common_dates = sorted(set(common_dates) & set(amount_data.dates))
    if market_data is not None:
        common_dates = sorted(set(common_dates) & set(market_data.dates))
    if not common_dates:
        raise ValueError(
            "No common dates found across industry, benchmark, amount, and market data"
        )

    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    aligned_industry_data = _slice_price_data(industry_data, common_dates)
    aligned_amount_data = _slice_price_data(amount_data, common_dates) if amount_data else None
    aligned_market_data = _slice_price_data(market_data, common_dates) if market_data else None

    industry_path = output_path / "industry_close.csv"
    amount_path = output_path / "industry_amount.csv" if aligned_amount_data else None
    market_path = output_path / "market_close.csv" if aligned_market_data else None
    benchmark_path = output_path / "benchmark_close.csv"
    manifest_path = output_path / "manifest.json"

    _write_industry_close(industry_path, aligned_industry_data)
    if aligned_amount_data and amount_path:
        _write_industry_amount(amount_path, aligned_amount_data)
    if aligned_market_data and market_path:
        _write_market_close(market_path, aligned_market_data)
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
            "market_close": market_path.name if market_path else None,
            "benchmark_close": benchmark_path.name,
        },
    }
    if market_symbols:
        manifest["market_symbols"] = market_symbols
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
        market_close_path=market_path,
        market_symbols=market_symbols,
    )


def write_breadth_data_files(
    output_dir: str | Path,
    breadth_by_window: dict[int, PriceData],
    *,
    min_stocks: int,
    provider: str = "akshare",
    current_constituents: bool = True,
) -> BreadthDataSummary:
    if not breadth_by_window:
        raise ValueError("breadth_by_window must not be empty")
    windows = tuple(sorted(breadth_by_window))
    assets = breadth_by_window[windows[0]].assets
    for window in windows:
        if window <= 0:
            raise ValueError("breadth windows must be positive")
        if breadth_by_window[window].assets != assets:
            raise ValueError("All breadth windows must share the same industries")

    common_dates = sorted(
        set.intersection(*(set(data.dates) for data in breadth_by_window.values()))
    )
    if not common_dates:
        raise ValueError("No common dates found across breadth windows")

    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    paths: dict[int, Path] = {}
    for window in windows:
        path = output_path / f"industry_breadth{window}.csv"
        _write_breadth(path, _slice_price_data(breadth_by_window[window], common_dates))
        paths[window] = path

    manifest_path = output_path / "breadth_manifest.json"
    manifest = {
        "provider": provider,
        "industry_source": "sw_level1_current_constituents",
        "current_constituents": current_constituents,
        "survivor_bias_warning": (
            "Breadth was computed from current SW index constituents. "
            "Use historical constituent snapshots before treating this as "
            "unbiased production research data."
        ),
        "start": common_dates[0].isoformat(),
        "end": common_dates[-1].isoformat(),
        "rows": len(common_dates),
        "industries": len(assets),
        "windows": list(windows),
        "min_stocks": min_stocks,
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "files": {f"industry_breadth{window}": paths[window].name for window in windows},
    }
    with manifest_path.open("w", encoding="utf-8") as handle:
        json.dump(manifest, handle, ensure_ascii=False, indent=2)

    return BreadthDataSummary(
        output_dir=output_path,
        breadth_paths=paths,
        manifest_path=manifest_path,
        start=common_dates[0],
        end=common_dates[-1],
        rows=len(common_dates),
        industries=len(assets),
        windows=windows,
        min_stocks=min_stocks,
        current_constituents=current_constituents,
    )


def fetch_and_write_breadth_data(
    output_dir: str | Path,
    start: date,
    end: date,
    *,
    industries: list[IndexInfo] | None = None,
    windows: tuple[int, ...] = (20, 60),
    min_stocks: int = 1,
    adjust: str = "",
    lookback_days: int | None = None,
    progress: ProgressCallback | None = None,
    request_interval: float = 0.0,
) -> BreadthDataSummary:
    ak = _require_akshare()
    breadth_by_window = fetch_sw_level1_breadth_data(
        start,
        end,
        ak=ak,
        industries=industries,
        windows=windows,
        min_stocks=min_stocks,
        adjust=adjust,
        lookback_days=lookback_days,
        progress=progress,
        request_interval=request_interval,
    )
    return write_breadth_data_files(
        output_dir,
        breadth_by_window,
        min_stocks=min_stocks,
    )


def fetch_and_write_real_data(
    output_dir: str | Path,
    start: date,
    end: date,
    *,
    benchmark_symbol: str = "sh000300",
    market_indices: list[IndexInfo] | None = None,
    progress: ProgressCallback | None = None,
    request_interval: float = 0.0,
) -> RealDataSummary:
    ak = _require_akshare()
    industry_market_data = fetch_sw_level1_market_data(
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
    resolved_market_indices = market_indices if market_indices is not None else DEFAULT_MARKET_INDICES
    style_market_data = None
    market_symbols = None
    if resolved_market_indices:
        style_market_data = fetch_market_close_data(
            resolved_market_indices,
            start,
            end,
            ak=ak,
            progress=progress,
        )
        market_symbols = {
            info.name: info.code for info in resolved_market_indices
        }
    return write_real_data_files(
        output_dir,
        industry_market_data.close,
        benchmark_closes,
        amount_data=industry_market_data.amount,
        market_data=style_market_data,
        benchmark_symbol=benchmark_symbol,
        market_symbols=market_symbols,
    )
