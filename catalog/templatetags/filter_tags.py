from django import template

register = template.Library()

@register.filter
def percentage(value):
    try:
        return '{:.2%}'.format(value)
    except (ValueError, TypeError):
        return value

@register.filter
def divide(value, arg):
    try:
        return float(value) / float(arg)
    except (ValueError, ZeroDivisionError):
        return None

@register.filter
def multiply(value, arg):
    try:
        return float(value) * float(arg)
    except (ValueError, TypeError):
        return None

@register.filter
def call_or_put(value):
    if value == 'P':
        return 'Put'
    elif value == 'C':
        return 'Call'
    return value