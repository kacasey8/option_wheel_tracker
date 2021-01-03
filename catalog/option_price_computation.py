from datetime import datetime

import yfinance
import mibian
import numpy

COMPUTE_EXTRA_STATS = False
# interest rate: https://ycharts.com/indicators/10_year_treasury_rate#:~:text=10%20Year%20Treasury%20Rate%20is%20at%200.94%25%2C%20compared%20to%200.94,long%20term%20average%20of%204.39%25.
INTEREST_RATE = 1
BUSINESS_DAYS_IN_YEAR = 252
# Some stats on yahoo finance are only based on a few stray trades, so we need to remove those
# because these are false
MINIMUM_VOLUME = 20

# For puts, we assume that when we fail we get a rate of return of 1x. For calls
# we assume we just miss out on the profits of the last strike, but everything else has already
# occured
def compute_annualized_rate_of_return(profit_decimal, odds, days, profit_decimal_fail_case=0):
    rate_of_return_success_case = 1 + profit_decimal
    rate_of_return_fail_case = 1 + profit_decimal_fail_case
    effective_rate_of_return = rate_of_return_success_case * odds + rate_of_return_fail_case * (1 - odds)
    return effective_rate_of_return ** (BUSINESS_DAYS_IN_YEAR / days)

def get_current_price(stockticker_name):
    yahoo_ticker = yfinance.Ticker(stockticker_name)
    yahoo_ticker_history = yahoo_ticker.history(period="1d")
    if yahoo_ticker_history.empty:
        return None
    return yahoo_ticker_history.tail(1)['Close'].iloc[0]

def get_yfinance_history(ticker_name):
    yahoo_ticker = yfinance.Ticker(ticker_name)
    if COMPUTE_EXTRA_STATS:
        yahoo_ticker_history = yahoo_ticker.history(period="150d")
        # https://blog.quantinsti.com/volatility-and-measures-of-risk-adjusted-return-based-on-volatility/
        logarithmic_returns = numpy.log(yahoo_ticker_history['Close'] / yahoo_ticker_history['Close'].shift(1))
        historical_volatility = logarithmic_returns.std() * numpy.sqrt(BUSINESS_DAYS_IN_YEAR) * 100
    else:
        yahoo_ticker_history = yahoo_ticker.history(period="1d")
        historical_volatility = None
    if yahoo_ticker_history.empty:
        return None
    return {
        'yahoo_ticker': yahoo_ticker,
        'yahoo_ticker_history': yahoo_ticker_history,
        'historical_volatility': historical_volatility,
        'current_price': yahoo_ticker_history.tail(1)['Close'].iloc[0]
    }

# only look at the 10 closest option days, so about 2 months weekly options
def get_put_stats_for_ticker(ticker_name, maximum_option_days=10):
    yfinance_history = get_yfinance_history(ticker_name)
    if yfinance_history is None:
        return {'put_stats': [], 'current_price': None}
    yahoo_ticker = yfinance_history['yahoo_ticker']
    yahoo_ticker_history = yfinance_history['yahoo_ticker_history']
    historical_volatility = yfinance_history['historical_volatility']
    current_price = yfinance_history['current_price']
    put_stats = []
    option_days = yahoo_ticker.options[:maximum_option_days]
    for option_day in option_days:
        puts = yahoo_ticker.option_chain(option_day).puts
        interesting_indicies = puts[puts['strike'].gt(current_price)].index
        if len(interesting_indicies) == 0:
            continue
        otm_threshold_index = interesting_indicies[0]
        # interesting defined as the 10 highest OTM puts (price is below strike price)
        # For our strategies, we don't particularly want to acquire the stock, so we sell OTM
        interesting_puts = puts[max(otm_threshold_index - 10, 0):otm_threshold_index]
        option_day_as_date_object = datetime.strptime(option_day, '%Y-%m-%d').date()
        # add one to business days since it includes the current day too
        days_to_expiry = numpy.busday_count(datetime.now().date(), option_day_as_date_object) + 1
        for index, interesting_put in interesting_puts.iterrows():
            put_stat = compute_put_stat(
                current_price,
                interesting_put,
                days_to_expiry,
                historical_volatility,
                expiration_date=option_day
            )
            if put_stat is not None:
                put_stat.update({"ticker": ticker_name})
                put_stats.append(put_stat)
    return {'put_stats': put_stats, 'current_price': current_price}

# only look at the 10 closest option days, so about 2 months on weekly options
def get_call_stats_for_option_wheel(ticker_name, days_active_so_far, revenue, collateral, maximum_option_days=10):
    yfinance_history = get_yfinance_history(ticker_name)
    if yfinance_history is None:
        return {'call_stats': [], 'current_price': None}
    yahoo_ticker = yfinance_history['yahoo_ticker']
    yahoo_ticker_history = yfinance_history['yahoo_ticker_history']
    historical_volatility = yfinance_history['historical_volatility']
    current_price = yfinance_history['current_price']
    call_stats = []
    option_days = yahoo_ticker.options[:maximum_option_days]
    for option_day in option_days:
        option_day_as_date_object = datetime.strptime(option_day, '%Y-%m-%d').date()
        # add one to business days since it includes the current day too
        days_to_expiry = numpy.busday_count(datetime.now().date(), option_day_as_date_object) + 1
        calls = yahoo_ticker.option_chain(option_day).calls
        interesting_indicies = calls[calls['strike'].gt(current_price)].index
        if len(interesting_indicies) == 0:
            continue
        otm_threshold_index = interesting_indicies[0]
        # For selling a call, we'll analysis the 5 highest ITM calls and 5 lowest OTM calls
        # ITM calls might be useful to make sure the stock gets sold, while OTM calls are useful
        # to hold onto the stock until it recovers.
        interesting_calls = calls[max(otm_threshold_index - 5, 0):min(otm_threshold_index + 5, calls.shape[0])]
        for index, interesting_call in interesting_calls.iterrows():
            call_stat = compute_call_stat(
                current_price,
                interesting_call,
                days_to_expiry,
                historical_volatility,
                expiration_date=option_day,
                days_active_so_far=days_active_so_far,
                revenue=revenue,
                collateral=collateral,
            )
            if call_stat is not None:
                call_stat.update({"ticker": ticker_name})
                call_stats.append(call_stat)
    return {'call_stats': call_stats, 'current_price': current_price}

