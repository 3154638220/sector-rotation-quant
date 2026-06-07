from __future__ import annotations

import calendar
import csv
import io
import json
import time
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Callable, Iterable

from .models import PriceData, StockIndustryMap


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

SW_2000_LEVEL1_INDICES = [
    ("801010", "农林牧渔"),
    ("801020", "采掘"),
    ("801030", "化工"),
    ("801040", "黑色金属"),
    ("801050", "有色金属"),
    ("801060", "建筑建材"),
    ("801070", "机械设备"),
    ("801080", "电子"),
    ("801090", "交运设备"),
    ("801100", "信息设备"),
    ("801110", "家用电器"),
    ("801120", "食品饮料"),
    ("801130", "纺织服装"),
    ("801140", "轻工制造"),
    ("801150", "医药生物"),
    ("801160", "公用事业"),
    ("801170", "交通运输"),
    ("801180", "房地产"),
    ("801190", "金融服务"),
    ("801200", "商业贸易"),
    ("801210", "餐饮旅游"),
    ("801220", "信息服务"),
    ("801230", "综合"),
]

SW_2014_LEVEL1_INDICES = [
    ("801010", "农林牧渔"),
    ("801020", "采掘"),
    ("801030", "化工"),
    ("801040", "钢铁"),
    ("801050", "有色金属"),
    ("801080", "电子"),
    ("801110", "家用电器"),
    ("801120", "食品饮料"),
    ("801130", "纺织服装"),
    ("801140", "轻工制造"),
    ("801150", "医药生物"),
    ("801160", "公用事业"),
    ("801170", "交通运输"),
    ("801180", "房地产"),
    ("801200", "商业贸易"),
    ("801210", "休闲服务"),
    ("801230", "综合"),
    ("801710", "建筑材料"),
    ("801720", "建筑装饰"),
    ("801730", "电气设备"),
    ("801740", "国防军工"),
    ("801750", "计算机"),
    ("801760", "传媒"),
    ("801770", "通信"),
    ("801780", "银行"),
    ("801790", "非银金融"),
    ("801880", "汽车"),
    ("801890", "机械设备"),
]


@dataclass(frozen=True)
class IndexInfo:
    code: str
    name: str


SW_LEVEL1_UNIVERSES = {
    "current": tuple(SW_LEVEL1_INDICES),
    "sw2021": tuple(SW_LEVEL1_INDICES),
    "sw2014": tuple(SW_2014_LEVEL1_INDICES),
    "sw2000": tuple(SW_2000_LEVEL1_INDICES),
}


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
class StockDataSummary:
    output_dir: Path
    stock_close_path: Path
    stock_amount_path: Path | None
    stock_industry_map_path: Path
    manifest_path: Path
    start: date
    end: date
    rows: int
    stocks: int
    industries: int
    current_constituents: bool = True


@dataclass(frozen=True)
class IndustryMarketData:
    close: PriceData
    amount: PriceData | None


@dataclass(frozen=True)
class StockMarketData:
    close: PriceData
    amount: PriceData | None
    industry_map: StockIndustryMap | dict[str, str]


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


def sw_level1_universe_names() -> tuple[str, ...]:
    return tuple(SW_LEVEL1_UNIVERSES)


def _index_infos_from_pairs(pairs: tuple[tuple[str, str], ...]) -> list[IndexInfo]:
    return [IndexInfo(code, name) for code, name in pairs]


def sw_level1_index_infos(
    ak: Any | None = None,
    *,
    universe: str = "current",
) -> list[IndexInfo]:
    normalized_universe = universe.strip().lower()
    if normalized_universe not in SW_LEVEL1_UNIVERSES:
        supported = ", ".join(sw_level1_universe_names())
        raise ValueError(
            f"Unsupported SW level-1 industry universe {universe!r}; "
            f"expected one of: {supported}"
        )

    if normalized_universe != "current":
        return _index_infos_from_pairs(SW_LEVEL1_UNIVERSES[normalized_universe])

    ak = ak or _require_akshare()
    fallback = _index_infos_from_pairs(SW_LEVEL1_UNIVERSES["sw2021"])

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
    industries: list[IndexInfo] | None = None,
    industry_universe: str = "current",
    progress: ProgressCallback | None = None,
    request_interval: float = 0.0,
) -> PriceData:
    return fetch_sw_level1_market_data(
        start,
        end,
        ak=ak,
        industries=industries,
        industry_universe=industry_universe,
        progress=progress,
        request_interval=request_interval,
        require_amount=False,
    ).close


def fetch_sw_level1_market_data(
    start: date,
    end: date,
    *,
    ak: Any | None = None,
    industries: list[IndexInfo] | None = None,
    industry_universe: str = "current",
    progress: ProgressCallback | None = None,
    request_interval: float = 0.0,
    require_amount: bool = True,
) -> IndustryMarketData:
    if start > end:
        raise ValueError("start must be earlier than or equal to end")

    ak = ak or _require_akshare()
    infos = (
        industries
        if industries is not None
        else sw_level1_index_infos(ak, universe=industry_universe)
    )
    if not infos:
        raise ValueError("industries must contain at least one SW index")
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


def _tx_stock_code(symbol: str) -> str:
    code = _normalize_stock_code(symbol)
    if not code:
        return code
    prefix = "sh" if code.startswith("6") else "sz"
    return prefix + code


def fetch_stock_daily_data(
    symbol: str,
    start: date,
    end: date,
    *,
    ak: Any | None = None,
    adjust: str = "",
) -> tuple[dict[date, float], dict[date, float]]:
    if start > end:
        raise ValueError("start must be earlier than or equal to end")

    ak = ak or _require_akshare()
    if hasattr(ak, "stock_zh_a_hist_tx"):
        frame = ak.stock_zh_a_hist_tx(
            symbol=_tx_stock_code(symbol),
            start_date=compact_date(start),
            end_date=compact_date(end),
            adjust=adjust,
        )
        date_columns = ("date",)
        close_columns = ("close",)
        amount_columns = ("amount",)
    else:
        frame = ak.stock_zh_a_hist(
            symbol=_normalize_stock_code(symbol),
            period="daily",
            start_date=compact_date(start),
            end_date=compact_date(end),
            adjust=adjust,
        )
        date_columns = ("日期", "date")
        close_columns = ("收盘", "close")
        amount_columns = ("成交额", "amount")
    closes: dict[date, float] = {}
    amounts: dict[date, float] = {}
    for row in _records(frame):
        day = _cell_date(_cell(row, *date_columns))
        if start <= day <= end:
            closes[day] = _cell_float(_cell(row, *close_columns))
            raw_amount = _cell(row, *amount_columns)
            if raw_amount is not None:
                amounts[day] = _cell_float(raw_amount)
    return closes, amounts


