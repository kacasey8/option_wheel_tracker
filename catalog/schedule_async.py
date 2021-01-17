from rq import Queue
from worker import conn
from .option_price_computation import (
  get_put_stats_for_ticker,
)
from django.core.cache import cache
from catalog.models import StockTicker

GLOBAL_PUT_CACHE_KEY = 'global_put_comparison'
GLOBAL_PUT_TIMEOUT_SECONDS = 10 * 60
GLOBAL_PUT_RUNNING_CACHE_KEY = 'global_put_comparison_running'

def schedule_global_put_comparison_async():
  is_currently_running = cache.get(GLOBAL_PUT_RUNNING_CACHE_KEY)
  if is_currently_running is None:
    cache.set(GLOBAL_PUT_RUNNING_CACHE_KEY, True, GLOBAL_PUT_TIMEOUT_SECONDS)
    q = Queue(connection=conn)
    return q.enqueue(_run_global_put_comparison)
  return True

def _run_global_put_comparison():
  put_stats = []
  for stock_ticker in StockTicker.objects.all():
    put_stats += get_put_stats_for_ticker(stock_ticker.name, maximum_option_days=2, options_per_day_to_consider=3)['put_stats']
  result = sorted(put_stats, key=lambda put: put['annualized_rate_of_return_decimal'], reverse=True)
  cache.set(GLOBAL_PUT_CACHE_KEY, result, GLOBAL_PUT_TIMEOUT_SECONDS)
  return result
