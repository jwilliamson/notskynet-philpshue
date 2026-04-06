#!/usr/bin/env python3
"""
Hue Scene Sync Script

Synchronizes Philips Hue room scenes based on a YAML configuration file.
This script DELETES all existing scenes for target rooms and creates new
scenes from the configuration.

DESTRUCTIVE OPERATION:
- Default mode: Dry-run (shows what would change)
- Real changes: Requires --execute flag

Usage:
    # Dry-run (safe)
    python sync_scenes.py

    # Execute changes
    python sync_scenes.py --execute

    # Single room only
    python sync_scenes.py --execute --room "Office Lights"

    # Custom config file
    python sync_scenes.py --config my_scenes.yaml --execute

Configuration:
- YAML file: rooms_scenes.yaml (default)
- Environment: .env (HUE_BRIDGE_IP, HUE_USERNAME)

Safety:
- Validates config before any API calls
- Room-by-room processing (one failure doesn't stop others)
- Clear logging of all operations
- Exit code 1 if any errors occurred
"""

import argparse
import logging
import os
import sys
from typing import Dict, List, Optional, Any

import requests
import urllib3
import yaml
from dotenv import load_dotenv
from pydantic import BaseModel, Field, field_validator, ValidationError


# ============================================================================
# Pydantic Models
# ============================================================================

class ColorXY(BaseModel):
    """XY color gamut coordinates."""
    x: float = Field(..., ge=0.0, le=1.0, description="X coordinate (0.0-1.0)")
    y: float = Field(..., ge=0.0, le=1.0, description="Y coordinate (0.0-1.0)")


class ColorTemperature(BaseModel):
    """Color temperature in mirek (micro reciprocal kelvin)."""
    mirek: int = Field(..., ge=150, le=500, description="Color temperature (150-500 mirek)")


class SceneConfig(BaseModel):
    """Scene definition with name and light settings (applies to all lights in room)."""
    name: str = Field(..., min_length=1, max_length=100, description="Scene name")
    brightness: Optional[float] = Field(None, ge=0.0, le=100.0, description="Brightness 0-100")
    color: Optional[ColorXY] = Field(None, description="XY color coordinates")
    color_temperature: Optional[ColorTemperature] = Field(None, description="Color temperature")

    @field_validator('color_temperature')
    @classmethod
    def validate_at_least_one_setting(cls, v, info):
        """Ensure at least one of brightness, color, or color_temperature is set."""
        data = info.data
        if data.get('brightness') is None and data.get('color') is None and v is None:
            raise ValueError("Must provide at least one of: brightness, color, color_temperature")
        return v


class TimeSlot(BaseModel):
    """Time slot configuration for timezone-based scene selection."""
    start_time: Dict[str, int] = Field(
        ...,
        description="Start time with 'hour' (0-23) and optional 'minute' (0-59, defaults to 0)"
    )
    scene: str = Field(..., min_length=1, description="Scene name to activate")

    @field_validator('start_time')
    @classmethod
    def validate_time_format(cls, v):
        """Validate time format has hour and optional minute."""
        if 'hour' not in v:
            raise ValueError("start_time must contain 'hour' key")
        hour = v['hour']
        if not isinstance(hour, int) or hour < 0 or hour > 23:
            raise ValueError(f"hour must be 0-23, got {hour}")

        minute = v.get('minute', 0)
        if not isinstance(minute, int) or minute < 0 or minute > 59:
            raise ValueError(f"minute must be 0-59, got {minute}")

        # Normalize: ensure minute exists
        v.setdefault('minute', 0)
        return v


class ButtonConfig(BaseModel):
    """Button configuration for a dimmer switch."""
    button_number: int = Field(..., ge=1, le=4, description="Button number (1-4)")
    action: str = Field(..., description="Action type: timezone, scene_cycle, dim_up, dim_down, room_toggle")
    target: Optional[str] = Field(None, description="Target room or zone name (required for timezone, scene_cycle, room_toggle)")
    time_slots: Optional[List[TimeSlot]] = Field(None, min_length=1, description="Time slots (required for timezone action)")
    scenes: Optional[List[str]] = Field(None, min_length=1, description="Scene names (required for scene_cycle action)")

    @field_validator('action')
    @classmethod
    def validate_action_type(cls, v):
        """Validate action type is supported."""
        valid_actions = {'timezone', 'scene_cycle', 'dim_up', 'dim_down', 'room_toggle'}
        if v not in valid_actions:
            raise ValueError(f"action must be one of {valid_actions}, got '{v}'")
        return v

    @field_validator('time_slots')
    @classmethod
    def validate_timezone_requirements(cls, v, info):
        """Validate timezone action has time_slots."""
        data = info.data
        action = data.get('action')

        if action == 'timezone':
            if not v:
                raise ValueError("timezone action requires time_slots")
            # Check chronological order
            times = [(slot.start_time['hour'], slot.start_time['minute']) for slot in v]
            if times != sorted(times):
                raise ValueError("time_slots must be in chronological order")
        elif v is not None:
            raise ValueError(f"time_slots only valid for timezone action, not {action}")

        return v

    @field_validator('scenes')
    @classmethod
    def validate_scene_cycle_requirements(cls, v, info):
        """Validate scene_cycle action has scenes."""
        data = info.data
        action = data.get('action')

        if action == 'scene_cycle':
            if not v:
                raise ValueError("scene_cycle action requires scenes list")
        elif v is not None:
            raise ValueError(f"scenes only valid for scene_cycle action, not {action}")

        return v

    @field_validator('target')
    @classmethod
    def validate_target_requirements(cls, v, info):
        """Validate actions that require targets."""
        data = info.data
        action = data.get('action')

        if action in {'timezone', 'scene_cycle', 'room_toggle'}:
            if not v:
                raise ValueError(f"{action} action requires target (room or zone name)")
        elif v is not None and action in {'dim_up', 'dim_down'}:
            raise ValueError(f"{action} action does not use target parameter")

        return v


class SwitchConfig(BaseModel):
    """Complete switch configuration with per-button settings."""
    device_name: str = Field(..., min_length=1, description="Device name (must match Hue Bridge)")
    model_type: str = Field(..., description="Switch model type: v1 or v2")
    buttons: List[ButtonConfig] = Field(..., min_length=1, max_length=4, description="Button configurations")

    @field_validator('model_type')
    @classmethod
    def validate_model_type(cls, v):
        """Validate model type."""
        if v not in {'v1', 'v2'}:
            raise ValueError(f"model_type must be 'v1' or 'v2', got '{v}'")
        return v

    @field_validator('buttons')
    @classmethod
    def validate_unique_button_numbers(cls, v):
        """Ensure button numbers are unique."""
        button_numbers = [b.button_number for b in v]
        if len(button_numbers) != len(set(button_numbers)):
            raise ValueError("button_number values must be unique")
        return v


