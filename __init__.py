import server
from aiohttp import web

from .workflow_manager import WorkflowManager
from .config import config
from .openapi_spec_generator import OpenAPISpecGenerator

WEB_DIRECTORY = "./js"
NODE_CLASS_MAPPINGS = {}
__all__ = ["NODE_CLASS_MAPPINGS"]
version = "V0.0.1"

print(f"⚡⚡⚡ Loading: ComfyUI Connect ({version})")

manager = WorkflowManager()


@server.PromptServer.instance.routes.get("/connect")
async def index(request):
    index = f"{config.COMFY_PATH}/custom_nodes/ComfyUI-Connect/www/index.html"

    with open(index, "r") as file:
        html = file.read()

    return web.Response(text=html, content_type="text/html")


@server.PromptServer.instance.routes.get("/connect/openapi.json")
async def index(request):
    workflows = []
    names = await manager.list_workflows()
    for name in names:
        workflow = await manager.get_workflow(name)
        workflows.append(workflow)

    generator = OpenAPISpecGenerator(workflows)
    return web.json_response(generator.generate())


@server.PromptServer.instance.routes.put("/connect/workflows")
async def save_workflow(request):
    try:
        data = await request.json()
        workflow = data["workflow"]
        name = data["name"]
        await manager.save_workflow(name, workflow)
        return web.json_response(
            {"status": "success", "message": f"Workflow '{name}' saved."}
        )
    except KeyError as e:
        return web.json_response(
            {"status": "error", "message": f"Missing key: {str(e)}"}, status=400
        )
    except Exception as e:
        return web.json_response({"status": "error", "message": str(e)}, status=500)


@server.PromptServer.instance.routes.delete("/connect/workflows/{name}")
async def delete_workflow(request):
    name = request.match_info["name"]
    try:
        await manager.delete_workflow(name)
        return web.json_response(
            {"status": "success", "message": f"Workflow '{name}' deleted."}
        )
    except FileNotFoundError:
        return web.json_response(
            {"status": "error", "message": f"Workflow '{name}' not found."}, status=404
        )
    except Exception as e:
        return web.json_response({"status": "error", "message": str(e)}, status=500)


@server.PromptServer.instance.routes.post("/connect/workflows/{name}")
async def execute_workflow(request):
    params = await request.json()
    name = request.match_info["name"]
    try:
        result = await manager.execute_workflow(name, params)
        return web.json_response(
            {"status": "success", "workflow": name, "result": result}
        )
    except FileNotFoundError:
        return web.json_response(
            {"status": "error", "message": f"Workflow '{name}' not found."}, status=404
        )
    except Exception as e:
        return web.json_response({"status": "error", "message": str(e)}, status=500)


@server.PromptServer.instance.routes.get("/connect/workflow/cache_nodes")
async def get_workflow(request):
    try:
        cached_nodes = manager.get_workflows_cached_nodes()
        return web.json_response({"status": "success", "nodes": cached_nodes})
    except Exception as e:
        return web.json_response({"status": "error", "message": str(e)}, status=500)


@server.PromptServer.instance.routes.get("/connect/workflows/{name}")
async def get_workflow(request):
    name = request.match_info["name"]
    try:
        result = await manager.get_workflow(name)
        return web.json_response(
            {"status": "success", "workflow": name, "workflow": result}
        )
    except FileNotFoundError:
        return web.json_response(
            {"status": "error", "message": f"Workflow '{name}' not found."}, status=404
        )
    except Exception as e:
        return web.json_response({"status": "error", "message": str(e)}, status=500)
