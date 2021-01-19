from datetime import datetime

import yfinance
import mibian
import numpy
from django.core.cache import caches
from django.core.cache import cache

from .implied_volatility import compute_delta
from .business_day_count import busday_count_inclusive

import time

# interest rate: https://ycharts.com/indicators/10_year_treasury_rate#:~:text=10%20Year%20Treasury%20Rate%20is%20at%200.94%25%2C%20compared%20to%200.94,long%20term%20average%20of%204.39%25.
INTEREST_RATE = 1
BUSINESS_DAYS_IN_YEAR = 252
# Some stats on yahoo finance are only based on a few stray trades, so we need to remove those
# because these are false
MINIMUM_VOLUME = 20
IMPOSSIBLE_BIDS_BUFFER_PERCENT_CALL = 1.01
IMPOSSIBLE_BIDS_BUFFER_PERCENT_PUT = 0.99

YAHOO_FINANCE_CACHE_TIMEOUT = 5 * 60

def _get_option_days(stockticker_name, maximum_option_days):
    cache_key = '_get_option_days' + stockticker_name + str(maximum_option_days)
    cached_result = cache.get(cache_key)
    if cached_result is not None:
        return cached_result
    yahoo_ticker = yfinance.Ticker(stockticker_name)
    result = yahoo_ticker.options[:maximum_option_days]
    cache.set(cache_key, result, YAHOO_FINANCE_CACHE_TIMEOUT)

    return result

def _get_option_chain(stockticker_name, option_day, is_call):
    cache_key = '_get_option_chain' + stockticker_name + option_day + str(is_call)
    cached_result = cache.get(cache_key)
    if cached_result is not None:
        return cached_result
    start = time.time()
    yahoo_ticker = yfinance.Ticker(stockticker_name)
    option_chain = yahoo_ticker.option_chain(option_day)
    if is_call:
        result = option_chain.calls
    else:
        result = option_chain.puts
    cache.set(cache_key, result, YAHOO_FINANCE_CACHE_TIMEOUT)
    ending = time.time() - start
    print(stockticker_name, option_day, ending)
    return result

def _get_odds_otm(current_price, strike, days_to_expiry, put_price):
    cache_key = '_get_odds_otm' + str(current_price) + str(strike) + str(days_to_expiry) + str(put_price)
    cached_result = cache.get(cache_key)
    if cached_result is not None:
        return cached_result
    put_implied_volatility_calculator = mibian.BS([current_price, strike, INTEREST_RATE, days_to_expiry], putPrice=put_price)
    # kinda silly, we need to construct another object to extract delta for a computation based on real put price
    # Yahoo's volatility in interesting_put.impliedVolatility seems low, ~20% too low, so lets use the implied volatility
    implied_volatility = put_implied_volatility_calculator.impliedVolatility
    put_with_implied_volatility = mibian.BS([current_price, strike, INTEREST_RATE, days_to_expiry], volatility=implied_volatility)
    result = 1 + put_with_implied_volatility.putDelta
    cache.set(cache_key, result, YAHOO_FINANCE_CACHE_TIMEOUT)
    return result


# We assume that when we fail (for a put we acquire stock, or call we keep stock)
# we get a rate of return of 1x, which is profit_decimal_fail_case as 0
def compute_annualized_rate_of_return(profit_decimal, odds, days, profit_decimal_fail_case=0):
    if days < 5:
        # typically you can't do options faster than once a week, so assume the minimum timeframe
        # is 5 days. This could be unnecessarily punishing toward short time frame, but is perhaps
        # more realistic
        days = 5

    rate_of_return_success_case = 1 + profit_decimal
    rate_of_return_fail_case = 1 + profit_decimal_fail_case
    effective_rate_of_return = rate_of_return_success_case * odds + rate_of_return_fail_case * (1 - odds)
    return effective_rate_of_return ** (BUSINESS_DAYS_IN_YEAR / days)

def get_current_price(stockticker_name):
    closes = _get_recent_closes(stockticker_name)
    if closes is None:
        return None
    # Second element, since 2 closes are saved in cache
    return closes[1]

def get_previous_close_price(stockticker_name):
    closes = _get_recent_closes(stockticker_name)
    if closes is None:
        return None
    # First element, since 2 closes are saved in cache
    return closes[0]

def _get_recent_closes(stockticker_name):
    cache_key = 'get_recent_closes_' + stockticker_name
    cached_result = cache.get(cache_key)
    if cached_result is not None:
        return cached_result
    yahoo_ticker = yfinance.Ticker(stockticker_name)
    yahoo_ticker_history = yahoo_ticker.history(period="10d")
    if yahoo_ticker_history.empty:
        return None
    result = yahoo_ticker_history.tail(2)['Close']
    cache.set(cache_key, result, YAHOO_FINANCE_CACHE_TIMEOUT)
    return result