def _stock_map_from_constituents(
    constituents_by_industry: dict[str, list[str]],
) -> dict[str, str]:
    stock_to_industry: dict[str, str] = {}
    for industry, stocks in constituents_by_industry.items():
        for stock in stocks:
            previous = stock_to_industry.get(stock)
            if previous is not None and previous != industry:
                raise ValueError(
                    f"Stock {stock} appears in multiple industries: "
                    f"{previous}, {industry}"
                )
            stock_to_industry[stock] = industry
    if not stock_to_industry:
        raise ValueError("No stocks found in constituent map")
    return stock_to_industry


def _limit_constituents_per_industry(
    constituents_by_industry: dict[str, list[str]],
    max_stocks_per_industry: int | None,
) -> dict[str, list[str]]:
    if max_stocks_per_industry is None:
        return constituents_by_industry
    if max_stocks_per_industry <= 0:
        raise ValueError("max_stocks_per_industry must be positive")
    return {
        industry: stocks[:max_stocks_per_industry]
        for industry, stocks in constituents_by_industry.items()
    }


def _stock_map_all_stocks(stock_map: StockIndustryMap | dict[str, str]) -> set[str]:
    if isinstance(stock_map, StockIndustryMap):
        return stock_map.all_stocks
    return set(stock_map)


def _filter_stock_industry_map_to_available_stocks(
    stock_map: StockIndustryMap | dict[str, str],
    available_stocks: Iterable[str],
) -> StockIndustryMap | dict[str, str]:
    available = set(available_stocks)
    if isinstance(stock_map, StockIndustryMap):
        snapshots = {
            snapshot_date: {
                stock: industry
                for stock, industry in mapping.items()
                if stock in available
            }
            for snapshot_date, mapping in stock_map.snapshots.items()
        }
        snapshots = {
            snapshot_date: mapping
            for snapshot_date, mapping in snapshots.items()
            if mapping
        }
        if not snapshots:
            raise ValueError("stock industry map has no stocks in stock close data")
        return StockIndustryMap(snapshots)

    filtered = {
        stock: industry
        for stock, industry in stock_map.items()
        if stock in available
    }
    if not filtered:
        raise ValueError("stock industry map has no stocks in stock close data")
    return filtered


def _limit_stock_industry_map_per_industry(
    stock_map: StockIndustryMap,
    max_stocks_per_industry: int | None,
) -> StockIndustryMap:
    if max_stocks_per_industry is None:
        return stock_map
    if max_stocks_per_industry <= 0:
        raise ValueError("max_stocks_per_industry must be positive")

    snapshots: dict[date, dict[str, str]] = {}
    for snapshot_date, mapping in stock_map.snapshots.items():
        constituents: dict[str, list[str]] = {}
        for stock, industry in mapping.items():
            constituents.setdefault(industry, []).append(stock)
        limited = _limit_constituents_per_industry(
            {
                industry: sorted(stocks)
                for industry, stocks in constituents.items()
            },
            max_stocks_per_industry,
        )
        snapshots[snapshot_date] = _stock_map_from_constituents(limited)
    return StockIndustryMap(snapshots)


def _build_stock_market_data_from_daily_series(
    closes_by_stock: dict[str, dict[date, float]],
    amounts_by_stock: dict[str, dict[date, float]],
    stock_industry_map: StockIndustryMap | dict[str, str],
) -> StockMarketData:
    if not closes_by_stock:
        raise ValueError("No stock close data returned")

    all_dates: set[date] = set()
    for values in closes_by_stock.values():
        all_dates |= set(values)
    common_dates = sorted(all_dates)
    if not common_dates:
        raise ValueError("No trading dates found across stocks")

    for stock, values in closes_by_stock.items():
        if not values:
            continue
        sorted_stock_dates = sorted(values)
        first_close = values[sorted_stock_dates[0]]
        filled: dict[date, float] = {}
        last_close = first_close
        for day in common_dates:
            if day in values:
                last_close = values[day]
            filled[day] = last_close
        closes_by_stock[stock] = filled

    for stock, values in amounts_by_stock.items():
        if not values:
            continue
        sorted_stock_dates = sorted(values)
        first_amount = values[sorted_stock_dates[0]]
        filled: dict[date, float] = {}
        last_amount = first_amount
        for day in common_dates:
            if day in values:
                last_amount = values[day]
                filled[day] = last_amount
            else:
                filled[day] = 0.0
        amounts_by_stock[stock] = filled

    amount_data = None
    if len(amounts_by_stock) == len(closes_by_stock):
        amount_common_dates = sorted(
            set(common_dates)
            & set.intersection(*(set(values) for values in amounts_by_stock.values()))
        )
        if amount_common_dates:
            common_dates = amount_common_dates
            amount_data = PriceData(
                dates=common_dates,
                closes={
                    stock: [values[day] for day in common_dates]
                    for stock, values in amounts_by_stock.items()
                },
            )

    close_data = PriceData(
        dates=common_dates,
        closes={
            stock: [values[day] for day in common_dates]
            for stock, values in closes_by_stock.items()
        },
    )
    available_map = _filter_stock_industry_map_to_available_stocks(
        stock_industry_map,
        close_data.closes,
    )
    return StockMarketData(
        close=close_data,
        amount=amount_data,
        industry_map=available_map,
    )


