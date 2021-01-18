from django import forms
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.utils.translation import ugettext_lazy as _

from catalog.models import Account, OptionPurchase, StockTicker, OptionWheel

import datetime

class SignupForm(UserCreationForm):
    email = forms.EmailField(required=True)

    class Meta:
        model = User
        fields = ('username', 'email')

class StockTickerForm(forms.ModelForm):
    class Meta:
        model = StockTicker
        fields = '__all__'

class AccountForm(forms.ModelForm):
    class Meta:
        model = Account
        fields = ('user', 'name')
        widgets = {
            'user': forms.widgets.HiddenInput(),
        }

class OptionWheelForm(forms.ModelForm):
    class Meta:
        model = OptionWheel
        fields = ('user', 'stock_ticker', 'account', 'quantity', 'is_active')
        widgets = {
            'user': forms.widgets.HiddenInput(),
            'is_active': forms.widgets.HiddenInput()
        }

    def __init__(self, *args, **kwargs): 
        user = kwargs.pop('user', None) # pop the 'user' from kwargs dictionary   
        super(OptionWheelForm, self).__init__(*args, **kwargs)
        user_accounts = Account.objects.filter(user=user)
        account_field = forms.ModelChoiceField(queryset=user_accounts, required=True)
        if not user_accounts:
            account_field.help_text = "Add a new account first."
        self.fields['account'] = account_field


class OptionPurchaseForm(forms.ModelForm):
    class Meta:
        model = OptionPurchase
        fields = '__all__'
        widgets = {
            'purchase_date': forms.widgets.DateInput(attrs={'type': 'date'}),
            'expiration_date': forms.widgets.DateInput(attrs={'type': 'date'}),
            'strike': forms.widgets.NumberInput(attrs={'step': 0.5, 'placeholder': 'Enter Strike price'}),
            'premium': forms.widgets.NumberInput(attrs={'placeholder': 'Enter Premium'}),
            'price_at_date': forms.widgets.NumberInput(attrs={'placeholder': 'Enter stock price'}),
            'user': forms.widgets.HiddenInput(),
            'option_wheel': forms.widgets.HiddenInput()
        }

    def clean(self):
        cleaned_data = super(OptionPurchaseForm, self).clean()
        purchase_date = cleaned_data['purchase_date'].date()
        expiration_date = cleaned_data['expiration_date']

        # The purchase date can't be in the future
        if purchase_date > datetime.date.today():
            raise ValidationError(_('Invalid date - purchase in future'))

        # The purchase date must be before the expiration date
        if purchase_date > expiration_date:
            raise ValidationError(_('Invalid dates - purchase date cannot be after expiration'))

        return cleaned_data
