#!/usr/bin/env python3
"""
Hue Configuration-as-Code Export Script

Exports the current state of a Philips Hue Bridge to a YAML file.
This is a READ-ONLY script that queries the Hue CLIP API v2.

Phases:
1. Resource Scaffolding: Pull rooms, zones, and devices
2. Service Join: Map light services to rooms/zones
3. Scene Recipes: Capture scene configurations
4. Button Configuration: Export switch button settings
"""

import os
import sys
import yaml
import requests
import urllib3
from typing import Dict, List, Any, Optional
from dotenv import load_dotenv

# Suppress SSL warnings for self-signed certificate
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# Load environment variables
load_dotenv()

HUE_BRIDGE_IP = os.getenv('HUE_BRIDGE_IP')
HUE_API_KEY = os.getenv('HUE_USERNAME')  # Note: Uses HUE_USERNAME env var

if not HUE_BRIDGE_IP or not HUE_API_KEY:
    print("ERROR: HUE_BRIDGE_IP and HUE_USERNAME must be set in .env file")
    sys.exit(1)

BASE_URL = f"https://{HUE_BRIDGE_IP}/clip/v2/resource"
HEADERS = {"hue-application-key": HUE_API_KEY}


def query_endpoint(endpoint: str) -> List[Dict[str, Any]]:
    """
    Query a Hue CLIP API v2 endpoint.

    Args:
        endpoint: API endpoint path (e.g., 'room', 'light', 'scene')

    Returns:
        List of resource dictionaries, or empty list on error
    """
    try:
        url = f"{BASE_URL}/{endpoint}"
        response = requests.get(url, headers=HEADERS, verify=False, timeout=10)
        response.raise_for_status()

        data = response.json()
        return data.get('data', [])

    except requests.exceptions.RequestException as e:
        print(f"WARNING: Failed to query /{endpoint}: {e}")
        return []


def extract_device_metadata(device: Dict[str, Any]) -> Dict[str, Any]:
    """
    Extract metadata from a device resource.

    Args:
        device: Device resource dictionary

    Returns:
        Dictionary with device metadata
    """
    metadata = device.get('metadata', {})
    product_data = device.get('product_data', {})

    return {
        'id': device.get('id'),
        'name': metadata.get('name', 'Unknown Device'),
        'model_id': product_data.get('model_id'),
        'archetype': metadata.get('archetype'),
        'software_version': product_data.get('software_version')
    }


def extract_room_zone_metadata(resource: Dict[str, Any]) -> Dict[str, Any]:
    """
    Extract metadata from a room or zone resource.

    Args:
        resource: Room or zone resource dictionary

    Returns:
        Dictionary with room/zone metadata including child RIDs
    """
    metadata = resource.get('metadata', {})
    children = resource.get('children', [])

    # Rooms have device children, Zones have light children
    # Extract both types for Phase 2 mapping
    child_device_rids = [child.get('rid') for child in children
                         if child.get('rtype') == 'device' and child.get('rid')]
    child_light_rids = [child.get('rid') for child in children
                        if child.get('rtype') == 'light' and child.get('rid')]

    return {
        'id': resource.get('id'),
        'name': metadata.get('name', 'Unknown'),
        'archetype': metadata.get('archetype'),
        'child_device_rids': child_device_rids,  # For rooms (Room → Device → Light)
        'child_light_rids': child_light_rids,    # For zones (Zone → Light directly)
        'lights': [],  # Will be populated in Phase 2
        'scenes': []   # Will be populated in Phase 3
    }


def extract_light_state(light: Dict[str, Any]) -> Dict[str, Any]:
    """
    Extract current state from a light service.

    Args:
        light: Light service resource dictionary

    Returns:
        Dictionary with light state (id, name, on, brightness, color)
    """
    metadata = light.get('metadata', {})
    on_state = light.get('on', {})
    dimming = light.get('dimming', {})
    color_data = light.get('color', {})
    color_temp = light.get('color_temperature', {})

    light_state = {
        'id': light.get('id'),
        'name': metadata.get('name', 'Unknown Light'),
        'on': on_state.get('on', False)
    }

    # Add brightness if available
    if 'brightness' in dimming:
        light_state['brightness'] = round(dimming['brightness'], 1)

    # Add color information (prefer xy over mirek)
    if 'xy' in color_data:
        xy = color_data['xy']
        light_state['color'] = {
            'xy': [round(xy.get('x', 0), 4), round(xy.get('y', 0), 4)]
        }
    elif 'mirek' in color_temp:
        light_state['color'] = {
            'mirek': color_temp['mirek']
        }

    return light_state


def extract_scene_data(scene: Dict[str, Any]) -> Dict[str, Any]:
    """
    Extract scene configuration including actions.

    Args:
        scene: Scene resource dictionary

    Returns:
        Dictionary with scene metadata and actions array
    """
    metadata = scene.get('metadata', {})
    group = scene.get('group', {})
    actions = scene.get('actions', [])

    # Process actions to extract target and action details
    processed_actions = []
    for action in actions:
        target = action.get('target', {})
        action_data = action.get('action', {})

        processed_action = {
            'target': target.get('rid')
        }

        # Extract action details (on, dimming, color, color_temperature)
        if action_data:
            processed_action['action'] = {}

            if 'on' in action_data:
                processed_action['action']['on'] = action_data['on']

            if 'dimming' in action_data:
                processed_action['action']['dimming'] = action_data['dimming']

            if 'color' in action_data:
                processed_action['action']['color'] = action_data['color']

            if 'color_temperature' in action_data:
                processed_action['action']['color_temperature'] = action_data['color_temperature']

        processed_actions.append(processed_action)

    return {
        'id': scene.get('id'),
        'name': metadata.get('name', 'Unknown Scene'),
        'group_rid': group.get('rid'),  # Links scene to room/zone
        'actions': processed_actions
    }


def is_switch_device(device: Dict[str, Any]) -> bool:
    """
    Check if a device is a switch (dimmer or smart button).

    Args:
        device: Device dictionary with 'model_id' key

    Returns:
        True if device is a switch (RWL* or RDM* model), False otherwise
    """
    model_id = device.get('model_id')
    if not model_id:
        return False
    return model_id.startswith('RWL') or model_id.startswith('RDM')


def extract_button_action_type(button_config: Dict[str, Any]) -> str:
    """
    Determine the action type from a button configuration.

    Args:
        button_config: Button configuration dictionary from behavior_instance

    Returns:
        Action type string: "scene_cycle", "room_toggle", "dim_up", "dim_down", "timezone", or "unknown"
    """
    # Check for scene cycle pattern
    on_short_release = button_config.get('on_short_release', {})
    if 'scene_cycle_extended' in on_short_release:
        return 'scene_cycle'

    # Check for timezone-based scene change
    if 'time_based_extended' in on_short_release:
        return 'timezone'

    # Check for room toggle pattern (recall with off enabled)
    if 'recall_single_extended' in on_short_release:
        with_off = on_short_release.get('recall_single_extended', {}).get('with_off', {})
        if with_off.get('enabled'):
            return 'room_toggle'

    # Check for dim actions
    on_repeat = button_config.get('on_repeat', {})
    if on_repeat.get('action') == 'dim_up':
        return 'dim_up'
    if on_repeat.get('action') == 'dim_down':
        return 'dim_down'

    # Unknown pattern (custom or future feature)
    return 'unknown'


def extract_button_configuration(
    behavior_instance: Dict[str, Any],
    buttons_by_id: Dict[str, Dict[str, Any]],
    rooms_by_id: Dict[str, Dict[str, Any]],
    scenes_by_id: Dict[str, str]
) -> Dict[str, Any]:
    """
    Extract button configuration from a behavior_instance.

    Args:
        behavior_instance: Behavior instance resource from API
        buttons_by_id: Lookup map of button UUID → button with control_id
        rooms_by_id: Lookup map of room UUID → room dict
        scenes_by_id: Lookup map of scene UUID → scene name

    Returns:
        Structured button configuration dictionary
    """
    config = behavior_instance.get('configuration', {})
    buttons_config = config.get('buttons', {})

    result = {
        'id': behavior_instance.get('id'),
        'enabled': behavior_instance.get('enabled', True),
        'buttons': []
    }

    # Process each button configuration
    for button_id, button_config in buttons_config.items():
        # Resolve button UUID to control_id
        button_info = buttons_by_id.get(button_id, {})
        control_id = button_info.get('metadata', {}).get('control_id')

        if control_id is None:
            continue  # Skip if we can't resolve button

        # Determine action type
        action_type = extract_button_action_type(button_config)

        # Extract target room name
        where = button_config.get('where', [])
        target_room = None
        if where:
            group_rid = where[0].get('group', {}).get('rid')
            if group_rid and group_rid in rooms_by_id:
                target_room = rooms_by_id[group_rid].get('name')

        button_data = {
            'control_id': control_id,
            'action_type': action_type,
            'target_room': target_room
        }

        # Extract scene names for scene_cycle
        if action_type == 'scene_cycle':
            scene_names = []
            on_short_release = button_config.get('on_short_release', {})
            scene_cycle = on_short_release.get('scene_cycle_extended', {})
            slots = scene_cycle.get('slots', [])

            for slot in slots:
                if isinstance(slot, list) and slot:
                    scene_rid = slot[0].get('action', {}).get('recall', {}).get('rid')
                    if scene_rid:
                        scene_name = scenes_by_id.get(scene_rid, scene_rid)
                        scene_names.append(scene_name)

            if scene_names:
                button_data['scene_names'] = scene_names

        # For timezone configs, resolve scene UUIDs to names and preserve structure
        elif action_type == 'timezone':
            on_short_release = button_config.get('on_short_release', {})
            time_based = on_short_release.get('time_based_extended', {})
            slots = time_based.get('slots', [])

            # Create a copy with resolved scene names
            resolved_slots = []
            for slot in slots:
                actions = slot.get('actions', [])
                start_time = slot.get('start_time', {})

                resolved_actions = []
                for action in actions:
                    scene_rid = action.get('action', {}).get('recall', {}).get('rid')
                    if scene_rid:
                        scene_name = scenes_by_id.get(scene_rid, scene_rid)
                        resolved_actions.append({
                            'scene': scene_name,
                            'scene_id': scene_rid  # Preserve UUID for reference
                        })

                resolved_slots.append({
                    'start_time': start_time,
                    'scenes': resolved_actions
                })

            button_data['timezone_slots'] = resolved_slots

            # Also preserve raw configuration for full details
            button_data['configuration'] = button_config

        # For unknown types, preserve raw configuration only
        elif action_type == 'unknown':
            button_data['configuration'] = button_config

        result['buttons'].append(button_data)

    # Sort buttons by control_id for consistent output
    result['buttons'].sort(key=lambda b: b['control_id'])

    return result


def phase_1_resource_scaffolding() -> Dict[str, Any]:
    """
    Phase 1: Pull rooms, zones, and devices from Hue Bridge.

    Returns:
        Dictionary with rooms, zones, and devices lists
    """
    print("Phase 1: Querying rooms, zones, and devices...")

    rooms_raw = query_endpoint('room')
    zones_raw = query_endpoint('zone')
    devices_raw = query_endpoint('device')

    rooms = [extract_room_zone_metadata(r) for r in rooms_raw]
    zones = [extract_room_zone_metadata(z) for z in zones_raw]
    devices = [extract_device_metadata(d) for d in devices_raw]

    print(f"  Found {len(rooms)} rooms, {len(zones)} zones, {len(devices)} devices")

    return {
        'rooms': rooms,
        'zones': zones,
        'devices': devices
    }


def phase_2_service_join(architecture: Dict[str, Any]) -> None:
    """
    Phase 2: Map light services to their parent rooms/zones.

    This phase performs the "service join" using the Room → Device → Light relationship:
    1. Room/Zone has 'children' (device RIDs)
    2. Device has 'services' (including light RIDs)
    3. Match light RIDs to actual Light resources

    Args:
        architecture: Dictionary from Phase 1 (modified in-place)
    """
    print("Phase 2: Mapping light services to rooms and zones...")

    # Query all resources needed for the join
    lights_raw = query_endpoint('light')
    devices_raw = query_endpoint('device')

    # Create lookup maps
    lights_by_id = {light['id']: extract_light_state(light) for light in lights_raw}
    devices_by_id = {device['id']: device for device in devices_raw}

    print(f"  Found {len(lights_by_id)} light services")

    # Build Device → Light mapping
    device_to_lights = {}
    for device_id, device in devices_by_id.items():
        services = device.get('services', [])
        light_rids = [svc.get('rid') for svc in services if svc.get('rtype') == 'light']
        device_to_lights[device_id] = light_rids

    # Map lights to rooms (Room → Device → Light)
    for room in architecture['rooms']:
        room_lights = []

        # Rooms use device children
        for device_rid in room.get('child_device_rids', []):
            light_rids = device_to_lights.get(device_rid, [])
            for light_rid in light_rids:
                if light_rid in lights_by_id:
                    room_lights.append(lights_by_id[light_rid])

        # Some rooms might also have direct light children (handle both cases)
        for light_rid in room.get('child_light_rids', []):
            if light_rid in lights_by_id:
                room_lights.append(lights_by_id[light_rid])

        room['lights'] = room_lights
        # Remove internal fields from final output
        del room['child_device_rids']
        del room['child_light_rids']

        print(f"  Room '{room['name']}': {len(room_lights)} lights")

    # Map lights to zones (Zone → Light directly, or Zone → Device → Light)
    for zone in architecture['zones']:
        zone_lights = []

        # Zones typically use direct light children
        for light_rid in zone.get('child_light_rids', []):
            if light_rid in lights_by_id:
                zone_lights.append(lights_by_id[light_rid])

        # Some zones might use device children (handle both cases)
        for device_rid in zone.get('child_device_rids', []):
            light_rids = device_to_lights.get(device_rid, [])
            for light_rid in light_rids:
                if light_rid in lights_by_id:
                    zone_lights.append(lights_by_id[light_rid])

        zone['lights'] = zone_lights
        # Remove internal fields from final output
        del zone['child_device_rids']
        del zone['child_light_rids']

        print(f"  Zone '{zone['name']}': {len(zone_lights)} lights")


def phase_3_scene_recipes(architecture: Dict[str, Any]) -> None:
    """
    Phase 3: Pull scene configurations and nest under correct room/zone.

    Args:
        architecture: Dictionary from Phase 1 & 2 (modified in-place)
    """
    print("Phase 3: Querying scenes and nesting under rooms/zones...")

    scenes_raw = query_endpoint('scene')
    scenes = [extract_scene_data(s) for s in scenes_raw]

    print(f"  Found {len(scenes)} scenes")

    # Create lookup maps for rooms and zones by ID
    rooms_by_id = {room['id']: room for room in architecture['rooms']}
    zones_by_id = {zone['id']: zone for zone in architecture['zones']}

    # Nest scenes under their parent room or zone
    for scene in scenes:
        group_rid = scene.get('group_rid')

        if not group_rid:
            print(f"  WARNING: Scene '{scene['name']}' has no group_rid, skipping")
            continue

        # Remove group_rid from final output (it's just for internal mapping)
        scene_data = {
            'id': scene['id'],
            'name': scene['name'],
            'actions': scene['actions']
        }

        # Try to match to room first, then zone
        if group_rid in rooms_by_id:
            rooms_by_id[group_rid]['scenes'].append(scene_data)
            print(f"  Scene '{scene['name']}' → Room '{rooms_by_id[group_rid]['name']}'")
        elif group_rid in zones_by_id:
            zones_by_id[group_rid]['scenes'].append(scene_data)
            print(f"  Scene '{scene['name']}' → Zone '{zones_by_id[group_rid]['name']}'")
        else:
            print(f"  WARNING: Scene '{scene['name']}' group_rid not found in rooms or zones")


