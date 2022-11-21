import logging
import time

from django.core.cache import cache
from rq import Queue

from catalog.models import StockTicker
from worker import conn

from .constants import GLOBAL_TICKERS
from .option_price_computation import get_put_stats_for_ticker

GLOBAL_PUT_CACHE_KEY = "global_put_comparison"
GLOBAL_PUT_TIMEOUT_SECONDS = 10 * 60
GLOBAL_PUT_RUNNING_CACHE_KEY = "global_put_comparison_running"

logger = logging.getLogger(__name__)


def get_global_puts() -> list:
    cache_key = "get_global_puts"
    cached_result = cache.get(cache_key)
    if cached_result is not None:
        return cached_result
    start = time.time()
    tickers = StockTicker.objects.filter(name__in=GLOBAL_TICKERS)
    put_stats = []
    for ticker in tickers:
        put_stats += get_put_stats_for_ticker(
            ticker, maximum_option_days=5, options_per_day_to_consider=5
        )["put_stats"]
    result = sorted(
        put_stats,
        key=lambda put: put["annualized_rate_of_return_decimal"],
        reverse=True,
    )
    cache.set(cache_key, result, GLOBAL_PUT_TIMEOUT_SECONDS)
    elapsed = time.time() - start
    logger.info(f"fetched global puts: {elapsed}")
    return result


def schedule_global_put_comparison_async():
    is_currently_running = cache.get(GLOBAL_PUT_RUNNING_CACHE_KEY)
    if is_currently_running is None:
        cache.set(GLOBAL_PUT_RUNNING_CACHE_KEY, True, GLOBAL_PUT_TIMEOUT_SECONDS)
        q = Queue(connection=conn)
        return q.enqueue(
            _run_global_put_comparison, job_timeout=GLOBAL_PUT_TIMEOUT_SECONDS
        )
    return True


def _run_global_put_comparison():
    put_stats = []
    for stock_ticker in StockTicker.objects.all():
        put_stats += get_put_stats_for_ticker(
            stock_ticker, maximum_option_days=2, options_per_day_to_consider=3
        )["put_stats"]
    result = sorted(
        put_stats,
        key=lambda put: put["annualized_rate_of_return_decimal"],
        reverse=True,
    )
    cache.set(GLOBAL_PUT_CACHE_KEY, result, GLOBAL_PUT_TIMEOUT_SECONDS)
    return result
