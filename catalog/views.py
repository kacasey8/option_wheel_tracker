from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.shortcuts import render, reverse, redirect
from django.urls import reverse_lazy
from django.utils import timezone
from django.views import generic

from catalog.forms import OptionPurchaseForm, StockTickerForm, SignupForm
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
        historical_volatility = logarithmic_returns.std() * numpy.sqrt(252) * 100
        current_price = yahoo_ticker_history.tail(1)['Close'].iloc[0]
        context['current_price'] = current_price
        put_stats = []
        option_days = [yahoo_ticker.options[0], yahoo_ticker.options[1]]
        for option_day in option_days:
            puts = yahoo_ticker.option_chain(option_day).puts
            interesting_index = puts[puts['strike'].gt(current_price)].index[0]
            # interesting defined as the 3 highest OTM puts (price is below strike price)
            # For our strategies it never really seems great to do a ITM put
            interesting_puts = puts[max(interesting_index - 3, 0):interesting_index]
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
        user = self.request.user
        option_wheel_id = self.kwargs.get('pk')
        purchases = OptionPurchase.objects.filter(user=user, option_wheel=option_wheel_id).order_by('-expiration_date')
        revenue = sum(purchase.premium for purchase in purchases)
        cost_basis = 'N/A'
        if purchases:
            cost_basis = purchases[0].strike - revenue
        context['purchases'] = purchases
        context['cost_basis'] = cost_basis
        return context

@login_required
def create_wheel(request):
    user = request.user
    option_wheel = OptionWheel(user=user, is_active=True)
    option_wheel.save()
    return redirect('purchase-create', wheel_id=option_wheel.pk)

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
        stock_ticker = None
        first_option_purchase = option_wheel.get_first_option_purchase()
        if first_option_purchase:
            stock_ticker = first_option_purchase.stock_ticker
        now = timezone.now()
        return {
            'user': user, 
            'option_wheel': option_wheel,
            'purchase_date': now,
            'expiration_date': _get_next_friday(),
            'stock_ticker': stock_ticker,
        }

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
