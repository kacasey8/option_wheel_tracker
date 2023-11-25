import logging
import time
from datetime import datetime
from decimal import Decimal
from json import JSONDecodeError

import mibian
import numpy
import yfinance
from django.core.cache import cache

from .business_day_count import busday_count_inclusive
from .implied_volatility import compute_delta

logger = logging.getLogger(__name__)

# interest rate: https://ycharts.com/indicators/10_year_treasury_rate#:~:text=10%20Year%20Treasury%20Rate%20is%20at%200.94%25%2C%20compared%20to%200.94,long%20term%20average%20of%204.39%25. # noqa
INTEREST_RATE = 1
BUSINESS_DAYS_IN_YEAR = 252
# Some stats on yahoo finance are only based on a few stray trades, remove those
# because these are false
MINIMUM_VOLUME = 10
IMPOSSIBLE_BIDS_BUFFER_PERCENT_CALL = 1.01
IMPOSSIBLE_BIDS_BUFFER_PERCENT_PUT = 0.99
IMPOSSIBLE_IMPLIED_VOLATILITY = 4.4

YAHOO_FINANCE_CACHE_TIMEOUT = 5 * 60  # 5 minutes
YAHOO_FINANCE_LONG_CACHE_TIMEOUT = 60 * 60 * 24 * 7  # 1 week


def _get_option_days(stockticker_name, maximum_option_days):
    cache_key = "_get_option_days" + stockticker_name + str(maximum_option_days)
    cached_result = cache.get(cache_key)
    if cached_result is not None:
        return cached_result
    yahoo_ticker = yfinance.Ticker(stockticker_name)
    try:
        result = yahoo_ticker.options[:maximum_option_days]
        cache.set(cache_key, result, YAHOO_FINANCE_CACHE_TIMEOUT)
    except Exception:
        # On certain downloads yahoo finance might fail :(.
        # Let's avoid caching in that case
        result = None

    return result


def _get_option_chain(stockticker_name, option_day, is_call):
    cache_key = "_get_option_chain" + stockticker_name + option_day + str(is_call)
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
    logging.info(f"fetched option chain {stockticker_name}: {option_day} took {ending}")
    return result


def _get_odds_otm(current_price, strike, days_to_expiry, put_price) -> Decimal:
    cache_key = (
        "_get_odds_otm"
        + str(current_price)
        + str(strike)
        + str(days_to_expiry)
        + str(put_price)
    )
    cached_result = cache.get(cache_key)
    if cached_result is not None:
        return cached_result
    put_implied_volatility_calculator = mibian.BS(
        [current_price, strike, INTEREST_RATE, days_to_expiry], putPrice=put_price
    )
    # kinda silly, we need to construct another object to extract delta for a
    # computation based on real put price.
    # Yahoo's volatility in interesting_put.impliedVolatility seems low, ~20% too low,
    # so lets use the implied volatility
    implied_volatility = put_implied_volatility_calculator.impliedVolatility
    put_with_implied_volatility = mibian.BS(
        [current_price, strike, INTEREST_RATE, days_to_expiry],
        volatility=implied_volatility,
    )
    put_delta = put_with_implied_volatility.putDelta
    try:
        result = Decimal(float(put_delta) + 1)
    except ValueError:
        raise Exception("invalid put delta", put_delta)
    cache.set(cache_key, result, YAHOO_FINANCE_CACHE_TIMEOUT)
    return result


# We assume that when we fail (for a put we acquire stock, or call we keep stock)
# we get a rate of return of 1x, which is profit_decimal_fail_case as 0
def compute_annualized_rate_of_return(
    profit_decimal: Decimal,
    odds: Decimal,
    days: float,
    profit_decimal_fail_case: Decimal = Decimal(0),
) -> Decimal:
    if days < 5:
        # typically you can't do options faster than once a week, so assume the minimum
        #  timeframe is 5 days. This could be unnecessarily punishing toward short time
        # frame, but is perhaps more realistic
        days = 5

    rate_of_return_success = (1 + profit_decimal) * odds
    rate_of_return_fail = (1 + profit_decimal_fail_case) * (1 - odds)
    effective_rate_of_return = rate_of_return_success + rate_of_return_fail
    return effective_rate_of_return ** Decimal((BUSINESS_DAYS_IN_YEAR / days))


def get_earnings(stockticker_name):
    cache_key = "get_earnings_" + stockticker_name
    cached_result = cache.get(cache_key)
    if cached_result is not None:
        if cached_result == "no earnings":
            return None
        return cached_result
    start = time.time()
    result = False
    logger.info(f"starting earnings: {stockticker_name}")
    try:
        yahoo_ticker = yfinance.Ticker(stockticker_name)
        if yahoo_ticker.earnings_dates is None:
            # handle tickers with no earnings
            result = "no earnings"
        else:
            future_earnings_dates = [
                d.date()
                for d in yahoo_ticker.earnings_dates.index
                if d.date() >= datetime.now().date()
            ]
            result = sorted(future_earnings_dates)[0]
    except Exception as e:
        # Handle yahoo finance download failure.
        logger.error(f"failed to get {e}")
        result = None

    cache.set(cache_key, result, YAHOO_FINANCE_LONG_CACHE_TIMEOUT)
    elapsed = time.time() - start
    logger.info(f"fetched earnings: {stockticker_name} {elapsed}")
    if result == "no earnings":
        return None
    return result


