# rooms_scenes.yaml Configuration Guide

This guide explains how to configure Philips Hue room scenes and dimmer switch button assignments using the `rooms_scenes.yaml` file.

## Overview

The `rooms_scenes.yaml` file allows you to declaratively define:

1. **Room Scenes** - Light configurations (brightness, color, color temperature) that apply to all lights in a room
2. **Switch Button Assignments** - Per-button configuration for dimmer switches with flexible actions:
   - **Timezone-based scene selection** - Automatically activate different scenes based on time of day
   - **Scene cycling** - Cycle through multiple scenes
   - **Dim up/down** - Adjust brightness
   - **Room toggle** - Turn lights on/off
   - **Hold ON button (~1s)** - Button 1 automatically turns off ALL lights in the house (default behavior)

When you run `sync_scenes.py --execute`, the script will:
- **DELETE** all existing scenes in configured rooms
- **CREATE** new scenes from your configuration
- **CONFIGURE** dimmer switch buttons with your specified actions (timezone, scene_cycle, dim_up, dim_down, room_toggle)
- **ENABLE** hold-to-turn-off-all functionality on button 1 (ON button)

⚠️ **WARNING**: This is a **destructive operation**. Always run in dry-run mode first (default) before using `--execute`.

---

## File Structure

```yaml
rooms:
  - room_name: "Exact Room Name"
    scenes:
      - name: "Scene Name"
        brightness: 100.0
        color_temperature:
          mirek: 370
    
    switches:
      - device_name: "Switch Name"
        model_type: "v1"  # or "v2"
        buttons:
          - button_number: 1
            action: "timezone"  # or scene_cycle, dim_up, dim_down, room_toggle
            target: "Room or Zone Name"
            time_slots:
              - start_time:
                  hour: 7
                scene: "Scene Name"
```

---

## Supported Device Types

The system supports multiple Philips Hue switch types with different button counts and capabilities:

| Device Type | Model IDs | Buttons | Supported Actions | Notes |
|-------------|-----------|---------|-------------------|-------|
| `dimmer_v1` (or `v1`) | RWL021 | 4 | **Button 1**: timezone, scene_cycle, room_toggle<br>**Button 2**: dim_up<br>**Button 3**: dim_down<br>**Button 4**: room_toggle, scene_cycle | Classic dimmer switch |
| `dimmer_v2` (or `v2`) | RWL022 | 4 | **Button 1**: timezone, scene_cycle, room_toggle<br>**Button 2**: dim_up<br>**Button 3**: dim_down<br>**Button 4**: timezone, scene_cycle, room_toggle | Newer dimmer with Hue button |
| `wall_switch` | RDM001, RDM002, RDM004 | 2 | **Button 1**: timezone, scene_cycle, room_toggle<br>**Button 2**: timezone, scene_cycle, room_toggle | Wall-mounted switch module |

**Hold Actions**: All device types support configurable long press behavior on buttons that support short_release actions (not dim_up/dim_down).

**Backward Compatibility**: Existing configs using `model_type: "v1"` or `"v2"` will continue to work. The new naming (`dimmer_v1`, `dimmer_v2`, `wall_switch`) is optional but recommended for clarity.

---

## Keyword Reference

### Top-Level Keywords

#### `rooms:` (required)
- **Type**: List of room configurations
- **Description**: The root-level list containing all room definitions
- **Must contain**: At least one room

---

### Room Keywords

#### `room_name:` (required)
- **Type**: String
- **Description**: The exact name of the room as it appears in the Hue Bridge
- **Example**: `"Office Lights"`, `"Living Room Lights"`
- **How to find**: Use the Hue mobile app or check `household_architecture.yaml`

#### `scenes:` (required)
- **Type**: List of scene configurations
- **Description**: Scenes to create for this room
- **Applies to**: All lights in the room automatically (no need to specify light IDs)
- **Must contain**: At least one scene

#### `switches:` (optional)
- **Type**: List of dimmer switch configurations
- **Description**: Dimmer switches in this room with per-button action configuration
- **Supports**: Both v1 (RWL021) and v2 (RWL022) dimmer switches
- **Actions**: Each button can be configured independently with timezone, scene_cycle, dim_up, dim_down, or room_toggle actions

---

### Scene Keywords

#### `name:` (required)
- **Type**: String (1-100 characters)
- **Description**: The scene name that will appear in the Hue app
- **Example**: `"Bright"`, `"Focus"`, `"Nightlight"`

