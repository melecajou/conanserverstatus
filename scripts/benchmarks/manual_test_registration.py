import re
import secrets
import sys

# Mocking cogs.registration REGISTRATION_COMMAND_REGEX as we can't easily import it without its dependencies
# REGISTRATION_COMMAND_REGEX = re.compile(r"!register ([\w-]+)")
# Actually, I should try to import it first.

try:
    from cogs.registration import REGISTRATION_COMMAND_REGEX
except ImportError:
    print("Could not import REGISTRATION_COMMAND_REGEX, using local definition for testing.")
    REGISTRATION_COMMAND_REGEX = re.compile(r"!register ([\w-]+)")

def test_regex_matches_hex_tokens():
    print("Running test_regex_matches_hex_tokens...")
    # Test basic hex (32 chars)
    token = "a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4"
    assert REGISTRATION_COMMAND_REGEX.match(f"!register {token}")
    print("PASSED")

def test_token_generation_length():
    print("Running test_token_generation_length...")
    token = secrets.token_hex(16)
    assert len(token) == 32
    print("PASSED")

def test_regex_capture_group():
    print("Running test_regex_capture_group...")
    token = "a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4"
    match = REGISTRATION_COMMAND_REGEX.match(f"!register {token}")
    assert match
    assert match.group(1) == token
    print("PASSED")

def test_regex_with_generated_tokens():
    print("Running test_regex_with_generated_tokens...")
    for _ in range(100):
        token = secrets.token_hex(16)
        match = REGISTRATION_COMMAND_REGEX.match(f"!register {token}")
        assert match, f"Regex failed to match generated token: {token}"
        assert match.group(1) == token
    print("PASSED")

if __name__ == "__main__":
    try:
        test_regex_matches_hex_tokens()
        test_token_generation_length()
        test_regex_capture_group()
        test_regex_with_generated_tokens()
        print("\nAll manual tests passed successfully!")
    except AssertionError as e:
        print(f"\nTest FAILED: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"\nAn error occurred: {e}")
        sys.exit(1)
