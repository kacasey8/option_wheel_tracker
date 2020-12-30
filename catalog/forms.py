from django import forms
from catalog.models import OptionPurchase, StockTicker

from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.models import User

class SignupForm(UserCreationForm):
    email = forms.EmailField(required=True)

    class Meta:
        model = User
        fields = ('username', 'email')

class StockTickerForm(forms.ModelForm):
    class Meta:
        model = StockTicker
        fields = '__all__'

class OptionPurchaseForm(forms.ModelForm):
    class Meta:
        model = OptionPurchase
        fields = '__all__'
        widgets = {
            'purchase_date': forms.widgets.DateInput(attrs={'type': 'date'}),
            'expiration_date': forms.widgets.DateInput(attrs={'type': 'date'}),
            'user': forms.widgets.HiddenInput(),
            'option_wheel': forms.widgets.HiddenInput()
        }