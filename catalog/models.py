from django.db import models
from django.utils.translation import gettext_lazy as _
from django.conf import settings
from django.urls import reverse

class StockTicker(models.Model):
    """Represents a publicly traded stock symbol"""
    name = models.CharField(max_length=200, help_text='Enter a ticker, like TSLA.')

    class StockRecommendation(models.TextChoices):
        NONE = 'NO', _('None')
        STABLE = 'ST', _('Stable Choice')
        HIGHVOLATILITY = 'HV', _('High Volatility')

    recommendation = models.CharField(
        max_length=2,
        choices=StockRecommendation.choices,
        default=StockRecommendation.NONE,
    )

    def __str__(self):
        return self.name

    def get_absolute_url(self):
        return reverse('ticker-detail', args=[str(self.id)])

class OptionPurchase(models.Model):
    """Represents an option sold on a specific day"""
    stock_ticker = models.ForeignKey(
        'StockTicker',
        on_delete=models.CASCADE,
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
    )
    option_wheel = models.ForeignKey(
        'OptionWheel',
        on_delete=models.CASCADE,
    )
    purchase_date = models.DateTimeField()
    expiration_date = models.DateField()
    premium = models.DecimalField(max_digits=12, decimal_places=2)
    strike = models.DecimalField(max_digits=12, decimal_places=2)
    price_at_date = models.DecimalField(max_digits=12, decimal_places=2)

    class CallOrPut(models.TextChoices):
        CALL = 'C', _('Call')
        PUT = 'P', _('Put')

    call_or_put = models.CharField(
        max_length=1,
        choices=CallOrPut.choices,
        default=CallOrPut.PUT,
    )

    def __str__(self):
        # TODO
        return f"{str(self.stock_ticker)}: {self.call_or_put} {self.expiration_date}"

    def get_absolute_url(self):
        return reverse('purchase-detail-view', args=[str(self.option_wheel.pk), str(self.id)])

class OptionWheel(models.Model):
    """Referenced by multiple OptionPurchase objects to track profit from using the wheel strategy"""
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
    )
    is_active = models.BooleanField()
    total_profit = models.DecimalField(max_digits=12, decimal_places=2, default=None, null=True)
    total_days_active = models.IntegerField(default=None, null=True)
    collatoral = models.DecimalField(max_digits=12, decimal_places=2, default=None, null=True)

    def get_first_option_purchase(self):
        return OptionPurchase.objects.filter(option_wheel=self.id).first()

    def __str__(self):
        first_option_purchase = self.get_first_option_purchase()
        if first_option_purchase is None:
            return "No options associated with this wheel"
        return f"{first_option_purchase.stock_ticker} {first_option_purchase.purchase_date.strftime('%Y-%m-%d')} ({self.id})"

    def get_absolute_url(self):
        return reverse('wheel-detail', args=[str(self.id)])
