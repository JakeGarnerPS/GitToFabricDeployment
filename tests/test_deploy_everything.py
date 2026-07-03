import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import scripts.deploy_everything as deploy_everything
from scripts.deploy_everything import collect_deployment_targets


def test_collect_targets_uses_params_file_resolutions() -> None:
    params = {
        "prefix": "Road4",
        "prod_environment": "Prod",
        "workspace_names": {
            "Bronze_Dev": "Road4_Bronze_Dev",
            "Silver_Prod": "Road4_Silver",
        },
        "tier_lakehouses": {
            "bronze": "bronze_lakehouse",
            "silver": "silver_lakehouse",
        },
    }

    targets = collect_deployment_targets(
        params=params,
        tiers=["Bronze", "Silver"],
        environments=["Dev", "Prod"],
    )

    assert targets[0]["tier"] == "Bronze"
    assert targets[0]["environment"] == "Dev"
    assert targets[0]["workspace_name"] == "Road4_Bronze_Dev"
    assert targets[0]["lakehouse_name"] == "bronze_lakehouse"

    assert targets[2]["tier"] == "Silver"
    assert targets[2]["environment"] == "Dev"
    assert targets[2]["workspace_name"] == "Road4_Silver_Dev"
    assert targets[2]["lakehouse_name"] == "silver_lakehouse"

    assert targets[3]["tier"] == "Silver"
    assert targets[3]["environment"] == "Prod"
    assert targets[3]["workspace_name"] == "Road4_Silver"
    assert targets[3]["lakehouse_name"] == "silver_lakehouse"


def test_main_deploys_workspaces_before_lakehouses(monkeypatch) -> None:
    calls = []

    def fake_deploy_lakehouse(access_token, **kwargs):
        calls.append(("lakehouse", kwargs["workspace_name"], kwargs["lakehouse_name"]))

    def fake_deploy_medallion_workspaces_main() -> None:
        calls.append(("workspaces",))

    def fake_deploy_notebooks_main() -> None:
        calls.append(("notebooks",))

    def fake_assign_workspaces_to_capacity_main() -> None:
        calls.append(("capacity",))

    monkeypatch.setattr(deploy_everything, "get_access_token_interactive", lambda: "token")
    monkeypatch.setattr(deploy_everything.os, "environ", {"FABRIC_ACCESS_TOKEN": "token"})
    monkeypatch.setattr(deploy_everything, "load_params_file", lambda path: {
        "tiers": "Bronze",
        "environments": "Dev",
    })
    monkeypatch.setattr(deploy_everything, "collect_deployment_targets", lambda params, tiers, environments: [{
        "tier": "Bronze",
        "environment": "Dev",
        "workspace_name": "Road4_Bronze_Dev",
        "lakehouse_name": "bronze_lakehouse",
    }])
    monkeypatch.setattr(deploy_everything, "deploy_lakehouse", fake_deploy_lakehouse)
    monkeypatch.setattr(deploy_everything, "deploy_medallion_workspaces_main", fake_deploy_medallion_workspaces_main)
    monkeypatch.setattr(deploy_everything, "deploy_notebooks_main", fake_deploy_notebooks_main)
    monkeypatch.setattr(deploy_everything, "assign_workspaces_to_capacity_main", fake_assign_workspaces_to_capacity_main)
    monkeypatch.setattr(sys, "argv", ["deploy_everything.py"])

    deploy_everything.main()

    assert calls[:2] == [("workspaces",), ("lakehouse", "Road4_Bronze_Dev", "bronze_lakehouse")]
