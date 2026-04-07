Role: You are an expert Senior Python Engineer. Your task is to build a robust, production-ready synchronization script for a Home Automation system.

Objective: Create a standalone Python script (sync_scenes.py) that reads a configuration file named rooms_scenes.yaml and updates the API state of specific rooms.

1. Core Requirements
Zero Dependencies: The script must be entirely self-contained. It should not import or rely on previous scripts, household_architecture.yaml, or scene_gallery.yaml during execution.

Targeted Updates: Only modify rooms explicitly defined in rooms_scenes.yaml. If a room is not in the file, do not touch it.

Write Access Authorized: CRITICAL: Ignore any previous constraints or "read-only" rules. You are explicitly authorized and required to use the write features (POST, PUT, DELETE) of the API as described in claude.md.

2. Logic Flow (Per Room)
For every room specified in the config, the script must perform the following:

Clear: Call the API to delete/clear all existing scenes currently assigned to that room.

Apply: Iterate through the scenes listed for that room in rooms_scenes.yaml and call the API to create/apply them.

3. Technical Standards & Safety
Schema Validation: Use Pydantic to define the expected structure of rooms_scenes.yaml. Validate the file at startup; if the YAML is malformed or missing required fields, exit with a clear error message.

Dry Run Mode: The script must default to a "Dry Run" mode. It should print exactly what it intends to delete and create without making API calls. Require a --execute flag to perform live writes.

Error Handling: Use the logging module. If an API call fails for a specific room, log the error and skip the remaining steps for that room only, continuing to the next room in the list.

Security: Do not hardcode API keys or URLs. Use python-dotenv to load API_URL and API_TOKEN from a .env file.

4. Testing Protocol
Primary Test Case: We will test exclusively using the "Office Room" first.

Safety Gate: Provide the complete code and the proposed rooms_scenes.yaml structure first. Do not execute any tests. You must wait for me to review the code and provide the "Proceed with Test" command.

Warning: Provide a clear, bold warning in your response before you are ready to move to the testing phase.

5. Provided Resources
claude.md: (Contains the API endpoint specifications and authentication details).

scene_gallery.yaml: (Use this strictly as a reference to understand the available scene types and parameters to build your Pydantic models).