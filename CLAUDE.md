# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is a **read-only** Philips Hue Configuration-as-Code export system with two complementary tools:

1. **Household Architecture Export** - Complete state snapshot with scenes nested by room/zone
2. **Scene Gallery Export** - Deduplicated scene configurations for DevOps workflows

Both tools query a Hue Bridge via the CLIP API v2 and produce YAML files optimized for version control.

**Key Principle**: These tools are strictly read-only. Never add POST/PUT/DELETE operations or modify bridge state.

## Running the Exports

```bash
# Install dependencies
pip install -r requirements.txt

# Run household architecture export (generates household_architecture.yaml)
python export_hue_architecture.py

# Run scene gallery export (generates scene_gallery.yaml)
python export_scene_gallery.py

# Both scripts are standalone and can be run independently
```

## Configuration

Required environment variables in `.env`:
- `HUE_BRIDGE_IP` - Bridge IP address
- `HUE_USERNAME` - API key (note: variable name is USERNAME, not API_KEY)

## Architecture

### Household Architecture Export (`export_hue_architecture.py`)

The export script follows a three-phase pipeline:

#### Phase 1: Resource Scaffolding
Queries top-level containers from `/clip/v2/resource/{room,zone,device}` endpoints and extracts metadata (id, name, archetype, child RIDs).

#### Phase 2: Service Join (Light Mapping)
Maps light services to their parent containers using two different relationship patterns:
- **Rooms**: Room → Device → Light (via `children[rtype=device]` → `services[rtype=light]`)
- **Zones**: Zone → Light (direct via `children[rtype=light]`)

This dual-path mapping is critical because the API v2 structure differs between rooms and zones.

#### Phase 3: Scene Recipes
Queries `/clip/v2/resource/scene` and nests scene configurations (including complete `actions` arrays) under their parent room/zone by matching `group.rid`.

### Scene Gallery Export (`export_scene_gallery.py`)

This standalone script focuses on scene configurations without room/zone context. It implements sophisticated deduplication logic:

#### Query Strategy
- Single API call to `/clip/v2/resource/scene`
- No room/zone/light resolution needed (pure configuration focus)
- Processes all 66+ scene instances into ~10 unique configurations

#### Deduplication Logic (Critical Pattern)

**Step 1: Action-Level Deduplication**
- Within each scene, identify unique action patterns
- If a scene controls 10 lights with identical settings (35% brightness, color xy=[0.56, 0.40]), only keep one action pattern
- **Key insight**: Device count doesn't matter, only the configuration recipe

**Step 2: Scene-Level Deduplication by Name**
- Group all scenes by scene name (e.g., "Rest", "Nightlight")
- Collect all unique action patterns across all instances of that name
- Merge into single entry per scene name

**Step 3: Structure Flattening**
- **Single pattern**: Flatten directly into scene object (no wrapper)
- **Multiple patterns**: Use `variations:[]` array

**Example transformation:**
```
Original API: "Rest" appears in 10 rooms (1-10 lights each)
→ All rooms use: 35% brightness, color xy=[0.56, 0.40]
→ Office room also has: 35% brightness, mirek 370

Result in gallery:
- name: Rest
  variations:
    - brightness: 35.0
      color: {xy: [0.5609999, 0.4042]}
    - brightness: 35.0
      color_temperature: {mirek: 370}
```

#### Configuration Signature Algorithm
1. Extract brightness, color (xy OR mirek), but **exclude `on` field** (always true)
2. Create JSON signature: `json.dumps(action_data, sort_keys=True)`
3. Build scene signature: `MD5(scene_name + sorted_unique_action_signatures)`
4. Deduplicate by signature to identify truly unique scene configurations

#### Critical Implementation Details
- **Why exclude `on`**: All scenes turn lights on; including it adds no discriminatory value
- **Why deduplicate actions before signature**: "Rest with 1 light" and "Rest with 10 lights" have the same configuration if all lights use identical settings
- **Why group by name**: Different rooms may have room-specific variants (e.g., Office "Rest" uses mirek, bedroom uses color xy)
- **Reduction rate**: Typically 84-85% (66 scenes → 10 unique configurations)

## Technical Details

**API Quirks**:
- Uses CLIP API v2 (not v1) - endpoint structure is `/clip/v2/resource/*`
- Bridge uses self-signed SSL cert - script disables verification with `verify=False` and suppresses warnings
- Some lights appear in both rooms AND zones (this is intentional, not a bug)
- Offline/unreachable lights should use last known state from API response

**YAML Output**:
- Anchors/aliases are disabled (`yaml.Dumper.ignore_aliases = lambda *args: True`) for better human readability in version control
- All data is fully expanded - no references

**Light State Extraction**:
- `on.on` → boolean state
- `dimming.brightness` → 0-100 percentage
- Color: Prefer `color.xy` over `color_temperature.mirek` when both exist

## Claude Skill

A `/hue-summary` skill is available at `.claude/skills/hue-summary/` that reads and analyzes both exported YAML files:

**Features:**
- Asks if you want to refresh data (runs both export scripts)
- Overview statistics (room count, device count, lights on/off)
- Scene gallery analysis (unique configurations, deduplication stats)
- Query specific rooms/zones
- Analyze scene patterns and device types

**Usage:** `/hue-summary [optional question]`

**Examples:**
- `/hue-summary` - Full architecture + scene gallery summary
- `/hue-summary what unique scenes do I have?` - Scene gallery analysis
- `/hue-summary what's in the kitchen?` - Room-specific details

## Output Files

### household_architecture.yaml

Complete household snapshot with nested hierarchy:

- **rooms[]** - Physical rooms with nested lights and scenes
- **zones[]** - Logical groupings with nested lights and scenes  
- **devices[]** - Physical hardware (bulbs, switches, bridges) with model_id, archetype, software_version

**Use case:** Understanding current state, room/zone organization, device inventory

**Size:** Large (~10-20KB for typical home), includes all relationships

### scene_gallery.yaml

Deduplicated scene configurations optimized for DevOps workflows:

```yaml
metadata:
  total_scenes: 10          # Unique configurations
  original_scene_count: 66  # Before deduplication
  
scenes:
  # Single-pattern scene (flattened)
  - name: Bright
    brightness: 100.0
    color_temperature:
      mirek: 370
      
  # Multi-pattern scene (variations)
  - name: Rest
    variations:
      - brightness: 35.0
        color: {xy: [0.5609999, 0.4042]}
      - brightness: 35.0
        color_temperature: {mirek: 370}
```

**Structure rules:**

- One entry per scene name (e.g., all "Rest" variants merged)
- No `actions:[]` wrapper or `on:` field (assumed always on)
- Single pattern: flattened directly into scene
- Multiple patterns: stored in `variations:[]` array
- No room/zone/light associations (pure configuration)

**Use case:** Scene recipe book for applying to different rooms, understanding available scene types

**Size:** Small (~2-5KB), focused on unique configurations only

**Key differences:**

| Aspect | household_architecture.yaml | scene_gallery.yaml |
| ------ | ---------------------------- | ------------------- |
| Scenes by room/zone | ✓ Nested under parent | ✗ No room context |
| Scene deduplication | ✗ All instances included | ✓ Merged by name |
| Light names | ✓ Resolved names | ✗ Pattern only |
| Device count | ✓ Shows per-room counts | ✗ Irrelevant |
| Typical scene count | 66+ | ~10 |

Both files represent state at export time, not real-time.
