---
name: sync-scenes
description: Sync Philips Hue room scenes from YAML config to bridge with environment setup and safety checks
---

# sync-scenes

Synchronize Philips Hue room scenes and dimmer switch configurations from `rooms_scenes.yaml` to your Hue Bridge. This skill provides environment setup, dry-run preview, and safety confirmations for this destructive operation.

## Overview

This skill wraps `sync_scenes.py` with a safe, interactive workflow that:
- Validates environment configuration (`.env` file)
- Checks required configuration files exist
- Runs dry-run preview before executing
- Requires explicit confirmation before applying changes
- Supports room filtering for targeted updates
- Handles errors with clear recovery suggestions

**⚠️  WARNING:** This operation is DESTRUCTIVE. It deletes all scenes on the bridge that are not defined in your configuration file and recreates them from your YAML config.

## Workflow

### Step 1: Environment Validation

**Check for `.env` file in the project root:**

Use the Bash tool to check if `.env` exists:
```bash
ls -la .env 2>/dev/null || echo "FILE_NOT_FOUND"
```

**If `.env` file does NOT exist:**

1. Inform the user: "`.env` file not found. I'll help you create it with the required Hue Bridge credentials."

2. Read `.env.example` using the Read tool to show them the template

3. Use AskUserQuestion to get `HUE_BRIDGE_IP`:
   ```
   What is your Hue Bridge IP address? (You can find this in the Philips Hue app under Settings → Hue Bridges → [Your Bridge] → Network Settings)
   ```

4. Use AskUserQuestion to get `HUE_USERNAME`:
   ```
   What is your Hue API username? (This is the API key you created. If you don't have one, you can create it by pressing the bridge button and running: curl -X POST http://<bridge-ip>/api -d '{"devicetype":"my_hue_app#device"}')
   ```

5. Create `.env` file using Write tool with content:
   ```
   HUE_BRIDGE_IP=<user_provided_ip>
   HUE_USERNAME=<user_provided_username>
   ```

6. Confirm creation: "✓ Created `.env` file with your Hue Bridge credentials"

**If `.env` file EXISTS:**

1. Read the file to validate it contains both required variables
2. If missing variables, inform the user which are missing and offer to add them
3. If valid, proceed: "✓ Found `.env` file with Hue Bridge credentials"

### Step 2: Configuration File Validation

**Check for required and optional files:**

Use Bash tool to check file existence:
```bash
ls -la rooms_scenes.yaml scene_gallery.yaml 2>/dev/null || true
```

**Required file:**
- `rooms_scenes.yaml` - Scene configuration (MUST exist)

**Optional file:**
- `scene_gallery.yaml` - Scene reference library (recommended but not required)

**If `rooms_scenes.yaml` is missing:**
- Stop and inform user: "❌ `rooms_scenes.yaml` not found. This file is required. See ROOMS_SCENES_GUIDE.md for configuration instructions."
- Exit the workflow

**If files exist:**
- Report status: "✓ Found `rooms_scenes.yaml`"
- If scene_gallery.yaml exists: "✓ Found `scene_gallery.yaml` (scene reference library)"
- If scene_gallery.yaml missing: "ℹ️  `scene_gallery.yaml` not found (optional - scene enrichment will be limited)"

### Step 3: Pre-Execution Questions

**Question 1 - Room Filter:**

Use AskUserQuestion:
```
Do you want to sync all rooms or filter to a specific room?

Options:
- "all" - Sync all rooms defined in rooms_scenes.yaml
- "<room name>" - Sync only the specified room (e.g., "Kitchen Lights", "Office Lights")

💡 Tip: For first-time use, it's recommended to test with a single room first.

Enter your choice:
```

Store the user's response:
- If "all" or empty: No room filter
- If specific room name: Set `--room "<room_name>"` flag

**Question 2 - Verbose Mode:**

Use AskUserQuestion:
```
Enable verbose logging?

Verbose mode shows detailed API calls and debug information. This is helpful for troubleshooting but produces more output.

Options:
- "yes" - Enable verbose logging
- "no" - Standard logging only

Enter your choice (default: no):
```

Store the user's response:
- If "yes": Set `--verbose` flag
- Otherwise: No verbose flag

### Step 4: Dry-Run Execution

**Build and run the dry-run command:**

1. Construct command:
   ```bash
   python sync_scenes.py [--room "X"] [--verbose]
   ```
   - Include `--room "X"` only if user specified a room
   - Include `--verbose` only if user said yes

2. Inform user: "Running dry-run preview (no changes will be made)..."

