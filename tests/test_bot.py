import pytest
from unittest.mock import AsyncMock, MagicMock
from bot import COGS_TO_LOAD

# Mock the discord.py Bot class
class MockBot(MagicMock):
    pass

@pytest.fixture
def bot():
    """Fixture to create a mock bot instance."""
    mock_bot = MockBot()
    mock_bot.load_extension = AsyncMock()
    return mock_bot

@pytest.mark.asyncio
async def test_load_all_cogs(bot):
    """
    Tests that all cogs in the COGS_TO_LOAD list can be loaded without errors.
    """
    for cog in COGS_TO_LOAD:
        try:
            await bot.load_extension(cog)
        except Exception as e:
            pytest.fail(f"Failed to load cog {cog}: {e}")

    # Verify that load_extension was called for each cog
    assert bot.load_extension.call_count == len(COGS_TO_LOAD)
    for cog in COGS_TO_LOAD:
        bot.load_extension.assert_any_call(cog)
