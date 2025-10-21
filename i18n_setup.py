import gettext
import config

lang = getattr(config, 'LANGUAGE', 'en')
try:
    translation = gettext.translation('messages', localedir='locale', languages=[lang])
    translation.install()
    _ = translation.gettext
except FileNotFoundError:
    _ = gettext.gettext
