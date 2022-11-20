from datetime import date, datetime
from decimal import Decimal
from typing import Optional

from django.conf import settings
from django.db import models
from django.urls import reverse
from django.utils.translation import gettext_lazy as _

from .business_day_count import busday_count_inclusive
from .constants import DATE_DISPLAY_FORMAT, MARKET_CLOSE_HOUR
from .option_price_computation import (
    compute_annualized_rate_of_return,
    get_current_price,
    get_previous_close_price,
)


class StockTicker(models.Model):
    """Represents a publicly traded stock symbol"""

    id: int
    name = models.CharField(
        max_length=200,
        help_text="Enter a ticker, like TSLA.",
        unique=True,
        db_index=True,
    )

    class StockRecommendation(models.TextChoices):
        NONE = "NO", _("None")
        STABLE = "ST", _("Stable Choice")
        HIGHVOLATILITY = "HV", _("High Volatility")

    recommendation = models.CharField(
        max_length=2,
        choices=StockRecommendation.choices,
        default=StockRecommendation.NONE,
    )

    def __str__(self):
        return self.name

    def get_absolute_url(self):
        return reverse("ticker-detail", args=[str(self.id)])

    @property
    def current_price(self):
        return get_current_price(self.name) or 0

    @property
    def change_today(self):
        if self.current_price:
            return self.current_price - get_previous_close_price(self.name)
        return 0

    @property
    def percent_change_today(self):
        if self.current_price:
            current_price = self.current_price
            return (
                (current_price - get_previous_close_price(self.name))
                * 1.0
                / current_price
            )
        return 0

    class Meta:
        ordering = ["name"]


class Account(models.Model):
    """Represents an account that can trade stocks options"""

    id: int
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        db_index=True,
    )
    name = models.CharField(
        max_length=50, help_text="Enter an account name, like Robinhood.", db_index=True
    )

    def __str__(self):
        return self.name

    def get_absolute_url(self):
        return reverse("account-detail", args=[str(self.id)])

    class Meta:
        ordering = ["name"]


class OptionPurchase(models.Model):
    """Represents an option sold on a specific day"""

    id: int
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        db_index=True,
    )
    option_wheel = models.ForeignKey(
        "OptionWheel",
        on_delete=models.CASCADE,
        db_index=True,
        related_name="option_purchases",
    )
    purchase_date = models.DateTimeField()
    expiration_date = models.DateField()
    strike = models.DecimalField(max_digits=12, decimal_places=2)
    price_at_date = models.DecimalField(max_digits=12, decimal_places=2)
    premium = models.DecimalField(max_digits=12, decimal_places=2)

    class CallOrPut(models.TextChoices):
        CALL = "C", _("Call")
        PUT = "P", _("Put")

    call_or_put = models.CharField(
        max_length=1,
        choices=CallOrPut.choices,
        default=CallOrPut.PUT,
    )

    def __str__(self):
        return f"""
            ${self.strike} {self.call_or_put} {str(self.option_wheel.stock_ticker)}
            (exp. {self.expiration_date.strftime(DATE_DISPLAY_FORMAT)})
            """

    def get_absolute_url(self):
        return reverse(
            "purchase-detail-view", args=[str(self.option_wheel.pk), str(self.id)]
        )

    class Meta:
        ordering = ["-expiration_date", "-purchase_date"]


