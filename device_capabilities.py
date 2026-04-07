"""
Device capability definitions for Philips Hue switches.

This module provides device type detection, capability validation, and button action
validation for different Hue switch models (RWL021, RWL022, RDM series).
"""

from dataclasses import dataclass
from enum import Enum
from typing import Dict, List, Any, Optional


class DeviceType(str, Enum):
    """Supported device types for Hue switches."""
    DIMMER_V1 = "dimmer_v1"
    DIMMER_V2 = "dimmer_v2"
    WALL_SWITCH = "wall_switch"
    UNKNOWN = "unknown"


@dataclass
class DeviceCapability:
    """
    Device capability definition describing button count, supported actions, and press types.

    Attributes:
        device_type: The device type enum
        model_ids: List of Hue model IDs for this device type
        button_count: Number of physical buttons
        supported_actions: Dict mapping button number to list of supported actions
        supported_press_types: Dict mapping button number to list of supported press types
        description: Human-readable device description
    """
    device_type: DeviceType
    model_ids: List[str]
    button_count: int
    supported_actions: Dict[int, List[str]]
    supported_press_types: Dict[int, List[str]]
    description: str


# Device capability registry - single source of truth for device capabilities
DEVICE_REGISTRY: Dict[DeviceType, DeviceCapability] = {
    DeviceType.DIMMER_V1: DeviceCapability(
        device_type=DeviceType.DIMMER_V1,
        model_ids=["RWL021"],
        button_count=4,
        supported_actions={
            1: ["timezone", "scene_cycle", "room_toggle"],
            2: ["dim_up"],
            3: ["dim_down"],
            4: ["room_toggle", "scene_cycle"]
        },
        supported_press_types={
            1: ["short_release", "long_press"],
            2: ["repeat"],
            3: ["repeat"],
            4: ["short_release", "long_press"]
        },
        description="Hue Dimmer Switch v1 (RWL021)"
    ),

    DeviceType.DIMMER_V2: DeviceCapability(
        device_type=DeviceType.DIMMER_V2,
        model_ids=["RWL022"],
        button_count=4,
        supported_actions={
            1: ["timezone", "scene_cycle", "room_toggle"],
            2: ["dim_up"],
            3: ["dim_down"],
            4: ["timezone", "scene_cycle", "room_toggle"]
        },
        supported_press_types={
            1: ["short_release", "long_press"],
            2: ["repeat"],
            3: ["repeat"],
            4: ["short_release", "long_press"]
        },
        description="Hue Dimmer Switch v2 (RWL022)"
    ),

    DeviceType.WALL_SWITCH: DeviceCapability(
        device_type=DeviceType.WALL_SWITCH,
        model_ids=["RDM001", "RDM002", "RDM004"],
        button_count=2,
        supported_actions={
            1: ["timezone", "scene_cycle", "room_toggle"],
            2: ["timezone", "scene_cycle", "room_toggle"]
        },
        supported_press_types={
            1: ["short_release", "long_press"],
            2: ["short_release", "long_press"]
        },
        description="Hue Wall Switch Module (RDM series)"
    )
}

# Backward compatibility aliases for v1/v2 naming
MODEL_TYPE_ALIASES = {
    "v1": DeviceType.DIMMER_V1,
    "v2": DeviceType.DIMMER_V2,
    "dimmer_v1": DeviceType.DIMMER_V1,
    "dimmer_v2": DeviceType.DIMMER_V2,
    "wall_switch": DeviceType.WALL_SWITCH
}


def normalize_model_type(model_type: str) -> DeviceType:
    """
    Convert user-provided model_type string to DeviceType enum.

    Handles backward compatibility:
    - "v1" -> DeviceType.DIMMER_V1
    - "v2" -> DeviceType.DIMMER_V2
    - "dimmer_v1" -> DeviceType.DIMMER_V1
    - "dimmer_v2" -> DeviceType.DIMMER_V2
    - "wall_switch" -> DeviceType.WALL_SWITCH

    Args:
        model_type: User-provided model type string

    Returns:
        DeviceType enum value

    Raises:
        ValueError: If model_type is not recognized
    """
    model_type_lower = model_type.lower()

    if model_type_lower not in MODEL_TYPE_ALIASES:
        valid_types = ", ".join(sorted(MODEL_TYPE_ALIASES.keys()))
        raise ValueError(
            f"Unknown model_type '{model_type}'. Valid types: {valid_types}"
        )

    return MODEL_TYPE_ALIASES[model_type_lower]


def get_device_capability(model_type: str) -> DeviceCapability:
    """
    Get device capability definition for a model_type string.

    Args:
        model_type: User-provided model type string (e.g., "v1", "dimmer_v2", "wall_switch")

    Returns:
        DeviceCapability object with button count, supported actions, etc.

    Raises:
        ValueError: If model_type is not recognized
    """
    device_type = normalize_model_type(model_type)
    return DEVICE_REGISTRY[device_type]


def validate_button_action(
    device_type: DeviceType,
    button_number: int,
    action: str
) -> bool:
    """
    Check if an action is supported for a specific device button.

    Args:
        device_type: DeviceType enum value
        button_number: Button number (1-based)
        action: Action type (e.g., "timezone", "scene_cycle", "dim_up")

    Returns:
        True if action is supported, False otherwise
    """
    if device_type not in DEVICE_REGISTRY:
        return False

    capability = DEVICE_REGISTRY[device_type]
    supported_actions = capability.supported_actions.get(button_number, [])

    return action in supported_actions


def get_model_id_from_bridge_device(device: Dict[str, Any]) -> str:
    """
    Extract model_id from a Hue Bridge device resource.

    Args:
        device: Device dictionary from /clip/v2/resource/device endpoint

    Returns:
        Model ID string (e.g., "RWL021", "RDM004"), or "Unknown" if not found
    """
    return device.get('product_data', {}).get('model_id', 'Unknown')


def detect_device_type_from_model_id(model_id: str) -> DeviceType:
    """
    Auto-detect device type from a Hue model ID.

    Searches through DEVICE_REGISTRY to find matching model_id.

    Args:
        model_id: Hue model ID (e.g., "RWL021", "RWL022", "RDM004")

    Returns:
        DeviceType enum value (DeviceType.UNKNOWN if not found)
    """
    for device_type, capability in DEVICE_REGISTRY.items():
        if model_id in capability.model_ids:
            return device_type

    return DeviceType.UNKNOWN


def get_supported_actions_for_button(
    device_type: DeviceType,
    button_number: int
) -> List[str]:
    """
    Get list of supported actions for a specific device button.

    Args:
        device_type: DeviceType enum value
        button_number: Button number (1-based)

    Returns:
        List of supported action strings
    """
    if device_type not in DEVICE_REGISTRY:
        return []

    capability = DEVICE_REGISTRY[device_type]
    return capability.supported_actions.get(button_number, [])
