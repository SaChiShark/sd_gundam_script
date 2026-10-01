"""Unit tests for PersonalBaseRequestTask and Single Task Lifecycle State Machine."""
import numpy as np
import pytest

from core.device import Device, DeviceConfig
from core.state_machine import StateMachine
from tasks.personal_base import (
    PersonalBaseRequestTask,
    CharacterRequestType,
    CharacterRequestDetail,
)


class DummyDevice(Device):
    """Mock device for unit testing."""
    def __init__(self):
        super().__init__(DeviceConfig())
        self._connected = True

    def screencap(self) -> np.ndarray:
        return np.zeros((1080, 1920, 3), dtype=np.uint8)


def test_character_request_type_enum():
    """Verify all recognized character request types exist."""
    assert CharacterRequestType.UNKNOWN
    assert CharacterRequestType.CAPTURE_UNIT
    assert CharacterRequestType.DEVELOP_UNIT
    assert CharacterRequestType.ENHANCE_UNIT
    assert CharacterRequestType.CLEAR_STAGE
    assert CharacterRequestType.EVENT_STAGE


def test_character_request_detail_dataclass():
    """Verify CharacterRequestDetail structure."""
    detail = CharacterRequestDetail(
        slot_idx=2,
        character_name="露娜瑪莉亞・霍克",
        title="奪取單位3",
        requirement_text="奪取3架「機動戰士鋼彈SEED DESTINY」系列的單位",
        request_type=CharacterRequestType.CAPTURE_UNIT,
        button_type="accept",
    )
    assert detail.slot_idx == 2
    assert detail.request_type == CharacterRequestType.CAPTURE_UNIT
    assert detail.button_type == "accept"


def test_parse_blank_frame_returns_unknown():
    """Verify blank frame classification defaults to UNKNOWN."""
    dev = DummyDevice()
    fsm = StateMachine(dev)
    task = PersonalBaseRequestTask(dev, fsm=fsm)

    blank_frame = np.zeros((1080, 1920, 3), dtype=np.uint8)
    detail = task.parse_current_request(blank_frame, slot_idx=1)
    assert detail.request_type == CharacterRequestType.UNKNOWN
