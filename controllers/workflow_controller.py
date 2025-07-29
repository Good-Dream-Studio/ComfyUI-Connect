import server
from aiohttp import web
from ..services.workflow_service import WorkflowService
from ..utils.helpers import connect_print


class WorkflowController:
    def __init__(self, service: WorkflowService):
        self.service = service
        self.setup_routes()

    def setup_routes(self):
        """Setup workflow-related routes"""
        
        @server.PromptServer.instance.routes.put("/connect/workflows")
        async def save_workflow(request):
            data = await request.json()
            workflow = data["workflow"]
            name = data["name"]

            connect_print(f"PUT /connect/workflows - Saving workflow {name}")
            await self.service.save_workflow(name, workflow)
            return web.json_response(
                {"status": "success", "message": f"Workflow '{name}' saved."}
            )

        @server.PromptServer.instance.routes.delete("/connect/workflows/{name}")
        async def delete_workflow(request):
            name = request.match_info["name"]

            connect_print(f"DELETE /connect/workflows/{name} - Deleting the workflow ...")
            await self.service.delete_workflow(name)
            return web.json_response(
                {"status": "success", "message": f"Workflow '{name}' deleted."}
            )

        @server.PromptServer.instance.routes.post("/connect/workflows/{name}")
        async def execute_workflow(request):
            params = await request.json()
            name = request.match_info["name"]

            # Extract token from payload if provided
            override_token = params.pop("_token", None)  # Remove _token from params
            
            connect_print(f"POST /connect/workflows/{name} - Running workflow ...")
            result = await self.service.execute_workflow(name, params, override_token)
            return web.json_response({"status": "success", "workflow": name, "result": result})

        @server.PromptServer.instance.routes.get("/connect/workflow/cache_nodes")
        async def get_cached_nodes(request):
            cached_nodes = self.service.get_workflows_cached_nodes()
            return web.json_response({"status": "success", "nodes": cached_nodes})

        @server.PromptServer.instance.routes.get("/connect/workflows/{name}")
        async def get_workflow(request):
            name = request.match_info["name"]
            result = await self.service.get_workflow(name)
            return web.json_response(
                {"status": "success", "workflow": name, "workflow": result}
            ) 