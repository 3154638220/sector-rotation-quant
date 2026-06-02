from __future__ import annotations

import csv
from datetime import date
from pathlib import Path

from .models import PriceData


def load_wide_asset_csv(path: str | Path, value_name: str = "value") -> PriceData:
    csv_path = Path(path)
    if not csv_path.exists():
        raise FileNotFoundError(f"{value_name.capitalize()} data not found: {csv_path}")

    with csv_path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        if not reader.fieldnames or "date" not in reader.fieldnames:
            raise ValueError(f"{csv_path} must contain a 'date' column")

        assets = [name for name in reader.fieldnames if name != "date"]
        if not assets:
            raise ValueError(f"{csv_path} must contain at least one asset column")

        dates: list[date] = []
        values_by_asset: dict[str, list[float]] = {asset: [] for asset in assets}
        for row in reader:
            if not row.get("date"):
                continue
            dates.append(date.fromisoformat(row["date"]))
            for asset in assets:
                value = row.get(asset)
                if value is None or value == "":
                    raise ValueError(
                        f"Missing {value_name} for {asset} on {row['date']}"
                    )
                values_by_asset[asset].append(float(value))

    order = sorted(range(len(dates)), key=dates.__getitem__)
    sorted_dates = [dates[i] for i in order]
    sorted_values = {
        asset: [values[i] for i in order] for asset, values in values_by_asset.items()
    }
    return PriceData(sorted_dates, sorted_values)


def load_wide_close_csv(path: str | Path) -> PriceData:
    return load_wide_asset_csv(path, value_name="close")


def load_benchmark_csv(path: str | Path) -> tuple[list[date], list[float]]:
    csv_path = Path(path)
    if not csv_path.exists():
        raise FileNotFoundError(f"Benchmark data not found: {csv_path}")

    with csv_path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        if not reader.fieldnames or "date" not in reader.fieldnames:
            raise ValueError(f"{csv_path} must contain a 'date' column")
        close_column = "close"
        if close_column not in reader.fieldnames:
            candidates = [name for name in reader.fieldnames if name != "date"]
            if len(candidates) != 1:
                raise ValueError(
                    f"{csv_path} must contain 'close' or one benchmark column"
                )
            close_column = candidates[0]

        rows: list[tuple[date, float]] = []
        for row in reader:
            if not row.get("date"):
                continue
            rows.append((date.fromisoformat(row["date"]), float(row[close_column])))

    rows.sort(key=lambda item: item[0])
    return [item[0] for item in rows], [item[1] for item in rows]


def load_stock_industry_map_csv(path: str | Path) -> dict[str, str]:
    csv_path = Path(path)
    if not csv_path.exists():
        raise FileNotFoundError(f"Stock industry map not found: {csv_path}")

    with csv_path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        if not reader.fieldnames:
            raise ValueError(f"{csv_path} must contain stock and industry columns")
        if "stock" not in reader.fieldnames or "industry" not in reader.fieldnames:
            raise ValueError(f"{csv_path} must contain 'stock' and 'industry' columns")

        mapping: dict[str, str] = {}
        for row in reader:
            stock = (row.get("stock") or "").strip()
            industry = (row.get("industry") or "").strip()
            if not stock or not industry:
                continue
            if stock in mapping:
                raise ValueError(f"Duplicate stock in industry map: {stock}")
            mapping[stock] = industry

    if not mapping:
        raise ValueError(f"{csv_path} must contain at least one stock mapping")
    return mapping


def align_benchmark(
    target_dates: list[date],
    benchmark_dates: list[date],
    benchmark_closes: list[float],
) -> list[float]:
    by_date = dict(zip(benchmark_dates, benchmark_closes, strict=True))
    missing = [day for day in target_dates if day not in by_date]
    if missing:
        preview = ", ".join(day.isoformat() for day in missing[:5])
        raise ValueError(f"Benchmark is missing {len(missing)} dates: {preview}")
    return [by_date[day] for day in target_dates]


def align_asset_data(
    target_dates: list[date],
    target_assets: list[str],
    data: PriceData,
    *,
    value_name: str = "value",
) -> PriceData:
    missing_assets = [asset for asset in target_assets if asset not in data.closes]
    if missing_assets:
        preview = ", ".join(missing_assets[:5])
        raise ValueError(f"{value_name.capitalize()} data is missing assets: {preview}")

    position_by_date = {day: index for index, day in enumerate(data.dates)}
    missing_dates = [day for day in target_dates if day not in position_by_date]
    if missing_dates:
        preview = ", ".join(day.isoformat() for day in missing_dates[:5])
        raise ValueError(
            f"{value_name.capitalize()} data is missing {len(missing_dates)} dates: {preview}"
        )

    aligned = {
        asset: [
            data.closes[asset][position_by_date[day]]
            for day in target_dates
        ]
        for asset in target_assets
    }
    return PriceData(target_dates, aligned)
