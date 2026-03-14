from __future__ import annotations

import logging

from work_harness.config import Settings
from work_harness.connectors.atlassian_self_hosted_enterprise import (
    ConfluenceSelfHostedEnterpriseAdapter,
    JiraSelfHostedEnterpriseAdapter,
)
from work_harness.connectors.github_enterprise_cloud import GitHubEnterpriseCloudAdapter
from work_harness.connectors.slack_enterprise_grid import SlackEnterpriseGridAdapter
from work_harness.domain.models import ConnectorSource

logger = logging.getLogger("work_harness.connectors.factory")


def build_connector(source: ConnectorSource, settings: Settings):
    if source == ConnectorSource.JIRA:
        return JiraSelfHostedEnterpriseAdapter(settings)
    if source == ConnectorSource.CONFLUENCE:
        return ConfluenceSelfHostedEnterpriseAdapter(settings)
    if source == ConnectorSource.SLACK:
        return SlackEnterpriseGridAdapter(settings)
    if source == ConnectorSource.GITHUB:
        return GitHubEnterpriseCloudAdapter(settings)
    raise KeyError(source)


def build_connectors(settings: Settings):
    connectors = {
        source: build_connector(source, settings)
        for source in (
            ConnectorSource.JIRA,
            ConnectorSource.CONFLUENCE,
            ConnectorSource.SLACK,
            ConnectorSource.GITHUB,
        )
    }
    logger.info("Built connectors: %s", [s.value for s in connectors])
    return connectors
