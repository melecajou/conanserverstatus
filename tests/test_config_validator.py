import unittest
from utils.config_validator import validate_config

# Dummy valid config object
class ValidConfig:
    LANGUAGE = "en"
    STATUS_BOT_TOKEN = "token"
    SERVERS = [
        {
            "NAME": "Test Server",
            "SERVER_IP": "127.0.0.1",
            "RCON_PORT": 25575,
            "STATUS_CHANNEL_ID": 123456789
        }
    ]

# Dummy invalid config (missing token)
class InvalidConfigMissingToken:
    LANGUAGE = "en"
    SERVERS = []

# Dummy invalid config (wrong type)
class InvalidConfigWrongType:
    LANGUAGE = "en"
    STATUS_BOT_TOKEN = "token"
    SERVERS = "This should be a list"

class TestConfigValidator(unittest.TestCase):
    def test_valid_config(self):
        self.assertTrue(validate_config(ValidConfig))

    def test_missing_token(self):
        self.assertFalse(validate_config(InvalidConfigMissingToken))

    def test_wrong_type(self):
        self.assertFalse(validate_config(InvalidConfigWrongType))
