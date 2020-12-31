from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.shortcuts import render, reverse, redirect
from django.urls import reverse_lazy
from django.utils import timezone
from django.views import generic

from catalog.forms import OptionPurchaseForm, StockTickerForm, SignupForm, OptionWheelForm
from catalog.models import OptionPurchase, StockTicker, OptionWheel

from datetime import datetime, timedelta, date

import yfinance
import mibian
import numpy

# see https://ycharts.com/indicators/10_year_treasury_rate#:~:text=10%20Year%20Treasury%20Rate%20is%20at%200.94%25%2C%20compared%20to%200.94,long%20term%20average%20of%204.39%25.
INTEREST_RATE = 1
BUSINESS_DAYS_IN_YEAR = 252

def _get_next_friday():
    now = timezone.now()
    return now + timedelta((3 - now.weekday()) % 7 + 1)

def _get_current_price(stockticker_name):
    yahoo_ticker = yfinance.Ticker(stockticker_name)
    yahoo_ticker_history = yahoo_ticker.history(period="1d")
    if yahoo_ticker_history.empty:
        return None
    return yahoo_ticker_history.tail(1)['Close'].iloc[0]

def _compute_put_stat(current_price, interesting_put, days_to_expiry, historical_volatility, expiration_date):
    put_implied_volatility_calculator = mibian.BS([current_price, interesting_put.strike, INTEREST_RATE, days_to_expiry], putPrice=interesting_put.lastPrice)
    # kinda silly, we need to construct another object to extract delta for a computation based on real put price
    implied_volatility = put_implied_volatility_calculator.impliedVolatility # Yahoo's volatility in interesting_put.impliedVolatility seems low, ~20% too low
    put_with_implied_volatility = mibian.BS([current_price, interesting_put.strike, INTEREST_RATE, days_to_expiry], volatility=implied_volatility)
    max_profit_decimal = interesting_put.lastPrice / interesting_put.strike
    stats = {
        "strike": interesting_put.strike,
        "price": interesting_put.lastPrice,
        "expiration_date": expiration_date,
        "days_to_expiry": days_to_expiry,
        # https://www.macroption.com/delta-calls-puts-probability-expiring-itm/ "Option’s delta as probability proxy"
        "max_profit_decimal": max_profit_decimal,
        "decimal_odds_in_the_money_implied": 1 + put_with_implied_volatility.putDelta,
        "annualized_rate_of_return_decimal": (1 + max_profit_decimal) ** ((1 + put_with_implied_volatility.putDelta) * BUSINESS_DAYS_IN_YEAR / days_to_expiry * (1 + put_with_implied_volatility.putDelta))
    }

    if False:
        # these extra computations are interesting, but take extra processing time
        put = mibian.BS([current_price, interesting_put.strike, INTEREST_RATE, days_to_expiry], volatility=historical_volatility)
        put_with_premium = mibian.BS([current_price, interesting_put.strike - interesting_put.lastPrice, INTEREST_RATE, days_to_expiry], volatility=historical_volatility)
        put_with_premium_with_implied_volatility = mibian.BS([current_price, interesting_put.strike - interesting_put.lastPrice, INTEREST_RATE, days_to_expiry], volatility=implied_volatility)
        stats.update({
            "historical_expected_put_price": put.putPrice,
            "actual_put_price": interesting_put.lastPrice,
            "decimal_odds_profitable_historical": 1 + put_with_premium.putDelta,
            "decimal_odds_profitable_implied": 1 + put_with_premium_with_implied_volatility.putDelta,
            "decimal_odds_in_the_money_historical": 1 + put.putDelta,
        })


    return stats


def index(request):
    stock_tickers = StockTicker.objects.all()
    stable_choices = StockTicker.objects.filter(recommendation__exact='ST')

    context = {
        'stock_tickers': stock_tickers,
        'stable_choices': stable_choices,
    }
    return render(request, 'index.html', context=context)