#### `brightness:` (optional)
- **Type**: Float (0.0 to 100.0)
- **Description**: Light brightness as a percentage
- **Example**: `100.0` (full brightness), `56.25` (56% brightness), `10.0` (10% brightness)
- **Note**: At least one of `brightness`, `color`, or `color_temperature` must be specified

#### `color:` (optional)
- **Type**: Object with `x` and `y` coordinates
- **Description**: Color in CIE 1931 color space (XY gamut)
- **Range**: Both x and y must be between 0.0 and 1.0
- **Example**:
  ```yaml
  color:
    x: 0.5609999
    y: 0.4042
  ```
- **Mutually Exclusive**: Cannot be used with `color_temperature`
- **Common Colors**:
  - Red: `x: 0.675, y: 0.322`
  - Orange: `x: 0.561, y: 0.404`
  - Yellow: `x: 0.441, y: 0.517`
  - Green: `x: 0.214, y: 0.709`
  - Blue: `x: 0.167, y: 0.040`

#### `color_temperature:` (optional)
- **Type**: Object with `mirek` value
- **Description**: Color temperature in mirek (micro reciprocal kelvin)
- **Range**: 150 to 500 mirek
- **Example**:
  ```yaml
  color_temperature:
    mirek: 370
  ```
- **Mutually Exclusive**: Cannot be used with `color`
- **Common Temperatures**:
  - Cool white (6500K): `mirek: 153`
  - Neutral white (4000K): `mirek: 250`
  - Warm white (2700K): `mirek: 370`
  - Very warm white (2200K): `mirek: 454`
- **Note**: Lower mirek = cooler/bluer, higher mirek = warmer/yellower

---

### Switch Keywords

#### `device_name:` (required)
- **Type**: String
- **Description**: The exact name of the dimmer switch device as it appears in the Hue Bridge
- **Example**: `"Office Light Switch"`, `"Bedroom Light Switch"`
- **How to find**: Check the Hue app or `household_architecture.yaml` under devices

#### `model_type:` (required)
- **Type**: String
- **Description**: The switch device type
- **Valid values**:
  - `"dimmer_v1"` or `"v1"` - Hue Dimmer Switch v1 (RWL021)
  - `"dimmer_v2"` or `"v2"` - Hue Dimmer Switch v2 (RWL022)
  - `"wall_switch"` - Hue Wall Switch Module (RDM001/RDM002/RDM004)
- **How to find**: Check the Hue app or `household_architecture.yaml` under devices for the model_id
- **Note**: Button layout and supported actions differ by device type (see Supported Device Types table below)

#### `buttons:` (required)
- **Type**: List of button configurations
- **Description**: Per-button action configuration (1-4 buttons)
- **Must contain**: At least one button configuration
- **Constraint**: Each button_number must be unique within the switch

---

### Button Keywords

#### `button_number:` (required)
- **Type**: Integer (1-4)
- **Description**: Physical button number on the switch
- **Valid values**: 1, 2, 3, 4
- **Layout**:
  - v1: 1=On, 2=Dim Up, 3=Dim Down, 4=Off
  - v2: 1=On, 2=Dim Up, 3=Dim Down, 4=Hue

#### `action:` (required)
- **Type**: String
- **Description**: The action type for this button
- **Valid values**:
  - `"timezone"` - Time-based scene selection (requires time_slots and target)
  - `"scene_cycle"` - Cycle through multiple scenes (requires scenes and target)
  - `"dim_up"` - Increase brightness (no additional parameters)
  - `"dim_down"` - Decrease brightness (no additional parameters)
  - `"room_toggle"` - Turn lights on/off (requires target)

#### `target:` (required for timezone, scene_cycle, room_toggle)
- **Type**: String
- **Description**: The room or zone name to control
- **Example**: `"Office Lights"`, `"Kitchen Spotlights"`
- **Note**: Must match exact room or zone name from Hue Bridge
- **Not used for**: dim_up, dim_down actions (they use implicit room context)

#### `time_slots:` (required for timezone action)
- **Type**: List of time slot configurations
- **Description**: Defines which scene activates at each time of day
- **Must contain**: At least one time slot
- **Constraint**: Time slots must be in chronological order (earliest to latest)
- **Behavior**: When button is pressed, activates the scene for the current time of day

#### `scenes:` (required for scene_cycle action)
- **Type**: List of scene names
- **Description**: Scenes to cycle through when button is pressed repeatedly
- **Must contain**: At least one scene name
- **Order**: Scenes cycle in the order specified (Scene 1 → Scene 2 → Scene 3 → Scene 1...)
- **Timeout**: 3-second timeout between presses; after timeout, cycle resets to first scene

