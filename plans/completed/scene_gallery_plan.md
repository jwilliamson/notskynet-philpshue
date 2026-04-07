Outcome: I want a yaml file that contains a list of scenes that have been fetched using the Hue API. This list will be a gallery of scenes I wish to use in the future when I use a devops method to see the scenes on rooms.

Requirements:
 - The python script is rerunnable
 - The python script is not depend on the export_hue_architecture.py script or the household_architecture.yaml file that it produces
 - Scenes should not be duplicated
 - Scenes should contains the information required to capture its settings eg colours and brightness
 - Scenes names should maatch what is in Hue gallery
 - If possible, they should reference the Hue gallery scene they originate from

 Verify by running the new script and summarizing the results back to me