"""Configuration models and loader using Pydantic."""
from pathlib import Path
from typing import Optional, List, Dict, Any
import yaml
from pydantic import BaseModel, Field


class DeviceConfig(BaseModel):
    """Device connection parameters."""
    host: str = Field(default="127.0.0.1", description="ADB host address")
    port: int = Field(default=5555, description="ADB port (e.g. 5555 for BlueStacks/LD, 16384 for MuMu, 62001 for Nox)")
    serial: Optional[str] = Field(default=None, description="Specific device serial (e.g. emulator-5554)")
    adb_path: Optional[str] = Field(
        default=r"C:\Program Files\BlueStacks_nxt\HD-Adb.exe",
        description="Path to ADB executable"
    )
    screencap_timeout: float = Field(default=5.0, description="Screenshot timeout in seconds")


class VisionConfig(BaseModel):
    """Computer vision parameters."""
    default_threshold: float = Field(default=0.82, description="Default confidence threshold for template matching")
    debug_save: bool = Field(default=True, description="Save debug matched crops in captures/temp")


class GameConfig(BaseModel):
    """Target game parameters."""
    package_name: str = Field(default="com.bandainamcoent.gget_WW", description="Target game package name")
    activity_name: Optional[str] = Field(default=None, description="Main launch activity if needed")


class TaskSettings(BaseModel):
    """Task pipeline controls."""
    enabled_tasks: List[str] = Field(
        default_factory=lambda: ["daily_login", "mailbox", "free_gacha"],
        description="List of tasks to execute in order"
    )
    max_retries_per_task: int = Field(default=3, description="Retry count on unexpected failure")


class AppConfig(BaseModel):
    """Root configuration model."""
    device: DeviceConfig = Field(default_factory=DeviceConfig)
    vision: VisionConfig = Field(default_factory=VisionConfig)
    game: GameConfig = Field(default_factory=GameConfig)
    tasks: TaskSettings = Field(default_factory=TaskSettings)

    @classmethod
    def load_from_file(cls, path: str | Path = "config.yaml") -> "AppConfig":
        """Load configuration from a YAML file, falling back to defaults if not found."""
        p = Path(path)
        if not p.is_file():
            # Return default config and write it out
            cfg = cls()
            cfg.save_to_file(p)
            return cfg

        with open(p, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        return cls(**data)

    def save_to_file(self, path: str | Path = "config.yaml") -> None:
        """Save configuration model to a YAML file."""
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        with open(p, "w", encoding="utf-8") as f:
            yaml.dump(self.model_dump(), f, allow_unicode=True, sort_keys=False)
