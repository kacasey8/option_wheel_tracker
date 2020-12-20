from django.shortcuts import render
from .models import StockTicker
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
