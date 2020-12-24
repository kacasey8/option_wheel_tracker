from django.shortcuts import render
from .models import StockTicker, OptionWheel
from django.views import generic

def index(request):
    stock_tickers = StockTicker.objects.all()
    stable_choices = StockTicker.objects.filter(recommendation__exact='ST')

    context = {
        'stock_tickers': stock_tickers,
        'stable_choices': stable_choices,
    }
    return render(request, 'index.html', context=context)

class StockTickerListView(generic.ListView):
    model = StockTicker
 
class StockTickerDetailView(generic.DetailView):
    model = StockTicker

class OptionWheelListView(generic.ListView):
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

class OptionWheelDetailView(generic.DetailView):
    model = OptionWheel
    context_object_name = 'wheel'