# only look at the 10 closest option days, so about 2 months weekly options
def get_put_stats_for_ticker(ticker_name, maximum_option_days=10, options_per_day_to_consider=10):
    current_price = get_current_price(ticker_name)
    if current_price is None:
        return {'put_stats': [], 'current_price': None}
    put_stats = []
    option_days = _get_option_days(ticker_name, maximum_option_days)
    for option_day in option_days:
        puts = _get_option_chain(ticker_name, option_day, is_call=False)
        interesting_indicies = puts[puts['strike'].gt(current_price)].index
        if len(interesting_indicies) == 0:
            continue
        otm_threshold_index = interesting_indicies[0]
        # interesting defined as the 10 highest OTM puts (price is below strike price)
        # For our strategies, we don't particularly want to acquire the stock, so we sell OTM
        interesting_puts = puts[max(otm_threshold_index - options_per_day_to_consider, 0):otm_threshold_index]
        option_day_as_date_object = datetime.strptime(option_day, '%Y-%m-%d').date()
        # add one to business days since it includes the current day too
        days_to_expiry = busday_count_inclusive(datetime.now().date(), option_day_as_date_object)
        for index, interesting_put in interesting_puts.iterrows():
            put_stat = compute_put_stat(
                current_price,
                interesting_put,
                days_to_expiry,
                expiration_date=option_day
            )
            if put_stat is not None:
                put_stat.update({"ticker": ticker_name})
                put_stats.append(put_stat)
    return {'put_stats': put_stats, 'current_price': current_price}

# only look at the 10 closest option days, so about 2 months on weekly options
def get_call_stats_for_option_wheel(ticker_name, days_active_so_far, revenue, collateral, maximum_option_days=10):
    yahoo_ticker = yfinance.Ticker(ticker_name)
    current_price = get_current_price(ticker_name)
    if current_price is None:
        return {'call_stats': [], 'current_price': None}
    call_stats = []
    option_days = _get_option_days(ticker_name, maximum_option_days)
    for option_day in option_days:
        option_day_as_date_object = datetime.strptime(option_day, '%Y-%m-%d').date()
        # add one to business days since it includes the current day too
        days_to_expiry = busday_count_inclusive(datetime.now().date(), option_day_as_date_object)
        calls = _get_option_chain(ticker_name, option_day, is_call=True)
        interesting_indicies = calls[calls['strike'].gt(current_price)].index
        if len(interesting_indicies) == 0:
            continue
        otm_threshold_index = interesting_indicies[0]
        # For selling a call, we'll analysis the 10 highest ITM calls and 10 lowest OTM calls
        # ITM calls might be useful to make sure the stock gets sold, while OTM calls are useful
        # to hold onto the stock until it recovers.
        interesting_calls = calls[max(otm_threshold_index - 10, 0):min(otm_threshold_index + 10, calls.shape[0])]
        for index, interesting_call in interesting_calls.iterrows():
            call_stat = compute_call_stat(
                current_price,
                interesting_call,
                days_to_expiry,
                expiration_date=option_day,
                days_active_so_far=days_active_so_far,
                revenue=revenue,
                collateral=collateral,
            )
            if call_stat is not None:
                call_stat.update({"ticker": ticker_name})
                call_stats.append(call_stat)
    return {'call_stats': call_stats, 'current_price': current_price}