#### `hold_action:` (optional)

- **Type**: String
- **Description**: Action to perform when button is held for ~1 second
- **Valid values**:
  - `"home_off"` - Turn off ALL lights in the house (default for button 1)
  - `"room_off"` - Turn off only the target room
  - `"scene_prev"` - Go to previous scene in cycle (if button uses scene_cycle)
  - `"do_nothing"` - Disable hold functionality (default for buttons 2-4)
- **Default behavior**:
  - Button 1: `home_off` (backward compatible with existing configs)
  - All other buttons: `do_nothing`
- **Example**: `hold_action: "room_off"`

---

### Time Slot Keywords

#### `start_time:` (required)
- **Type**: Object with hour and optional minute
- **Description**: The time of day when this scene should activate
- **Format**:
  ```yaml
  start_time:
    hour: 7      # Required: 0-23 (24-hour format)
    minute: 30   # Optional: 0-59 (defaults to 0 if omitted)
  ```
- **Example**: `hour: 7` = 7:00 AM, `hour: 18, minute: 30` = 6:30 PM
- **Note**: Bridge uses 24-hour time format

#### `scene:` (required)
- **Type**: String
- **Description**: The scene name to activate at this time
- **Must exist**: Scene must be defined in the room's scenes list
- **Example**: `"Bright"`, `"Focus"`, `"Nightlight"`

---

## Complete Example

```yaml
rooms:
  # Office with timezone-based scene selection (v1 switch)
  - room_name: "Office Lights"
    scenes:
      - name: "Bright"
        brightness: 100.0
        color_temperature:
          mirek: 233
      
      - name: "Focus"
        brightness: 100.0
        color_temperature:
          mirek: 200
      
      - name: "Relax"
        brightness: 56.25
        color_temperature:
          mirek: 447
      
      - name: "Nightlight"
        brightness: 10.0
        color:
          x: 0.5609999
          y: 0.4042
    
    switches:
      - device_name: "Office Light Switch"
        model_type: "v1"
        buttons:
          - button_number: 1
            action: "timezone"
            target: "Office Lights"
            time_slots:
              - start_time:
                  hour: 7
                scene: "Bright"
              - start_time:
                  hour: 13
                scene: "Focus"
              - start_time:
                  hour: 18
                scene: "Relax"
              - start_time:
                  hour: 21
                scene: "Nightlight"
          - button_number: 2
            action: "dim_up"
          - button_number: 3
            action: "dim_down"
          - button_number: 4
            action: "room_toggle"
            target: "Office Lights"

  # Bedroom with scene cycling (v2 switch)
  - room_name: "Bedroom Lights"
    scenes:
      - name: "Morning"
        brightness: 80.0
        color_temperature:
          mirek: 250
      
      - name: "Evening"
        brightness: 40.0
        color_temperature:
          mirek: 400
      
      - name: "Nightlight"
        brightness: 10.0
        color:
          x: 0.6
          y: 0.4
    
    switches:
      - device_name: "Bedroom Light Switch"
        model_type: "v2"
        buttons:
          - button_number: 1
            action: "room_toggle"
            target: "Bedroom Lights"
          - button_number: 2
            action: "dim_up"
          - button_number: 3
            action: "dim_down"
          - button_number: 4
            action: "scene_cycle"
            target: "Bedroom Lights"
            scenes: ["Morning", "Evening", "Nightlight"]
            hold_action: "scene_prev"  # Hold button 4 to go backwards

  # Kitchen with wall switch (RDM004)
  - room_name: "Kitchen Lights"
    scenes:
      - name: "Bright"
        brightness: 100.0
        color_temperature:
          mirek: 370
      
      - name: "Cooking"
        brightness: 80.0
        color_temperature:
          mirek: 346
      
      - name: "Dining"
        brightness: 40.0
        color_temperature:
          mirek: 447
    
    switches:
      - device_name: "Kitchen Light Switch"
        model_type: "wall_switch"
        buttons:
          - button_number: 1
            action: "timezone"
            target: "Kitchen Lights"
            time_slots:
              - start_time:
                  hour: 6
                scene: "Bright"
              - start_time:
                  hour: 18
                scene: "Dining"
            hold_action: "room_off"  # Hold button 1 to turn off kitchen only
          
          - button_number: 2
            action: "scene_cycle"
            target: "Kitchen Lights"
            scenes: ["Bright", "Cooking", "Dining"]
            hold_action: "do_nothing"

  # Living Room with no switch (scenes only)
  - room_name: "Living Room Lights"
    scenes:
      - name: "Bright"
        brightness: 100.0
        color_temperature:
          mirek: 300
      
      - name: "Dining"
        brightness: 60.0
        color_temperature:
          mirek: 370
```