class RoomConfig(BaseModel):
    """Room configuration with associated scenes."""
    room_name: str = Field(..., min_length=1, description="Room name (must match Hue Bridge)")
    scenes: List[SceneConfig] = Field(..., min_length=1, description="Scenes for this room")
    switches: Optional[List[SwitchConfig]] = Field(default=None, description="Dimmer switch configurations")

    @field_validator('switches')
    @classmethod
    def validate_scene_references(cls, v, info):
        """Validate that button scene names exist in room's scenes."""
        if not v:
            return v

        data = info.data
        room_scenes = {scene.name for scene in data.get('scenes', [])}

        for switch in v:
            for button in switch.buttons:
                # Check scene_cycle scenes
                if button.action == 'scene_cycle' and button.scenes:
                    for scene_name in button.scenes:
                        if scene_name not in room_scenes:
                            raise ValueError(
                                f"Scene '{scene_name}' in button {button.button_number} "
                                f"not found in room scenes: {sorted(room_scenes)}"
                            )

                # Check timezone scenes
                if button.action == 'timezone' and button.time_slots:
                    for slot in button.time_slots:
                        if slot.scene not in room_scenes:
                            raise ValueError(
                                f"Scene '{slot.scene}' in time slot {slot.start_time} "
                                f"not found in room scenes: {sorted(room_scenes)}"
                            )

        return v


class RoomsScenesConfig(BaseModel):
    """Root configuration for rooms_scenes.yaml."""
    rooms: List[RoomConfig] = Field(..., min_length=1, description="List of room configurations")

    model_config = {"extra": "forbid"}  # Reject unknown fields


# ============================================================================
# Custom Exceptions
# ============================================================================

class HueAPIError(Exception):
    """Custom exception for Hue API errors."""
    pass


class RoomNotFoundError(Exception):
    """Raised when a room name cannot be resolved to an ID."""
    pass


class TargetNotFoundError(Exception):
    """Raised when a room or zone target cannot be resolved."""
    pass


# ============================================================================
# Hue API Client
# ============================================================================

