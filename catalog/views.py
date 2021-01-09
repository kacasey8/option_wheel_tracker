from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.shortcuts import render, reverse, redirect
from django.urls import reverse_lazy
from django.utils import timezone
from django.views import generic

from catalog.forms import OptionPurchaseForm, StockTickerForm, SignupForm, OptionWheelForm
from catalog.models import OptionPurchase, StockTicker, OptionWheel

from datetime import datetime, timedelta, date

from .option_price_computation import (
    get_current_price,
    compute_put_stat,
    get_put_stats_for_ticker,
    compute_annualized_rate_of_return,
    get_call_stats_for_option_wheel
)

import numpy

def _get_next_friday():
    now = timezone.now()
    return now + timedelta((3 - now.weekday()) % 7 + 1)


def index(request):
    return render(request, 'index.html')

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

def global_put_comparison(request):
    context = {}
    put_stats = []
    for stock_ticker in StockTicker.objects.all():
        put_stats += get_put_stats_for_ticker(stock_ticker.name, maximum_option_days=4)['put_stats']
    context['put_stats'] = sorted(put_stats, key=lambda put: put['annualized_rate_of_return_decimal'], reverse=True)
    return render(request, 'global_put_comparison.html', context=context)


# StockTicker views
class StockTickerListView(generic.ListView):
    model = StockTicker
 
class StockTickerDetailView(generic.DetailView):
    model = StockTicker

    def get_context_data(self, **kwargs):
        context = super(StockTickerDetailView, self).get_context_data(**kwargs)
        result = get_put_stats_for_ticker(self.object.name)
        context['put_stats'] = sorted(result['put_stats'], key=lambda put: put['annualized_rate_of_return_decimal'], reverse=True)
        context['current_price'] = result['current_price']
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

        wheels = OptionWheel.objects.filter(user=user)
        sorted_wheels = sorted(wheels, key=lambda x: (x.get_expiration_date(), x.get_open_date()), reverse=True)

        expired = []
        active = []
        completed = []
        for wheel in sorted_wheels:
            if (wheel.is_expired()):
                expired.append(wheel)
            elif (wheel.is_active):
                active.append(wheel)
            else:
                completed.append(wheel)

        queryset = {
            'expired_wheels': expired,
            'active_wheels': active, 
            'completed_wheels': completed,
        }
        return queryset

class OptionWheelDetailView(LoginRequiredMixin, generic.DetailView):
    model = OptionWheel
    context_object_name = 'wheel'

    def get_context_data(self, **kwargs):
        context = super(OptionWheelDetailView, self).get_context_data(**kwargs)
        option_wheel = OptionWheel.objects.get(pk=self.kwargs.get('pk'))
        purchases = option_wheel.get_all_option_purchases()
        cost_basis = option_wheel.get_cost_basis()
        profit_if_exits_here = 'N/A'
        annualized_rate_of_return_if_exits_here = 'N/A'
        days_active_so_far = 'N/A'
        decimal_rate_of_return = 'N/A'
        expires = None
        if purchases:
            first_purchase = option_wheel.get_first_option_purchase()
            last_purchase = option_wheel.get_last_option_purchase()
            if last_purchase.expiration_date > timezone.now().date():
                expires = last_purchase.expiration_date
            profit_if_exits_here = last_purchase.strike - cost_basis
            days_active_so_far = numpy.busday_count(
                first_purchase.purchase_date.date(),
                last_purchase.expiration_date,
            )
            decimal_rate_of_return = float(profit_if_exits_here / first_purchase.strike)
            annualized_rate_of_return_if_exits_here = compute_annualized_rate_of_return(decimal_rate_of_return, 1, days_active_so_far)
            # days active so far basically assumes that if the last purchase is still ongoing
            # that we'll be able to duplicate the current situation after the last purchase expires
            if option_wheel.is_active:
                # call_stats = get_call_stats_for_option_wheel(option_wheel.stock_ticker.name, days_active_so_far, option_wheel.get_revenue(), collateral=first_purchase.strike)
                # context['call_stats'] = call_stats['call_stats']
                context['call_stats'] = []
        context['decimal_rate_of_return'] = decimal_rate_of_return
        context['profit_if_exits_here'] = profit_if_exits_here
        context['annualized_rate_of_return_if_exits_here'] = annualized_rate_of_return_if_exits_here
        context['days_active_so_far'] = days_active_so_far
        context['purchases'] = purchases
        context['cost_basis'] = cost_basis
        context['expires'] = expires

        current_price = get_current_price(option_wheel.stock_ticker.name)
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

        bus_days = numpy.busday_count(
            first_purchase.purchase_date.date(),
            last_purchase.expiration_date,
        )
        max_collatoral = max(purchase.strike for purchase in purchases)

        option_wheel.total_profit = profit
        option_wheel.total_days_active = bus_days
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

    def get_initial(self):
        user = self.request.user
        return {
            'user': user, 
            'is_active': True
        }

    def get_success_url(self):
        return reverse('purchase-create', args=[str(self.object.id)])

class OptionWheelUpdate(generic.edit.UpdateView):
    model = OptionWheel
    form_class = OptionWheelForm

    def get_success_url(self):
        return reverse('wheel-detail', args=[str(self.object.id)])

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
        current_price = get_current_price(option_wheel.stock_ticker.name)
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
        context['cost_basis'] = option_wheel.get_cost_basis()
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
