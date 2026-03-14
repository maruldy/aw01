from __future__ import annotations

from work_harness.config import Settings
from work_harness.connectors.atlassian_self_hosted_enterprise import (
    ConfluenceSelfHostedEnterpriseAdapter,
    JiraSelfHostedEnterpriseAdapter,
)
from work_harness.connectors.github_enterprise_cloud import GitHubEnterpriseCloudAdapter
from work_harness.connectors.slack_enterprise_grid import SlackEnterpriseGridAdapter
from work_harness.domain.models import ConnectorSource


def build_connectors(settings: Settings):
    return {
        ConnectorSource.JIRA: JiraSelfHostedEnterpriseAdapter(settings),
        ConnectorSource.CONFLUENCE: ConfluenceSelfHostedEnterpriseAdapter(settings),
        ConnectorSource.SLACK: SlackEnterpriseGridAdapter(settings),
        ConnectorSource.GITHUB: GitHubEnterpriseCloudAdapter(settings),
    }