---

## Usage Workflow

### 1. Prepare Your Configuration

1. Find your room names using the Hue app or by running:
   ```bash
   python export_hue_architecture.py
   # Check household_architecture.yaml for room names
   ```

2. Find your switch device names (if configuring switches):
   ```bash
   # Check household_architecture.yaml under "devices:"
   # Look for entries with model_id: RWL021 (v1) or RWL022 (v2)
   ```

3. Edit `rooms_scenes.yaml` with your desired configuration

### 2. Validate Configuration (Dry-Run)

**Always run in dry-run mode first:**

```bash
# Test all rooms
python sync_scenes.py --verbose

# Test specific room
python sync_scenes.py --room "Office Lights" --verbose
```

This will show you:
- What scenes would be deleted
- What scenes would be created
- What switch configurations would be applied
- Any validation errors

### 3. Execute Changes

**Only after verifying dry-run output:**

```bash
# Sync all rooms
python sync_scenes.py --execute

# Sync specific room
python sync_scenes.py --execute --room "Office Lights"
```

### 4. Verify Results

1. **In Hue App**: Check that scenes appear correctly in the room
2. **Test Switch**: Press the scene button to cycle through scenes
3. **Export State**: Run `python export_hue_architecture.py` to verify

---

## Switch Button Behavior

### Button Actions Overview

Each button can be configured with one of five action types:

1. **timezone** - Automatically activates different scenes based on time of day
2. **scene_cycle** - Cycles through multiple scenes with each press
3. **dim_up** - Increases brightness when held
4. **dim_down** - Decreases brightness when held
5. **room_toggle** - Toggles room lights on/off

**⚠️ Important: Button 1 (ON button) has a default hold action (~1 second) that turns off ALL lights in the house.** This provides an emergency "all off" capability.

### v1 Dimmer (RWL021)

```
Physical Switch:
┌──────────────────┐
│  [ON]  Button 1  │ ← Configure with any action (commonly timezone or scene_cycle)
├──────────────────┤
│  [+]   Button 2  │ ← Configure with dim_up action
├──────────────────┤
│  [-]   Button 3  │ ← Configure with dim_down action
├──────────────────┤
│  [OFF] Button 4  │ ← Configure with room_toggle action
└──────────────────┘
```

**Typical v1 Configuration:**
- Button 1: timezone or scene_cycle (main scene control)
- Button 2: dim_up
- Button 3: dim_down
- Button 4: room_toggle

### v2 Dimmer (RWL022)

```
Physical Switch:
┌──────────────────┐
│  [ON]  Button 1  │ ← Configure with room_toggle action
├──────────────────┤
│  [+]   Button 2  │ ← Configure with dim_up action
├──────────────────┤
│  [-]   Button 3  │ ← Configure with dim_down action
├──────────────────┤
│  [●]   Button 4  │ ← Configure with timezone or scene_cycle action
│ (Hue logo)       │
└──────────────────┘
```

**Typical v2 Configuration:**
- Button 1: room_toggle
- Button 2: dim_up
- Button 3: dim_down
- Button 4: timezone or scene_cycle (main scene control)

### Action Behavior Details

**Timezone Action (typically on button 1):**
- **Short press**: Activates scene for current time of day
- **Hold (~1s)**: Turns off ALL lights in the house (button 1 only)
- Example: At 8am → "Bright", at 7pm → "Relax", at 10pm → "Nightlight"
- Bridge automatically determines which scene to activate based on current time

**Scene Cycle Action (typically on button 1 for v1 or button 4 for v2):**
- **Short press**: Cycle to next scene (Scene 1 → Scene 2 → Scene 3 → Scene 1...)
- **Hold (~1s)**: If on button 1, turns off ALL lights in the house; otherwise does nothing
- 3-second timeout: If you don't press again within 3 seconds, cycle resets to first scene
- Scenes cycle in the order specified in the `scenes:` list

**Dim Up/Down Actions (typically on buttons 2 and 3):**
- **Hold button**: Continuously adjust brightness
- **Release**: Stop adjustment
- Works on all lights in the switch's room