3. Execute using Bash tool

4. Parse the output to extract:
   - Scenes marked with `[CREATE]` - count these
   - Scenes marked with `[UPDATE]` - count these
   - Scenes marked with `[DELETE]` - count these
   - Scenes marked with `[SKIP]` - count these
   - Switch configurations being updated
   - Any `ERROR` messages
   - Any `WARNING` messages

5. Present a formatted summary:
   ```markdown
   ## 📋 Dry-Run Results

   **Operations that would be performed:**
   - **CREATE**: X scenes would be created
   - **UPDATE**: Y scenes would be updated
   - **DELETE**: Z scenes would be permanently deleted
   - **SKIP**: W scenes would remain unchanged

   **Switch Configurations:**
   - A switches would be configured

   **Warnings:** [list any warnings from output]
   **Errors:** [list any errors - if any, stop before Step 5]
   ```

6. If there are errors in dry-run:
   - Stop the workflow
   - Display errors clearly
   - Suggest fixes based on error type:
     - Connection errors → "Check HUE_BRIDGE_IP and network connectivity"
     - Authentication errors → "Check HUE_USERNAME is valid"
     - Validation errors → "Check rooms_scenes.yaml configuration"

### Step 5: Execution Confirmation

**Only proceed if dry-run was successful (no errors).**

Use AskUserQuestion with this prominent warning:
```
⚠️  ⚠️  ⚠️  WARNING: DESTRUCTIVE OPERATION ⚠️  ⚠️  ⚠️

This operation will PERMANENTLY DELETE the following scenes from your Hue Bridge:
- Z scenes will be DELETED (not in your config)

And will apply these changes:
- X scenes will be CREATED
- Y scenes will be UPDATED
- W scenes will be SKIPPED (unchanged)

Scenes on the bridge that are not defined in rooms_scenes.yaml will be permanently deleted and cannot be recovered.

Do you want to proceed with execution?

Type "yes" to proceed, or anything else to cancel:
```

**Handle response:**
- If user types exactly "yes" (case-insensitive): Proceed to Step 6
- If user types anything else: "Operation cancelled. No changes were made to your Hue Bridge. ✓"
  - Exit workflow gracefully

### Step 6: Execute Mode

**Only if user confirmed "yes" in Step 5:**

1. Inform user: "Executing scene synchronization..."

2. Construct execution command:
   ```bash
   python sync_scenes.py --execute [--room "X"] [--verbose]
   ```
   - Include same flags as dry-run, plus `--execute`

3. Execute using Bash tool

4. Parse output for:
   - Final success/error counts
   - Which rooms succeeded/failed
   - Exit code (0 = success, 1 = errors)

5. Present results:

   **If exit code is 0 (success):**
   ```markdown
   ## ✓ Synchronization Complete

   **Results:**
   - Created: X scenes
   - Updated: Y scenes
   - Deleted: Z scenes
   - Skipped: W scenes (unchanged)

   **Status:** All operations completed successfully!

   💡 **Next Steps:**
   - Run `/hue-summary` to verify your changes
   - Test your scenes in the Philips Hue app
   - Check dimmer switch button assignments
   ```

   **If exit code is 1 (errors):**
   ```markdown
   ## ⚠️  Synchronization Completed with Errors

   **Results:**
   - Created: X scenes
   - Updated: Y scenes
   - Deleted: Z scenes
   - Errors: E operations failed

   **Failed rooms:** [list rooms that failed]

   **Recovery suggestions:**
   - Review error messages above for specific issues
   - Try syncing failed rooms individually with `--room "Room Name"`
   - Check bridge connectivity and credentials
   - Validate rooms_scenes.yaml configuration for failed rooms
   - Run `/hue-summary` to see current state
   ```

6. If user had filtered to a single room, remind them:
   "ℹ️  You synced only '<room name>'. To sync other rooms, run `/sync-scenes` again."

## Usage

Invoke with: `/sync-scenes`

The skill will guide you through an interactive workflow with safety prompts.

### Example Sessions

**First-time user (no .env):**
```
User: /sync-scenes
Skill: .env file not found. I'll help you create it.
       What is your Hue Bridge IP address?
User: 192.168.1.50
Skill: What is your Hue API username?
User: abc123def456...
Skill: ✓ Created .env file
       Do you want to sync all rooms or filter to a specific room?
User: Office Lights
Skill: Enable verbose logging? (yes/no)
User: no
Skill: [runs dry-run]
       📋 Dry-Run Results: Will CREATE 3, UPDATE 1, DELETE 2 scenes
       ⚠️  WARNING: Proceed with execution? (yes/no)
User: yes
Skill: [executes]
       ✓ Synchronization Complete: 3 created, 1 updated, 2 deleted
```

