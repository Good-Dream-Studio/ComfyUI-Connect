import uuid
import json
import urllib.request
import urllib.parse
import aiohttp
import base64
import asyncio
from typing import Dict, List
from ..config import config
from ..utils.helpers import connect_print


class ComfyUIService:
    """
    Service for managing ComfyUI connections and workflow execution.
    Combines client functionality with service-level management.
    Implements singleton pattern for connection management.
    """

    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return

        self._initialized = True
        self.CLIENT_ID = str(uuid.uuid4())
        self.ws = None
        self.session = None
        self._message_queue = asyncio.Queue()
        self._prompt_events: Dict[str, asyncio.Event] = {}
        self._listener_task = None
        self._connected = False

    async def connect(self):
        """Establish connection to ComfyUI"""
        if self._connected:
            return

        self.session = aiohttp.ClientSession()
        
        # Build WebSocket URL with token if available
        ws_url = f"ws://{config.comfy_endpoint}/ws?clientId={self.CLIENT_ID}"
        if config.comfy_token:
            ws_url += f"&token={config.comfy_token}"
            connect_print("WebSocket connection using token authentication")
        else:
            connect_print("WebSocket connection using direct access (no token)")
            
        self.ws = await self.session.ws_connect(ws_url)
        # Start the global websocket listener
        self._listener_task = asyncio.create_task(self._listen_websocket())
        self._connected = True

    async def _listen_websocket(self):
        """Listen for WebSocket messages from ComfyUI"""
        try:
            while True:
                message = await self.ws.receive()
                if message.type == aiohttp.WSMsgType.TEXT:
                    data = json.loads(message.data)
                    # Put the message in the queue
                    await self._message_queue.put(data)
                    # If it's an executing message with no node, it means the prompt is done
                    if (
                        data["type"] == "executing"
                        and data["data"]["node"] is None
                        and "prompt_id" in data["data"]
                    ):
                        prompt_id = data["data"]["prompt_id"]
                        if prompt_id in self._prompt_events:
                            self._prompt_events[prompt_id].set()
        except Exception as e:
            print(f"WebSocket listener error: {e}")
            # Restart the listener if it fails
            self._listener_task = asyncio.create_task(self._listen_websocket())

    async def close(self):
        """Close the ComfyUI connection"""
        if self._listener_task:
            self._listener_task.cancel()
        if self.ws:
            await self.ws.close()
        if self.session:
            await self.session.close()
        self._connected = False

    async def _ensure_connected(self):
        """Ensure we have an active connection to ComfyUI"""
        if not self._connected:
            await self.connect()

    async def queue_prompt(self, prompt):
        """Queue a prompt for execution in ComfyUI"""
        await self._ensure_connected()
        payload = {"prompt": prompt, "client_id": self.CLIENT_ID}
        data = json.dumps(payload).encode("utf-8")
        
        # Build URL with token if available
        url = f"http://{config.comfy_endpoint}/prompt"
        if config.comfy_token:
            url += f"?token={config.comfy_token}"
            connect_print("Prompt execution using token authentication")
        else:
            connect_print("Prompt execution using direct access (no token)")
            
        async with self.session.post(url, data=data) as response:
            return await response.json()

    async def get_image(self, filename, subfolder, folder_type):
        """Retrieve an image from ComfyUI"""
        await self._ensure_connected()
        params = {"filename": filename, "subfolder": subfolder, "type": folder_type}
        if config.comfy_token:
            params["token"] = config.comfy_token
            connect_print("Image retrieval using token authentication")
        else:
            connect_print("Image retrieval using direct access (no token)")
        url_values = urllib.parse.urlencode(params)
        async with self.session.get(
            f"http://{config.comfy_endpoint}/view?{url_values}"
        ) as response:
            image_binary = await response.read()
            image_base64 = base64.b64encode(image_binary).decode("utf-8")
            return image_base64

    async def get_history(self, prompt_id):
        """Get execution history for a prompt"""
        await self._ensure_connected()
        
        # Build URL with token if available, works for comfyui-login plugin
        url = f"http://{config.comfy_endpoint}/history/{prompt_id}"
        if config.comfy_token:
            url += f"?token={config.comfy_token}"
            connect_print("History retrieval using token authentication")
        else:
            connect_print("History retrieval using direct access (no token)")
            
        async with self.session.get(url) as response:
            return await response.json()

    async def run_workflow(self, workflow: dict) -> dict:
        """
        Execute a workflow and return the generated images.

        :param workflow: The workflow to execute
        :return: Dictionary of generated images by node ID
        """
        await self._ensure_connected()

        # Create an event for this prompt
        prompt_id = (await self.queue_prompt(workflow))["prompt_id"]
        self._prompt_events[prompt_id] = asyncio.Event()

        try:
            # Wait for the prompt completion event
            await self._prompt_events[prompt_id].wait()

            output_images = {}
            history = (await self.get_history(prompt_id))[prompt_id]
            for node_id, node_output in history["outputs"].items():
                images_output = []
                if "images" in node_output:
                    for image in node_output["images"]:
                        image_data = await self.get_image(
                            image["filename"], image.get("subfolder", ""), image["type"]
                        )
                        images_output.append(image_data)
                output_images[node_id] = images_output

            return output_images
        finally:
            # Clean up the event
            del self._prompt_events[prompt_id]


# Global service instance
comfyui_service = ComfyUIService()
