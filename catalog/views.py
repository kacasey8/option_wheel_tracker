from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.shortcuts import render, reverse, redirect
from django.urls import reverse_lazy
from django.utils import timezone
from django.views import generic

from catalog.forms import OptionPurchaseForm, StockTickerForm, SignupForm
from catalog.models import OptionPurchase, StockTicker, OptionWheel

from datetime import timedelta


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

class StockTickerListView(generic.ListView):
    model = StockTicker
 
class StockTickerDetailView(generic.DetailView):
    model = StockTicker

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

 
class OptionPurchaseDetailView(generic.DetailView):
    model = OptionPurchase

class OptionWheelListView(LoginRequiredMixin, generic.ListView):
    model = OptionWheel
    context_object_name = 'wheels'
    template_name = 'catalog/optionwheel_list.html'

    def get_queryset(self):
        user = self.request.user
        queryset = {
            'active_wheels': OptionWheel.objects.filter(user=user, is_active=True), 
            'completed_wheels': OptionWheel.objects.filter(user=user, is_active=False),
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
    return redirect('wheel-detail', pk=option_wheel.pk)

class OptionWheelDelete(generic.edit.DeleteView):
    model = OptionWheel
    success_url = reverse_lazy('wheels')

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
        next_friday = now + timedelta((3 - now.weekday()) % 7 + 1)
        return {
            'user': user, 
            'option_wheel': option_wheel,
            'purchase_date': now,
            'expiration_date': next_friday,
            'stock_ticker': stock_ticker,
        }

    def get_success_url(self):
        wheel_id = self.kwargs.get('wheel_id')
        return reverse('wheel-detail', args=[str(wheel_id)])


class OptionPurchaseUpdate(generic.edit.UpdateView):
    model = OptionPurchase
    form_class = OptionPurchaseForm


class OptionPurchaseDelete(generic.edit.DeleteView):
    model = OptionPurchase

    def get_success_url(self):
        wheel_id = self.kwargs.get('wheel_id')
        return reverse('wheel-detail', args=[str(wheel_id)])