def get_current_price(stockticker_name):
    closes = _get_recent_closes(stockticker_name)
    if closes is None:
        return None
    # Second element, since 2 closes are saved in cache
    if len(closes) < 2:
        return closes[0]
    return closes[1]


def get_previous_close_price(stockticker_name):
    closes = _get_recent_closes(stockticker_name)
    if closes is None:
        return None
    # First element, since 2 closes are saved in cache
    return closes[0]


def _get_recent_closes(stockticker_name):
    cache_key = "get_recent_closes_" + stockticker_name
    cached_result = cache.get(cache_key)
    if cached_result is not None:
        logger.info(f"cache hit for recent closes: {stockticker_name}")
        return cached_result
    start = time.time()
    try:
        yahoo_ticker = yfinance.Ticker(stockticker_name)
        yahoo_ticker_history = yahoo_ticker.history(period="10d")
    except JSONDecodeError:
        return None
    if yahoo_ticker_history.empty:
        return None
    result = yahoo_ticker_history.tail(2)["Close"]
    cache.set(cache_key, result, YAHOO_FINANCE_CACHE_TIMEOUT)
    elapsed = time.time() - start
    logger.info(f"fetched recent closes: {stockticker_name} {elapsed}")
    return result


# only look at the 10 closest option days, so about 2 months weekly options
def get_put_stats_for_ticker(
    ticker, maximum_option_days=10, options_per_day_to_consider=10
):
    ticker_name = ticker.name
    current_price = get_current_price(ticker_name)
    earnings = get_earnings(ticker_name)
    if current_price is None:
        return {"put_stats": [], "current_price": None}
    put_stats = []
    option_days = _get_option_days(ticker_name, maximum_option_days)
    if option_days is None:
        # can happen if option days fails to download
        return {"put_stats": [], "current_price": None}
    for option_day in option_days:
        puts = _get_option_chain(ticker_name, option_day, is_call=False)
        interesting_indicies = puts[puts["strike"].gt(current_price)].index
        if len(interesting_indicies) == 0:
            continue
        otm_threshold_index = interesting_indicies[0]
        # interesting defined as the 10 highest OTM puts (price is below strike price)
        # For our strategies, we don't particularly want to acquire the stock, so we
        # sell OTM
        interesting_puts = puts[
            max(
                otm_threshold_index - options_per_day_to_consider, 0
            ) : otm_threshold_index
        ]
        option_day_as_date_object = datetime.strptime(option_day, "%Y-%m-%d").date()
        # add one to business days since it includes the current day too
        days_to_expiry = busday_count_inclusive(
            datetime.now().date(), option_day_as_date_object
        )
        for index, interesting_put in interesting_puts.iterrows():
            put_stat = compute_put_stat(
                current_price,
                interesting_put,
                days_to_expiry,
                expiration_date=option_day,
            )
            if put_stat is not None:
                put_stat.update({"ticker": ticker})
                if earnings and earnings <= option_day_as_date_object:
                    put_stat.update({"includes_earnings": True})
                put_stats.append(put_stat)
    return {"put_stats": put_stats, "current_price": current_price}


# only look at the 10 closest option days, so about 2 months on weekly options
def get_call_stats_for_option_wheel(
    ticker, days_active_so_far, revenue, collateral, maximum_option_days=10
):
    ticker_name = ticker.name
    current_price = get_current_price(ticker_name)
    earnings = get_earnings(ticker_name)
    if current_price is None:
        return {"call_stats": [], "current_price": None}
    call_stats = []
    option_days = _get_option_days(ticker_name, maximum_option_days) or []
    for option_day in option_days:
        option_day_as_date_object = datetime.strptime(option_day, "%Y-%m-%d").date()
        # add one to business days since it includes the current day too
        days_to_expiry = busday_count_inclusive(
            datetime.now().date(), option_day_as_date_object
        )
        calls = _get_option_chain(ticker_name, option_day, is_call=True)
        interesting_indicies = calls[calls["strike"].gt(current_price)].index
        if len(interesting_indicies) == 0:
            continue
        otm_threshold_index = interesting_indicies[0]
        # For selling a call, analysis the 10 highest ITM calls and 10 lowest OTM calls
        # ITM calls might be useful to make sure the stock gets sold, while OTM calls
        # are useful to hold onto the stock until it recovers.
        interesting_calls = calls[
            max(otm_threshold_index - 10, 0) : min(
                otm_threshold_index + 10, calls.shape[0]
            )
        ]
        for _, interesting_call in interesting_calls.iterrows():
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
                call_stat.update({"ticker": ticker})
                if earnings and earnings <= option_day_as_date_object:
                    call_stat.update({"includes_earnings": True})
                call_stats.append(call_stat)
    return {"call_stats": call_stats, "current_price": current_price}


