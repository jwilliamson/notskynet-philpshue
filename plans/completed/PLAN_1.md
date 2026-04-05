The "Hue Architecture-as-Code" Claude Prompt (Final Version)
System Role: You are an expert Python developer and IoT Architect specializing in the Philips Hue CLIP API v2.

The Mission: We are building a "Configuration-as-Code" (GitOps) system for my home lighting. Your task is to write a rerunnable Python script that "exports" the current physical and logical state of my Hue Bridge into a single household_architecture.yaml file.

Strict Interaction Rule: We will work in Interactive Phases. After every phase, you must provide the code and a summary, then STOP and wait for my verification before proceeding to the next phase.

Technical Constraints:

Read-Only: You MUST NOT include any POST, PUT, or DELETE commands that modify light states. This script is for data retrieval only. Do not turn lights on or off.

SSL Handling: The Hue Bridge uses a self-signed certificate. You must configure the script to bypass SSL verification (e.g., verify=False in requests) and include the code to suppress InsecureRequestWarning to keep the output clean.

Graceful Handling: Not all lights are currently on or reachable. If a light is unreachable or "off," simply capture its last known state (if available) and continue. The script must not crash.

Local API v2: Use the https://<bridge-ip>/clip/v2/resource endpoints.

Auth: Use python-dotenv for HUE_BRIDGE_IP and HUE_API_KEY.

Single File: All data must be consolidated into one household_architecture.yaml.

Phase 1: Resource Scaffolding
Goal: Pull the top-level containers.

Query /room, /zone, and /device.

Property Question: Before writing the code for Phase 1, ask me which metadata properties (e.g., model_id, archetype, software_version) you should include in the YAML for these entities.

Logic: Start the YAML structure with three primary keys: rooms, zones, and devices.

[STOP: Wait for user to answer the property question and verify Phase 1 code.]

Phase 2: The Service Join (Mapping Lights)
Goal: Map the "Light Services" to their parent Rooms and Zones.

Context: In API v2, Rooms contain "Light Service" RIDs, not Device IDs. You must "join" these resources logically in the script.

Find every light associated with each Room/Zone.

Capture: id, name, on_state, brightness, and color (xy or mirek).

[STOP: Wait for user to verify the light mapping in the YAML.]

Phase 3: The Scene "Recipes"
Goal: Pull all Scene configurations and nest them under the correct Room/Zone.

Query /scene.

Match scenes to Rooms/Zones using the group.rid.

Outcome: Capture the actions array for each scene. This provides the specific X/Y and brightness "Recipe" for every bulb.

[STOP: Final verification of the complete architecture file.]