**Room Toggle Action (typically on button 4 for v1 or button 1 for v2):**
- **Short press**: Turn lights on (to last state) or off
- **Hold (~1s)**: If on button 1, turns off ALL lights in the house; otherwise does nothing
- Can target any room or zone, not just the switch's room

---

## Tips and Best Practices

### Scene Design

1. **Consistent Naming**: Use consistent scene names across rooms (e.g., "Bright", "Relax", "Nightlight")
2. **Scene Order**: List scenes in chronological order for timezone configurations, or brightness order for scene_cycle
3. **Color vs Temperature**: Use `color` for accent/mood lighting, `color_temperature` for functional lighting
4. **Scene Count**: Works best with 2-6 scenes per room for scene_cycle (too many = harder to remember order)

### Switch Configuration

1. **v1 vs v2**: Check your switch model before configuring (look for Hue logo on bottom button = v2)
2. **Multiple Switches**: You can configure multiple switches per room with different button assignments
3. **Action Selection**:
   - Use **timezone** for "set and forget" automation (scenes change automatically with time of day)
   - Use **scene_cycle** for manual control (press button to cycle through scenes)
   - Combine both: timezone on one button, scene_cycle on another for maximum flexibility

### Timezone Configuration

1. **Time Slot Coverage**: Define time slots for your typical daily routine (morning, afternoon, evening, night)
2. **Chronological Order**: Time slots must be in order (7am, 1pm, 6pm, etc.) - validation will fail otherwise
3. **24-Hour Time**: Use 24-hour format (hour: 18 = 6:00 PM, hour: 23 = 11:00 PM)
4. **Minute Precision**: Omit `minute` if you want on-the-hour activation (defaults to 0)
5. **Scene Selection Logic**: Bridge activates the scene for the most recent time slot that has passed
   - At 8:00 AM → activates 7:00 AM slot scene
   - At 7:30 PM → activates 6:00 PM slot scene
   - At 2:00 AM → activates last slot from previous day (e.g., 11:00 PM scene)

### Target Selection

1. **Room vs Zone**: Timezone and scene_cycle can target rooms OR zones
   - Room: All lights in the physical room
   - Zone: Subset of lights (e.g., "Kitchen Spotlights" within "Kitchen Lights" room)
2. **Cross-Room Control**: A switch in one room can control scenes in a different room or zone
3. **Consistent Targeting**: Most users target the switch's own room, but cross-room control is supported

### Safety

1. **Always Dry-Run First**: Never skip the dry-run step
2. **Backup Current State**: Run `export_hue_architecture.py` before executing changes
3. **Test Single Room**: Use `--room` flag to test one room before syncing all
4. **Version Control**: Commit your `rooms_scenes.yaml` to git before making changes

### Troubleshooting

**"Room not found" or "Target not found"**
- Check exact spelling and capitalization in `room_name` or `target`
- Verify room/zone exists in Hue app or `household_architecture.yaml`
- For zones: check that zone name matches exactly (zones are listed separately from rooms)

**"Switch not found"**
- Check exact spelling of `device_name`
- Verify switch is paired with bridge in Hue app
- Check `household_architecture.yaml` under `devices:` for exact device name

**"Validation error: Scene 'X' not found in room scenes"**
- Ensure scene name in `time_slots` or `scenes` list matches a scene defined in the room's `scenes:` section
- Check for typos or capitalization differences
- Scene names are case-sensitive

**"Validation error: time_slots must be in chronological order"**
- Sort time slots by hour (earliest to latest)
- Example: 7am, 1pm, 6pm, 11pm (not 7am, 11pm, 1pm, 6pm)
- If using minutes, sort by hour first, then minute

**"Validation error: button_number values must be unique"**
- Each button (1-4) can only be configured once per switch
- Remove duplicate button_number entries

**"Validation error: timezone action requires time_slots"**
- Add `time_slots:` list with at least one time slot
- Ensure each time slot has `start_time` and `scene`

**"Validation error: scene_cycle action requires scenes"**
- Add `scenes:` list with at least one scene name
- Ensure scene names exist in room's scenes list

**Configuration format errors**
- Old format (`dimmer_switches_v1`, `dimmer_switches_v2`) is no longer supported
- Migrate to new `switches:` format (see Migration Guide below)

**Timezone scenes not activating correctly**
- Verify bridge time is correct (check Hue app settings)
- Test by pressing the timezone button - it should activate the scene for current time
- Check that time slots cover your entire day (gaps will use the most recent previous slot)

