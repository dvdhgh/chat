# Version Control & Deployment Guide

> [!IMPORTANT]
> This environment does NOT have a working `git` CLI in the system PATH.
> All version control operations (commits, pushes) MUST be performed using the **GitHub MCP Server**.

## Recommended Workflow

1.  **Develop & Test**: Make changes and verify locally.
2.  **Deploy to Production**: Use `.\deploy_prod.ps1` to deploy to Google Cloud Run.
3.  **Synchronize GitHub**: Use the GitHub MCP `push_files` tool to push changes to the `main` branch of `dvdhgh/chat`.

## GitHub MCP Details
- **Server Name**: `github-mcp-server`
- **Primary Tool**: `push_files`
- **Authenticated via**: Personal Access Token (PAT) configured in Antigravity settings.

*Note: This file serves as a reminder for AI assistants and human developers to use the GitHub MCP bridge to maintain synchronization.*
