from __future__ import annotations

import math

INDUSTRY_CLUSTER_SW2021 = {
    "TMT":      ["计算机", "电子", "通信", "传媒"],
    "新能源":   ["电力设备", "汽车"],
    "周期":     ["煤炭", "钢铁", "有色金属", "基础化工", "石油石化"],
    "金融":     ["银行", "非银金融"],
    "消费":     ["食品饮料", "家用电器", "美容护理", "商贸零售", "农林牧渔"],
    "医疗":     ["医药生物"],
    "防御":     ["公用事业", "交通运输", "社会服务"],
    "制造":     ["机械设备", "建筑装饰", "建筑材料", "纺织服饰", "轻工制造", "环保", "国防军工", "综合", "房地产"],
}

INDUSTRY_CLUSTER_SW2014 = {
    "TMT":      ["计算机", "电子", "通信", "传媒"],
    "新能源":   ["电力设备", "汽车"],
    "周期":     ["采掘", "钢铁", "有色金属", "化工"],
    "金融":     ["银行", "非银金融"],
    "消费":     ["食品饮料", "家用电器", "商业贸易", "农林牧渔", "休闲服务"],
    "医疗":     ["医药生物"],
    "防御":     ["公用事业", "交通运输"],
    "制造":     ["机械设备", "建筑装饰", "建筑材料", "纺织服装", "轻工制造", "国防军工", "综合", "房地产"],
}

INDUSTRY_CLUSTER_SW2000 = {
    "TMT":      ["信息服务", "信息设备", "电子"],
    "周期":     ["采掘", "黑色金属", "有色金属", "化工"],
    "金融":     ["金融服务"],
    "消费":     ["食品饮料", "家用电器", "商业贸易", "农林牧渔", "餐饮旅游"],
    "医疗":     ["医药生物"],
    "防御":     ["公用事业", "交通运输"],
    "制造":     ["机械设备", "建筑建材", "纺织服装", "轻工制造", "综合", "交运设备", "房地产"],
}


def _build_reverse_cluster_map(cluster_map: dict[str, list[str]]) -> dict[str, str]:
    return {ind: cluster for cluster, inds in cluster_map.items() for ind in inds}


def select_with_cluster_constraint(
    scores: dict[str, float],
    top_k: int,
    cluster_map: dict[str, list[str]] | None = None,
    max_per_cluster: int = 2,
) -> list[str]:
    if cluster_map is None:
        cluster_map = INDUSTRY_CLUSTER_SW2021
    if top_k <= 0:
        raise ValueError("top_k must be positive")
    if max_per_cluster <= 0:
        raise ValueError("max_per_cluster must be positive")

    reverse_map = _build_reverse_cluster_map(cluster_map)
    cluster_count: dict[str, int] = {c: 0 for c in cluster_map}
    selected: list[str] = []
    for industry, score in sorted(scores.items(), key=lambda x: (-x[1], x[0])):
        if len(selected) >= top_k:
            break
        cluster = reverse_map.get(industry)
        if cluster is None:
            selected.append(industry)
            continue
        if cluster_count[cluster] < max_per_cluster:
            selected.append(industry)
            cluster_count[cluster] += 1
    return selected


def select_top_k(scores: dict[str, float], top_k: int) -> list[str]:
    if top_k <= 0:
        raise ValueError("top_k must be positive")
    ranked = sorted(scores.items(), key=lambda item: (-item[1], item[0]))
    return [asset for asset, _score in ranked[:top_k]]


def _get_holdings(
    scores: dict[str, float],
    top_k: int,
    holdings: list[str] | None = None,
) -> list[str]:
    """Select top_k holdings, or use provided override list."""
    if holdings is not None:
        return holdings
    return select_top_k(scores, top_k)


def equal_weight_target(
    scores: dict[str, float],
    top_k: int,
    exposure: float,
    max_weight: float,
    holdings: list[str] | None = None,
) -> dict[str, float]:
    if not 0 <= exposure <= 1:
        raise ValueError("exposure must be between 0 and 1")
    if max_weight <= 0:
        raise ValueError("max_weight must be positive")

    selected = _get_holdings(scores, top_k, holdings)
    if not selected or exposure == 0:
        return {}

    per_asset = min(exposure / len(selected), max_weight)
    return {asset: per_asset for asset in selected}