**Scene cycle not working**
- Press the configured button multiple times to cycle through scenes
- Wait 3 seconds between presses to see cycle timeout behavior (resets to first scene)
- Verify scenes were created successfully in Hue app

**Dim buttons not working**
- Ensure action is `dim_up` or `dim_down` (no target needed)
- Hold button down to see brightness change
- Check that lights in the room support dimming

---

## Migration Guide: Old to New Configuration Format

The configuration format changed to support per-button actions. The old `dimmer_switches_v1` and `dimmer_switches_v2` keywords are **no longer supported**.

### Old Format (Deprecated)

```yaml
rooms:
  - room_name: "Office Lights"
    scenes:
      - name: "Bright"
        brightness: 100.0
        color_temperature:
          mirek: 233
      - name: "Focus"
        brightness: 100.0
        color_temperature:
          mirek: 200
    
    dimmer_switches_v1:
      - device_name: "Office Light Switch"
        assign_scenes_to_on_button: true
```

### New Format (Current)

```yaml
rooms:
  - room_name: "Office Lights"
    scenes:
      - name: "Bright"
        brightness: 100.0
        color_temperature:
          mirek: 233
      - name: "Focus"
        brightness: 100.0
        color_temperature:
          mirek: 200
    
    switches:
      - device_name: "Office Light Switch"
        model_type: "v1"
        buttons:
          - button_number: 1
            action: "scene_cycle"
            target: "Office Lights"
            scenes: ["Bright", "Focus"]  # List all room scenes in order
          - button_number: 2
            action: "dim_up"
          - button_number: 3
            action: "dim_down"
          - button_number: 4
            action: "room_toggle"
            target: "Office Lights"
```

### Migration Rules

**v1 Switch (RWL021) with `assign_scenes_to_on_button: true`:**

Old behavior: Button 1 cycles through all room scenes

New equivalent:
```yaml
switches:
  - device_name: "Switch Name"
    model_type: "v1"
    buttons:
      - button_number: 1
        action: "scene_cycle"
        target: "Room Name"
        scenes: ["Scene1", "Scene2", "Scene3"]  # All room scenes
      - button_number: 2
        action: "dim_up"
      - button_number: 3
        action: "dim_down"
      - button_number: 4
        action: "room_toggle"
        target: "Room Name"
```

**v2 Switch (RWL022) with `assign_scenes_to_on_button: true`:**

Old behavior: Button 4 (Hue) cycles through all room scenes

New equivalent:
```yaml
switches:
  - device_name: "Switch Name"
    model_type: "v2"
    buttons:
      - button_number: 1
        action: "room_toggle"
        target: "Room Name"
      - button_number: 2
        action: "dim_up"
      - button_number: 3
        action: "dim_down"
      - button_number: 4
        action: "scene_cycle"
        target: "Room Name"
        scenes: ["Scene1", "Scene2", "Scene3"]  # All room scenes
```

### Upgrade Benefits

The new format enables:

1. **Timezone automation**: Set scenes to change automatically throughout the day
2. **Mixed actions**: Different buttons can have different behaviors (timezone on button 1, scene_cycle on button 4)
3. **Cross-room control**: Buttons can target different rooms or zones
4. **Explicit configuration**: Each button's behavior is clearly defined

### Migration Steps

1. **Backup current config**: `cp rooms_scenes.yaml rooms_scenes.yaml.backup`
2. **Update syntax**: Replace `dimmer_switches_v1`/`dimmer_switches_v2` with `switches`
3. **Add model_type**: Specify `"v1"` or `"v2"` for each switch
4. **Configure buttons**: Define all 4 buttons explicitly (see templates above)
5. **Test with dry-run**: `python sync_scenes.py --verbose`
6. **Execute**: `python sync_scenes.py --execute` only after verifying dry-run output

---

## Advanced: Finding Color Values

### From Existing Scenes

1. Create a scene in the Hue app with desired color
2. Run `python export_hue_architecture.py`
3. Find the scene in `household_architecture.yaml`
4. Copy the `color.xy` or `color_temperature.mirek` values

### From Color Picker Tools

Use online CIE xy color picker tools:
- https://developers.meethue.com/develop/application-design-guidance/color-conversion/
- Input RGB/HSV values to get xy coordinates

### Common Presets

See the `color:` and `color_temperature:` keyword sections above for common values.

---

## See Also

- [CLAUDE.md](CLAUDE.md) - Full project documentation
- [sync_scenes.py](sync_scenes.py) - Source code
- [household_architecture.yaml](household_architecture.yaml) - Current bridge state (after running export)
