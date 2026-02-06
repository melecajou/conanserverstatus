from pydantic import BaseModel, Field, ValidationError, field_validator
from typing import List, Dict, Optional, Union
import logging
import sys

# --- CONFIGURATION MODELS ---


class ClusterStatusConfig(BaseModel):
    ENABLED: bool = False
    CHANNEL_ID: Optional[int] = None

    @field_validator("CHANNEL_ID")
    @classmethod
    def check_channel_id(cls, v, info):
        if info.data.get("ENABLED") and not v:
            raise ValueError("CHANNEL_ID is required when ENABLED is True")
        return v


class GuildSyncConfig(BaseModel):
    ENABLED: bool = False
    SERVER_ID: Optional[int] = None
    ROLE_PREFIX: str = "🛡️ "
    CLEANUP_EMPTY_ROLES: bool = True

    @field_validator("SERVER_ID")
    @classmethod
    def check_server_id(cls, v, info):
        if info.data.get("ENABLED") and not v:
            raise ValueError("SERVER_ID is required when ENABLED is True")
        return v


class TradeItem(BaseModel):
    item_id: int
    quantity: int
    price_id: int
    price_amount: int
    price_label: str
    label: str


class KillfeedConfig(BaseModel):
    ENABLED: bool = False
    CHANNEL_ID: Optional[int] = None
    RANKING_CHANNEL_ID: Optional[int] = None
    LAST_EVENT_FILE: Optional[str] = None
    POLL_INTERVAL: int = 20
    RANKING_UPDATE_INTERVAL: int = 300
    PVP_ONLY: bool = False


class RewardConfig(BaseModel):
    ENABLED: bool = False
    INTERVALS_MINUTES: Optional[Dict[int, int]] = None
    REWARD_ITEM_ID: Optional[int] = None
    REWARD_QUANTITY: Optional[int] = 1


class AnnouncementSchedule(BaseModel):
    DAY: str
    HOUR: int = Field(ge=0, le=23)
    MESSAGE: str


class AnnouncementsConfig(BaseModel):
    ENABLED: bool = False
    CHANNEL_ID: Optional[int] = None
    TIMEZONE: str = "UTC"
    SCHEDULE: List[AnnouncementSchedule] = []


class BuildingWatcherConfig(BaseModel):
    ENABLED: bool = False
    CHANNEL_ID: Optional[int] = None
    SQL_PATH: Optional[str] = None
    DB_BACKUP_PATH: Optional[str] = None
    BUILD_LIMIT: int = 2000


class WarpConfig(BaseModel):
    ENABLED: bool = False
    COOLDOWN_MINUTES: int = 5
    HOME_ENABLED: bool = True
    HOME_COOLDOWN_MINUTES: int = 15
    SETHOME_COOLDOWN_MINUTES: int = 5
    LOCATIONS: Dict[str, str] = {}


class InactivityReportConfig(BaseModel):
    ENABLED: bool = False
    DAYS: int = 15
    CHANNEL_ID: Optional[int] = None
    SQL_PATH: Optional[str] = None


class ServerConfig(BaseModel):
    NAME: str
    ALIAS: Optional[str] = None
    SERVER_IP: str
    RCON_PORT: int
    RCON_PASS: Optional[str] = None
    STATUS_CHANNEL_ID: int
    DB_PATH: Optional[str] = ""
    LOG_PATH: Optional[str] = ""
    PLAYER_DB_PATH: Optional[str] = None

    KILLFEED_CONFIG: Optional[KillfeedConfig] = None
    REWARD_CONFIG: Optional[RewardConfig] = None
    ANNOUNCEMENTS: Optional[AnnouncementsConfig] = None
    BUILDING_WATCHER: Optional[BuildingWatcherConfig] = None
    WARP_CONFIG: Optional[WarpConfig] = None
    INACTIVITY_REPORT: Optional[InactivityReportConfig] = None


class BotConfiguration(BaseModel):
    LANGUAGE: str = "en"
    STATUS_BOT_TOKEN: str
    REGISTERED_ROLE_ID: Optional[int] = None
    KILLFEED_RANKING_DB: Optional[str] = None
    KILLFEED_SPAWNS_DB: Optional[str] = None
    KILLFEED_STATE_FILE: Optional[str] = None
    KILLFEED_UNIFIED_RANKINGS: List[Dict] = []
    CLUSTER_STATUS: Optional[ClusterStatusConfig] = None
    GUILD_SYNC: Optional[GuildSyncConfig] = None
    TRADE_ITEMS: Dict[str, TradeItem] = {}
    SERVERS: List[ServerConfig]


# --- VALIDATION LOGIC ---


def validate_config(config_module) -> bool:
    """
    Validates the configuration module against the defined Pydantic models.
    Returns True if valid, False otherwise.
    """
    try:
        # Extract dictionary from module, filtering out built-ins
        config_dict = {
            k: getattr(config_module, k)
            for k in dir(config_module)
            if not k.startswith("__")
        }

        # Validate using Pydantic
        BotConfiguration(**config_dict)
        logging.info("✅ Configuration validated successfully.")
        return True

    except ValidationError as e:
        logging.critical("❌ Configuration Validation Failed:")
        for error in e.errors():
            loc = " -> ".join(str(l) for l in error["loc"])
            msg = error["msg"]
            logging.critical(f"   - Field '{loc}': {msg}")
        return False
    except Exception as e:
        logging.critical(f"❌ Unexpected error during config validation: {e}")
        return False
