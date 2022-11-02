from django.contrib import admin

from .models import OptionPurchase, OptionWheel, StockTicker

admin.site.register(OptionPurchase)
admin.site.register(OptionWheel)


class StockTickerAdmin(admin.ModelAdmin):
    list_display = ("name", "recommendation")


admin.site.register(StockTicker, StockTickerAdmin)