def compute_put_stat(current_price, interesting_put, days_to_expiry, expiration_date):
    volume = interesting_put.volume
    if volume < MINIMUM_VOLUME or numpy.isnan(volume):
        # These are probably too low volume to be legit. Yahoo finance will show wrong prices
        return None
    if interesting_put.impliedVolatility == 0:
        # This likely indicates a broken option (bid/ask is busted),
        # and mibian will take a long time computing these
        return None
    strike, last_price, bid, ask = [interesting_put.strike, interesting_put.lastPrice, interesting_put.bid, interesting_put.ask]
    effective_price = last_price
    if (bid == 0 and ask == 0) == False:
        # bid and ask will be 0 during off hours, so use last_price as an estimate.
        # During trading hours we assume we'll assuming worse case that we can only get it for bid price
        effective_price = bid
    if effective_price == 0 or numpy.isnan(effective_price):
        return None
    if strike > (current_price * IMPOSSIBLE_BIDS_BUFFER_PERCENT_PUT) + effective_price:
        # this option has no intrinsic value, since it would be more efficient
        # to just buy the stock on the open market in this case. This is probably from
        # there being no legitimate bids, and we need to skip, since mibian will lag out
        # if it attempts to compute this
        return None
    if effective_price > last_price * 1.1 or effective_price < last_price * 0.9:
        # The price seems pretty stale. We should avoid computation since mibian's computation
        # will tend to time out in this case.
        return None
    RUN_NEW_FORUMLA = False
    if RUN_NEW_FORUMLA:
        delta = compute_delta(
            current_price=current_price,
            strike=strike,
            interest_rate=INTEREST_RATE,
            days_to_expiry=days_to_expiry,
            option_price=effective_price,
            is_call=False
        )
        probability_out_of_the_money = 1 + delta
    else:
        probability_out_of_the_money = _get_odds_otm(current_price, strike, days_to_expiry, effective_price)
    max_profit_decimal = effective_price / strike
    stats = {
        "strike": strike,
        "price": effective_price,
        "expiration_date": expiration_date,
        "days_to_expiry": days_to_expiry,
        # https://www.macroption.com/delta-calls-puts-probability-expiring-itm/ "Option’s delta as probability proxy"
        "max_profit_decimal": max_profit_decimal,
        "decimal_odds_out_of_the_money_implied": probability_out_of_the_money,
        "annualized_rate_of_return_decimal": compute_annualized_rate_of_return(max_profit_decimal, probability_out_of_the_money, days_to_expiry)
    }

    return stats

def compute_call_stat(
    current_price,
    interesting_call,
    days_to_expiry,
    expiration_date,
    days_active_so_far,
    revenue,
    collateral,
):
    volume = interesting_call.volume
    if volume < MINIMUM_VOLUME or numpy.isnan(volume):
        # These are probably too low volume to be legit. Yahoo finance will show wrong prices
        return None
    if interesting_call.impliedVolatility == 0:
        # This likely indicates a broken option (bid/ask is busted),
        # and mibian will take a long time computing these
        return None
    strike, last_price, bid, ask = [interesting_call.strike, interesting_call.lastPrice, interesting_call.bid, interesting_call.ask]
    effective_price = last_price
    if (bid == 0 and ask == 0) == False:
        # bid and ask will be 0 during off hours, so use last_price as an estimate.
        # During trading hours we assume we'll assuming worse case that we can only get it for bid price
        effective_price = bid
    if effective_price == 0 or numpy.isnan(effective_price):
        return None
    if strike + effective_price < current_price * IMPOSSIBLE_BIDS_BUFFER_PERCENT_CALL:
        # this option has no intrinsic value, since it would be more efficient
        # to just sell the stock on the open market in this case. This is probably from
        # there being no legitimate bids, and we need to skip, since mibian will lag out
        # if it attempts to compute this
        return None
    if effective_price > last_price * 1.1 or effective_price < last_price * 0.9:
        # The price seems pretty stale. We should avoid computation since mibian's computation
        # will tend to time out in this case.
        return None
    call_implied_volatility_calculator = mibian.BS([current_price, strike, INTEREST_RATE, days_to_expiry], callPrice=effective_price)
    # kinda silly, we need to construct another object to extract delta for a computation based on real call price
    # Yahoo's volatility in interesting_call.impliedVolatility seems low, ~20% too low, so lets use the implied volatility
    implied_volatility = call_implied_volatility_calculator.impliedVolatility
    call_with_implied_volatility = mibian.BS([current_price, strike, INTEREST_RATE, days_to_expiry], volatility=implied_volatility)

    proposed_strike_difference_proceeds = strike - float(collateral)
    wheel_total_max_profit_decimal = (proposed_strike_difference_proceeds + effective_price + float(revenue)) / float(collateral)

    # For computing the return of just this call, we ignore any previous profit/losses
    # and assume we had to buy the stock at the current price
    call_max_profit_decimal = (strike + effective_price - current_price) / current_price
    odds = call_with_implied_volatility.callDelta

    annualized_rate_of_return = compute_annualized_rate_of_return(call_max_profit_decimal, odds, days_to_expiry)
    stats = {
        "strike": strike,
        "price": effective_price,
        "expiration_date": expiration_date,
        "days_to_expiry": days_to_expiry,
        "call_max_profit_decimal": call_max_profit_decimal,
        "wheel_total_max_profit_decimal": wheel_total_max_profit_decimal,
        "decimal_odds_out_of_the_money_implied": odds,
        "annualized_rate_of_return_decimal": annualized_rate_of_return
    }
    return stats
