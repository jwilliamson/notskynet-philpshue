# Hue Configuration-as-Code Export

A GitOps-ready Python script that exports your complete Philips Hue Bridge state to YAML.

## Features

✅ **Read-only** - No modifications to your Hue Bridge  
✅ **Complete export** - Rooms, zones, devices, lights, and scenes  
✅ **Rich metadata** - Includes model IDs, archetypes, software versions  
✅ **Scene recipes** - Captures exact color/brightness for each light in every scene  
✅ **Graceful handling** - Works even when lights are offline  

## Quick Start

```bash
# Install dependencies
pip install -r requirements.txt

# Run export
python export_hue_architecture.py
```

Output: `household_architecture.yaml`

## Configuration

Set these in your `.env` file:

```env
HUE_BRIDGE_IP=192.168.0.118
HUE_USERNAME=your-api-key-here
```

## Output Structure

```yaml
rooms:
  - id: <uuid>
    name: "Kitchen Lights"
    archetype: kitchen
    lights:
      - id: <uuid>
        name: "Kitchen light 1"
        on: true
        brightness: 75.5
        color:
          xy: [0.3, 0.4]
    scenes:
      - id: <uuid>
        name: "Bright"
        actions:
          - target: <light-id>
            action:
              on: {on: true}
              dimming: {brightness: 100.0}
              color_temperature: {mirek: 370}

zones:
  - # Same structure as rooms

devices:
  - id: <uuid>
    name: "Hue bulb 1"
    model_id: "LCA001"
    archetype: "pendant_round"
    software_version: "1.122.8"
```

## Your Current Setup

**Discovered Resources:**
- 7 rooms with 24 lights
- 5 zones with 19 lights
- 33 devices
- 66 scenes

## Implementation Details

### Phase 1: Resource Scaffolding
Queries `/clip/v2/resource/room`, `/zone`, and `/device` endpoints to pull top-level containers.

### Phase 2: Service Join
Maps lights to rooms/zones using the relationships:
- **Rooms**: Room → Device → Light
- **Zones**: Zone → Light (direct)

### Phase 3: Scene Recipes
Queries `/clip/v2/resource/scene` and nests scene configurations under their parent room/zone, including complete action arrays.

## Technical Notes

- Uses Hue CLIP API v2
- Bypasses SSL verification (self-signed cert)
- Suppresses `InsecureRequestWarning`
- Captures last known state for offline lights
- No YAML anchors (fully expanded for human readability)
