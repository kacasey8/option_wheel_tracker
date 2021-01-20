from django.db import models
from django.utils.translation import gettext_lazy as _
from django.conf import settings
from django.urls import reverse

from datetime import datetime
from .business_day_count import busday_count_inclusive
from .option_price_computation import (
    compute_annualized_rate_of_return,
    get_current_price,
    get_previous_close_price
)

import numpy

MARKET_CLOSE_HOUR = 13


class StockTicker(models.Model):
    """Represents a publicly traded stock symbol"""
    name = models.CharField(max_length=200, help_text='Enter a ticker, like TSLA.', unique=True, db_index=True)

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

    @property
    def current_price(self):
        return get_current_price(self.name)

    @property
    def change_today(self):
        return self.current_price - get_previous_close_price(self.name)

    @property
    def percent_change_today(self):
        current_price = self.current_price
        return (current_price - get_previous_close_price(self.name)) * 1.0 / current_price

    class Meta:
        ordering = ["name"]


class Account(models.Model):
    """Represents an account that can trade stocks options"""

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        db_index=True,
    )

    name = models.CharField(max_length=50, help_text='Enter an account name, like Robinhood.', db_index=True)

    def __str__(self):
        return self.name

    def get_absolute_url(self):
        return reverse('account-detail', args=[str(self.id)])

    class Meta:
        ordering = ["name"]


class OptionPurchase(models.Model):
    """Represents an option sold on a specific day"""
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        db_index=True,
    )
    option_wheel = models.ForeignKey(
        'OptionWheel',
        on_delete=models.CASCADE,
        db_index=True,
        related_name='option_purchases'
    )
    purchase_date = models.DateTimeField()
    expiration_date = models.DateField()
    strike = models.DecimalField(max_digits=12, decimal_places=2)
    price_at_date = models.DecimalField(max_digits=12, decimal_places=2)
    premium = models.DecimalField(max_digits=12, decimal_places=2)

    class CallOrPut(models.TextChoices):
        CALL = 'C', _('Call')
        PUT = 'P', _('Put')

    call_or_put = models.CharField(
        max_length=1,
        choices=CallOrPut.choices,
        default=CallOrPut.PUT,
    )

    def __str__(self):
        return f"${self.strike} {self.call_or_put} {str(self.option_wheel.stock_ticker)} (exp. {self.expiration_date.strftime('%m/%d')})"

    def get_absolute_url(self):
        return reverse('purchase-detail-view', args=[str(self.option_wheel.pk), str(self.id)])

class OptionWheel(models.Model):
    """Referenced by multiple OptionPurchase objects to track profit from using the wheel strategy"""
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        db_index=True,
    )
    stock_ticker = models.ForeignKey(
        'StockTicker',
        on_delete=models.CASCADE,
    )
    account = models.ForeignKey(
        Account,
        on_delete=models.SET_NULL,
        db_index=True,
        blank=True,
        null=True,
    )
    quantity = models.IntegerField(default=1)
    is_active = models.BooleanField(db_index=True)
    total_profit = models.DecimalField(max_digits=12, decimal_places=2, default=None, null=True)
    total_days_active = models.IntegerField(default=None, null=True)
    collatoral = models.DecimalField(max_digits=12, decimal_places=2, default=None, null=True)

    @property
    def collateral(self):
        # ugh, misspelled in the database
        return self.collatoral

    def get_all_option_purchases(self):
         return OptionPurchase.objects.filter(option_wheel=self.id).order_by('-expiration_date', '-purchase_date')
     
    def get_first_option_purchase(self):
        return OptionPurchase.objects.filter(option_wheel=self.id).order_by('purchase_date', 'expiration_date').first()

    def get_last_option_purchase(self):
        return OptionPurchase.objects.filter(option_wheel=self.id).order_by('purchase_date', 'expiration_date').last()
    
    def get_open_date(self):
        first = self.get_first_option_purchase()
        if first:
            return first.purchase_date.date()
        return datetime.min.date()

    def get_expiration_date(self):
        last_purchase = self.get_last_option_purchase()
        if last_purchase:
            return last_purchase.expiration_date
        return datetime.max.date()

    def is_expired(self):
        if not self.is_active:
            return False
        now = datetime.now()
        today = now.date()
        if now.hour >= MARKET_CLOSE_HOUR:
            return self.get_expiration_date() <= today
        return self.get_expiration_date() < today

    def get_cost_basis(self):
        purchases = self.get_all_option_purchases()
        if not purchases:
            return 'N/A'
        revenue = sum(purchase.premium for purchase in purchases)
        first_purchase = self.get_first_option_purchase()
        return first_purchase.strike - revenue

    def get_revenue(self):
        purchases = self.get_all_option_purchases()
        if not purchases:
            return 'N/A'
        return sum(purchase.premium for purchase in purchases)

    def add_purchase_data(self):
        purchases = self.get_all_option_purchases()
        if purchases:
            cost_basis = self.get_cost_basis()
            first_purchase = self.get_first_option_purchase()
            last_purchase = self.get_last_option_purchase()
            profit_if_exits_here = last_purchase.strike - cost_basis

            days_active_so_far = busday_count_inclusive(
                first_purchase.purchase_date.date(),
                last_purchase.expiration_date,
            )
            decimal_rate_of_return = float(profit_if_exits_here / first_purchase.strike)
            annualized_rate_of_return_if_exits_here = compute_annualized_rate_of_return(decimal_rate_of_return, 1, days_active_so_far)

            self.cost_basis = cost_basis
            self.profit_if_exits_here = profit_if_exits_here
            self.days_active_so_far = days_active_so_far
            self.decimal_rate_of_return = decimal_rate_of_return
            self.annualized_rate_of_return_if_exits_here = annualized_rate_of_return_if_exits_here

            self.open_date = self.get_open_date().strftime('%m/%d')
            self.open_strike = first_purchase.strike

            self.expiration_date = self.get_expiration_date().strftime('%m/%d')
            self.last_purchase = last_purchase

            self.expired = self.is_expired()
            self.current_price = get_current_price(self.stock_ticker.name)
            self.purchases = purchases


    def __str__(self):
        last_purchase = self.get_last_option_purchase()
        quantity_str = f"({self.quantity}X) " if self.quantity > 1 else ""
        account_str = f" [{self.account}]" if self.account else ""
        if not last_purchase:
            return f"{quantity_str}{self.stock_ticker}{account_str}"
        strike = last_purchase.strike
        call_or_put = last_purchase.call_or_put
        open_date = self.get_open_date().strftime('%m/%d')
        exp_date = self.get_expiration_date().strftime('%m/%d')
        return f"{quantity_str}${strike} {call_or_put} {self.stock_ticker} (opened {open_date}, exp. {exp_date}){account_str}"

    def get_absolute_url(self):
        return reverse('wheel-detail', args=[str(self.id)])