def _clamp_and_renormalize(
    weights: dict[str, float],
    max_weight: float,
) -> dict[str, float]:
    result = dict(weights)
    for _ in range(10):
        excess = sum(
            result[k] - max_weight for k in result if result[k] > max_weight
        )
        if excess < 1e-10:
            break
        clamped = {k: min(v, max_weight) for k, v in result.items()}
        below_max = [k for k, v in result.items() if v < max_weight]
        if not below_max:
            break
        per_asset = excess / len(below_max)
        result = {
            k: clamped[k] + (per_asset if k in below_max else 0.0)
            for k in result
        }
    return {k: min(v, max_weight) for k, v in result.items()}


def softmax_weight_target(
    scores: dict[str, float],
    top_k: int,
    exposure: float,
    max_weight: float,
    temperature: float = 1.0,
    holdings: list[str] | None = None,
) -> dict[str, float]:
    if not 0 <= exposure <= 1:
        raise ValueError("exposure must be between 0 and 1")
    if temperature <= 0:
        raise ValueError("temperature must be positive")

    selected = _get_holdings(scores, top_k, holdings)
    if not selected or exposure == 0:
        return {}

    top_scores = {asset: scores[asset] for asset in selected}
    max_score = max(top_scores.values())
    exp_scores = {
        asset: math.exp((s - max_score) / temperature)
        for asset, s in top_scores.items()
    }
    total = sum(exp_scores.values())
    raw_weights = {asset: (v / total) * exposure for asset, v in exp_scores.items()}

    return _clamp_and_renormalize(raw_weights, max_weight)


def vol_parity_target(
    scores: dict[str, float],
    vol_data: dict[str, float],
    top_k: int,
    exposure: float,
    max_weight: float,
    holdings: list[str] | None = None,
) -> dict[str, float]:
    selected = _get_holdings(scores, top_k, holdings)
    if not selected or exposure == 0:
        return {}

    inv_vols = {
        asset: 1.0 / max(vol_data.get(asset, 0.02), 0.001)
        for asset in selected
    }
    total = sum(inv_vols.values())
    raw_weights = {asset: (v / total) * exposure for asset, v in inv_vols.items()}
    return _clamp_and_renormalize(raw_weights, max_weight)


def rank_weight_target(
    scores: dict[str, float],
    top_k: int,
    exposure: float,
    max_weight: float,
    holdings: list[str] | None = None,
) -> dict[str, float]:
    if not 0 <= exposure <= 1:
        raise ValueError("exposure must be between 0 and 1")

    selected = _get_holdings(scores, top_k, holdings)
    if not selected or exposure == 0:
        return {}

    ranked = sorted(selected, key=lambda i: scores[i], reverse=True)
    n = len(ranked)
    rank_weights_sum = sum(n - r for r in range(n))
    raw_weights = {
        i: (n - rank) / rank_weights_sum * exposure
        for rank, i in enumerate(ranked)
    }
    return _clamp_and_renormalize(raw_weights, max_weight)


def adaptive_top_k(
    scores: dict[str, float],
    base_k: int = 5,
    concentration_threshold: float = 1.5,
) -> int:
    if not scores:
        return base_k
    ranked = sorted(scores.values(), reverse=True)
    if len(ranked) < base_k:
        return len(ranked)
    top_mean = sum(ranked[:base_k]) / base_k
    if top_mean > 0 and ranked[0] / top_mean > concentration_threshold:
        return max(3, base_k - 2)
    elif top_mean <= 0 or ranked[0] / max(top_mean, 0.01) < 0.8:
        return min(7, base_k + 2)
    return base_k


def top_k_from_dispersion(
    dispersion: float,
    k_min: int = 3,
    k_max: int = 7,
    disp_low: float = 0.04,
    disp_high: float = 0.10,
) -> int:
    if dispersion <= disp_low:
        return k_min
    if dispersion >= disp_high:
        return k_max
    ratio = (dispersion - disp_low) / (disp_high - disp_low)
    return int(round(k_min + ratio * (k_max - k_min)))


def turnover(previous: dict[str, float], target: dict[str, float]) -> float:
    assets = set(previous) | set(target)
    return sum(abs(target.get(asset, 0.0) - previous.get(asset, 0.0)) for asset in assets)


def shrink_toward_current(
    target_weights: dict[str, float],
    current_weights: dict[str, float],
    factor: float,
) -> dict[str, float]:
    if factor <= 0:
        return dict(current_weights)
    if factor >= 1:
        return dict(target_weights)
    assets = set(target_weights) | set(current_weights)
    return {
        asset: current_weights.get(asset, 0.0) * factor
        + target_weights.get(asset, 0.0) * (1 - factor)
        for asset in assets
    }
