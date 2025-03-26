import logging
from pathlib import Path
from typing import Sequence
from mcp.server import Server
from mcp.server.session import ServerSession
from mcp.server.stdio import stdio_server
from mcp.server import NotificationOptions
from mcp.server import InitializationOptions
from mcp.types import (
    ClientCapabilities,
    TextContent,
    Tool,
    ListRootsResult,
    RootsCapability,
    Resource,
    Prompt
)

from enum import Enum
import git
from pydantic import BaseModel


class GitStatus(BaseModel):
    repo_path: str

class GitDiffUnstaged(BaseModel):
    repo_path: str

class GitDiffStaged(BaseModel):
    repo_path: str

class GitDiff(BaseModel):
    repo_path: str
    target: str

class GitCommit(BaseModel):
    repo_path: str
    message: str

class GitAdd(BaseModel):
    repo_path: str
    files: list[str]

class GitReset(BaseModel):
    repo_path: str

class GitLog(BaseModel):
    repo_path: str
    max_count: int = 10

class GitCreateBranch(BaseModel):
    repo_path: str
    branch_name: str
    base_branch: str | None = None

class GitCheckout(BaseModel):
    repo_path: str
    branch_name: str

class GitShow(BaseModel):
    repo_path: str
    revision: str

class GitInit(BaseModel):
    repo_path: str

class GitTools(str, Enum):
    STATUS = "git_status"
    DIFF_UNSTAGED = "git_diff_unstaged"
    DIFF_STAGED = "git_diff_staged"
    DIFF = "git_diff"
    COMMIT = "git_commit"
    ADD = "git_add"
    RESET = "git_reset"
    LOG = "git_log"
    CREATE_BRANCH = "git_create_branch"
    CHECKOUT = "git_checkout"
    SHOW = "git_show"
    INIT = "git_init"

def git_status(repo: git.Repo) -> str:
    try:
        return repo.git.status()
    except git.GitCommandError as e:
        return f"Error getting status: {e}"

def git_diff_unstaged(repo: git.Repo) -> str:
    try:
        return repo.git.diff()
    except git.GitCommandError as e:
        return f"Error getting unstaged diff: {e}"

def git_diff_staged(repo: git.Repo) -> str:
    try:
        return repo.git.diff("--cached")
    except git.GitCommandError as e:
        return f"Error getting staged diff: {e}"

def git_diff(repo: git.Repo, target: str) -> str:
    try:
        return repo.git.diff(target)
    except git.GitCommandError as e:
        return f"Error getting diff with {target}: {e}"

def git_commit(repo: git.Repo, message: str) -> str:
    commit = repo.index.commit(message)
    return f"Changes committed successfully with hash {commit.hexsha}"

def git_add(repo: git.Repo, files: list[str]) -> str:
    repo.index.add(files)
    return "Files staged successfully"

def git_reset(repo: git.Repo) -> str:
    repo.index.reset()
    return "All staged changes reset"

def git_log(repo: git.Repo, max_count: int = 10) -> str:
    try:
        commits = list(repo.iter_commits(max_count=max_count))
        log = []
        for commit in commits:
            log.append(
                f"Commit: {commit.hexsha}\n"
                f"Author: {commit.author}\n"
                f"Date: {commit.authored_datetime}\n"
                f"Message: {commit.message}\n"
            )
        return "\n".join(log)
    except git.GitCommandError as e:
        return f"Error getting commit logs: {e}"

def git_create_branch(repo: git.Repo, branch_name: str, base_branch: str | None = None) -> str:
    if base_branch:
        base = repo.refs[base_branch]
    else:
        base = repo.active_branch

    repo.create_head(branch_name, base)
    return f"Created branch '{branch_name}' from '{base.name}'"

def git_checkout(repo: git.Repo, branch_name: str) -> str:
    repo.git.checkout(branch_name)
    return f"Switched to branch '{branch_name}'"

def git_init(repo_path: str) -> str:
    try:
        repo = git.Repo.init(path=repo_path, mkdir=True)
        return f"Initialized empty Git repository in {repo.git_dir}"
    except Exception as e:
        return f"Error initializing repository: {str(e)}"