def compute_put_stat(current_price, interesting_put, days_to_expiry, expiration_date):
    volume = interesting_put.volume
    if volume < MINIMUM_VOLUME or numpy.isnan(volume):
        # Pprobably too low volume to be legit. Yahoo finance will show wrong prices
        return None
    if interesting_put.impliedVolatility == 0:
        # This likely indicates a broken option (bid/ask is busted),
        # and mibian will take a long time computing these
        return None
    strike, last_price, bid = [
        interesting_put.strike,
        interesting_put.lastPrice,
        interesting_put.bid,
    ]
    # Default to the last price (note that bid is 0 during off hours)
    effective_price = last_price
    if bid > 0:
        # During trading hours, assume worst case that we can only get the bid price
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
        # The price seems pretty stale. We should avoid computation since mibian's
        # computation will tend to time out in this case.
        return None

    RUN_NEW_FORUMLA = False
    if interesting_put.impliedVolatility > IMPOSSIBLE_IMPLIED_VOLATILITY:
        # Mibian times out if the implied volatility is too high. In this case run the
        # new formula.
        RUN_NEW_FORUMLA = True
    if RUN_NEW_FORUMLA:
        delta = compute_delta(
            current_price=current_price,
            strike=strike,
            interest_rate=INTEREST_RATE,
            days_to_expiry=days_to_expiry,
            option_price=effective_price,
            is_call=False,
        )
        probability_out_of_the_money = 1 + delta
    else:
        probability_out_of_the_money = _get_odds_otm(
            current_price, strike, days_to_expiry, effective_price
        )
    if not probability_out_of_the_money:
        return None
    max_profit_decimal = Decimal(effective_price / strike)
    # https://www.macroption.com/delta-calls-puts-probability-expiring-itm/
    # "Option’s delta as probability proxy"
    stats = {
        "strike": strike,
        "price": effective_price,
        "expiration_date": expiration_date,
        "days_to_expiry": days_to_expiry,
        "max_profit_decimal": max_profit_decimal,
        "decimal_odds_out_of_the_money_implied": probability_out_of_the_money,
        "annualized_rate_of_return_decimal": compute_annualized_rate_of_return(
            max_profit_decimal, probability_out_of_the_money, days_to_expiry
        ),
        "current_price": current_price,
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
        # Probably too low volume to be legit. Yahoo finance will show wrong prices
        return None
    if interesting_call.impliedVolatility == 0:
        # This likely indicates a broken option (bid/ask is busted),
        # and mibian will take a long time computing these
        return None
    strike, last_price, bid = [
        interesting_call.strike,
        interesting_call.lastPrice,
        interesting_call.bid,
    ]
    # Default to the last price (note that bid is 0 during off hours)
    effective_price = last_price
    if bid > 0:
        # During trading hours, assume worst case that we can only get the bid price
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
        # The price seems pretty stale. We should avoid computation since mibian's
        # computation will tend to time out in this case.
        return None

    if interesting_call.impliedVolatility > IMPOSSIBLE_IMPLIED_VOLATILITY:
        # Bail early, since mibian will fail
        return None
    call_implied_volatility_calculator = mibian.BS(
        [current_price, strike, INTEREST_RATE, days_to_expiry],
        callPrice=effective_price,
    )
    # kinda silly, we need to construct another object to extract delta for a
    # computation based on real call price.
    # Yahoo's volatility in interesting_call.impliedVolatility seems low, ~20% too low,
    #  so lets use the implied volatility
    implied_volatility = call_implied_volatility_calculator.impliedVolatility
    call_with_implied_volatility = mibian.BS(
        [current_price, strike, INTEREST_RATE, days_to_expiry],
        volatility=implied_volatility,
    )

    proposed_strike_difference_proceeds = strike - float(collateral)
    wheel_total_max_profit_decimal = (
        proposed_strike_difference_proceeds + effective_price + float(revenue)
    ) / float(collateral)

    # For computing the return of just this call, we ignore any previous profit/losses
    # and assume we had to buy the stock at the current price
    call_max_profit_decimal = Decimal(
        (strike + effective_price - current_price) / current_price
    )
    call_delta = call_with_implied_volatility.callDelta
    if isinstance(call_delta, float):
        odds = Decimal(call_delta)
    else:
        raise Exception("invalid call delta", call_delta)

    annualized_rate_of_return = compute_annualized_rate_of_return(
        call_max_profit_decimal, odds, days_to_expiry
    )
    stats = {
        "strike": strike,
        "price": effective_price,
        "expiration_date": expiration_date,
        "days_to_expiry": days_to_expiry,
        "call_max_profit_decimal": call_max_profit_decimal,
        "wheel_total_max_profit_decimal": wheel_total_max_profit_decimal,
        "decimal_odds_out_of_the_money_implied": odds,
        "annualized_rate_of_return_decimal": annualized_rate_of_return,
    }
    return stats
