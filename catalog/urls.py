from django.urls import path
from . import views

urlpatterns = [
    path('', views.index, name='index'),
    path('tickers/', views.StockTickerListView.as_view(), name='tickers'),
    path('tickers/<int:pk>', views.StockTickerDetailView.as_view(), name='stockticker-detail'),
]