from datetime import datetime

import yfinance
import mibian
import numpy

COMPUTE_EXTRA_STATS = False
# interest rate: https://ycharts.com/indicators/10_year_treasury_rate#:~:text=10%20Year%20Treasury%20Rate%20is%20at%200.94%25%2C%20compared%20to%200.94,long%20term%20average%20of%204.39%25.
INTEREST_RATE = 1
BUSINESS_DAYS_IN_YEAR = 252

def get_current_price(stockticker_name):
    yahoo_ticker = yfinance.Ticker(stockticker_name)
    yahoo_ticker_history = yahoo_ticker.history(period="1d")
    if yahoo_ticker_history.empty:
        return None
    return yahoo_ticker_history.tail(1)['Close'].iloc[0]

# only look at the 10 closest option days, so about 2 months weekly options
def get_put_stats_for_ticker(ticker_name, maximum_option_days=10):
    yahoo_ticker = yfinance.Ticker(ticker_name)
    if COMPUTE_EXTRA_STATS:
        yahoo_ticker_history = yahoo_ticker.history(period="150d")
        # https://blog.quantinsti.com/volatility-and-measures-of-risk-adjusted-return-based-on-volatility/
        logarithmic_returns = numpy.log(yahoo_ticker_history['Close'] / yahoo_ticker_history['Close'].shift(1))
        historical_volatility = logarithmic_returns.std() * numpy.sqrt(BUSINESS_DAYS_IN_YEAR) * 100
    else:
        historical_volatility = None
        yahoo_ticker_history = yahoo_ticker.history(period="1d")
    if yahoo_ticker_history.empty:
        return {'put_stats': [], 'current_price': None}
    current_price = yahoo_ticker_history.tail(1)['Close'].iloc[0]
    put_stats = []
    option_days = yahoo_ticker.options[:maximum_option_days]
    for option_day in option_days:
        puts = yahoo_ticker.option_chain(option_day).puts
        interesting_indicies = puts[puts['strike'].gt(current_price)].index
        if len(interesting_indicies) == 0:
            continue
        interesting_index = interesting_indicies[0]
        # interesting defined as the 3 highest OTM puts (price is below strike price)
        # For our strategies it never really seems great to do a ITM put
        interesting_puts = puts[max(interesting_index - 10, 0):interesting_index]
        option_day_as_date_object = datetime.strptime(option_day, '%Y-%m-%d').date()
        # add one to business days since it includes the current day too
        days_to_expiry = numpy.busday_count(datetime.now().date(), option_day_as_date_object) + 1
        for index, interesting_put in interesting_puts.iterrows():
            put_stat = compute_put_stat(current_price, interesting_put, days_to_expiry, historical_volatility, expiration_date=option_day)
            if put_stat is not None:
                put_stat.update({"ticker": ticker_name})
                put_stats.append(put_stat)
    return {'put_stats': put_stats, 'current_price': current_price}

def compute_put_stat(current_price, interesting_put, days_to_expiry, historical_volatility, expiration_date):
    strike, last_price, bid, ask = [interesting_put.strike, interesting_put.lastPrice, interesting_put.bid, interesting_put.ask]
    volume = interesting_put.volume
    if volume < 10 or numpy.isnan(volume):
        # These are probably too low volume to be legit. Yahoo finance will show wrong prices
        return None
    effective_price = last_price
    if (bid == 0 and ask == 0) == False:
        # bid and ask will be 0 during off hours, so use last_price as an estimate.
        # During trading hours we assume we'll assuming worse case that we can only get it for bid price
        effective_price = bid
    if effective_price == 0:
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
        "decimal_odds_in_the_money_implied": 1 + put_with_implied_volatility.putDelta,
        "annualized_rate_of_return_decimal": (1 + max_profit_decimal) ** ((1 + put_with_implied_volatility.putDelta) * BUSINESS_DAYS_IN_YEAR / days_to_expiry * (1 + put_with_implied_volatility.putDelta))
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