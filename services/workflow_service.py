import os
import json
import copy
import aiofiles
import base64
import requests
from ..entities.workflow import Workflow
from ..config import config
from .comfyui_service import comfyui_service


class WorkflowService:
    """
    Manages workflows by loading them from JSON files, saving, deleting, and executing them.
    Also handles updating workflows and caching certain nodes.
    """

    def __init__(self):
        """
        Initializes the WorkflowService by:
        - Creating necessary directories if they don't exist.
        - Loading JSON workflow files from disk into memory.
        - Refreshing the cached nodes for all loaded workflows.
        """
        self.workflows = {}  # Holds the loaded workflows, keyed by their name
        self.workflows_cached_nodes = (
            []
        )  # Stores information about nodes tagged as cached

        # Ensure that the workflows directory and the input directory exist
        os.makedirs(config.WORKFLOWS_PATH, exist_ok=True)
        os.makedirs(config.INPUT_PATH, exist_ok=True)

        # Load existing workflow JSON files into memory
        for filename in os.listdir(config.WORKFLOWS_PATH):
            if filename.endswith(".json"):
                file_path = os.path.join(config.WORKFLOWS_PATH, filename)
                try:
                    with open(file_path, "r", encoding="utf-8") as file:
                        data = json.load(file)
                        name = os.path.splitext(filename)[
                            0
                        ]  # Extract the base filename
                        self.workflows[name] = data
                except Exception as e:
                    # If a file cannot be loaded, print an error and continue
                    print(f"Error loading file '{filename}': {e}")

        # Update the list of cached nodes after loading all workflows
        self.refresh_workflows_cached_nodes()

    def refresh_workflows_cached_nodes(self):
        """
        Updates self.workflows_cached_nodes with all nodes tagged as "!cache"
        from every workflow currently loaded.
        """
        workflows_cached_nodes = []

        # Go through each workflow and check for cached nodes
        for workflow_name, workflow_data in self.workflows.items():
            wrapper = Workflow(workflow_data)
            cached_nodes = wrapper.get_tagged_nodes("!cache")

            # Store each cached node with the workflow name for reference
            for node in cached_nodes:
                workflows_cached_nodes.append(
                    {"workflow_name": workflow_name, "node": node["node"]}
                )

        self.workflows_cached_nodes = workflows_cached_nodes

    def get_cached_nodes_except(self, name: str) -> list:
        """
        Returns a list of cached nodes for all workflows except the specified one.

        :param name: Name of the workflow to exclude.
        :return: A list of cached node data.
        """
        return [
            item["node"]
            for item in self.workflows_cached_nodes
            if item["workflow_name"] != name
        ]

    def get_workflows_cached_nodes(self):
        """
        Returns the entire list of cached nodes (from all workflows).

        :return: A list of cached node information.
        """
        return self.workflows_cached_nodes

    async def save_workflow(self, name: str, workflow: dict) -> None:
        """
        Saves a workflow to disk in JSON format and updates in-memory workflows.

        :param name: Name of the workflow.
        :param workflow: The workflow data (dictionary) to be saved.
        """
        file_path = os.path.join(config.WORKFLOWS_PATH, f"{name}.json")

        # Write the workflow to a file asynchronously
        async with aiofiles.open(file_path, "w", encoding="utf-8") as file:
            await file.write(json.dumps(workflow))

        # Update the in-memory representation
        self.workflows[name] = workflow

        # Refresh the cached nodes since the workflow has changed
        self.refresh_workflows_cached_nodes()

    async def delete_workflow(self, name: str) -> None:
        """
        Deletes a workflow JSON file from disk and removes it from memory.

        :param name: Name of the workflow to be deleted.
        """
        file_path = os.path.join(config.WORKFLOWS_PATH, f"{name}.json")

        # Remove the file if it exists
        if os.path.exists(file_path):
            os.remove(file_path)

        # Remove from in-memory dictionary if present
        self.workflows.pop(name, None)

        # Refresh the cached nodes after deletion
        self.refresh_workflows_cached_nodes()

    async def execute_workflow(self, name: str, params: dict, override_token: str = None) -> dict:
        """
        Executes a specified workflow with given parameters.

        :param name: Name of the workflow to execute.
        :param params: Dictionary containing tags and payload data to alter or bypass certain nodes.
        :param override_token: Optional token to override the configured ComfyUI token for this execution.
        :return: A dictionary of results keyed by their tags, usually images generated by each node.
        :raises FileNotFoundError: If the requested workflow is not found.
        """
        # Temporarily override the comfy token if provided
        if override_token:
            config.set_temp_token(override_token)
            
        try:
            if name not in self.workflows:
                raise FileNotFoundError(f"Workflow '{name}' not found.")

            # Wrap the workflow in a Workflow object for convenience
            workflow = Workflow(copy.deepcopy(self.workflows[name]))

            # Bypass any nodes tagged with "!bypass" if present
            workflow.bypass_nodes("!bypass")

            # Merge cached nodes from other workflows into this workflow,
            # using a unique key to avoid collisions
            key = config.CACHED_NODE_KEY_START
            for node in self.get_cached_nodes_except(name):
                key += 1
                workflow[key] = node

            # Process each tag in the provided parameters
            for tag, payload in (params or {}).items():
                # If the payload is simply False, bypass all nodes with this tag
                if payload is False:
                    workflow.bypass_nodes("$" + tag)
                    workflow.bypass_nodes("#" + tag)

                elif isinstance(payload, dict):
                    # Otherwise, iterate through the input data for the tag
                    for input_name, value in payload.items():
                        if isinstance(value, dict):
                            # Handle file uploads and URLs
                            if value.get("type") == "file":
                                try:
                                    filename = None
                                    file_path = None
                                    
                                    # If "content" is present, treat it as a base64-encoded file
                                    if "content" in value and value["content"]:
                                        filename = value.get("name")
                                        if not filename:
                                            raise ValueError(
                                                "File name is required with content."
                                            )
                                        file_path = os.path.join(config.INPUT_PATH, filename)
                                        
                                        # Check if file already exists
                                        if os.path.exists(file_path):
                                            print(
                                                f"File {filename} already exists in {config.INPUT_PATH}, using existing file for {tag}.{input_name}"
                                            )
                                        else:
                                            file_content = base64.b64decode(value["content"])
                                            # Write the decoded file to the INPUT_PATH
                                            with open(file_path, "wb") as f:
                                                f.write(file_content)

                                            print(
                                                f"File {filename} written to {config.INPUT_PATH} and specified into {tag}.{input_name}"
                                            )

                                    # If "url" is present, download the file and store it
                                    elif "url" in value and value["url"]:
                                        filename = value.get("name")
                                        if not filename:
                                            filename = value["url"].split("/")[-1]
                                        
                                        file_path = os.path.join(config.INPUT_PATH, filename)
                                        
                                        # Check if file already exists
                                        if os.path.exists(file_path):
                                            print(
                                                f"File {filename} already exists in {config.INPUT_PATH}, using existing file for {tag}.{input_name}"
                                            )
                                        else:
                                            response = requests.get(value["url"])
                                            response.raise_for_status()
                                            with open(file_path, "wb") as f:
                                                f.write(response.content)

                                            print(
                                                f"File {filename} downloaded from {value['url']} and written to {config.INPUT_PATH} and specified into {tag}.{input_name}"
                                            )
                                    else:
                                        # If there's no valid content or URL, skip
                                        print(
                                            f"No valid content/url for {value.get('name', 'unknown file')}"
                                        )
                                        continue

                                    # Update the workflow with the file name for this tag
                                    workflow.update_tagged_nodes_input(
                                        tag, input_name, filename
                                    )

                                except Exception as e:
                                    print(
                                        f"Error writing file {value.get('name', 'unknown file')} : {e}"
                                    )
                            else:
                                # TODO: Handling for other dict-based types, if needed
                                pass
                        else:
                            # Update the workflow with the value
                            workflow.update_tagged_nodes_input(tag, input_name, value)

            # Run the workflow asynchronously using the ComfyUI service
            images = await comfyui_service.run_workflow(workflow)
            response = {}

            # Collect and group the resulting images by each node's tags
            for node_id, node_images in images.items():
                tags = workflow.get_node_tags(node_id)
                for tag in tags:
                    # If there's only one element in the array, return it directly
                    if isinstance(node_images, list) and len(node_images) == 1:
                        response[tag[1:]] = node_images[0]
                    else:
                        response[tag[1:]] = node_images

            return response
            
        finally:
            # Clear temporary token override
            if override_token:
                config.clear_temp_token()

    async def list_workflows(self) -> list:
        """
        Returns a list of the names of all loaded workflows.

        :return: A list of workflow names.
        """
        return list(self.workflows.keys())

    async def get_workflow(self, name: str) -> dict:
        """
        Retrieves the inputs and outputs from a specified workflow.

        :param name: The name of the workflow to retrieve information from.
        :return: A dictionary containing the workflow's name, its tagged inputs, and outputs.
        """
        wrapper = Workflow(self.workflows[name])
        return {
            "name": name,
            "inputs": wrapper.get_tagged_inputs(),
            "outputs": wrapper.get_tagged_outputs(),
        }