**Experienced user:**
```
User: /sync-scenes
Skill: ✓ Found .env and rooms_scenes.yaml
       Do you want to sync all rooms or filter to a specific room?
User: all
Skill: Enable verbose logging? (yes/no)
User: no
Skill: [runs dry-run]
       📋 Dry-Run Results across 8 rooms
       ⚠️  WARNING: Proceed with execution? (yes/no)
User: yes
Skill: [executes]
       ✓ Synchronization Complete: 24 created, 12 updated, 8 deleted
```

**Dry-run only (user cancels):**
```
User: /sync-scenes
Skill: ✓ Found .env and rooms_scenes.yaml
       Do you want to sync all rooms or filter to a specific room?
User: Living Room
Skill: Enable verbose logging? (yes/no)
User: yes
Skill: [runs dry-run with verbose output]
       📋 Dry-Run Results for Living Room
       ⚠️  WARNING: Proceed with execution? (yes/no)
User: no
Skill: Operation cancelled. No changes were made. ✓
```

## Notes

- **Destructive Operation:** This skill wraps a destructive operation. Always review dry-run results carefully.
- **Room Names:** Room names must match exactly as defined in `rooms_scenes.yaml` (case-sensitive)
- **Safety First:** The skill enforces a mandatory dry-run before any execution
- **Dry-run is Safe:** Running dry-run mode makes no changes to your bridge
- **Configuration Validation:** The script validates your config against the bridge before making changes
- **Room-by-Room Processing:** One room failure doesn't stop processing other rooms
- **Switch Configuration:** If your config includes dimmer switches, button mappings will be updated
- **Scene Gallery:** If present, `scene_gallery.yaml` enriches scene configurations with additional metadata

## Technical Details

### Script Being Executed

**Script:** `sync_scenes.py`
**Location:** Project root directory

**Command-line flags:**
- `--execute` - Apply changes (without this, runs in safe dry-run mode)
- `--room "Room Name"` - Filter to specific room
- `--verbose` / `-v` - Enable DEBUG logging
- `--config path` - Custom config file (default: `rooms_scenes.yaml`)
- `--gallery path` - Custom gallery file (default: `scene_gallery.yaml`)

### Environment Variables

**Required in `.env` file:**
- `HUE_BRIDGE_IP` - IP address of your Philips Hue Bridge
- `HUE_USERNAME` - API key/username for bridge access

### Configuration Files

**Required:**
- `rooms_scenes.yaml` - Scene and switch configuration (see ROOMS_SCENES_GUIDE.md)

**Optional:**
- `scene_gallery.yaml` - Scene reference library for enrichment
- `.env.example` - Template for environment variables

### Output Parsing

The script produces structured logging with these prefixes:
- `[DRY-RUN]` - Indicates dry-run mode
- `[CREATE]` - Scene will be/was created
- `[UPDATE]` - Scene will be/was updated
- `[DELETE]` - Scene will be/was deleted
- `[SKIP]` - Scene is unchanged
- `ERROR` - Operation failed
- `WARNING` - Non-fatal issues (e.g., low battery)

### Exit Codes
- `0` - Success (all operations completed)
- `1` - Errors occurred (some operations failed)

### Safety Features

1. **Mandatory dry-run** - Always runs dry-run first
2. **Explicit confirmation** - User must type "yes" to proceed
3. **Room filtering** - Test changes on single room first
4. **Configuration validation** - Validates against bridge before execution
5. **Per-room error handling** - One failure doesn't stop others
6. **Clear warnings** - Prominent warnings about deletion

### Error Recovery

**Common errors and solutions:**
- **Connection refused:** Check `HUE_BRIDGE_IP` is correct and bridge is reachable
- **Unauthorized:** Check `HUE_USERNAME` is valid (may need to regenerate)
- **File not found:** Ensure `rooms_scenes.yaml` exists in project root
- **Validation errors:** Check YAML syntax and room/device names match bridge
- **Room not found:** Verify room name in config matches bridge exactly

### Related Tools

- `/hue-summary` - View current Hue architecture and verify changes
- `export_hue_architecture.py` - Export current bridge state to YAML
- `export_scene_gallery.py` - Export scene configurations
- `ROOMS_SCENES_GUIDE.md` - Configuration guide for rooms_scenes.yaml
