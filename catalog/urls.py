from django.urls import path
from . import views

urlpatterns = [
    path('', views.index, name='index'),
    path('tickers/', views.StockTickerListView.as_view(), name='tickers'),
    path('wheels/', views.OptionWheelListView.as_view(), name='wheels'),
    path('tickers/<int:pk>', views.StockTickerDetailView.as_view(), name='stockticker-detail'),
    path('wheels/<int:pk>', views.OptionWheelDetailView.as_view(), name='wheel-detail'),
]