def signup(request):
    if request.method == 'POST':
        form = SignupForm(request.POST)
        if form.is_valid():
            form.save()
            return redirect('signup-complete')
    else:
        form = SignupForm()
    return render(request, 'signup.html', {'form': form})

def signup_complete(request):
    return render(request, 'signup_complete.html')


# StockTicker views
class StockTickerListView(generic.ListView):
    model = StockTicker
 
class StockTickerDetailView(generic.DetailView):
    model = StockTicker

    def get_context_data(self, **kwargs):
        context = super(StockTickerDetailView, self).get_context_data(**kwargs)
        yahoo_ticker = yfinance.Ticker(self.object.name)
        yahoo_ticker_history = yahoo_ticker.history(period="150d")
        # https://blog.quantinsti.com/volatility-and-measures-of-risk-adjusted-return-based-on-volatility/
        logarithmic_returns = numpy.log(yahoo_ticker_history['Close'] / yahoo_ticker_history['Close'].shift(1))
        historical_volatility = logarithmic_returns.std() * numpy.sqrt(BUSINESS_DAYS_IN_YEAR) * 100
        if yahoo_ticker_history.empty:
            return context
        current_price = yahoo_ticker_history.tail(1)['Close'].iloc[0]
        context['current_price'] = current_price
        put_stats = []
        # only look at the 5 closest option days, so about a month for weekly options
        option_days = yahoo_ticker.options[:5]
        for option_day in option_days:
            puts = yahoo_ticker.option_chain(option_day).puts
            interesting_index = puts[puts['strike'].gt(current_price)].index[0]
            # interesting defined as the 3 highest OTM puts (price is below strike price)
            # For our strategies it never really seems great to do a ITM put
            interesting_puts = puts[max(interesting_index - 10, 0):interesting_index]
            option_day_as_date_object = datetime.strptime(option_day, '%Y-%m-%d').date()
            days_to_expiry = numpy.busday_count(datetime.now().date(), option_day_as_date_object)
            for index, interesting_put in interesting_puts.iterrows():
                put_stats.append(_compute_put_stat(current_price, interesting_put, days_to_expiry, historical_volatility, expiration_date=option_day))
        context['put_stats'] = sorted(put_stats, key=lambda put: put['annualized_rate_of_return_decimal'], reverse=True)
        return context


 
class OptionPurchaseDetailView(generic.DetailView):
    model = OptionPurchase

class StockTickerCreate(generic.edit.CreateView):
    model = StockTicker
    form_class = StockTickerForm
    success_url = reverse_lazy('tickers')

class StockTickerUpdate(generic.edit.UpdateView):
    model = StockTicker
    form_class = StockTickerForm
    success_url = reverse_lazy('tickers')

class StockTickerDelete(generic.edit.DeleteView):
    model = StockTicker
    success_url = reverse_lazy('tickers')


# OptionWheel views
class OptionWheelListView(LoginRequiredMixin, generic.ListView):
    model = OptionWheel
    context_object_name = 'wheels'
    template_name = 'catalog/optionwheel_list.html'

    def get_queryset(self):
        user = self.request.user
        active = OptionWheel.objects.filter(user=user, is_active=True)
        active_sorted = sorted(active, key=lambda x: x.get_open_date(), reverse=True)
        completed = OptionWheel.objects.filter(user=user, is_active=False)
        completed_sorted = sorted(completed, key=lambda x: x.get_open_date(), reverse=True)
        queryset = {
            'active_wheels': active_sorted, 
            'completed_wheels': completed_sorted,
        }
        return queryset

class OptionWheelDetailView(LoginRequiredMixin, generic.DetailView):
    model = OptionWheel
    context_object_name = 'wheel'

    def get_context_data(self, **kwargs):
        context = super(OptionWheelDetailView, self).get_context_data(**kwargs)
        option_wheel = OptionWheel.objects.get(pk=self.kwargs.get('pk'))
        purchases = option_wheel.get_all_option_purchases()
        revenue = sum(purchase.premium for purchase in purchases)
        cost_basis = 'N/A'
        expires = None
        if purchases:
            last_purchase = purchases[0]
            cost_basis = last_purchase.strike - revenue
            if last_purchase.expiration_date > timezone.now().date():
                expires = last_purchase.expiration_date
        context['purchases'] = purchases
        context['cost_basis'] = cost_basis
        context['expires'] = expires

        current_price = _get_current_price(option_wheel.stock_ticker.name)
        context['current_price'] = current_price
        return context


