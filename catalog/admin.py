from django.contrib import admin

from .models import StockTicker, OptionPurchase, OptionWheel

admin.site.register(OptionPurchase)
admin.site.register(OptionWheel)

class StockTickerAdmin(admin.ModelAdmin):
    list_display = ('name', 'recommendation')

admin.site.register(StockTicker, StockTickerAdmin)
