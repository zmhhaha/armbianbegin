# Repository Workflow

## OpenSpec project

For specification, proposal, design, task, validation, apply, or archive work in this repository:

1. Read `.openspec-project.json` at the repository root when it exists.
2. Use the OpenSpec Service MCP endpoint from its `baseUrl` (normally `https://openspec.panghuer.top/mcp`) and pass the recorded `projectId` to every project-scoped tool.
3. If the mapping file does not exist, run `bash openspec_service/scripts/register-project.sh` with a user-provided Casdoor JWT before creating OpenSpec artifacts.
4. Do not use `openspec-service/project-a-specs` for this repository unless the user explicitly requests that shared project.

The application source may remain in GitHub. The OpenSpec project is the separate Gitea private store for this repository's `openspec/` specifications and changes.
