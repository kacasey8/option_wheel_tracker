from django.urls import path
from . import views

urlpatterns = [
    path('', views.index, name='index'),
    path('signup/', views.signup, name='signup'),
    path('signup_complete/', views.signup_complete, name='signup-complete'),
    path('global_put_comparison/', views.global_put_comparison, name='global-put-comparison'),
    path('tickers/', views.StockTickerListView.as_view(), name='tickers'),
    path('tickers/<int:pk>', views.StockTickerDetailView.as_view(), name='ticker-detail'),
    path('tickers/create/', views.StockTickerCreate.as_view(), name='ticker-create'),
    path('tickers/<int:pk>/update/', views.StockTickerUpdate.as_view(), name='ticker-update'),
    path('tickers/<int:pk>/delete/', views.StockTickerDelete.as_view(), name='ticker-delete'),
    path('my_active_wheels/', views.my_active_wheels, name='my-active-wheels'),
    path('my_completed_wheels/', views.my_completed_wheels, name='my-completed-wheels'),
    path('all_active_wheels/', views.all_active_wheels, name='all-active-wheels'),
    path('all_completed_wheels/', views.all_completed_wheels, name='all-completed-wheels'),
    path('wheels/<int:pk>', views.OptionWheelDetailView.as_view(), name='wheel-detail'),
    path('wheels/<int:wheel_id>/purchase/<int:pk>', views.OptionPurchaseDetailView.as_view(), name='purchase-detail-view'),
    path('wheels/<int:wheel_id>/purchase/create/', views.OptionPurchaseCreate.as_view(), name='purchase-create'),
    path('wheels/<int:wheel_id>/purchase/<int:pk>/update/', views.OptionPurchaseUpdate.as_view(), name='purchase-update'),
    path('wheels/<int:wheel_id>/purchase/<int:pk>/delete/', views.OptionPurchaseDelete.as_view(), name='purchase-delete'),
    path('wheels/<int:pk>/complete/', views.complete_wheel, name='wheel-complete'),
    path('wheels/<int:pk>/reactivate/', views.reactivate_wheel, name='wheel-reactivate'),
    path('wheels/create/', views.OptionWheelCreate.as_view(), name='wheel-create'),
    path('wheels/<int:pk>/update/', views.OptionWheelUpdate.as_view(), name='wheel-update'),
    path('wheels/<int:pk>/delete/', views.OptionWheelDelete.as_view(), name='wheel-delete'),
    path('my_total_profit/', views.my_total_profit, name='my-total-profit')
]