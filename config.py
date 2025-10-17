import os
import json
import sys
import folder_paths


class Config:
    # Path configuration
    WORKFLOWS_PATH: str = os.path.abspath(
        os.path.join(
            folder_paths.get_user_directory(), "default", "ComfyUI-Connect", "workflows"
        )
    )
    INPUT_PATH: str = os.path.abspath(folder_paths.get_input_directory())
    OUTPUT_PATH: str = os.path.abspath(folder_paths.get_output_directory())
    
    # Workflow configuration
    CACHED_NODE_KEY_START: int = 1000
    
    # WebSocket configuration
    GPU_INFO_INTERVAL: float = 0.5  # seconds
    SETTINGS_FILENAME: str = "comfy.settings.json"
    
    # GPU monitoring configuration
    POWER_CONVERSION_FACTOR: float = 1000.0  # mW to W conversion
    
    # OpenAPI configuration
    OPENAPI_VERSION: str = "3.0.0"
    API_TITLE: str = "Workflow API Documentation"
    API_VERSION: str = "1.0.0"
    
    def __init__(self):
        self._user_settings = None
        self._settings_loaded = False
        self._override_token = None  # For temporary token override
    
    @property
    def user_settings(self):
        """Lazy loading of user settings from comfy.settings.json"""
        if not self._settings_loaded:
            self._load_user_settings()
        return self._user_settings
    
    def _load_user_settings(self):
        """Load user settings from comfy.settings.json file"""
        self._settings_loaded = True
        settings_path = os.path.join(
            folder_paths.get_user_directory(), 
            "default", 
            self.SETTINGS_FILENAME
        )
        
        try:
            if not os.path.exists(settings_path):
                self._user_settings = {}
                return
                
            with open(settings_path, "r", encoding="utf-8") as f:
                self._user_settings = json.load(f)
        except (json.JSONDecodeError, Exception):
            self._user_settings = {}
    
    def _get_port_from_args(self):
        """Extract port from command line arguments"""
        try:
            for i, arg in enumerate(sys.argv):
                if arg == "--port" and i + 1 < len(sys.argv):
                    return int(sys.argv[i + 1])
        except (ValueError, IndexError):
            pass
        return 8000
    
    @property
    def comfy_endpoint(self):
        """Get ComfyUI endpoint from settings with intelligent defaults"""
        host = self.user_settings.get("Connect.ComfyUIHost")
        if not host:
            host = "127.0.0.1"
        
        port = self.user_settings.get("Connect.ComfyUIPort")
        if not port:
            port = self._get_port_from_args()
        
        return f"{host}:{port}"
    
    @property
    def comfy_token(self):
        """Get ComfyUI authentication token from settings"""
        # Check temporary override first, then environment variable, then user settings
        return self._override_token or os.environ.get("COMFYUI_TOKEN") or self.user_settings.get("Connect.ComfyUIToken", "")
    
    def set_temp_token(self, token: str):
        """Temporarily override the ComfyUI token"""
        self._override_token = token
        
    def clear_temp_token(self):
        """Clear the temporary token override"""
        self._override_token = None


config = Config()
