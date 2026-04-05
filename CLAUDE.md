# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is a **read-only** Philips Hue Configuration-as-Code export system. It queries a Hue Bridge via the CLIP API v2 and exports the complete household state (rooms, zones, devices, lights, scenes) to `household_architecture.yaml` for GitOps workflows.

**Key Principle**: This tool is strictly read-only. Never add POST/PUT/DELETE operations or modify bridge state.

## Running the Export

```bash
# Install dependencies
pip install -r requirements.txt

# Run export (generates household_architecture.yaml)
python export_hue_architecture.py
```

## Configuration

Required environment variables in `.env`:
- `HUE_BRIDGE_IP` - Bridge IP address
- `HUE_USERNAME` - API key (note: variable name is USERNAME, not API_KEY)

## Architecture

The export script follows a three-phase pipeline:

### Phase 1: Resource Scaffolding
Queries top-level containers from `/clip/v2/resource/{room,zone,device}` endpoints and extracts metadata (id, name, archetype, child RIDs).

### Phase 2: Service Join (Light Mapping)
Maps light services to their parent containers using two different relationship patterns:
- **Rooms**: Room → Device → Light (via `children[rtype=device]` → `services[rtype=light]`)
- **Zones**: Zone → Light (direct via `children[rtype=light]`)

This dual-path mapping is critical because the API v2 structure differs between rooms and zones.

### Phase 3: Scene Recipes
Queries `/clip/v2/resource/scene` and nests scene configurations (including complete `actions` arrays) under their parent room/zone by matching `group.rid`.

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

A `/hue-summary` skill is available at `.claude/skills/hue-summary/` that reads and analyzes the exported YAML file. Use it to:
- Get overview statistics (room count, device count, lights on/off)
- Query specific rooms/zones
- Analyze scenes and device types

Usage: `/hue-summary [optional question]`

## Output File

`household_architecture.yaml` contains:
- **rooms[]** - Physical rooms with nested lights and scenes
- **zones[]** - Logical groupings with nested lights and scenes
- **devices[]** - Physical hardware (bulbs, switches, bridges) with model_id, archetype, software_version

This file represents the state at export time, not real-time.
