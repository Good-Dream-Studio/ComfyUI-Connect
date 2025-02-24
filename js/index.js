import { app } from "../../scripts/app.js";
import { api } from "../../scripts/api.js";

app.registerExtension({
  name: "Comfy.Connect",
  commands: [
    {
      id: "comfy-connect-save-api-endpoint",
      label: "Save API Endpoint",
      icon: "pi pi-bolt",
      function: async () => {
        let name = app.graph.extra?.comfy_connect?.name ?? "";

        name = await app.extensionManager.dialog.prompt({
          title: "Endpoint Name",
          message: "Type the endpoint name",
          defaultValue: name
        });

        if (!name) return;

        app.graph.extra.comfy_connect = {
          name
        };

        const { output } = await app.graphToPrompt();
        await api
          .fetchApi("/connect/workflows", {
            method: "PUT",
            body: JSON.stringify({ name, workflow: output }),
            cache: "no-store"
          })
          .then((response) => {
            console.log(response);
          })
          .catch((error) => {
            console.error("Error:", error);
          });

        app.extensionManager.toast.add({
          severity: "success",
          summary: "API Endpoint Saved",
          detail: `The endpoint "/api/connect/workflows/${name}" has been saved.`,
          life: 3000
        });
      }
    }
  ],

  menuCommands: [
    {
      path: ["Workflow"],
      commands: ["comfy-connect-save-api-endpoint"]
    }
  ],

  async setup() {}
});
