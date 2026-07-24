import json
import os
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CATALOG_PATH = PROJECT_ROOT / "config" / "llm_prices.json"


def calculate_krw_cost(model, input_tokens, output_tokens, cached_input_tokens=0):
    """Calculate reproducible micro-KRW costs when an explicit USD/KRW rate is configured."""
    exchange_text = os.getenv("QA_OBSERVER_USD_KRW", "").strip()
    if not exchange_text:
        return _unpriced()
    try:
        usd_krw = Decimal(exchange_text)
    except Exception:
        return _unpriced("invalid_exchange_rate")
    if usd_krw <= 0:
        return _unpriced("invalid_exchange_rate")

    catalog_path = Path(os.getenv("QA_OBSERVER_PRICE_CATALOG", "") or DEFAULT_CATALOG_PATH)
    try:
        catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return _unpriced("catalog_unavailable")
    model_name, price = _find_model(catalog.get("models", {}), model)
    if price is None:
        return _unpriced("model_not_found")

    unit = Decimal(str(catalog.get("unit_tokens") or 1_000_000))
    cached = max(0, min(int(cached_input_tokens or 0), int(input_tokens or 0)))
    uncached = max(0, int(input_tokens or 0) - cached)
    input_usd = (
        Decimal(uncached) * Decimal(str(price["input_usd_per_unit"]))
        + Decimal(cached) * Decimal(str(price["cached_input_usd_per_unit"]))
    ) / unit
    output_usd = (
        Decimal(max(0, int(output_tokens or 0))) * Decimal(str(price["output_usd_per_unit"]))
    ) / unit
    input_micros = _micro_krw(input_usd, usd_krw)
    output_micros = _micro_krw(output_usd, usd_krw)
    return {
        "priced": True,
        "reason": None,
        "price_snapshot_id": f"{catalog['snapshot_id']}:usdkrw-{exchange_text}",
        "catalog_model": model_name,
        "input_cost_micros_krw": input_micros,
        "output_cost_micros_krw": output_micros,
        "total_cost_micros_krw": input_micros + output_micros,
    }


def _find_model(models, requested):
    requested = str(requested or "")
    if requested in models:
        return requested, models[requested]
    for name, price in models.items():
        if requested in price.get("aliases", []):
            return name, price
    return None, None


def _micro_krw(usd, usd_krw):
    return int((usd * usd_krw * Decimal(1_000_000)).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def _unpriced(reason="exchange_rate_missing"):
    return {
        "priced": False,
        "reason": reason,
        "price_snapshot_id": None,
        "catalog_model": None,
        "input_cost_micros_krw": None,
        "output_cost_micros_krw": None,
        "total_cost_micros_krw": None,
    }