def compute_put_stat(current_price, interesting_put, days_to_expiry, historical_volatility, expiration_date):
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
    if effective_price == 0:
        return None
    if strike > current_price + effective_price:
        # this option has no intrinsic value, since it would be more efficient
        # to just buy the stock on the open market in this case. This is probably from
        # there being no legitimate bids, and we need to skip, since mibian will lag out
        # if it attempts to compute this
        return None
    put_implied_volatility_calculator = mibian.BS([current_price, strike, INTEREST_RATE, days_to_expiry], putPrice=effective_price)
    # kinda silly, we need to construct another object to extract delta for a computation based on real put price
    # Yahoo's volatility in interesting_put.impliedVolatility seems low, ~20% too low, so lets use the implied volatility
    implied_volatility = put_implied_volatility_calculator.impliedVolatility
    put_with_implied_volatility = mibian.BS([current_price, strike, INTEREST_RATE, days_to_expiry], volatility=implied_volatility)
    max_profit_decimal = effective_price / strike
    stats = {
        "strike": strike,
        "price": effective_price,
        "expiration_date": expiration_date,
        "days_to_expiry": days_to_expiry,
        # https://www.macroption.com/delta-calls-puts-probability-expiring-itm/ "Option’s delta as probability proxy"
        "max_profit_decimal": max_profit_decimal,
        "decimal_odds_out_of_the_money_implied": 1 + put_with_implied_volatility.putDelta,
        "annualized_rate_of_return_decimal": compute_annualized_rate_of_return(max_profit_decimal, 1 + put_with_implied_volatility.putDelta, days_to_expiry)
    }

    if COMPUTE_EXTRA_STATS:
        # these extra computations are interesting, but take extra processing time
        put = mibian.BS([current_price, strike, INTEREST_RATE, days_to_expiry], volatility=historical_volatility)
        put_with_premium = mibian.BS([current_price, strike - effective_price, INTEREST_RATE, days_to_expiry], volatility=historical_volatility)
        put_with_premium_with_implied_volatility = mibian.BS([current_price, strike - effective_price, INTEREST_RATE, days_to_expiry], volatility=implied_volatility)
        stats.update({
            "historical_expected_put_price": put.putPrice,
            "actual_put_price": effective_price,
            "decimal_odds_profitable_historical": 1 + put_with_premium.putDelta,
            "decimal_odds_profitable_implied": 1 + put_with_premium_with_implied_volatility.putDelta,
            "decimal_odds_in_the_money_historical": 1 + put.putDelta,
        })


    return stats

def compute_call_stat(
    current_price,
    interesting_call,
    days_to_expiry,
    historical_volatility,
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
    if effective_price == 0:
        return None
    if strike + effective_price < current_price:
        # this option has no intrinsic value, since it would be more efficient
        # to just sell the stock on the open market in this case. This is probably from
        # there being no legitimate bids, and we need to skip, since mibian will lag out
        # if it attempts to compute this
        return None
    call_implied_volatility_calculator = mibian.BS([current_price, strike, INTEREST_RATE, days_to_expiry], callPrice=effective_price)
    # kinda silly, we need to construct another object to extract delta for a computation based on real call price
    # Yahoo's volatility in interesting_call.impliedVolatility seems low, ~20% too low, so lets use the implied volatility
    implied_volatility = call_implied_volatility_calculator.impliedVolatility
    call_with_implied_volatility = mibian.BS([current_price, strike, INTEREST_RATE, days_to_expiry], volatility=implied_volatility)
    proposed_strike_difference_proceeds = strike - float(collateral)
    max_profit_decimal = (proposed_strike_difference_proceeds + effective_price + float(revenue)) / float(collateral)

    odds = call_with_implied_volatility.callDelta
    total_days_to_expiry = days_to_expiry + days_active_so_far
    success_rate_of_return = (1 + max_profit_decimal) ** (BUSINESS_DAYS_IN_YEAR / total_days_to_expiry)
    # In the case that we keep the stock, one choice is to sell the stock on the open market right after
    # We'll assume the stock price decays at a slow rate, of at most .1% loss each day.
    failure_rate_of_return = 1 + (effective_price + float(revenue) + current_price * (0.999 ** days_to_expiry) - float(collateral)) / float(collateral)
    # If this is profitable, we'll repeat it the rest of the year
    # if not, we'll assume it takes the rest of the year to recover, but that we can secure a net equal return
    if failure_rate_of_return > 1:
        failure_rate_of_return = failure_rate_of_return ** (BUSINESS_DAYS_IN_YEAR / total_days_to_expiry)
    else:
        failure_rate_of_return = 1
    annualized_rate_of_return = odds * success_rate_of_return + (1 - odds) * failure_rate_of_return
    stats = {
        "strike": strike,
        "price": effective_price,
        "expiration_date": expiration_date,
        "days_to_expiry": days_to_expiry,
        "total_days_to_expiry": total_days_to_expiry,
        "max_profit_decimal": max_profit_decimal,
        "decimal_odds_out_of_the_money_implied": odds,
        "annualized_rate_of_return_decimal": annualized_rate_of_return
    }
    return stats