def fetch_sw_level1_stock_data(
    start: date,
    end: date,
    *,
    ak: Any | None = None,
    industries: list[IndexInfo] | None = None,
    adjust: str = "",
    max_stocks_per_industry: int | None = None,
    progress: ProgressCallback | None = None,
    request_interval: float = 0.0,
) -> StockMarketData:
    if start > end:
        raise ValueError("start must be earlier than or equal to end")

    ak = ak or _require_akshare()
    constituents = fetch_sw_level1_constituents(
        ak=ak,
        industries=industries,
        progress=progress,
        request_interval=request_interval,
    )
    constituents = _limit_constituents_per_industry(
        constituents,
        max_stocks_per_industry,
    )
    stock_industry_map = _stock_map_from_constituents(constituents)
    all_stocks = sorted(stock_industry_map)

    closes_by_stock: dict[str, dict[date, float]] = {}
    amounts_by_stock: dict[str, dict[date, float]] = {}
    for number, stock in enumerate(all_stocks, start=1):
        if progress:
            progress(f"Fetching stock {number}/{len(all_stocks)}: {stock}")
        try:
            closes, amounts = fetch_stock_daily_data(
                stock,
                start,
                end,
                ak=ak,
                adjust=adjust,
            )
        except Exception:
            import traceback
            traceback.print_exc()
            closes = {}
            amounts = {}
        if closes:
            closes_by_stock[stock] = closes
            if amounts:
                amounts_by_stock[stock] = amounts
        if request_interval > 0 and number < len(all_stocks):
            time.sleep(request_interval)
    return _build_stock_market_data_from_daily_series(
        closes_by_stock,
        amounts_by_stock,
        stock_industry_map,
    )


def fetch_sw_level1_stock_data_from_snapshot_map(
    stock_map: StockIndustryMap,
    start: date,
    end: date,
    *,
    ak: Any | None = None,
    adjust: str = "",
    max_stocks_per_industry: int | None = None,
    progress: ProgressCallback | None = None,
    request_interval: float = 0.0,
) -> StockMarketData:
    if start > end:
        raise ValueError("start must be earlier than or equal to end")

    ak = ak or _require_akshare()
    resolved_map = _limit_stock_industry_map_per_industry(
        stock_map,
        max_stocks_per_industry,
    )
    all_stocks = sorted(resolved_map.all_stocks)
    if not all_stocks:
        raise ValueError("historical stock map contains no stocks")

    closes_by_stock: dict[str, dict[date, float]] = {}
    amounts_by_stock: dict[str, dict[date, float]] = {}
    for number, stock in enumerate(all_stocks, start=1):
        if progress:
            progress(f"Fetching historical-map stock {number}/{len(all_stocks)}: {stock}")
        try:
            closes, amounts = fetch_stock_daily_data(
                stock,
                start,
                end,
                ak=ak,
                adjust=adjust,
            )
        except Exception:
            import traceback
            traceback.print_exc()
            closes = {}
            amounts = {}
        if closes:
            closes_by_stock[stock] = closes
            if amounts:
                amounts_by_stock[stock] = amounts
        if request_interval > 0 and number < len(all_stocks):
            time.sleep(request_interval)

    return _build_stock_market_data_from_daily_series(
        closes_by_stock,
        amounts_by_stock,
        resolved_map,
    )


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


def compute_historical_industry_breadth(
    stock_map: StockIndustryMap,
    stock_closes: dict[str, dict[date, float]],
    start: date,
    end: date,
    *,
    windows: tuple[int, ...] = (20, 60),
    min_stocks: int = 1,
) -> dict[int, PriceData]:
    if start > end:
        raise ValueError("start must be earlier than or equal to end")
    if not stock_closes:
        raise ValueError("stock_closes must not be empty")
    if not windows:
        raise ValueError("windows must contain at least one value")
    if any(window <= 0 for window in windows):
        raise ValueError("breadth windows must be positive")
    if min_stocks <= 0:
        raise ValueError("min_stocks must be positive")

    sorted_windows = tuple(sorted(dict.fromkeys(windows)))
    industries = sorted(
        {
            industry
            for mapping in stock_map.snapshots.values()
            for industry in mapping.values()
        }
    )
    if not industries:
        raise ValueError("stock_map must contain at least one industry")

    above_by_window_stock: dict[int, dict[str, dict[date, bool]]] = {
        window: {} for window in sorted_windows
    }
    candidate_dates: set[date] = set()
    for stock, series in stock_closes.items():
        if not series:
            continue
        ordered = sorted(series.items(), key=lambda item: item[0])
        for window in sorted_windows:
            signals: dict[date, bool] = {}
            for index, (day, close) in enumerate(ordered):
                if day < start or day > end or index + 1 < window:
                    continue
                trailing = [
                    value
                    for _, value in ordered[index + 1 - window : index + 1]
                ]
                moving_average = sum(trailing) / window
                signals[day] = close > moving_average
                candidate_dates.add(day)
            if signals:
                above_by_window_stock[window][stock] = signals

    values_by_window: dict[int, dict[str, dict[date, float]]] = {
        window: {industry: {} for industry in industries}
        for window in sorted_windows
    }
    for day in sorted(candidate_dates):
        mapping = stock_map.get_map_at(day)
        for window in sorted_windows:
            above_counts: dict[str, int] = {industry: 0 for industry in industries}
            eligible_counts: dict[str, int] = {industry: 0 for industry in industries}
            stock_signals = above_by_window_stock[window]
            for stock, industry in mapping.items():
                signal = stock_signals.get(stock, {}).get(day)
                if signal is None:
                    continue
                eligible_counts[industry] = eligible_counts.get(industry, 0) + 1
                if signal:
                    above_counts[industry] = above_counts.get(industry, 0) + 1

            for industry, eligible in eligible_counts.items():
                if eligible >= min_stocks:
                    values_by_window[window][industry][day] = (
                        above_counts.get(industry, 0) / eligible
                    )

    result: dict[int, PriceData] = {}
    for window, values_by_industry in values_by_window.items():
        empty_industries = [
            industry
            for industry, values in values_by_industry.items()
            if not values
        ]
        if empty_industries:
            preview = ", ".join(empty_industries[:5])
            raise ValueError(
                f"No historical breadth values for MA{window}: {preview}"
            )
        common_dates = sorted(
            set.intersection(*(set(values) for values in values_by_industry.values()))
        )
        if not common_dates:
            raise ValueError(f"No common historical breadth dates found for MA{window}")
        closes = {
            industry: [values[day] for day in common_dates]
            for industry, values in values_by_industry.items()
        }
        result[window] = PriceData(dates=common_dates, closes=closes)
    return result


def build_constituents_from_snapshot(
    stock_map: StockIndustryMap,
    signal_date: date,
) -> dict[str, list[str]]:
    mapping = stock_map.get_map_at(signal_date)
    constituents: dict[str, list[str]] = {}
    for stock, industry in mapping.items():
        constituents.setdefault(industry, []).append(stock)
    return constituents


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


