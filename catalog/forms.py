from django import forms
from .models import OptionPurchase

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