# Database
# https://docs.djangoproject.com/en/3.1/ref/settings/#databases
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': BASE_DIR / 'db.sqlite3',
    }
}

# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = 'zyfwk)7^_=22%ll^ojv6h803%k!v@6=m0rone7=@h@5=&seiba'

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = True