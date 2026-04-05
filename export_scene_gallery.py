#!/usr/bin/env python3
"""
Hue Scene Gallery Export Script

Exports deduplicated Philips Hue scenes to a YAML gallery file.
This is a READ-ONLY script that queries the Hue CLIP API v2.

Focuses on scene configurations (brightness, colors) rather than
room/zone assignments. Deduplicates scenes with identical settings.
"""

import os
import sys
import yaml
import requests
import urllib3
import json
import hashlib
from typing import Dict, List, Any
from datetime import datetime, timezone
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
        endpoint: API endpoint path (e.g., 'scene')

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


def create_action_signature(action: Dict[str, Any]) -> str:
    """
    Create a hashable signature for a light action configuration.

    Args:
        action: Action dictionary with 'action' key containing light settings

    Returns:
        JSON string representation of normalized action
    """
    action_data = action['action']

    # Build normalized action dict (excluding 'on' since all scenes turn lights on)
    sig = {}

    if 'dimming' in action_data:
        sig['brightness'] = round(action_data['dimming']['brightness'], 2)

    if 'color' in action_data:
        sig['color_xy'] = [
            round(action_data['color']['xy']['x'], 4),
            round(action_data['color']['xy']['y'], 4)
        ]
    elif 'color_temperature' in action_data:
        sig['color_mirek'] = action_data['color_temperature']['mirek']

    # Sort keys for consistent hashing
    return json.dumps(sig, sort_keys=True)


def create_scene_signature(scene: Dict[str, Any]) -> str:
    """
    Create unique signature for scene based on name + unique action configs.

    Args:
        scene: Scene resource dictionary

    Returns:
        MD5 hash of scene name + sorted unique action signatures
    """
    name = scene['metadata']['name']

    # Collect UNIQUE action signatures (deduplicate identical actions)
    seen_sigs = set()
    unique_action_sigs = []

    for action in scene.get('actions', []):
        sig = create_action_signature(action)
        if sig not in seen_sigs:
            seen_sigs.add(sig)
            unique_action_sigs.append(sig)

    unique_action_sigs.sort()

    # Combine name + unique actions into single signature
    combined = f"{name}::{':'.join(unique_action_sigs)}"
    return hashlib.md5(combined.encode()).hexdigest()


def process_scene(scene: Dict[str, Any]) -> Dict[str, Any]:
    """
    Extract scene configuration without room/light names.
    Deduplicates identical actions within the scene.
    Flattens single-action scenes, uses 'variations' for multi-action.

    Args:
        scene: Scene resource dictionary

    Returns:
        Dictionary with scene id, name, and flattened settings
    """
    scene_data = {
        'id': scene['id'],
        'name': scene['metadata']['name']
    }

    # Track unique actions to avoid duplicates within the same scene
    seen_actions = set()
    unique_actions = []

    # Process each light action
    for action in scene.get('actions', []):
        light_action = action['action']

        action_data = {}

        # Extract brightness
        if 'dimming' in light_action:
            action_data['brightness'] = light_action['dimming']['brightness']

        # Extract color (xy coordinates or mirek temperature)
        if 'color' in light_action:
            action_data['color'] = {
                'xy': [
                    light_action['color']['xy']['x'],
                    light_action['color']['xy']['y']
                ]
            }
        elif 'color_temperature' in light_action:
            action_data['color_temperature'] = {
                'mirek': light_action['color_temperature']['mirek']
            }

        # Deduplicate: only add if this action pattern hasn't been seen
        action_signature = json.dumps(action_data, sort_keys=True)
        if action_signature not in seen_actions:
            seen_actions.add(action_signature)
            unique_actions.append(action_data)

    # Flatten structure based on number of unique actions
    if len(unique_actions) == 1:
        # Single action: flatten directly into scene
        scene_data.update(unique_actions[0])
    elif len(unique_actions) > 1:
        # Multiple actions: use variations array
        scene_data['variations'] = unique_actions

    return scene_data


def deduplicate_scenes(scenes: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Deduplicate scenes by scene name, merging all unique action patterns.

    Args:
        scenes: List of scene resource dictionaries

    Returns:
        List of unique scene configurations, one per scene name
    """
    # Group scenes by name and collect unique action patterns
    scenes_by_name = {}

    for scene in scenes:
        try:
            name = scene['metadata']['name']

            if name not in scenes_by_name:
                scenes_by_name[name] = {
                    'id': scene['id'],
                    'name': name,
                    'unique_actions': {},  # signature -> action_data
                }

            # Collect unique actions from this scene instance
            for action in scene.get('actions', []):
                light_action = action['action']

                action_data = {}

                # Extract brightness
                if 'dimming' in light_action:
                    action_data['brightness'] = light_action['dimming']['brightness']

                # Extract color
                if 'color' in light_action:
                    action_data['color'] = {
                        'xy': [
                            light_action['color']['xy']['x'],
                            light_action['color']['xy']['y']
                        ]
                    }
                elif 'color_temperature' in light_action:
                    action_data['color_temperature'] = {
                        'mirek': light_action['color_temperature']['mirek']
                    }

                # Store by signature to deduplicate
                sig = json.dumps(action_data, sort_keys=True)
                scenes_by_name[name]['unique_actions'][sig] = action_data

        except (KeyError, TypeError) as e:
            print(f"WARNING: Skipping malformed scene {scene.get('id', 'unknown')}: {e}")
            continue

    # Build final scene list
    unique_scenes = []
    for name, scene_info in scenes_by_name.items():
        scene_data = {
            'id': scene_info['id'],
            'name': name
        }

        unique_actions = list(scene_info['unique_actions'].values())

        if len(unique_actions) == 1:
            # Single action: flatten directly
            scene_data.update(unique_actions[0])
        elif len(unique_actions) > 1:
            # Multiple actions: use variations
            scene_data['variations'] = unique_actions

        unique_scenes.append(scene_data)

    # Sort by name for consistent output
    unique_scenes.sort(key=lambda s: s['name'])

    return unique_scenes


def main():
    """Main execution flow."""
    print("Querying Hue Bridge for scenes...")

    # 1. Query scenes only (no need for rooms/zones/lights)
    scenes = query_endpoint('scene')
    original_count = len(scenes)

    if original_count == 0:
        print("ERROR: No scenes found or API query failed")
        sys.exit(1)

    print(f"Found {original_count} scenes")

    # 2. Deduplicate scenes by configuration
    print("Deduplicating scenes by configuration...")
    unique_scenes = deduplicate_scenes(scenes)

    # 3. Build output structure
    output = {
        'metadata': {
            'export_timestamp': datetime.now(timezone.utc).isoformat(),
            'bridge_ip': HUE_BRIDGE_IP,
            'total_scenes': len(unique_scenes),
            'original_scene_count': original_count,
            'note': 'Deduplicated by scene configuration. Gallery scene origin cannot be determined from Hue API v2.'
        },
        'scenes': unique_scenes
    }

    # 4. Write YAML (disable aliases like existing script)
    yaml.Dumper.ignore_aliases = lambda *args: True
    output_file = 'scene_gallery.yaml'

    with open(output_file, 'w') as f:
        yaml.dump(output, f, default_flow_style=False, sort_keys=False)

    # 5. Print summary
    print(f"\n✓ Exported {len(unique_scenes)} unique scenes to {output_file}")
    print(f"✓ Deduplicated from {original_count} total scenes")
    print(f"✓ Bridge: {HUE_BRIDGE_IP}")

    # Show scene name distribution
    scene_names = {}
    for scene in unique_scenes:
        name = scene['name']
        scene_names[name] = scene_names.get(name, 0) + 1

    print(f"\nUnique scene configurations:")
    for name in sorted(scene_names.keys()):
        print(f"  - {name}")


if __name__ == '__main__':
    main()
