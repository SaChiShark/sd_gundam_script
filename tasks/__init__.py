"""Game daily and event tasks modules."""
from tasks.base import BaseTask
from tasks.daily_login import DailyLoginTask
from tasks.personal_base import PersonalBaseRequestTask
from tasks.daily_cultivation import DailyCultivationTask
from tasks.warship_cruise import WarshipCruiseTask

__all__ = [
    "BaseTask",
    "DailyLoginTask",
    "PersonalBaseRequestTask",
    "DailyCultivationTask",
    "WarshipCruiseTask",
]