def git_show(repo: git.Repo, revision: str) -> str:
    try:
        commit = repo.commit(revision)
        output = [
            f"Commit: {commit.hexsha}\n"
            f"Author: {commit.author}\n"
            f"Date: {commit.authored_datetime}\n"
            f"Message: {commit.message}\n"
        ]
        if commit.parents:
            parent = commit.parents[0]
            diff = parent.diff(commit, create_patch=True)
        else:
            diff = commit.diff(git.NULL_TREE, create_patch=True)
        for d in diff:
            output.append(f"\n--- {d.a_path}\n+++ {d.b_path}\n")
            output.append(d.diff.decode('utf-8'))
        return "".join(output)
    except (git.GitCommandError, ValueError) as e:
        return f"Error showing commit {revision}: {e}"

async def serve(repository: Path | None) -> None:
    logger = logging.getLogger(__name__)

    if repository is not None:
        try:
            git.Repo(repository)
            logger.info(f"Using repository at {repository}")
        except git.InvalidGitRepositoryError:
            logger.error(f"{repository} is not a valid Git repository")
            return

    server = Server("mcp-git")

    @server.list_tools()
    async def list_tools() -> list[Tool]:
        return [
            Tool(
                name=GitTools.STATUS,
                description="Shows the working tree status. The repo_path must be the Git repository root.",
                inputSchema=GitStatus.schema(),
            ),
            Tool(
                name=GitTools.DIFF_UNSTAGED,
                description="Shows changes in the working directory that are not yet staged. The repo_path must be the Git repository root.",
                inputSchema=GitDiffUnstaged.schema(),
            ),
            Tool(
                name=GitTools.DIFF_STAGED,
                description="Shows changes that are staged for commit. The repo_path must be the Git repository root.",
                inputSchema=GitDiffStaged.schema(),
            ),
            Tool(
                name=GitTools.DIFF,
                description="Shows differences between branches or commits. The repo_path must be the Git repository root.",
                inputSchema=GitDiff.schema(),
            ),
            Tool(
                name=GitTools.COMMIT,
                description="Records changes to the repository. The repo_path must be the Git repository root.",
                inputSchema=GitCommit.schema(),
            ),
            Tool(
                name=GitTools.ADD,
                description="Adds file contents to the staging area. The repo_path must be the Git repository root.",
                inputSchema=GitAdd.schema(),
            ),
            Tool(
                name=GitTools.RESET,
                description="Unstages all staged changes. The repo_path must be the Git repository root.",
                inputSchema=GitReset.schema(),
            ),
            Tool(
                name=GitTools.LOG,
                description="Shows the commit logs. The repo_path must be the Git repository root.",
                inputSchema=GitLog.schema(),
            ),
            Tool(
                name=GitTools.CREATE_BRANCH,
                description="Creates a new branch from an optional base branch. The repo_path must be the Git repository root.",
                inputSchema=GitCreateBranch.schema(),
            ),
            Tool(
                name=GitTools.CHECKOUT,
                description="Switches branches. The repo_path must be the Git repository root.",
                inputSchema=GitCheckout.schema(),
            ),
            Tool(
                name=GitTools.SHOW,
                description="Shows the contents of a commit. The repo_path must be the Git repository root.",
                inputSchema=GitShow.schema(),
            ),
            Tool(
                name=GitTools.INIT,
                description="Initialize a new Git repository. The repo_path is the directory where the repository will be initialized.",
                inputSchema=GitInit.schema(),
            )
        ]

    async def list_repos() -> Sequence[str]:
        async def by_roots() -> Sequence[str]:
            if not isinstance(server.request_context.session, ServerSession):
                raise TypeError("server.request_context.session must be a ServerSession")

            if not server.request_context.session.check_client_capability(
                ClientCapabilities(roots=RootsCapability())
            ):
                return []

            roots_result: ListRootsResult = await server.request_context.session.list_roots()
            logger.debug(f"Roots result: {roots_result}")
            repo_paths = []
            for root in roots_result.roots:
                path = root.uri.path
                try:
                    git.Repo(path)
                    repo_paths.append(str(path))
                except git.InvalidGitRepositoryError:
                    pass
            return repo_paths

        def by_commandline() -> Sequence[str]:
            return [str(repository)] if repository is not None else []

        cmd_repos = by_commandline()
        root_repos = await by_roots()
        return [*root_repos, *cmd_repos]

    @server.call_tool()
    async def call_tool(name: str, arguments: dict) -> list[TextContent]:
        repo_path = Path(arguments["repo_path"])
        
        # Handle git init separately since it doesn't require an existing repo
        if name == GitTools.INIT.value:
            result = git_init(str(repo_path))
            return [TextContent(
                type="text",
                text=result
            )]
            
        # For all other commands, we need an existing repo
        try:
            repo = git.Repo(repo_path)
        except git.InvalidGitRepositoryError:
            return [TextContent(
                type="text",
                text=(f"Error: '{repo_path}' is not a valid Git repository root. "
                      f"Please provide the path to the repository root (the directory containing the '.git' folder), "
                      f"not a subdirectory.")
            )]
        except git.NoSuchPathError:
            return [TextContent(
                type="text",
                text=f"Error: Path '{repo_path}' does not exist."
            )]
        except Exception as e:
            return [TextContent(
                type="text",
                text=f"Error accessing repository: {str(e)}"
            )]

        # Use string comparison instead of enum comparison
        if name == GitTools.STATUS.value:  # Use .value
            logging.error(f"[DEBUG] Matched STATUS using .value")

        if name == GitTools.STATUS.value:
            status = git_status(repo)
            return [TextContent(
                type="text",
                text=status
            )]

        elif name == GitTools.DIFF_UNSTAGED.value:  # Use .value
            logging.error(f"[DEBUG] Matched DIFF_UNSTAGED using .value")
            diff = git_diff_unstaged(repo)
            return [TextContent(
                type="text",
                text=diff
            )]

        elif name == GitTools.DIFF_STAGED.value:  # Use .value
            logging.error(f"[DEBUG] Matched DIFF_STAGED using .value")
            diff = git_diff_staged(repo)
            return [TextContent(
                type="text",
                text=diff
            )]

        elif name == GitTools.DIFF.value:  # Use .value
            logging.error(f"[DEBUG] Matched DIFF using .value")
            diff = git_diff(repo, arguments["target"])
            return [TextContent(
                type="text",
                text=diff
            )]

        elif name == GitTools.COMMIT.value:  # Use .value
            logging.error(f"[DEBUG] Matched COMMIT using .value")
            result = git_commit(repo, arguments["message"])
            return [TextContent(
                type="text",
                text=result
            )]

        elif name == GitTools.ADD.value:  # Use .value
            logging.error(f"[DEBUG] Matched ADD using .value")
            result = git_add(repo, arguments["files"])
            return [TextContent(
                type="text",
                text=result
            )]

        elif name == GitTools.RESET.value:  # Use .value
            logging.error(f"[DEBUG] Matched RESET using .value")
            result = git_reset(repo)
            return [TextContent(
                type="text",
                text=result
            )]

        elif name == GitTools.LOG.value:
            log = git_log(repo, int(arguments.get("max_count", 10)))
            return [TextContent(
                type="text",
                text=log
            )]

        elif name == GitTools.CREATE_BRANCH.value:  # Use .value
            logging.error(f"[DEBUG] Matched CREATE_BRANCH using .value")
            result = git_create_branch(
                repo,
                arguments["branch_name"],
                arguments.get("base_branch")
            )
            return [TextContent(
                type="text",
                text=result
            )]

        elif name == GitTools.CHECKOUT.value:  # Use .value
            logging.error(f"[DEBUG] Matched CHECKOUT using .value")
            result = git_checkout(repo, arguments["branch_name"])
            return [TextContent(
                type="text",
                text=result
            )]

        elif name == GitTools.SHOW.value:  # Use .value
            logging.error(f"[DEBUG] Matched SHOW using .value")
            result = git_show(repo, arguments["revision"])
            return [TextContent(
                type="text",
                text=result
            )]

        else:
            logging.error(f"[DEBUG] No match found for tool name: {name}")
            raise ValueError(f"Unknown tool: {name}")

    @server.list_resources()
    async def handle_list_resources() -> list[Resource]:
        return []

    @server.list_prompts()
    async def handle_list_prompts() -> list[Prompt]:
        return []

    # Define notification options
    notification_options = NotificationOptions(
            prompts_changed=True,    
            resources_changed=True,  
            tools_changed=True      
    )

    # Create initialization options with these capabilities
    options = server.create_initialization_options(
        notification_options=notification_options,
        experimental_capabilities={}
    )

    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, options, raise_exceptions=True)

