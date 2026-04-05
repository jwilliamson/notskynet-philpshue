---
name: hue-summary
description: Analyze and summarize your Philips Hue architecture from household_architecture.yaml and scene_gallery.yaml
---

# hue-summary

Analyze and summarize your Philips Hue smart home architecture from the exported YAML configuration files. Provides insights into rooms, zones, devices, lights, scenes, and scene gallery.

## Workflow

### Step 1: Offer to Refresh Data

**Before analyzing, ask the user if they want to refresh the data:**

Use the AskUserQuestion tool with this question:
"Would you like to run the export scripts to refresh the Hue data before analyzing? This will update both household_architecture.yaml and scene_gallery.yaml with the latest state from your bridge."

**If user says yes:**
1. Run: `python export_hue_architecture.py`
2. Run: `python export_scene_gallery.py`
3. Wait for both to complete before proceeding

**If user says no or skip:**
Proceed directly to reading the existing files

### Step 2: Read the Configuration Files

Read both YAML files in the current working directory using the Read tool:
1. `household_architecture.yaml` - Full household architecture
2. `scene_gallery.yaml` - Deduplicated scene gallery

### Step 3: Parse and Analyze Data

Extract key information from both YAML files:

#### From household_architecture.yaml:

**Top-level collections:**
- `rooms` - Physical rooms with lights and scenes
- `zones` - Logical groupings of lights
- `devices` - Physical Hue devices (bulbs, switches, bridges)

**For each room/zone:**
- `id` - Unique identifier
- `name` - Friendly name
- `archetype` - Room/zone type (kitchen, bedroom, hallway, etc.)
- `lights[]` - Array of light states
- `scenes[]` - Array of scene configurations (nested by room)

**For each light:**
- `id` - Light service ID
- `name` - Friendly name
- `on` - Boolean state (true/false)
- `brightness` - 0-100 percentage
- `color` - Either `xy` coordinates or `mirek` color temperature

**For each device:**
- `model_id` - Device model (e.g., LCA001, LCG002, RWL022)
- `archetype` - Device type
- `software_version` - Firmware version

**For each scene:**
- `name` - Scene name
- `actions[]` - Array of light actions with specific states

#### From scene_gallery.yaml:

**Metadata:**
- `export_timestamp` - When gallery was exported
- `total_scenes` - Number of unique scene configurations
- `original_scene_count` - Total scenes before deduplication
- `note` - Information about deduplication

**For each unique scene:**
- `id` - Scene UUID
- `name` - Scene name (e.g., "Rest", "Bright", "Nightlight")
- `actions[]` - Light action patterns (no room/light associations)
  - `on` - Boolean power state
  - `brightness` - 0-100 percentage
  - `color.xy` - XY color coordinates OR
  - `color_temperature.mirek` - Mirek color temperature

### Step 4: Calculate Statistics

Compute summary metrics from both files:

#### From household_architecture.yaml:

**Overview:**
- Total rooms, zones, devices
- Total lights (deduplicate across rooms/zones)
- Total scenes (nested in rooms/zones)
- Lights currently on vs off

**Device breakdown:**
- Count by model type
- Identify bulbs vs switches vs infrastructure
- Check for software version consistency

**Room/Zone analysis:**
- Average lights per room/zone
- Average scenes per room/zone
- Identify largest/smallest spaces

**Scene analysis (contextual):**
- Most common scene names across rooms
- Average actions per scene
- Identify rooms with most/least scenes

#### From scene_gallery.yaml:

**Scene Gallery Statistics:**
- Total unique scene configurations (metadata.total_scenes)
- Original scene count before deduplication (metadata.original_scene_count)
- Deduplication ratio (e.g., "66 → 43 scenes, 35% reduction")
- Unique scene names (list all)
- Scene configuration patterns:
  - Number of actions per unique scene
  - Color vs color temperature usage
  - Brightness ranges (min/max/avg)
  - Most complex scene (most actions)

### Step 5: Format Summary Output

Present a well-structured markdown summary:

