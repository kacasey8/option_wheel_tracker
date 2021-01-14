from math import sqrt, exp, log, pi
from scipy.stats import norm
from scipy.special import ndtr

# taken from https://github.com/kpmooney/numerical_methods_youtube/blob/master/root_finding/implied_volatility/find_vol_put.py

# volatility moves by less than 1%
TOLERANCE = 0.01
# bail out after 20 iterations, either we find a good volatility or just give up here
MAX_ITERATIONS = 20

# S is current price, K is strike, r is interest rate, t is time
# Function to calculate the values of d1 and d2
def d(sigma, S, K, r, t):
    d1 = 1 / (sigma * sqrt(t)) * ( log(S/K) + (r + sigma**2/2) * t)
    d2 = d1 - sigma * sqrt(t)
    return d1, d2

def call_price(sigma, S, K, r, t, d1, d2):
    C = ndtr(d1) * S - ndtr(d2) * K * exp(-r * t)
    return C


def put_price(sigma, S, K, r, t, d1, d2):
    P = -ndtr(-d1) * S + ndtr(-d2) * K * exp(-r * t)
    return P

# only works for puts right now
def compute_delta(current_price, strike, interest_rate, days_to_expiry, option_price, is_call):
  # epsilon is how far off the guess is
  epsilon = 1
  # initial guess is 0.5
  volatility = 0.50
  t = days_to_expiry / 365.0
  # This calculator assumes the interest rate is a percent
  interest_rate = interest_rate / 100.0

  for _ in range(MAX_ITERATIONS):
    #  Log the value previously calculated to computer percent change
    #  between iterations
    orig_volatility = volatility

    #  Calculate the value of the call price
    d1, d2 = d(volatility, current_price, strike, interest_rate, t)
    if is_call:
      value = call_price(volatility, current_price, strike, interest_rate, t, d1, d2) - option_price
    else:
      value = put_price(volatility, current_price, strike, interest_rate, t, d1, d2) - option_price

    #  Calculate vega, the derivative of the price with respect to
    #  volatility
    vega = current_price * norm._pdf(d1) * sqrt(t)

    #  Update for value of the volatility
    volatility += -value / vega

    #  Check the percent change between current and last iteration
    epsilon = abs( (volatility - orig_volatility) / orig_volatility )
    if epsilon < TOLERANCE:
      break
  # http://janroman.dhis.org/stud/I2014/BS2/BS_Daniel.pdf, compute put delta
  return -ndtr(-d1)