def phase_4_button_configuration(architecture: Dict[str, Any]) -> None:
    """
    Phase 4: Export button configurations for switch devices.

    Args:
        architecture: Dictionary from Phase 1-3 (modified in-place)
    """
    print("Phase 4: Exporting switch button configurations...")

    try:
        # Query button and behavior_instance endpoints
        buttons_raw = query_endpoint('button')
        behaviors_raw = query_endpoint('behavior_instance')

        if not buttons_raw or not behaviors_raw:
            print("  WARNING: Could not query button configurations, skipping Phase 4")
            return

        print(f"  Found {len(buttons_raw)} buttons, {len(behaviors_raw)} behavior instances")

        # Build lookup maps
        buttons_by_device_id = {}
        buttons_by_id = {}

        for button in buttons_raw:
            button_id = button.get('id')
            owner_rid = button.get('owner', {}).get('rid')

            if button_id and owner_rid:
                buttons_by_id[button_id] = button

                if owner_rid not in buttons_by_device_id:
                    buttons_by_device_id[owner_rid] = []
                buttons_by_device_id[owner_rid].append(button)

        # Sort buttons by control_id within each device
        for device_id in buttons_by_device_id:
            buttons_by_device_id[device_id].sort(
                key=lambda b: b.get('metadata', {}).get('control_id', 0)
            )

        # Build behavior_instance lookup by device
        behaviors_by_device_id = {}
        for behavior in behaviors_raw:
            device_rid = behavior.get('configuration', {}).get('device', {}).get('rid')
            if device_rid:
                behaviors_by_device_id[device_rid] = behavior

        # Build rooms lookup
        rooms_by_id = {room['id']: room for room in architecture['rooms']}

        # Build scenes lookup (from all rooms and zones)
        scenes_by_id = {}
        for room in architecture['rooms']:
            for scene in room.get('scenes', []):
                scenes_by_id[scene['id']] = scene['name']
        for zone in architecture['zones']:
            for scene in zone.get('scenes', []):
                scenes_by_id[scene['id']] = scene['name']

        # Process each device
        for device in architecture['devices']:
            device_id = device.get('id')

            # Skip non-switch devices
            if not is_switch_device(device):
                continue

            # Look up behavior instance
            behavior_instance = behaviors_by_device_id.get(device_id)
            if not behavior_instance:
                continue  # No button configuration for this switch

            # Extract button configuration
            try:
                button_config = extract_button_configuration(
                    behavior_instance,
                    buttons_by_id,
                    rooms_by_id,
                    scenes_by_id
                )

                device['button_configuration'] = button_config
                button_count = len(button_config.get('buttons', []))
                print(f"  Device '{device['name']}': {button_count} buttons configured")

            except Exception as e:
                print(f"  WARNING: Failed to extract button config for '{device['name']}': {e}")
                continue

    except Exception as e:
        print(f"  WARNING: Phase 4 failed: {e}")
        print("  Continuing with Phases 1-3 data...")


def export_to_yaml(architecture: Dict[str, Any], output_file: str = 'household_architecture.yaml') -> None:
    """
    Export architecture data to YAML file.

    Args:
        architecture: Complete architecture dictionary
        output_file: Output filename (default: household_architecture.yaml)
    """
    print(f"\nExporting to {output_file}...")

    try:
        # Disable anchors/aliases for better human readability in GitOps
        yaml.Dumper.ignore_aliases = lambda *args: True

        with open(output_file, 'w') as f:
            yaml.dump(architecture, f, default_flow_style=False, sort_keys=False, allow_unicode=True)

        print(f"SUCCESS: Architecture exported to {output_file}")

    except Exception as e:
        print(f"ERROR: Failed to write YAML file: {e}")
        sys.exit(1)


def main():
    """Main execution flow."""
    print("=== Hue Architecture Export ===")
    print(f"Bridge IP: {HUE_BRIDGE_IP}\n")

    # Phase 1: Resource Scaffolding
    architecture = phase_1_resource_scaffolding()

    # Phase 2: Service Join (Light Mapping)
    phase_2_service_join(architecture)

    # Phase 3: Scene Recipes
    phase_3_scene_recipes(architecture)

    # Phase 4: Button Configuration Export
    phase_4_button_configuration(architecture)

    # Export to YAML
    export_to_yaml(architecture)

    print("\n=== Export Complete ===")


if __name__ == '__main__':
    main()