```markdown
# 🏠 Hue Architecture Summary

## 📊 Overview
- **Rooms:** X
- **Zones:** Y
- **Devices:** Z
- **Lights:** A (B on, C off)
- **Scenes:** D (across all rooms)

## 🏠 Rooms
| Room Name | Type | Lights | Scenes | State |
|-----------|------|--------|--------|-------|
| Living Room | living_room | 10 | 5 | 10 on |
| Kitchen | kitchen | 6 | 7 | 0 on |
...

## 🔲 Zones
| Zone Name | Type | Lights | Scenes |
|-----------|------|--------|--------|
| Kitchen Spotlights | kitchen | 6 | 4 |
...

## 💡 Devices by Type

**Bulbs/Lights (X devices):**
- LCA001 (pendant round): Y devices
- LCG002 (spotlights): Z devices
...

**Switches/Controls (X devices):**
- RWL022 (dimmer switch): Y devices
- RDM004 (wall module): Z devices

**Infrastructure:**
- Hue Bridge (BSB002): version X.X.X

## 🎨 Scene Gallery (Unique Configurations)

**Summary:**
- **Unique Scenes:** X (deduplicated from Y)
- **Reduction:** Z% duplicates removed
- **Export Time:** [timestamp]

**Available Scene Names:**
- Bright
- Concentrate
- Dimmed
- Energise
- Nightlight
- Read
- Relax
- Rest
- Super nightlight
- [etc...]

**Scene Complexity:**
- Most complex: "[Scene Name]" (X actions)
- Simplest: "[Scene Name]" (Y actions)
- Average actions per scene: Z

**Color Patterns:**
- XY color scenes: X
- Mirek temperature scenes: Y
- Mixed scenes: Z

## 🎯 Scene Insights (Contextual)
- Most common scenes: Relax (12 rooms), Bright (11 rooms), Nightlight (10 rooms)
- Rooms with most scenes: Living Room (5), Kitchen (7)
- Average actions per scene: X

## ⚠️ Notable Observations
- All lights in Bedroom are currently off
- Living Room has the most lights (10)
- Software versions: [note any inconsistencies]
- Scene deduplication shows [X]% of scenes are duplicated across rooms
- [Any other interesting patterns]
```

**Formatting guidelines:**
- Use tables for structured multi-column data
- Use emojis for section headers
- Bold important numbers
- Group similar items together
- Highlight any anomalies or interesting patterns

### Step 6: Answer Follow-up Questions

If the user has specific questions, filter and present relevant data:

**Room/Zone queries:**
- "What's in the kitchen?" → Show kitchen room + kitchen zones
- "Which room has most lights?" → Sort and highlight

**Light queries:**
- "Which lights are on?" → Filter lights by state
- "What's the brightest setting?" → Analyze scene brightness values

**Scene queries:**
- "What scenes are in the bedroom?" → List bedroom scenes from household_architecture.yaml
- "What's the Nightlight scene like?" → Show Nightlight from scene gallery with action patterns
- "Show me all unique scenes" → List from scene_gallery.yaml
- "What scene has the most actions?" → Analyze scene gallery complexity

**Scene Gallery queries:**
- "What are the unique scene configurations?" → List from scene_gallery.yaml
- "How many scenes were deduplicated?" → Show metadata stats
- "What's the Rest scene configuration?" → Show specific scene actions

**Device queries:**
- "How many bulbs do I have?" → Count light devices
- "What switches are installed?" → List switch models

## Usage

Invoke with: `/hue-summary [optional question]`

Examples:
- `/hue-summary` - Full architecture summary with scene gallery
- `/hue-summary what's in the living room?` - Focus on living room
- `/hue-summary how many lights are on?` - Light state summary
- `/hue-summary show me all scenes` - Scene breakdown from both files
- `/hue-summary what unique scenes do I have?` - Scene gallery analysis
- `/hue-summary what's the Rest scene configuration?` - Specific scene details

## Notes

- This skill is READ-ONLY - it analyzes the exported YAML configurations
- Data represents the state at the time of export, not real-time
- File locations (both in current directory):
  - `household_architecture.yaml` - Full household state with nested scenes
  - `scene_gallery.yaml` - Deduplicated scene configurations
- The same light may appear in both a room and multiple zones
- Scenes in household_architecture.yaml are nested by room/zone
- Scenes in scene_gallery.yaml are deduplicated configurations without room context
- Scene gallery shows pure "recipes" - what settings define each scene type
- Scripts to regenerate:
  - `python export_hue_architecture.py` - Full household export
  - `python export_scene_gallery.py` - Scene gallery export

## Technical Details

**household_architecture.yaml:**
- Generated by: `export_hue_architecture.py`
- Contains: Rooms, zones, devices, lights, scenes (nested)
- Purpose: Complete household state snapshot

**scene_gallery.yaml:**
- Generated by: `export_scene_gallery.py`
- Contains: Deduplicated scene configurations (action patterns only)
- Purpose: Scene "recipe book" for DevOps workflows

**Both use:**
- API: Philips Hue CLIP API v2
- Format: YAML (PyYAML)
- Authentication: Via `.env` file