class OptionWheel(models.Model):
    """Referenced by multiple OptionPurchase objects to track profit from using
    the wheel strategy"""

    id: int
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        db_index=True,
    )
    stock_ticker = models.ForeignKey(
        "StockTicker",
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
    total_profit = models.DecimalField(
        max_digits=12, decimal_places=2, default=None, null=True
    )
    total_days_active = models.IntegerField(default=None, null=True)
    collatoral = models.DecimalField(
        max_digits=12, decimal_places=2, default=None, null=True
    )

    _option_purchase_list: list[OptionPurchase] = []

    @property
    def collateral(self):
        # ugh, misspelled in the database
        return self.collatoral

    @property
    def option_purchase_list(self) -> list[OptionPurchase]:
        if not self._option_purchase_list:
            """Fetch all related option purchase objects, if we haven't done the query
            yet. Note that they will be in descending order by expiration date, with
            the most recent purchases first."""
            self._option_purchase_list = self.option_purchases.all()  # type: ignore
        return self._option_purchase_list

    @property
    def opening_purchase(self) -> Optional[OptionPurchase]:
        """The opening purchase is actually the last one in the purchase list."""
        if self.option_purchase_list:
            return self.option_purchase_list[len(self.option_purchase_list) - 1]
        return None

    @property
    def last_purchase(self) -> Optional[OptionPurchase]:
        """The last recent purchase is the first one in the purchase list."""
        if self.option_purchase_list:
            return self.option_purchase_list[0]
        return None

    @property
    def opening_date(self) -> date:
        if self.opening_purchase:
            return self.opening_purchase.purchase_date.date()
        return datetime.min.date()

    @property
    def expiration_date(self) -> date:
        if self.last_purchase:
            return self.last_purchase.expiration_date
        return datetime.max.date()

    @property
    def expired(self) -> bool:
        if not self.is_active:
            return False
        now = datetime.now()
        today = now.date()
        if now.hour >= MARKET_CLOSE_HOUR:
            return self.expiration_date <= today
        return self.expiration_date < today

    @property
    def cost_basis(self) -> Optional[Decimal]:
        revenue = self.revenue
        if not revenue or not self.opening_purchase:
            return None
        return self.opening_purchase.strike - revenue

    @property
    def revenue(self) -> Optional[Decimal]:
        purchases = self.option_purchase_list
        if not purchases:
            return None
        return Decimal(sum(purchase.premium for purchase in purchases))

    def add_purchase_data(self, fetch_price=True) -> None:
        purchases = self.option_purchase_list
        if purchases:
            opening_purchase = self.opening_purchase
            last_purchase = self.last_purchase
            if not self.cost_basis or not opening_purchase or not last_purchase:
                return
            profit_if_exits_here = last_purchase.strike - self.cost_basis

            days_active_so_far = busday_count_inclusive(
                opening_purchase.purchase_date.date(),
                last_purchase.expiration_date,
            )
            decimal_rate_of_return = profit_if_exits_here / opening_purchase.strike
            annualized_rate_of_return_if_exits_here = compute_annualized_rate_of_return(
                decimal_rate_of_return, Decimal(1), days_active_so_far
            )

            self.profit_if_exits_here = profit_if_exits_here
            self.days_active_so_far = days_active_so_far
            self.decimal_rate_of_return = decimal_rate_of_return
            self.annualized_rate_of_return_if_exits_here = (
                annualized_rate_of_return_if_exits_here
            )

            self.open_strike = opening_purchase.strike
            if fetch_price:
                current_price = get_current_price(self.stock_ticker.name)
                if current_price is not None:
                    self.current_price = current_price
                    if current_price >= last_purchase.strike:
                        self.on_track = "Exit"
                    elif current_price >= self.cost_basis:
                        self.on_track = "Hold"
                    else:
                        self.on_track = "Under"
            self.purchases = purchases

    def __str__(self):
        quantity_str = f"({self.quantity}) " if self.quantity > 1 else ""
        account_str = f" [{self.account}]" if self.account else ""
        if not self.last_purchase:
            return f"{quantity_str}{self.stock_ticker}{account_str}"
        strike = self.last_purchase.strike
        call_or_put = self.last_purchase.call_or_put
        opening_date = self.opening_date.strftime(DATE_DISPLAY_FORMAT)
        exp_date = self.expiration_date.strftime(DATE_DISPLAY_FORMAT)
        return f"""
            {quantity_str}${strike} {call_or_put} {self.stock_ticker}
            (opened {opening_date}, exp. {exp_date}){account_str}
        """

    def get_absolute_url(self):
        return reverse("wheel-detail", args=[str(self.id)])