class HueAPIClient:
    """Hue CLIP API v2 client for scene management."""

    def __init__(self, bridge_ip: str, api_key: str, timeout: int = 10):
        """
        Initialize Hue API client.

        Args:
            bridge_ip: Hue Bridge IP address
            api_key: API key (HUE_USERNAME from .env)
            timeout: Request timeout in seconds
        """
        self.base_url = f"https://{bridge_ip}/clip/v2/resource"
        self.headers = {"hue-application-key": api_key}
        self.timeout = timeout

        # Suppress SSL warnings for self-signed cert
        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

    def get_rooms(self) -> List[Dict[str, Any]]:
        """
        Query all rooms from the bridge.

        Returns:
            List of room dictionaries with id and metadata.name

        Raises:
            HueAPIError: If request fails
        """
        data = self._request("GET", "room")
        return data.get("data", [])

    def get_zones(self) -> List[Dict[str, Any]]:
        """
        Query all zones from the bridge.

        Returns:
            List of zone dictionaries with id and metadata.name

        Raises:
            HueAPIError: If request fails
        """
        data = self._request("GET", "zone")
        return data.get("data", [])

    def get_scenes_for_room(self, room_id: str) -> List[Dict[str, Any]]:
        """
        Query scenes for a specific room.

        Args:
            room_id: Room UUID

        Returns:
            List of scene dictionaries (id, metadata.name, group.rid, actions)

        Raises:
            HueAPIError: If request fails
        """
        data = self._request("GET", "scene")
        scenes = data.get("data", [])
        # Filter to scenes belonging to this room
        return [s for s in scenes if s.get("group", {}).get("rid") == room_id]

    def get_lights_for_room(self, room_id: str) -> List[str]:
        """
        Get list of light IDs in a room.

        Args:
            room_id: Room UUID

        Returns:
            List of light UUIDs in the room

        Raises:
            HueAPIError: If request fails
        """
        # Query room details
        room_data = self._request("GET", f"room/{room_id}")
        room = room_data.get("data", [{}])[0]

        # Get device IDs from room children
        device_rids = [
            child["rid"]
            for child in room.get("children", [])
            if child.get("rtype") == "device"
        ]

        # Query each device to get light services
        light_ids = []
        for device_rid in device_rids:
            device_data = self._request("GET", f"device/{device_rid}")
            device = device_data.get("data", [{}])[0]

            light_services = [
                service["rid"]
                for service in device.get("services", [])
                if service.get("rtype") == "light"
            ]
            light_ids.extend(light_services)

        return light_ids

    def delete_scene(self, scene_id: str) -> Dict[str, Any]:
        """
        Delete a scene by ID.

        Args:
            scene_id: Scene UUID

        Returns:
            Deletion confirmation data

        Raises:
            HueAPIError: If request fails
        """
        return self._request("DELETE", f"scene/{scene_id}")

    def create_scene(self, room_id: str, scene_config: SceneConfig) -> Dict[str, Any]:
        """
        Create a new scene for a room.

        Args:
            room_id: Room UUID (links scene to room)
            scene_config: Scene configuration (name, actions)

        Returns:
            Created scene data (includes new scene ID)

        Raises:
            HueAPIError: If request fails
        """
        body = self._build_scene_body(room_id, scene_config)
        return self._request("POST", "scene", json_data=body)

    def update_scene(self, scene_id: str, room_id: str, scene_config: SceneConfig) -> Dict[str, Any]:
        """
        Update an existing scene with new configuration.

        Args:
            scene_id: Scene UUID to update
            room_id: Room UUID (needed to resolve lights)
            scene_config: New scene configuration

        Returns:
            Update confirmation from API

        Raises:
            HueAPIError: If PUT request fails (404 = scene deleted externally)

        Note:
            The group field must be excluded from PUT requests as the API
            does not allow modifying group references in scene updates.
        """
        body = self._build_scene_body(room_id, scene_config)
        # Remove 'group' field - API doesn't allow modifying group reference in updates
        body.pop('group', None)
        return self._request("PUT", f"scene/{scene_id}", json_data=body)

    def _build_scene_body(self, room_id: str, scene_config: SceneConfig) -> Dict[str, Any]:
        """
        Build POST /scene request body from SceneConfig.
        Automatically applies scene settings to all lights in the room.

        Args:
            room_id: Room UUID
            scene_config: Scene configuration (applies to all lights in room)

        Returns:
            Request body dictionary

        Raises:
            HueAPIError: If no lights found in room
        """
        # Query lights in the room
        light_ids = self.get_lights_for_room(room_id)

        if not light_ids:
            raise HueAPIError(f"No lights found in room {room_id}")

        # Build actions array - one action per light with same settings
        actions = []
        for light_id in light_ids:
            action_dict = {
                "target": {"rid": light_id, "rtype": "light"},
                "action": {"on": {"on": True}}  # Always turn lights on
            }

            # Add brightness if specified
            if scene_config.brightness is not None:
                action_dict["action"]["dimming"] = {"brightness": scene_config.brightness}

            # Add color (xy or mirek, not both)
            if scene_config.color is not None:
                action_dict["action"]["color"] = {
                    "xy": {"x": scene_config.color.x, "y": scene_config.color.y}
                }
            elif scene_config.color_temperature is not None:
                action_dict["action"]["color_temperature"] = {
                    "mirek": scene_config.color_temperature.mirek
                }

            actions.append(action_dict)

        return {
            "metadata": {"name": scene_config.name},
            "group": {"rid": room_id, "rtype": "room"},
            "actions": actions
        }

    @staticmethod
    def _floats_equal(a: float, b: float, tolerance: float = 0.01) -> bool:
        """
        Compare floats with tolerance for floating point precision.

        Args:
            a: First float value
            b: Second float value
            tolerance: Maximum difference to consider equal (default 0.01)

        Returns:
            True if values are within tolerance, False otherwise
        """
        return abs(a - b) < tolerance

    def _compare_scene_to_config(
        self,
        existing_scene: Dict[str, Any],
        scene_config: SceneConfig,
        room_id: str
    ) -> tuple[bool, List[str]]:
        """
        Compare existing scene with config to detect changes.

        Args:
            existing_scene: Scene data from GET /scene (includes actions array)
            scene_config: SceneConfig from YAML
            room_id: Room UUID (to validate action count)

        Returns:
            Tuple of (is_equal, list_of_differences)
            - is_equal: True if scene matches config exactly
            - list_of_differences: Human-readable list of what changed
        """
        differences = []

        try:
            # Get current lights in room to validate action count
            light_ids = self.get_lights_for_room(room_id)
            existing_actions = existing_scene.get('actions', [])

            # Check action count matches current light count
            if len(existing_actions) != len(light_ids):
                differences.append(
                    f"action count: {len(existing_actions)} → {len(light_ids)} "
                    f"(lights changed in room)"
                )
                return (False, differences)

            # If no actions, scene is malformed
            if not existing_actions:
                return (False, ["no actions found (malformed scene)"])

            # Extract values from first action (all should be identical)
            first_action = existing_actions[0].get('action', {})

            # Extract existing brightness
            existing_brightness = first_action.get('dimming', {}).get('brightness')

            # Extract existing color (xy or mirek)
            existing_color_xy = first_action.get('color', {}).get('xy')
            existing_mirek = first_action.get('color_temperature', {}).get('mirek')

            # Compare brightness
            if scene_config.brightness is not None:
                if existing_brightness is None:
                    differences.append(f"brightness: None → {scene_config.brightness}")
                elif not self._floats_equal(existing_brightness, scene_config.brightness, 0.01):
                    differences.append(
                        f"brightness: {existing_brightness:.1f} → {scene_config.brightness:.1f}"
                    )
            elif existing_brightness is not None:
                differences.append(f"brightness: {existing_brightness:.1f} → None")

            # Compare color mode and values
            if scene_config.color is not None:
                # Config uses color xy
                if existing_color_xy is None:
                    # Existing uses mirek or no color - mode change
                    if existing_mirek is not None:
                        differences.append("color mode: mirek → xy")
                        differences.append(
                            f"color: None → xy({scene_config.color.x:.4f}, {scene_config.color.y:.4f})"
                        )
                    else:
                        differences.append(
                            f"color: None → xy({scene_config.color.x:.4f}, {scene_config.color.y:.4f})"
                        )
                else:
                    # Both use color xy - compare values
                    existing_x = existing_color_xy.get('x')
                    existing_y = existing_color_xy.get('y')

                    if not (self._floats_equal(existing_x, scene_config.color.x, 0.0001) and
                            self._floats_equal(existing_y, scene_config.color.y, 0.0001)):
                        differences.append(
                            f"color xy: ({existing_x:.4f}, {existing_y:.4f}) → "
                            f"({scene_config.color.x:.4f}, {scene_config.color.y:.4f})"
                        )

            elif scene_config.color_temperature is not None:
                # Config uses color temperature (mirek)
                if existing_mirek is None:
                    # Existing uses xy or no color - mode change
                    if existing_color_xy is not None:
                        differences.append("color mode: xy → mirek")
                        differences.append(
                            f"color_temperature: None → {scene_config.color_temperature.mirek} mirek"
                        )
                    else:
                        differences.append(
                            f"color_temperature: None → {scene_config.color_temperature.mirek} mirek"
                        )
                else:
                    # Both use mirek - compare values (exact match for integers)
                    if existing_mirek != scene_config.color_temperature.mirek:
                        differences.append(
                            f"color_temperature: {existing_mirek} → "
                            f"{scene_config.color_temperature.mirek} mirek"
                        )

            else:
                # Config has no color - check if existing has color
                if existing_color_xy is not None:
                    existing_x = existing_color_xy.get('x')
                    existing_y = existing_color_xy.get('y')
                    differences.append(
                        f"color xy: ({existing_x:.4f}, {existing_y:.4f}) → None"
                    )
                elif existing_mirek is not None:
                    differences.append(f"color_temperature: {existing_mirek} mirek → None")

            # Return results
            return (len(differences) == 0, differences)

        except (KeyError, TypeError, AttributeError) as e:
            # Malformed scene data - mark as different
            return (False, [f"malformed scene data: {e}"])
        except HueAPIError as e:
            # API error during comparison - re-raise
            raise HueAPIError(f"Cannot compare scene without room light data: {e}")

    def get_devices(self) -> List[Dict[str, Any]]:
        """
        Query all devices from the bridge.

        Returns:
            List of device dictionaries with id, metadata.name, model_id

        Raises:
            HueAPIError: If request fails
        """
        data = self._request("GET", "device")
        return data.get("data", [])

    def get_buttons_for_device(self, device_id: str) -> List[Dict[str, Any]]:
        """
        Get buttons for a specific device.

        Args:
            device_id: Device UUID

        Returns:
            List of button dictionaries, sorted by control_id

        Raises:
            HueAPIError: If request fails
        """
        data = self._request("GET", "button")
        buttons = data.get("data", [])

        # Filter to buttons belonging to this device
        device_buttons = [
            b for b in buttons
            if b.get("owner", {}).get("rid") == device_id
        ]

        # Sort by control_id for consistent ordering
        device_buttons.sort(key=lambda b: b.get("metadata", {}).get("control_id", 0))

        return device_buttons

    def get_behavior_instance_for_device(self, device_id: str) -> Optional[Dict[str, Any]]:
        """
        Get behavior_instance for a specific device.

        Args:
            device_id: Device UUID

        Returns:
            Behavior instance dictionary, or None if not found

        Raises:
            HueAPIError: If request fails
        """
        data = self._request("GET", "behavior_instance")
        behaviors = data.get("data", [])

        # Find behavior for this device
        for behavior in behaviors:
            if behavior.get("configuration", {}).get("device", {}).get("rid") == device_id:
                return behavior

        return None

    def delete_behavior_instance(self, behavior_id: str) -> Dict[str, Any]:
        """
        Delete a behavior instance by ID.

        Args:
            behavior_id: Behavior instance UUID

        Returns:
            Deletion confirmation data

        Raises:
            HueAPIError: If request fails
        """
        return self._request("DELETE", f"behavior_instance/{behavior_id}")

    def create_behavior_instance(
        self,
        device_id: str,
        device_name: str,
        model_id: str,
        room_id: str,
        buttons: List[Dict[str, Any]],
        scene_ids: List[str],
        switch_type: str = "v1"
    ) -> Dict[str, Any]:
        """
        Create behavior_instance for dimmer switch with button-to-scene mappings.

        Args:
            device_id: Device UUID
            device_name: Device name (for metadata)
            model_id: Device model ID (e.g., RWL021, RWL022)
            room_id: Room UUID (for button assignments)
            buttons: List of button dictionaries (must have 4 buttons)
            scene_ids: List of scene UUIDs to assign to On button (cycle)
            switch_type: Switch version - "v1" (RWL021) or "v2" (RWL022)

        Returns:
            Created behavior instance data

        Raises:
            HueAPIError: If request fails or invalid button count

        Button Layout:
            v1 (RWL021):
                Button 1 (On): Scene cycle
                Button 2 (Dim Up): Dim up
                Button 3 (Dim Down): Dim down
                Button 4 (Off): Room off/toggle

            v2 (RWL022):
                Button 1 (On): Room on/toggle
                Button 2 (Dim Up): Dim up
                Button 3 (Dim Down): Dim down
                Button 4 (Hue): Scene cycle
        """
        if len(buttons) != 4:
            raise HueAPIError(f"Expected 4 buttons for dimmer switch, got {len(buttons)}")

        # Sort buttons by control_id to ensure correct mapping
        sorted_buttons = sorted(buttons, key=lambda b: b.get("metadata", {}).get("control_id", 0))

        # v1 layout (RWL021): On top, Off bottom, scenes on On button
        # v2 layout (RWL022): On top, Hue bottom, scenes on Hue button
        if switch_type == "v1":
            button_on = sorted_buttons[0]["id"]       # control_id: 1 - On (scene cycle)
            button_dim_up = sorted_buttons[1]["id"]   # control_id: 2 - Dim Up
            button_dim_down = sorted_buttons[2]["id"] # control_id: 3 - Dim Down
            button_off = sorted_buttons[3]["id"]      # control_id: 4 - Off (room toggle)
            scene_button = button_on
            toggle_button = button_off
        else:  # v2
            button_on = sorted_buttons[0]["id"]       # control_id: 1 - On (room toggle)
            button_dim_up = sorted_buttons[1]["id"]   # control_id: 2 - Dim Up
            button_dim_down = sorted_buttons[2]["id"] # control_id: 3 - Dim Down
            button_hue = sorted_buttons[3]["id"]      # control_id: 4 - Hue (scene cycle)
            scene_button = button_hue
            toggle_button = button_on

        # Build scene cycle slots
        scene_slots = []
        for scene_id in scene_ids:
            scene_slots.append([{
                "action": {
                    "recall": {
                        "rid": scene_id,
                        "rtype": "scene"
                    }
                }
            }])

        # Build behavior_instance body
        body = {
            "type": "behavior_instance",
            "script_id": "67d9395b-4403-42cc-b5f0-740b699d67c6",  # Standard script ID for switch behaviors
            "enabled": True,
            "configuration": {
                "buttons": {
                    # Scene cycle button (On for v1, Hue for v2)
                    scene_button: {
                        "on_short_release": {
                            "scene_cycle_extended": {
                                "repeat_timeout": {"seconds": 3},
                                "slots": scene_slots,
                                "with_off": {"enabled": False}
                            }
                        },
                        "on_long_press": {
                            "action": "do_nothing"
                        },
                        "where": [{
                            "group": {"rid": room_id, "rtype": "room"}
                        }]
                    },
                    # Dim Up button
                    button_dim_up: {
                        "on_repeat": {"action": "dim_up"},
                        "where": [{
                            "group": {"rid": room_id, "rtype": "room"}
                        }]
                    },
                    # Dim Down button
                    button_dim_down: {
                        "on_repeat": {"action": "dim_down"},
                        "where": [{
                            "group": {"rid": room_id, "rtype": "room"}
                        }]
                    },
                    # Room toggle button (Off for v1, On for v2)
                    toggle_button: {
                        "on_short_release": {
                            "recall_single_extended": {
                                "actions": [{"action": "last_on"}],
                                "with_off": {"enabled": True}
                            }
                        },
                        "on_long_press": {
                            "action": "do_nothing"
                        },
                        "where": [{
                            "group": {"rid": room_id, "rtype": "room"}
                        }]
                    }
                },
                "device": {"rid": device_id, "rtype": "device"},
                "model_id": model_id
            },
            "metadata": {"name": device_name}
        }

        return self._request("POST", "behavior_instance", json_data=body)

    def _build_long_press_config(
        self,
        button_number: int
    ) -> Dict[str, Any]:
        """
        Build on_long_press configuration for button.

        Button 1 (ON button) turns off all house lights when held using home_off action.
        All other buttons do nothing on hold.

        Args:
            button_number: Button number (1-4)

        Returns:
            Dictionary with on_long_press configuration
        """
        # Only button 1 (ON button) has hold-to-turn-off-all functionality
        if button_number == 1:
            return {"action": "home_off"}

        # All other buttons: do nothing on hold
        return {"action": "do_nothing"}

    def create_behavior_instance_v2(
        self,
        device_id: str,
        device_name: str,
        model_id: str,
        room_id: str,
        switch_config: 'SwitchConfig',
        room_lookup: Dict[str, str],
        zone_lookup: Dict[str, str],
        scene_name_to_id: Dict[str, str]
    ) -> Dict[str, Any]:
        """
        Create behavior_instance for dimmer switch with per-button configuration.

        Args:
            device_id: Device UUID
            device_name: Device name (for metadata)
            model_id: Device model ID (e.g., RWL021, RWL022, RDM004)
            room_id: Room UUID (fallback context for dim buttons)
            switch_config: SwitchConfig with button configurations
            room_lookup: Room name to ID mapping
            zone_lookup: Zone name to ID mapping
            scene_name_to_id: Scene name to ID mapping (for this room)

        Returns:
            Created behavior instance data

        Raises:
            HueAPIError: If request fails or invalid button configuration
        """
        # Get button resources from API
        api_buttons = self.get_buttons_for_device(device_id)
        if len(api_buttons) != 4:
            raise HueAPIError(f"Expected 4 buttons for dimmer switch, got {len(api_buttons)}")

        # Sort by control_id for consistent mapping
        sorted_buttons = sorted(api_buttons, key=lambda b: b.get("metadata", {}).get("control_id", 0))
        button_number_to_id = {i + 1: sorted_buttons[i]["id"] for i in range(4)}

        # Build configuration dict for each button
        buttons_config = {}

        for button_cfg in switch_config.buttons:
            button_id = button_number_to_id[button_cfg.button_number]

            if button_cfg.action == 'timezone':
                # Build time_based_extended configuration
                target_id, target_rtype = self._resolve_target(button_cfg.target, room_lookup, zone_lookup)
                slots = []
                for time_slot in button_cfg.time_slots:
                    scene_id = scene_name_to_id[time_slot.scene]
                    slots.append({
                        "actions": [{"action": {"recall": {"rid": scene_id, "rtype": "scene"}}}],
                        "start_time": {
                            "hour": time_slot.start_time['hour'],
                            "minute": time_slot.start_time['minute']
                        }
                    })

                buttons_config[button_id] = {
                    "on_short_release": {
                        "time_based_extended": {
                            "slots": slots,
                            "with_off": {"enabled": True}
                        }
                    },
                    "on_long_press": self._build_long_press_config(button_cfg.button_number),
                    "where": [{"group": {"rid": target_id, "rtype": target_rtype}}]
                }

            elif button_cfg.action == 'scene_cycle':
                # Build scene_cycle_extended configuration
                target_id, target_rtype = self._resolve_target(button_cfg.target, room_lookup, zone_lookup)
                scene_slots = []
                for scene_name in button_cfg.scenes:
                    scene_id = scene_name_to_id[scene_name]
                    scene_slots.append([{"action": {"recall": {"rid": scene_id, "rtype": "scene"}}}])

                buttons_config[button_id] = {
                    "on_short_release": {
                        "scene_cycle_extended": {
                            "repeat_timeout": {"seconds": 3},
                            "slots": scene_slots,
                            "with_off": {"enabled": False}
                        }
                    },
                    "on_long_press": self._build_long_press_config(button_cfg.button_number),
                    "where": [{"group": {"rid": target_id, "rtype": target_rtype}}]
                }

            elif button_cfg.action in {'dim_up', 'dim_down'}:
                # Dim buttons use implicit room context
                # Note: Buttons with on_repeat cannot have on_long_press (API constraint)
                buttons_config[button_id] = {
                    "on_repeat": {"action": button_cfg.action},
                    "where": [{"group": {"rid": room_id, "rtype": "room"}}]
                }

            elif button_cfg.action == 'room_toggle':
                # Room toggle configuration
                target_id, target_rtype = self._resolve_target(button_cfg.target, room_lookup, zone_lookup)

                buttons_config[button_id] = {
                    "on_short_release": {
                        "recall_single_extended": {
                            "actions": [{"action": "last_on"}],
                            "with_off": {"enabled": True}
                        }
                    },
                    "on_long_press": self._build_long_press_config(button_cfg.button_number),
                    "where": [{"group": {"rid": target_id, "rtype": target_rtype}}]
                }

        # Build final behavior_instance body
        body = {
            "type": "behavior_instance",
            "script_id": "67d9395b-4403-42cc-b5f0-740b699d67c6",
            "enabled": True,
            "configuration": {
                "buttons": buttons_config,
                "device": {"rid": device_id, "rtype": "device"},
                "model_id": model_id
            },
            "metadata": {"name": device_name}
        }

        return self._request("POST", "behavior_instance", json_data=body)

    def _resolve_target(
        self,
        target_name: str,
        room_lookup: Dict[str, str],
        zone_lookup: Dict[str, str]
    ) -> tuple[str, str]:
        """
        Helper to resolve target name to (id, rtype).

        Returns:
            Tuple of (target_id, rtype)

        Raises:
            HueAPIError: If target not found
        """
        if target_name in room_lookup:
            return (room_lookup[target_name], "room")
        if target_name in zone_lookup:
            return (zone_lookup[target_name], "zone")

        raise HueAPIError(f"Target '{target_name}' not found in rooms or zones")

    def _request(
        self,
        method: str,
        endpoint: str,
        json_data: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Internal method for making API requests.

        Args:
            method: HTTP method (GET, POST, DELETE)
            endpoint: API endpoint (e.g., 'scene', 'room')
            json_data: Optional request body

        Returns:
            Response data dictionary

        Raises:
            HueAPIError: If request fails
        """
        url = f"{self.base_url}/{endpoint}"

        try:
            response = requests.request(
                method,
                url,
                headers=self.headers,
                json=json_data,
                verify=False,  # Self-signed cert
                timeout=self.timeout
            )
            response.raise_for_status()
            return response.json()
        except requests.exceptions.Timeout as e:
            raise HueAPIError(f"Request timeout: {e}")
        except requests.exceptions.ConnectionError as e:
            raise HueAPIError(f"Connection failed: {e}")
        except requests.exceptions.HTTPError as e:
            raise HueAPIError(f"HTTP {response.status_code}: {response.text}")
        except requests.exceptions.RequestException as e:
            raise HueAPIError(f"Request failed: {e}")


# ============================================================================
# Main Script Logic
# ============================================================================

def parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description="Sync Philips Hue room scenes from YAML config (destructive: deletes existing scenes)"
    )
    parser.add_argument(
        '--execute',
        action='store_true',
        help="Execute changes (default: dry-run mode)"
    )
    parser.add_argument(
        '--config',
        default='rooms_scenes.yaml',
        help="Path to YAML config file (default: rooms_scenes.yaml)"
    )
    parser.add_argument(
        '--room',
        help="Only sync specific room name (filters config)"
    )
    parser.add_argument(
        '--verbose', '-v',
        action='store_true',
        help="Enable verbose logging (DEBUG level)"
    )

    return parser.parse_args()


def setup_logging(verbose: bool) -> None:
    """Configure logging based on verbosity level."""
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format='%(asctime)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )


def load_config(config_path: str, logger: logging.Logger) -> RoomsScenesConfig:
    """
    Load and validate YAML configuration file.

    Args:
        config_path: Path to YAML config file
        logger: Logger instance

    Returns:
        Validated RoomsScenesConfig object

    Raises:
        SystemExit: If file not found or validation fails
    """
    try:
        with open(config_path, 'r') as f:
            config_data = yaml.safe_load(f)

        logger.debug(f"Loaded config from {config_path}")
        config = RoomsScenesConfig(**config_data)
        logger.info(f"Config validation passed: {len(config.rooms)} room(s) defined")
        return config

    except FileNotFoundError:
        logger.error(f"Config file not found: {config_path}")
        sys.exit(1)
    except yaml.YAMLError as e:
        logger.error(f"YAML parsing error: {e}")
        sys.exit(1)
    except ValidationError as e:
        logger.error(f"Config validation failed:\n{e}")
        sys.exit(1)


def validate_credentials(bridge_ip: Optional[str], api_key: Optional[str], logger: logging.Logger) -> None:
    """
    Validate that required credentials are present.

    Args:
        bridge_ip: Hue Bridge IP address
        api_key: API key
        logger: Logger instance

    Raises:
        SystemExit: If credentials are missing
    """
    if not bridge_ip or not api_key:
        logger.error("HUE_BRIDGE_IP and HUE_USERNAME must be set in .env file")
        sys.exit(1)

    logger.debug(f"Credentials validated: bridge_ip={bridge_ip}")


def build_room_lookup(client: HueAPIClient, logger: logging.Logger) -> Dict[str, str]:
    """
    Build room name to ID lookup map.

    Args:
        client: HueAPIClient instance
        logger: Logger instance

    Returns:
        Dictionary mapping room names to room IDs

    Raises:
        SystemExit: If API call fails
    """
    try:
        all_rooms = client.get_rooms()
        logger.debug(f"Retrieved {len(all_rooms)} rooms from bridge")

        # Build lookup map
        room_name_to_id = {}
        for room in all_rooms:
            name = room.get('metadata', {}).get('name', 'Unknown')
            room_id = room.get('id')

            if name in room_name_to_id:
                logger.warning(f"Duplicate room name found: '{name}' - using first match")
            else:
                room_name_to_id[name] = room_id
                logger.debug(f"  {name} -> {room_id}")

        return room_name_to_id

    except HueAPIError as e:
        logger.error(f"Failed to query rooms from bridge: {e}")
        sys.exit(1)


def build_zone_lookup(client: HueAPIClient, logger: logging.Logger) -> Dict[str, str]:
    """
    Build zone name to ID lookup map.

    Args:
        client: HueAPIClient instance
        logger: Logger instance

    Returns:
        Dictionary mapping zone names to zone IDs

    Raises:
        SystemExit: If API call fails
    """
    try:
        all_zones = client.get_zones()
        logger.debug(f"Retrieved {len(all_zones)} zones from bridge")

        # Build lookup map
        zone_name_to_id = {}
        for zone in all_zones:
            name = zone.get('metadata', {}).get('name', 'Unknown')
            zone_id = zone.get('id')

            if name in zone_name_to_id:
                logger.warning(f"Duplicate zone name found: '{name}' - using first match")
            else:
                zone_name_to_id[name] = zone_id
                logger.debug(f"  {name} -> {zone_id}")

        return zone_name_to_id

    except HueAPIError as e:
        logger.error(f"Failed to query zones from bridge: {e}")
        sys.exit(1)


def resolve_target(
    target_name: str,
    room_lookup: Dict[str, str],
    zone_lookup: Dict[str, str],
    logger: logging.Logger
) -> tuple[str, str]:
    """
    Resolve a target name to (id, rtype) by checking rooms first, then zones.

    Args:
        target_name: Room or zone name
        room_lookup: Room name to ID mapping
        zone_lookup: Zone name to ID mapping
        logger: Logger instance

    Returns:
        Tuple of (target_id, rtype) where rtype is "room" or "zone"

    Raises:
        TargetNotFoundError: If target not found in rooms or zones
    """
    if target_name in room_lookup:
        logger.debug(f"Resolved target '{target_name}' to room ID: {room_lookup[target_name]}")
        return (room_lookup[target_name], "room")

    if target_name in zone_lookup:
        logger.debug(f"Resolved target '{target_name}' to zone ID: {zone_lookup[target_name]}")
        return (zone_lookup[target_name], "zone")

    raise TargetNotFoundError(
        f"Target '{target_name}' not found in rooms or zones. "
        f"Available rooms: {sorted(room_lookup.keys())}. "
        f"Available zones: {sorted(zone_lookup.keys())}"
    )


def build_scene_name_to_id_map(
    scene_configs: List[SceneConfig],
    created_scene_ids: List[str]
) -> Dict[str, str]:
    """
    Build scene name to ID mapping from config and created scenes.

    Args:
        scene_configs: List of SceneConfig from YAML
        created_scene_ids: List of created scene IDs (same order as scene_configs)

    Returns:
        Dictionary mapping scene names to scene IDs

    Raises:
        ValueError: If lengths don't match
    """
    if len(scene_configs) != len(created_scene_ids):
        raise ValueError(
            f"Scene config count ({len(scene_configs)}) doesn't match "
            f"created scene IDs count ({len(created_scene_ids)})"
        )

    return {
        config.name: scene_id
        for config, scene_id in zip(scene_configs, created_scene_ids)
    }


def sync_switches_for_room(
    client: HueAPIClient,
    room_config: RoomConfig,
    room_id: str,
    scene_name_to_id: Dict[str, str],
    room_lookup: Dict[str, str],
    zone_lookup: Dict[str, str],
    dry_run: bool,
    logger: logging.Logger
) -> None:
    """
    Sync dimmer switch button assignments for a room.

    Args:
        client: HueAPIClient instance
        room_config: Room configuration
        room_id: Room UUID (for dim button fallback context)
        scene_name_to_id: Scene name to ID mapping for this room
        room_lookup: Room name to ID mapping (for target resolution)
        zone_lookup: Zone name to ID mapping (for target resolution)
        dry_run: If True, only log actions without executing
        logger: Logger instance

    Raises:
        HueAPIError: If API call fails
    """
    if not room_config.switches:
        return

    # Build device name to data lookup
    all_devices = client.get_devices()
    device_name_to_data = {d.get('metadata', {}).get('name', 'Unknown'): d for d in all_devices}

    for switch_config in room_config.switches:
        switch_name = switch_config.device_name
        logger.info(f"\n--- Processing Switch: {switch_name} ---")

        # Find device by name
        device_data = device_name_to_data.get(switch_name)
        if not device_data:
            logger.warning(f"Switch '{switch_name}' not found on bridge - skipping")
            continue

        device_id = device_data.get('id')
        model_id = device_data.get('product_data', {}).get('model_id', 'Unknown')
        logger.debug(f"Resolved '{switch_name}' to ID: {device_id} (Model: {model_id})")

        # Get buttons for device
        buttons = client.get_buttons_for_device(device_id)
        if len(buttons) != 4:
            logger.warning(f"Switch '{switch_name}' has {len(buttons)} buttons (expected 4) - skipping")
            continue

        logger.info(f"Found {len(buttons)} buttons on switch (type: {switch_config.model_type})")

        # Get existing behavior instance
        existing_behavior = client.get_behavior_instance_for_device(device_id)

        # Delete existing behavior
        if existing_behavior:
            behavior_id = existing_behavior.get('id')
            if dry_run:
                logger.info(f"[DRY-RUN] Would delete existing button configuration (Behavior ID: {behavior_id})")
            else:
                logger.info(f"Deleting existing button configuration")
                client.delete_behavior_instance(behavior_id)
        else:
            logger.info("No existing button configuration found")

        # Log button configuration plan
        if dry_run:
            logger.info(f"[DRY-RUN] Would create button configuration:")
            for button_cfg in switch_config.buttons:
                if button_cfg.action == 'timezone':
                    slot_summary = ", ".join([
                        f"{s.start_time['hour']:02d}:{s.start_time['minute']:02d}→{s.scene}"
                        for s in button_cfg.time_slots
                    ])
                    logger.info(f"  Button {button_cfg.button_number}: timezone ({button_cfg.target}) - {slot_summary}")
                elif button_cfg.action == 'scene_cycle':
                    logger.info(f"  Button {button_cfg.button_number}: scene_cycle ({button_cfg.target}) - {', '.join(button_cfg.scenes)}")
                elif button_cfg.action == 'room_toggle':
                    logger.info(f"  Button {button_cfg.button_number}: room_toggle ({button_cfg.target})")
                else:
                    logger.info(f"  Button {button_cfg.button_number}: {button_cfg.action}")

                # Log long press action (only button 1 has hold-to-turn-off-all)
                if button_cfg.button_number == 1:
                    num_rooms = len(room_lookup)
                    logger.info(f"      Hold: ALL LIGHTS OFF ({num_rooms} rooms)")
        else:
            logger.info(f"Creating button configuration:")
            for button_cfg in switch_config.buttons:
                if button_cfg.action == 'timezone':
                    slot_summary = ", ".join([
                        f"{s.start_time['hour']:02d}:{s.start_time['minute']:02d}→{s.scene}"
                        for s in button_cfg.time_slots
                    ])
                    logger.info(f"  Button {button_cfg.button_number}: timezone ({button_cfg.target}) - {slot_summary}")
                elif button_cfg.action == 'scene_cycle':
                    logger.info(f"  Button {button_cfg.button_number}: scene_cycle ({button_cfg.target}) - {', '.join(button_cfg.scenes)}")
                elif button_cfg.action == 'room_toggle':
                    logger.info(f"  Button {button_cfg.button_number}: room_toggle ({button_cfg.target})")
                else:
                    logger.info(f"  Button {button_cfg.button_number}: {button_cfg.action}")

                # Log long press action (only button 1 has hold-to-turn-off-all)
                if button_cfg.button_number == 1:
                    num_rooms = len(room_lookup)
                    logger.info(f"      Hold: ALL LIGHTS OFF ({num_rooms} rooms)")

            result = client.create_behavior_instance_v2(
                device_id=device_id,
                device_name=switch_name,
                model_id=model_id,
                room_id=room_id,
                switch_config=switch_config,
                room_lookup=room_lookup,
                zone_lookup=zone_lookup,
                scene_name_to_id=scene_name_to_id
            )
            behavior_id = result.get('data', [{}])[0].get('rid', 'unknown')
            logger.debug(f"Created behavior instance ID: {behavior_id}")

        logger.info(f"✓ Completed switch: {switch_name}")


def sync_room(
    client: HueAPIClient,
    room_config: RoomConfig,
    room_name_to_id: Dict[str, str],
    zone_name_to_id: Dict[str, str],
    dry_run: bool,
    logger: logging.Logger
) -> None:
    """
    Sync scenes for a single room.

    Args:
        client: HueAPIClient instance
        room_config: Room configuration
        room_name_to_id: Room name to ID mapping
        zone_name_to_id: Zone name to ID mapping
        dry_run: If True, only log actions without executing
        logger: Logger instance

    Raises:
        RoomNotFoundError: If room name not found on bridge
        HueAPIError: If API call fails
    """
    room_name = room_config.room_name
    logger.info(f"\n--- Processing: {room_name} ---")

    # Resolve room ID
    room_id = room_name_to_id.get(room_name)
    if not room_id:
        raise RoomNotFoundError(f"Room '{room_name}' not found on bridge")

    logger.debug(f"Resolved '{room_name}' to ID: {room_id}")

    # Query lights in the room
    light_ids = client.get_lights_for_room(room_id)
    light_count = len(light_ids)
    logger.info(f"Room contains {light_count} light(s)")

    # Query existing scenes
    existing_scenes = client.get_scenes_for_room(room_id)
    logger.info(f"Found {len(existing_scenes)} existing scene(s)")

    # Build lookup of existing scenes by name
    existing_by_name = {}
    for scene in existing_scenes:
        scene_name = scene.get('metadata', {}).get('name', 'Unknown')
        if scene_name in existing_by_name:
            logger.warning(
                f"Duplicate scene name '{scene_name}' found in room "
                f"(IDs: {existing_by_name[scene_name]['id']}, {scene['id']}) - "
                f"using first match, will delete duplicate"
            )
        else:
            existing_by_name[scene_name] = scene

    # Track matched scene IDs (to delete unmatched) and created scene IDs (for switch integration)
    matched_scene_ids = set()
    created_scene_ids = []  # Preserves order for build_scene_name_to_id_map()

    # Process each config scene - SKIP/UPDATE/CREATE
    for scene_config in room_config.scenes:
        scene_name = scene_config.name

        if scene_name in existing_by_name:
            # Scene exists - compare configuration
            existing_scene = existing_by_name[scene_name]
            scene_id = existing_scene.get('id')

            is_equal, differences = client._compare_scene_to_config(
                existing_scene, scene_config, room_id
            )

            if is_equal:
                # [SKIP] - No changes needed
                prefix = "[DRY-RUN] " if dry_run else ""
                logger.info(f"{prefix}[SKIP] {scene_name} (already matches config)")
                matched_scene_ids.add(scene_id)
                created_scene_ids.append(scene_id)
            else:
                # [UPDATE] - Differences found
                diff_summary = ", ".join(differences)
                prefix = "[DRY-RUN] " if dry_run else ""
                logger.info(f"{prefix}[UPDATE] {scene_name} → {diff_summary}")
                if not dry_run:
                    client.update_scene(scene_id, room_id, scene_config)
                    logger.debug(f"Updated scene ID: {scene_id}")
                matched_scene_ids.add(scene_id)
                created_scene_ids.append(scene_id)
        else:
            # [CREATE] - Scene doesn't exist
            prefix = "[DRY-RUN] " if dry_run else ""
            logger.info(f"{prefix}[CREATE] {scene_name} (applies to {light_count} light(s))")
            if dry_run:
                # For dry-run, use placeholder IDs
                placeholder_id = f"placeholder-scene-{len(created_scene_ids)}"
                created_scene_ids.append(placeholder_id)
            else:
                result = client.create_scene(room_id, scene_config)
                new_scene_id = result.get('data', [{}])[0].get('rid', 'unknown')
                created_scene_ids.append(new_scene_id)
                logger.debug(f"Created scene ID: {new_scene_id}")

    # Delete unmatched existing scenes (not in config)
    for scene in existing_scenes:
        scene_name = scene.get('metadata', {}).get('name', 'Unknown')
        scene_id = scene.get('id')

        if scene_id not in matched_scene_ids:
            # [DELETE] - Scene exists on bridge but not in config
            prefix = "[DRY-RUN] " if dry_run else ""
            logger.info(f"{prefix}[DELETE] {scene_name} (not in config)")
            if not dry_run:
                client.delete_scene(scene_id)

    logger.info(f"✓ Completed scenes for: {room_name}")

    # Sync switches (if configured)
    if room_config.switches:
        scene_name_to_id = build_scene_name_to_id_map(room_config.scenes, created_scene_ids)
        sync_switches_for_room(
            client,
            room_config,
            room_id,
            scene_name_to_id,
            room_name_to_id,
            zone_name_to_id,
            dry_run,
            logger
        )

    logger.info(f"✓ Completed all sync for: {room_name}")


def print_summary(
    results: Dict[str, List[str]],
    dry_run: bool,
    logger: logging.Logger
) -> None:
    """
    Print final summary report.

    Args:
        results: Dictionary with 'success', 'errors', 'skipped' lists
        dry_run: Whether this was a dry-run
        logger: Logger instance
    """
    logger.info("\n" + "=" * 60)
    logger.info("SUMMARY")
    logger.info("=" * 60)
    logger.info(f"Success: {len(results['success'])} room(s)")
    logger.info(f"Errors:  {len(results['errors'])} room(s)")
    logger.info(f"Skipped: {len(results['skipped'])} room(s)")

    if results['success']:
        logger.info("\nSuccessfully synced:")
        for room in results['success']:
            logger.info(f"  ✓ {room}")

    if results['errors']:
        logger.info("\nFailed to sync:")
        for room in results['errors']:
            logger.info(f"  ✗ {room}")

    if results['skipped']:
        logger.info("\nSkipped (room not found on bridge):")
        for room in results['skipped']:
            logger.info(f"  - {room}")

    if dry_run:
        logger.info("\n" + "!" * 60)
        logger.info("DRY-RUN MODE: No changes were made")
        logger.info("Use --execute flag to apply changes")
        logger.info("!" * 60)


def main() -> None:
    """Main entry point."""
    # Parse CLI arguments
    args = parse_args()

    # Setup logging
    setup_logging(args.verbose)
    logger = logging.getLogger(__name__)

    # Load credentials from .env
    load_dotenv()
    bridge_ip = os.getenv('HUE_BRIDGE_IP')
    api_key = os.getenv('HUE_USERNAME')
    validate_credentials(bridge_ip, api_key, logger)

    # Load and validate YAML config
    config = load_config(args.config, logger)

    # Filter by --room if specified
    rooms_to_sync = config.rooms
    if args.room:
        rooms_to_sync = [r for r in config.rooms if r.room_name == args.room]
        if not rooms_to_sync:
            logger.error(f"Room '{args.room}' not found in config")
            sys.exit(1)
        logger.info(f"Filtering to single room: {args.room}")

    # Initialize API client
    logger.debug(f"Initializing API client for {bridge_ip}")
    client = HueAPIClient(bridge_ip, api_key)

    # Resolve room and zone names to IDs
    logger.info("Resolving room and zone names to IDs...")
    room_name_to_id = build_room_lookup(client, logger)
    zone_name_to_id = build_zone_lookup(client, logger)

    # Determine mode
    dry_run = not args.execute
    if dry_run:
        logger.info("\n" + "=" * 60)
        logger.info("DRY-RUN MODE (use --execute to apply changes)")
        logger.info("=" * 60)
    else:
        logger.warning("\n" + "!" * 60)
        logger.warning("EXECUTE MODE: Changes will be applied to Hue Bridge")
        logger.warning("!" * 60)

    # Sync each room
    results = {
        'success': [],
        'errors': [],
        'skipped': []
    }

    for room_config in rooms_to_sync:
        try:
            sync_room(client, room_config, room_name_to_id, zone_name_to_id, dry_run, logger)
            results['success'].append(room_config.room_name)
        except RoomNotFoundError as e:
            logger.error(f"Room '{room_config.room_name}' not found - skipping")
            results['skipped'].append(room_config.room_name)
        except TargetNotFoundError as e:
            logger.error(f"Target resolution failed for '{room_config.room_name}': {e}")
            results['errors'].append(room_config.room_name)
        except HueAPIError as e:
            logger.error(f"Failed to sync '{room_config.room_name}': {e}")
            results['errors'].append(room_config.room_name)

    # Print summary
    print_summary(results, dry_run, logger)

    # Exit with appropriate code
    exit_code = 0 if not results['errors'] else 1
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
