import os
import sys
import json
import base64
import asyncio
from pathlib import Path

try:
    from mcp import ClientSession
    from mcp.client.stdio import stdio_client, StdioServerParameters
except ImportError:
    print("Error: The 'mcp' package is not installed.")
    print("Please run: .venv\\Scripts\\pip install mcp")
    sys.exit(1)

# Configuration
REPO_OWNER = "dvdhgh"
REPO_NAME = "chat"
BRANCH_NAME = "main"

# Directories and files to explicitly ignore
IGNORE_DIRS = {".venv", "__pycache__", "node_modules", ".git", ".vscode", "uploads", "assets"}
IGNORE_EXTS = {".png", ".jpg", ".jpeg", ".gif", ".ico", ".woff", ".woff2", ".ttf", ".zip", ".tar", ".gz", ".pyc"}

def is_text_file(filepath):
    try:
        with open(filepath, 'tr') as check_file:
            check_file.read(1024)
            return True
    except UnicodeDecodeError:
        return False

def gather_files(root_dir):
    """
    Gathers all valid text files in the project.
    Returns a list of dicts: {"path": "relative/path/to/file", "content": "..."}
    """
    files_to_push = []
    root_path = Path(root_dir)
    
    for dirpath, dirnames, filenames in os.walk(root_dir):
        # Mutating dirnames in-place to ignore directories
        dirnames[:] = [d for d in dirnames if d not in IGNORE_DIRS and not d.startswith('.')]
        
        for filename in filenames:
            if filename.startswith('.'):
                if filename not in {".gitignore", ".firebaserc"}: # Explicitly allow some dotfiles
                    continue
            
            ext = os.path.splitext(filename)[1].lower()
            if ext in IGNORE_EXTS:
                continue
                
            filepath = os.path.join(dirpath, filename)
            rel_path = os.path.relpath(filepath, root_dir).replace('\\', '/')
            
            # Read content
            if is_text_file(filepath):
                try:
                    with open(filepath, 'r', encoding='utf-8') as f:
                        content = f.read()
                    files_to_push.append({
                        "path": rel_path,
                        "content": content
                    })
                    print(f"Adding (text): {rel_path}")
                except Exception as e:
                    print(f"Warning: Could not read {rel_path}: {e}")
            else:
                # GitHub MCP might expect binary content base64 encoded, but the schema says text.
                print(f"Skipping binary/non-text file: {rel_path}")
                
    return files_to_push

async def push_to_github(commit_message, repo_owner=REPO_OWNER, repo_name=REPO_NAME):
    token = os.environ.get("GITHUB_PERSONAL_ACCESS_TOKEN")
    if not token:
        print("Error: GITHUB_PERSONAL_ACCESS_TOKEN environment variable is missing.")
        print("Please set it in your terminal before running this script.")
        print('Example: $env:GITHUB_PERSONAL_ACCESS_TOKEN="your_token"')
        sys.exit(1)

    print(f"Gathering files for repository {repo_owner}/{repo_name}...")
    project_root = os.path.abspath(os.path.dirname(__file__))
    files = gather_files(project_root)
    
    if not files:
        print("No files discovered to push.")
        sys.exit(0)
        
    print(f"\nDiscovered {len(files)} files to push.")
    print("Starting GitHub MCP Server via npx...")
    
    # Configure the MCP server command
    server_params = StdioServerParameters(
        command="npx",
        args=["-y", "@modelcontextprotocol/server-github"],
        env=os.environ.copy() # Passes the GITHUB_PERSONAL_ACCESS_TOKEN
    )

    try:
        async with stdio_client(server_params) as (read_stream, write_stream):
            async with ClientSession(read_stream, write_stream) as session:
                await session.initialize()
                
                print("\nPushing code via push_files tool...")
                # The arguments for the push_files tool according to @modelcontextprotocol/server-github
                tool_args = {
                    "owner": repo_owner,
                    "repo": repo_name,
                    "branch": BRANCH_NAME,
                    "message": commit_message,
                    "files": files
                }
                
                # We call the tool generically
                result = await session.call_tool("push_files", tool_args)
                
                print("\n--- Push Result ---")
                # Results usually have `content` as a list of TextContent objects
                if hasattr(result, 'content'):
                    for item in result.content:
                        if hasattr(item, 'text'):
                            print(item.text)
                        else:
                            print(item)
                else:
                    print(result)
                    
                print("\nPush complete!")

    except Exception as e:
        print(f"\nError interacting with MCP server: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    message = "Automated push via MCP script"
    if len(sys.argv) > 1:
        message = sys.argv[1]
        
    asyncio.run(push_to_github(message))