@login_required
def complete_wheel(request, pk):
    option_wheel = OptionWheel.objects.get(pk=pk)
    purchases = option_wheel.get_all_option_purchases()

    option_wheel.is_active = False
    if purchases:
        last_purchase = purchases[0]
        first_purchase = purchases[len(purchases) - 1]

        premiums = sum(purchase.premium for purchase in purchases)
        profit = premiums + last_purchase.strike - first_purchase.strike
        total_profit = option_wheel.quantity * profit

        days = (last_purchase.expiration_date - first_purchase.purchase_date.date()).days
        max_collatoral = max(purchase.strike for purchase in purchases)

        option_wheel.total_profit = total_profit
        option_wheel.total_days_active = days
        option_wheel.collatoral = max_collatoral
    option_wheel.save()
    return redirect('wheel-detail', pk=pk)

@login_required
def reactivate_wheel(request, pk):
    option_wheel = OptionWheel.objects.get(pk=pk)
    option_wheel.is_active = True
    option_wheel.save()
    return redirect('wheel-detail', pk=pk)

class OptionWheelCreate(generic.edit.CreateView):
    model = OptionWheel
    form_class = OptionWheelForm
    success_url = reverse_lazy('wheels')

    def get_initial(self):
        user = self.request.user
        return {
            'user': user, 
            'is_active': True
        }

class OptionWheelUpdate(generic.edit.UpdateView):
    model = OptionWheel
    form_class = OptionWheelForm
    success_url = reverse_lazy('wheels')

class OptionWheelDelete(LoginRequiredMixin, generic.edit.DeleteView):
    model = OptionWheel
    success_url = reverse_lazy('wheels')


# OptionPurchase views
class OptionPurchaseDetailView(LoginRequiredMixin, generic.DetailView):
    model = OptionPurchase

class OptionPurchaseCreate(LoginRequiredMixin, generic.edit.CreateView):
    model = OptionPurchase
    form_class = OptionPurchaseForm

    def get_initial(self):
        user = self.request.user
        option_wheel = OptionWheel.objects.get(pk=self.kwargs.get('wheel_id'))

        price_at_date = None
        current_price = _get_current_price(option_wheel.stock_ticker.name)
        if current_price:
            price_at_date = round(current_price, 2)

        first_strike = None
        call_or_put = 'P'
        first_option_purchase = option_wheel.get_first_option_purchase()
        if first_option_purchase:
            call_or_put = 'C'
            first_strike = first_option_purchase.strike
        now = timezone.now()
        return {
            'user': user, 
            'option_wheel': option_wheel,
            'purchase_date': now,
            'expiration_date': _get_next_friday(),
            'call_or_put': call_or_put,
            'strike': first_strike,
            'price_at_date': price_at_date
        }

    def get_context_data(self, **kwargs):
        context = super(OptionPurchaseCreate, self).get_context_data(**kwargs)
        option_wheel = OptionWheel.objects.get(pk=self.kwargs.get('wheel_id'))
        context['option_wheel'] = option_wheel
        return context

    def get_success_url(self):
        wheel_id = self.kwargs.get('wheel_id')
        return reverse('wheel-detail', args=[str(wheel_id)])

class OptionPurchaseUpdate(LoginRequiredMixin, generic.edit.UpdateView):
    model = OptionPurchase
    form_class = OptionPurchaseForm

class OptionPurchaseDelete(LoginRequiredMixin, generic.edit.DeleteView):
    model = OptionPurchase

    def get_success_url(self):
        wheel_id = self.kwargs.get('wheel_id')
        return reverse('wheel-detail', args=[str(wheel_id)])