def fetch_sw_level1_breadth_data_from_snapshot_map(
    stock_map: StockIndustryMap,
    start: date,
    end: date,
    *,
    ak: Any | None = None,
    windows: tuple[int, ...] = (20, 60),
    min_stocks: int = 1,
    adjust: str = "",
    lookback_days: int | None = None,
    max_stocks_per_industry: int | None = None,
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
    resolved_map = _limit_stock_industry_map_per_industry(
        stock_map,
        max_stocks_per_industry,
    )
    all_stocks = sorted(resolved_map.all_stocks)
    if not all_stocks:
        raise ValueError("historical stock map contains no stocks")

    stock_closes: dict[str, dict[date, float]] = {}
    for number, stock in enumerate(all_stocks, start=1):
        if progress:
            progress(f"Fetching historical-map stock {number}/{len(all_stocks)}: {stock}")
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

    return compute_historical_industry_breadth(
        resolved_map,
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


def _write_industry_append(path: Path, data: PriceData) -> None:
    assets = data.assets
    header = ["date", *assets]
    rows = []
    for row_index, day in enumerate(data.dates):
        rows.append(
            [
                day.isoformat(),
                *[f"{data.closes[asset][row_index]:.4f}" for asset in assets],
            ]
        )
    _append_csv_rows(path, header, rows)


def _write_industry_amount_append(path: Path, data: PriceData) -> None:
    assets = data.assets
    header = ["date", *assets]
    rows = []
    for row_index, day in enumerate(data.dates):
        rows.append(
            [
                day.isoformat(),
                *[f"{data.closes[asset][row_index]:.2f}" for asset in assets],
            ]
        )
    _append_csv_rows(path, header, rows)


def _write_benchmark_append(path: Path, dates: list[date], closes: dict[date, float]) -> None:
    header = ["date", "close"]
    rows = [[day.isoformat(), f"{closes[day]:.4f}"] for day in dates]
    _append_csv_rows(path, header, rows)


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


def _write_stock_industry_map(
    path: Path,
    stock_industry_map: StockIndustryMap | dict[str, str],
) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.writer(handle)
        if isinstance(stock_industry_map, StockIndustryMap):
            writer.writerow(["snapshot_date", "stock", "industry"])
            for snapshot_date in sorted(stock_industry_map.snapshots):
                mapping = stock_industry_map.snapshots[snapshot_date]
                for stock, industry in sorted(mapping.items()):
                    writer.writerow([snapshot_date.isoformat(), stock, industry])
        else:
            writer.writerow(["stock", "industry"])
            for stock, industry in sorted(stock_industry_map.items()):
                writer.writerow([stock, industry])


def _stock_industry_map_industry_count(
    stock_industry_map: StockIndustryMap | dict[str, str],
) -> int:
    if isinstance(stock_industry_map, StockIndustryMap):
        return len(
            {
                industry
                for mapping in stock_industry_map.snapshots.values()
                for industry in mapping.values()
            }
        )
    return len(set(stock_industry_map.values()))


def _stock_industry_map_manifest_fields(
    stock_industry_map: StockIndustryMap | dict[str, str],
) -> dict[str, Any]:
    if not isinstance(stock_industry_map, StockIndustryMap):
        return {}
    snapshot_dates = sorted(stock_industry_map.snapshots)
    return {
        "snapshot_count": len(snapshot_dates),
        "snapshot_start": snapshot_dates[0].isoformat(),
        "snapshot_end": snapshot_dates[-1].isoformat(),
    }


def _slice_price_data(data: PriceData, dates: list[date]) -> PriceData:
    position_by_date = {day: index for index, day in enumerate(data.dates)}
    closes = {
        asset: [values[position_by_date[day]] for day in dates]
        for asset, values in data.closes.items()
    }
    return PriceData(dates=dates, closes=closes)


def _load_manifest_last_date(output_path: Path) -> date | None:
    manifest_path = output_path / "manifest.json"
    if not manifest_path.exists():
        return None
    try:
        with manifest_path.open("r", encoding="utf-8") as handle:
            data = json.load(handle)
            return date.fromisoformat(data["end"])
    except (KeyError, json.JSONDecodeError, ValueError):
        return None


def _read_csv_last_date(path: Path) -> date | None:
    if not path.exists():
        return None
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.reader(handle)
        next(reader, None)
        last_date = None
        for row in reader:
            if row:
                try:
                    last_date = date.fromisoformat(row[0])
                except (ValueError, IndexError):
                    pass
        return last_date


def _append_csv_rows(path: Path, header: list[str], rows: list[list[str]]) -> None:
    exists = path.exists()
    with path.open("a", encoding="utf-8-sig", newline="") as handle:
        writer = csv.writer(handle)
        if not exists:
            writer.writerow(header)
        for row in rows:
            writer.writerow(row)


def _update_manifest(
    output_path: Path,
    end_date: date,
    new_rows: int,
    extra: dict | None = None,
) -> None:
    manifest_path = output_path / "manifest.json"
    manifest = {}
    if manifest_path.exists():
        try:
            with manifest_path.open("r", encoding="utf-8") as handle:
                manifest = json.load(handle)
        except (json.JSONDecodeError, ValueError):
            pass
    manifest["end"] = end_date.isoformat()
    manifest["rows"] = new_rows
    if extra:
        manifest.update(extra)
    manifest["generated_at"] = datetime.now().isoformat(timespec="seconds")
    with manifest_path.open("w", encoding="utf-8") as handle:
        json.dump(manifest, handle, ensure_ascii=False, indent=2)


def write_real_data_files(
    output_dir: str | Path,
    industry_data: PriceData,
    benchmark_closes: dict[date, float],
    *,
    amount_data: PriceData | None = None,
    market_data: PriceData | None = None,
    benchmark_symbol: str,
    market_symbols: dict[str, str] | None = None,
    industry_universe: str | None = None,
    industry_symbols: dict[str, str] | None = None,
    provider: str = "akshare",
    update_mode: str = "replace",
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

    if update_mode == "append":
        _write_industry_append(industry_path, aligned_industry_data)
        if aligned_amount_data and amount_path:
            _write_industry_amount_append(amount_path, aligned_amount_data)
        if aligned_market_data and market_path:
            _write_industry_append(market_path, aligned_market_data)
        _write_benchmark_append(benchmark_path, common_dates, benchmark_closes)
        total_rows = _read_csv_last_date(industry_path)
        if total_rows:
            total_rows = (total_rows - date.fromisoformat(common_dates[0].isoformat())).days
            total_rows = len(common_dates)
        else:
            total_rows = len(common_dates)
    else:
        _write_industry_close(industry_path, aligned_industry_data)
        if aligned_amount_data and amount_path:
            _write_industry_amount(amount_path, aligned_amount_data)
        if aligned_market_data and market_path:
            _write_market_close(market_path, aligned_market_data)
        _write_benchmark_close(benchmark_path, common_dates, benchmark_closes)
        total_rows = len(common_dates)

    manifest = {
        "provider": provider,
        "industry_source": "sw_level1_index",
        "benchmark_symbol": benchmark_symbol,
        "start": common_dates[0].isoformat(),
        "end": common_dates[-1].isoformat(),
        "rows": total_rows,
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
    if industry_universe:
        manifest["industry_universe"] = industry_universe
    if industry_symbols:
        manifest["industry_symbols"] = industry_symbols
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
    constituent_snapshots: StockIndustryMap | None = None,
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
        "industry_source": (
            "sw_level1_current_constituents"
            if current_constituents
            else "sw_level1_historical_constituent_snapshots"
        ),
        "current_constituents": current_constituents,
        "start": common_dates[0].isoformat(),
        "end": common_dates[-1].isoformat(),
        "rows": len(common_dates),
        "industries": len(assets),
        "windows": list(windows),
        "min_stocks": min_stocks,
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "files": {f"industry_breadth{window}": paths[window].name for window in windows},
    }
    if current_constituents:
        manifest["survivor_bias_warning"] = (
            "Breadth was computed from current SW index constituents. "
            "Use historical constituent snapshots before treating this as "
            "unbiased production research data."
        )
    if constituent_snapshots is not None:
        manifest.update(_stock_industry_map_manifest_fields(constituent_snapshots))
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


def write_stock_data_files(
    output_dir: str | Path,
    stock_data: StockMarketData,
    *,
    provider: str = "akshare",
    current_constituents: bool = True,
) -> StockDataSummary:
    close_data = stock_data.close
    amount_data = stock_data.amount
    if amount_data is not None and amount_data.assets != close_data.assets:
        raise ValueError("Stock amount data assets must match stock close data assets")
    if not _stock_map_all_stocks(stock_data.industry_map):
        raise ValueError("stock industry map must not be empty")

    common_dates = set(close_data.dates)
    if amount_data is not None:
        common_dates &= set(amount_data.dates)
    sorted_dates = sorted(common_dates)
    if not sorted_dates:
        raise ValueError("No common dates found across stock data")

    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    aligned_close_data = _slice_price_data(close_data, sorted_dates)
    aligned_amount_data = (
        _slice_price_data(amount_data, sorted_dates)
        if amount_data is not None
        else None
    )
    available_map = _filter_stock_industry_map_to_available_stocks(
        stock_data.industry_map,
        aligned_close_data.closes,
    )

    stock_close_path = output_path / "stock_close.csv"
    stock_amount_path = output_path / "stock_amount.csv" if aligned_amount_data else None
    stock_industry_map_path = output_path / "stock_industry_map.csv"
    manifest_path = output_path / "stock_manifest.json"

    _write_industry_close(stock_close_path, aligned_close_data)
    if aligned_amount_data and stock_amount_path:
        _write_industry_amount(stock_amount_path, aligned_amount_data)
    _write_stock_industry_map(stock_industry_map_path, available_map)

    manifest = {
        "provider": provider,
        "stock_source": (
            "sw_level1_current_constituents"
            if current_constituents
            else "sw_level1_historical_constituent_snapshots"
        ),
        "current_constituents": current_constituents,
        "start": sorted_dates[0].isoformat(),
        "end": sorted_dates[-1].isoformat(),
        "rows": len(sorted_dates),
        "stocks": len(aligned_close_data.assets),
        "industries": _stock_industry_map_industry_count(available_map),
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "files": {
            "stock_close": stock_close_path.name,
            "stock_amount": stock_amount_path.name if stock_amount_path else None,
            "stock_industry_map": stock_industry_map_path.name,
        },
    }
    if current_constituents:
        manifest["survivor_bias_warning"] = (
            "Stock data and stock_industry_map were built from current SW "
            "constituents. Use historical constituent snapshots before treating "
            "this as unbiased production research data."
        )
    manifest.update(_stock_industry_map_manifest_fields(available_map))
    with manifest_path.open("w", encoding="utf-8") as handle:
        json.dump(manifest, handle, ensure_ascii=False, indent=2)

    return StockDataSummary(
        output_dir=output_path,
        stock_close_path=stock_close_path,
        stock_amount_path=stock_amount_path,
        stock_industry_map_path=stock_industry_map_path,
        manifest_path=manifest_path,
        start=sorted_dates[0],
        end=sorted_dates[-1],
        rows=len(sorted_dates),
        stocks=len(aligned_close_data.assets),
        industries=_stock_industry_map_industry_count(available_map),
        current_constituents=current_constituents,
    )


def fetch_and_write_breadth_data(
    output_dir: str | Path,
    start: date,
    end: date,
    *,
    industries: list[IndexInfo] | None = None,
    constituent_snapshots: StockIndustryMap | None = None,
    windows: tuple[int, ...] = (20, 60),
    min_stocks: int = 1,
    adjust: str = "",
    lookback_days: int | None = None,
    max_stocks_per_industry: int | None = None,
    progress: ProgressCallback | None = None,
    request_interval: float = 0.0,
) -> BreadthDataSummary:
    ak = _require_akshare()
    if constituent_snapshots is None:
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
        current_constituents = True
    else:
        breadth_by_window = fetch_sw_level1_breadth_data_from_snapshot_map(
            constituent_snapshots,
            start,
            end,
            ak=ak,
            windows=windows,
            min_stocks=min_stocks,
            adjust=adjust,
            lookback_days=lookback_days,
            max_stocks_per_industry=max_stocks_per_industry,
            progress=progress,
            request_interval=request_interval,
        )
        current_constituents = False
    return write_breadth_data_files(
        output_dir,
        breadth_by_window,
        min_stocks=min_stocks,
        current_constituents=current_constituents,
        constituent_snapshots=constituent_snapshots,
    )


def fetch_and_write_stock_data(
    output_dir: str | Path,
    start: date,
    end: date,
    *,
    industries: list[IndexInfo] | None = None,
    constituent_snapshots: StockIndustryMap | None = None,
    adjust: str = "",
    max_stocks_per_industry: int | None = None,
    progress: ProgressCallback | None = None,
    request_interval: float = 0.0,
) -> StockDataSummary:
    ak = _require_akshare()
    if constituent_snapshots is None:
        stock_data = fetch_sw_level1_stock_data(
            start,
            end,
            ak=ak,
            industries=industries,
            adjust=adjust,
            max_stocks_per_industry=max_stocks_per_industry,
            progress=progress,
            request_interval=request_interval,
        )
        current_constituents = True
    else:
        stock_data = fetch_sw_level1_stock_data_from_snapshot_map(
            constituent_snapshots,
            start,
            end,
            ak=ak,
            adjust=adjust,
            max_stocks_per_industry=max_stocks_per_industry,
            progress=progress,
            request_interval=request_interval,
        )
        current_constituents = False
    return write_stock_data_files(
        output_dir,
        stock_data,
        current_constituents=current_constituents,
    )


def fetch_and_write_real_data(
    output_dir: str | Path,
    start: date,
    end: date,
    *,
    benchmark_symbol: str = "sh000300",
    industries: list[IndexInfo] | None = None,
    industry_universe: str = "current",
    market_indices: list[IndexInfo] | None = None,
    progress: ProgressCallback | None = None,
    request_interval: float = 0.0,
    update_mode: str = "replace",
) -> RealDataSummary:
    output_path = Path(output_dir)
    if update_mode == "append":
        last_date = _load_manifest_last_date(output_path)
        if last_date is not None and last_date >= end:
            raise ValueError(
                f"Manifest last_date {last_date.isoformat()} >= end {end.isoformat()}; "
                "nothing to append"
            )
        if last_date is not None and last_date >= start:
            start = last_date + timedelta(days=1)
            if progress:
                progress(f"Appending from {start.isoformat()} (manifest last_date + 1)")

    ak = _require_akshare()
    industry_infos = (
        industries
        if industries is not None
        else sw_level1_index_infos(ak, universe=industry_universe)
    )
    industry_market_data = fetch_sw_level1_market_data(
        start,
        end,
        ak=ak,
        industries=industry_infos,
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
        industry_universe="custom" if industries is not None else industry_universe,
        industry_symbols={info.name: info.code for info in industry_infos},
        update_mode=update_mode,
    )


def compute_industry_amount_zscore(
    amount_data: PriceData,
    window: int = 60,
    min_periods: int | None = None,
) -> PriceData:
    if window < 5:
        raise ValueError("window must be at least 5 to compute meaningful z-scores")
    if min_periods is None:
        min_periods = window // 2

    assets = list(amount_data.assets)
    n_dates = len(amount_data.dates)
    result_closes: dict[str, list[float]] = {}

    for asset in assets:
        raw = amount_data.closes[asset]
        z_series: list[float] = []
        for i in range(n_dates):
            lookback_start = max(0, i - window + 1)
            lookback_end = i + 1
            lookback = raw[lookback_start:lookback_end]
            if len(lookback) < min_periods:
                z_series.append(0.0)
            else:
                mean_val = sum(lookback) / len(lookback)
                variance = sum((v - mean_val) ** 2 for v in lookback) / len(lookback)
                std_val = variance ** 0.5
                if std_val == 0:
                    z_series.append(0.0)
                else:
                    z_series.append((raw[i] - mean_val) / std_val)
        result_closes[asset] = z_series

    return PriceData(dates=amount_data.dates, closes=result_closes)


def _require_requests() -> Any:
    try:
        import requests
    except ModuleNotFoundError as exc:
        raise RuntimeError(
            "requests is required for web data sources. Install it with "
            "`python -m pip install requests`."
        ) from exc
    return requests


def _require_pandas() -> Any:
    try:
        import pandas as pd
    except ModuleNotFoundError as exc:
        raise RuntimeError(
            "pandas is required to read downloaded constituent spreadsheets. "
            "Install it with `python -m pip install pandas openpyxl`."
        ) from exc
    return pd


def _coerce_interval_date(value: Any, *, allow_empty: bool = False) -> date | None:
    if value is None:
        if allow_empty:
            return None
        raise ValueError("empty date")
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, float) and value != value:
        if allow_empty:
            return None
        raise ValueError("empty date")

    raw = str(value).strip()
    if not raw or raw.lower() in {"nan", "nat", "none", "null"}:
        if allow_empty:
            return None
        raise ValueError("empty date")
    raw = raw.replace("/", "-")
    if " " in raw:
        raw = raw.split(" ", 1)[0]
    if "T" in raw:
        raw = raw.split("T", 1)[0]
    if len(raw) == 8 and raw.isdigit():
        return parse_date(raw)
    return date.fromisoformat(raw)


def _interval_cell(row: dict[str, Any], aliases: tuple[str, ...]) -> Any:
    for alias in aliases:
        if alias in row:
            return row[alias]
    return None


def _normalize_constituent_interval_row(row: dict[str, Any]) -> dict[str, Any]:
    stock = _normalize_stock_code(
        _interval_cell(
            row,
            (
                "stock",
                "symbol",
                "ts_code",
                "con_code",
                "证券代码",
                "股票代码",
                "成分券代码",
            ),
        )
    )
    industry = str(
        _interval_cell(
            row,
            (
                "industry",
                "industry_name",
                "l1_name",
                "name",
                "行业名称",
                "一级行业",
            ),
        )
        or ""
    ).strip()
    start_value = _interval_cell(
        row,
        (
            "start_date",
            "in_date",
            "start",
            "from",
            "起始日期",
            "起始时间",
            "纳入日期",
        ),
    )
    end_value = _interval_cell(
        row,
        (
            "end_date",
            "out_date",
            "end",
            "to",
            "结束日期",
            "结束时间",
            "剔除日期",
        ),
    )
    if not stock:
        raise ValueError("interval row missing stock")
    if not industry:
        raise ValueError(f"interval row missing industry for {stock}")
    return {
        "stock": stock,
        "industry": industry,
        "start_date": _coerce_interval_date(start_value),
        "end_date": _coerce_interval_date(end_value, allow_empty=True),
    }


def read_constituent_interval_csv(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        raise FileNotFoundError(f"Constituent interval CSV not found: {path}")
    intervals: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        if not reader.fieldnames:
            raise ValueError(f"{path} must contain a header row")
        for row_number, row in enumerate(reader, start=2):
            try:
                intervals.append(_normalize_constituent_interval_row(row))
            except ValueError as exc:
                raise ValueError(f"{path}:{row_number}: {exc}") from exc
    if not intervals:
        raise ValueError(f"{path} must contain at least one interval row")
    return intervals


def _month_end_dates(start: date, end: date, *, quarter_only: bool = False) -> list[date]:
    current = date(start.year, start.month, 1)
    dates: list[date] = []
    while current <= end:
        if not quarter_only or current.month in {3, 6, 9, 12}:
            last_day = calendar.monthrange(current.year, current.month)[1]
            candidate = date(current.year, current.month, last_day)
            if start <= candidate <= end:
                dates.append(candidate)
        if current.month == 12:
            current = date(current.year + 1, 1, 1)
        else:
            current = date(current.year, current.month + 1, 1)
    return dates


def _snapshot_dates_from_intervals(
    intervals: list[dict[str, Any]],
    start: date,
    end: date,
    frequency: str,
) -> list[date]:
    if frequency == "daily":
        days = (end - start).days
        return [start + timedelta(days=offset) for offset in range(days + 1)]
    if frequency == "month-end":
        return sorted({start, end, *_month_end_dates(start, end)})
    if frequency == "quarter-end":
        return sorted({start, end, *_month_end_dates(start, end, quarter_only=True)})
    if frequency != "event":
        raise ValueError(
            "snapshot_frequency must be one of: event, daily, month-end, quarter-end"
        )

    dates = {start, end}
    for interval in intervals:
        in_date = interval["start_date"]
        out_date = interval.get("end_date")
        if in_date <= end and (out_date is None or out_date >= start):
            dates.add(max(in_date, start))
            if out_date is not None and out_date < end:
                dates.add(out_date + timedelta(days=1))
    return sorted(day for day in dates if start <= day <= end)


def build_constituent_snapshots_from_intervals(
    intervals: list[dict[str, Any]],
    start: date,
    end: date,
    *,
    snapshot_frequency: str = "event",
) -> StockIndustryMap:
    if start > end:
        raise ValueError("start must be earlier than or equal to end")
    normalized = [_normalize_constituent_interval_row(row) for row in intervals]
    snapshot_dates = _snapshot_dates_from_intervals(
        normalized,
        start,
        end,
        snapshot_frequency,
    )
    snapshots: dict[date, dict[str, str]] = {}
    for snapshot_date in snapshot_dates:
        mapping: dict[str, str] = {}
        for row in normalized:
            in_date = row["start_date"]
            out_date = row.get("end_date")
            if in_date <= snapshot_date and (
                out_date is None or snapshot_date <= out_date
            ):
                stock = row["stock"]
                industry = row["industry"]
                previous = mapping.get(stock)
                if previous is not None and previous != industry:
                    raise ValueError(
                        f"Stock {stock} appears in multiple active industries "
                        f"on {snapshot_date}: {previous}, {industry}"
                    )
                mapping[stock] = industry
        if mapping:
            snapshots[snapshot_date] = mapping

    if not snapshots:
        raise ValueError("No active constituents found in requested date range")
    return StockIndustryMap(snapshots)


def write_constituent_snapshot_csv(
    stock_map: StockIndustryMap,
    output_csv: Path,
    *,
    overwrite: bool = False,
) -> int:
    if output_csv.exists() and not overwrite:
        raise FileExistsError(
            f"Target already exists: {output_csv}. Use --overwrite to replace."
        )
    output_csv.parent.mkdir(parents=True, exist_ok=True)
    _write_stock_industry_map(output_csv, stock_map)
    return sum(len(mapping) for mapping in stock_map.snapshots.values())


def fetch_sws_level1_constituent_intervals(
    *,
    industries: list[str] | None = None,
    verify_ssl: bool = True,
    request_interval: float = 0.0,
    progress: ProgressCallback | None = None,
) -> list[dict[str, Any]]:
    requests = _require_requests()
    pd = _require_pandas()
    if not verify_ssl:
        try:
            import urllib3

            urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
        except ModuleNotFoundError:
            pass
    headers = {
        "User-Agent": "Mozilla/5.0",
        "Referer": (
            "https://www.swsresearch.com/institute_sw/allIndex/"
            "downloadCenter/industryType"
        ),
    }
    list_url = (
        "https://www.swsresearch.com/institute-sw/api/"
        "download_center/trade_classification/"
    )
    response = requests.get(
        list_url,
        params={"page": 1, "page_size": 200, "indextype": "一级行业"},
        headers=headers,
        timeout=30,
        verify=verify_ssl,
    )
    response.raise_for_status()
    payload = response.json()
    results = payload.get("data", {}).get("results", [])
    names = [str(item.get("swindexname") or "").strip() for item in results]
    names = [name for name in names if name]
    if industries is not None:
        requested = set(industries)
        names = [name for name in names if name in requested]
        missing = requested - set(names)
        if missing:
            raise ValueError(
                "SWS did not return requested industries: "
                + ", ".join(sorted(missing))
            )
    if not names:
        raise ValueError("No SWS level-1 industries returned")

    download_url = (
        "https://www.swsresearch.com/institute-sw/api/"
        "download_center/download_file/"
    )
    intervals: list[dict[str, Any]] = []
    for number, industry in enumerate(names, start=1):
        if progress:
            progress(f"Fetching SWS classification {number}/{len(names)}: {industry}")
        file_response = requests.get(
            download_url,
            params={"file_name": f"{industry}分类表"},
            headers=headers,
            timeout=60,
            verify=verify_ssl,
        )
        file_response.raise_for_status()
        frame = pd.read_excel(io.BytesIO(file_response.content))
        for row in frame.to_dict("records"):
            intervals.append(_normalize_constituent_interval_row(row))
        if request_interval > 0 and number < len(names):
            time.sleep(request_interval)

    if not intervals:
        raise ValueError("No SWS constituent intervals downloaded")
    return intervals


def fetch_tushare_sw_level1_constituent_intervals(
    *,
    token: str,
    src: str = "SW2021",
    progress: ProgressCallback | None = None,
) -> list[dict[str, Any]]:
    try:
        import tushare as ts
    except ModuleNotFoundError as exc:
        raise RuntimeError(
            "tushare is required for --source tushare. Install it with "
            "`python -m pip install tushare`."
        ) from exc

    pro = ts.pro_api(token)
    classify = pro.index_classify(src=src, level="L1")
    intervals: list[dict[str, Any]] = []
    rows = _records(classify)
    if not rows:
        raise ValueError(f"Tushare returned no SW level-1 classifications for {src}")
    for number, row in enumerate(rows, start=1):
        l1_code = str(
            _cell(row, "index_code", "l1_code", "industry_code", "code") or ""
        ).strip()
        l1_name = str(
            _cell(row, "industry_name", "l1_name", "name") or l1_code
        ).strip()
        if not l1_code:
            continue
        if progress:
            progress(f"Fetching Tushare SW member {number}/{len(rows)}: {l1_name}")
        members = pro.index_member_all(l1_code=l1_code)
        for member in _records(members):
            item = {
                "stock": _cell(member, "ts_code", "con_code", "stock"),
                "industry": _cell(member, "l1_name", "industry_name") or l1_name,
                "start_date": _cell(member, "in_date", "start_date"),
                "end_date": _cell(member, "out_date", "end_date"),
            }
            intervals.append(_normalize_constituent_interval_row(item))
    if not intervals:
        raise ValueError("Tushare returned no constituent intervals")
    return intervals


def fetch_joinquant_sw_level1_constituent_intervals(
    *,
    username: str,
    password: str,
    name: str = "sw_l1",
    progress: ProgressCallback | None = None,
) -> list[dict[str, Any]]:
    try:
        import jqdatasdk as jq
    except ModuleNotFoundError as exc:
        raise RuntimeError(
            "jqdatasdk is required for --source joinquant. Install it with "
            "`python -m pip install jqdatasdk`."
        ) from exc

    jq.auth(username, password)
    industries_frame = jq.get_industries(name=name)
    industry_name_by_code = {
        str(index): str(row.get("name") or index)
        for index, row in industries_frame.iterrows()
    }
    if progress:
        progress(f"Fetching JoinQuant industry history: {name}")
    history = jq.get_history_industry(name=name)
    intervals: list[dict[str, Any]] = []
    for row in history.to_dict("records"):
        industry_code = str(_cell(row, "code", "industry_code") or "").strip()
        item = {
            "stock": _cell(row, "stock", "security", "securities"),
            "industry": industry_name_by_code.get(industry_code, industry_code),
            "start_date": _cell(row, "start_date", "in_date"),
            "end_date": _cell(row, "end_date", "out_date"),
        }
        intervals.append(_normalize_constituent_interval_row(item))
    if not intervals:
        raise ValueError("JoinQuant returned no constituent intervals")
    return intervals


def validate_constituent_snapshot_csv(path: Path) -> list[str]:
    issues: list[str] = []
    if not path.exists():
        return [f"File not found: {path}"]

    required_cols = ["snapshot_date", "stock", "industry"]
    alt_date_cols = ["date", "as_of"]

    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        if not reader.fieldnames:
            return ["CSV has no header row"]
        columns = set(reader.fieldnames)
        if "stock" not in columns or "industry" not in columns:
            return ["CSV must contain 'stock' and 'industry' columns"]
        date_col = None
        for col in ["snapshot_date"] + alt_date_cols:
            if col in columns:
                date_col = col
                break
        if not date_col:
            date_opts = ", ".join(["snapshot_date"] + alt_date_cols)
            issues.append(
                f"No date column found; expected one of: {date_opts}"
            )
            return issues

        seen: set[tuple[str, str]] = set()
        dates_seen: set[date] = set()
        row_count = 0
        for row in reader:
            row_count += 1
            stock = (row.get("stock") or "").strip()
            industry = (row.get("industry") or "").strip()
            if not stock:
                issues.append(f"Row {row_count}: empty stock code")
            if not industry:
                issues.append(f"Row {row_count}: empty industry name")
            if not stock or not industry:
                continue
            try:
                dt = date.fromisoformat((row.get(date_col) or "").strip())
            except (ValueError, TypeError):
                issues.append(f"Row {row_count}: invalid date '{row.get(date_col)}'")
                continue

            dates_seen.add(dt)
            key = (dt.isoformat(), stock)
            if key in seen:
                issues.append(f"Row {row_count}: duplicate stock {stock} on {dt}")
            seen.add(key)

        if row_count == 0:
            issues.append("CSV has no data rows")

    if not issues and not dates_seen:
        issues.append("No valid rows found")

    return issues


def import_constituent_snapshot(
    source_csv: Path,
    target_csv: Path,
    *,
    overwrite: bool = False,
) -> int:
    issues = validate_constituent_snapshot_csv(source_csv)
    if issues:
        for issue in issues:
            print(f"  ✗ {issue}")
        raise ValueError(
            f"Snapshot CSV validation failed with {len(issues)} issue(s)"
        )

    if target_csv.exists() and not overwrite:
        raise FileExistsError(
            f"Target already exists: {target_csv}. Use --overwrite to replace."
        )

    target_csv.parent.mkdir(parents=True, exist_ok=True)
    content = source_csv.read_bytes()
    target_csv.write_bytes(content)

    with source_csv.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        row_count = sum(1 for _ in reader)

    return row_count


def compute_industry_valuation_proxy(
    close_data: PriceData,
    window: int = 252,
    min_periods: int | None = None,
) -> PriceData:
    """Compute a price-based valuation proxy for each industry.

    For each industry on each date, computes where the current price sits
    within its trailing *window*-day range, returning a 0.0–1.0 percentile:
      0.0 = at or below the window-low (cheapest)
      1.0 = at or above the window-high (most expensive)

    The output is compatible with ``factors.compute_factor_snapshot``, which
    feeds ``-value`` into the cross-sectional z-score so that cheaper
    industries receive higher composite scores.
    """
    if window < 20:
        raise ValueError("window must be at least 20")
    if min_periods is None:
        min_periods = window // 2

    assets = list(close_data.assets)
    n_dates = len(close_data.dates)
    result_closes: dict[str, list[float]] = {}

    for asset in assets:
        prices = close_data.closes[asset]
        percentiles: list[float] = []
        for i in range(n_dates):
            lookback_start = max(0, i - window + 1)
            lookback = prices[lookback_start : i + 1]
            if len(lookback) < min_periods:
                percentiles.append(0.5)
                continue
            lo = min(lookback)
            hi = max(lookback)
            rng = hi - lo
            if rng <= 0:
                percentiles.append(0.5)
            else:
                pct = (prices[i] - lo) / rng
                percentiles.append(max(0.0, min(1.0, pct)))
        result_closes[asset] = percentiles

    return PriceData(dates=close_data.dates, closes=result_closes)
