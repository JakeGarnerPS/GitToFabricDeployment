import subprocess
from typing import Dict


def build_git_provider_details(args, params: dict, tier: str) -> dict:
    git_params = params.get("git_connection", {})
    provider = args.git_provider or git_params.get("git_provider_type", "GitHub")
    owner = args.git_org or git_params.get("owner_name", "")
    repo = args.git_repo or git_params.get("repository_name", "")
    branch = args.git_branch or git_params.get("branch_name", "")

    if not branch:
        try:
            result = subprocess.run(
                ["git", "branch", "--show-current"],
                capture_output=True,
                text=True,
                check=True,
            )
            branch = result.stdout.strip()
        except Exception:  # pylint: disable=broad-except
            pass

    details: dict = {
        "gitProviderType": provider,
        "repositoryName": repo,
        "branchName": branch,
        "directoryName": f"/{tier}",
    }

    if provider == "AzureDevOps":
        details["organizationName"] = owner
        details["projectName"] = args.git_project or git_params.get("project_name", "")
    else:
        details["ownerName"] = owner

    return details


def build_git_credentials(args, params: dict) -> dict:
    git_params = params.get("git_connection", {})
    cred_type = (
        getattr(args, "git_credential_type", None)
        or git_params.get("git_credential_type", "Automatic")
    )

    if cred_type == "ConfiguredConnection":
        connection_id = (
            getattr(args, "git_connection_id", None)
            or git_params.get("git_connection_id", "")
        )
        if not connection_id:
            raise ValueError(
                "--git-connection-id (or git_connection_id in git_connection params) "
                "is required when git_credential_type is ConfiguredConnection."
            )
        return {"source": "ConfiguredConnection", "connectionId": connection_id}

    if cred_type == "PersonalAccessToken":
        raise ValueError(
            "git_credential_type=PersonalAccessToken is not supported by the Fabric "
            "git/connect API in this script. Use ConfiguredConnection with a Fabric "
            "connection ID instead."
        )

    return {"source": "Automatic"}
