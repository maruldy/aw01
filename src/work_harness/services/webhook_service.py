from __future__ import annotations

import hashlib
import hmac
import logging
import time
from typing import Any, Mapping

from work_harness.config import Settings
from work_harness.domain.models import (
    WebhookDeliveryEnvelope,
    WebhookProvider,
    WebhookVerificationResult,
)
from work_harness.services.webhook_store import WebhookStore

SLACK_SIGNATURE_TTL_SECONDS = 300


logger = logging.getLogger("work_harness.services.webhook")


class WebhookReceiverService:
    def __init__(self, settings: Settings, store: WebhookStore) -> None:
        self._settings = settings
        self._store = store

    async def receive(
        self,
        provider: WebhookProvider,
        raw_body: bytes,
        headers: Mapping[str, str],
        payload: dict[str, Any],
    ) -> tuple[WebhookVerificationResult, WebhookDeliveryEnvelope]:
        logger.debug("Receiving webhook: provider=%s body_size=%d", provider.value, len(raw_body))
        verification = self.verify_request(provider, raw_body, headers)
        envelope = self.normalize_envelope(
            provider,
            headers,
            payload,
            verification,
            raw_body,
        )
        await self.persist_delivery(envelope)
        logger.info(
            "Webhook processed: provider=%s delivery=%s "
            "accepted=%s verified=%s method=%s",
            provider.value, envelope.delivery_id,
            verification.accepted, verification.verified,
            verification.verification_method,
        )
        return verification, envelope

    def verify_request(
        self,
        provider: WebhookProvider,
        raw_body: bytes,
        headers: Mapping[str, str],
    ) -> WebhookVerificationResult:
        lowered_headers = self._normalize_headers(headers)
        if provider == WebhookProvider.GITHUB:
            return self._verify_github(raw_body, lowered_headers)
        if provider == WebhookProvider.SLACK:
            return self._verify_slack(raw_body, lowered_headers)
        if provider == WebhookProvider.JIRA:
            return self._verify_jira(lowered_headers)
        return self._verify_confluence(raw_body, lowered_headers)

    def extract_delivery_metadata(
        self,
        provider: WebhookProvider,
        headers: Mapping[str, str],
        payload: dict[str, Any],
        payload_hash: str,
    ) -> dict[str, str | None]:
        lowered_headers = self._normalize_headers(headers)
        fallback_delivery_id = f"{provider.value}-{payload_hash[:12]}"
        if provider == WebhookProvider.GITHUB:
            repository = payload.get("repository", {})
            pull_request = payload.get("pull_request", {})
            issue = payload.get("issue", {})
            resource_hint = (
                repository.get("full_name")
                if isinstance(repository, dict)
                else None
            )
            if isinstance(pull_request, dict) and pull_request.get("id"):
                resource_hint = (
                    f"{resource_hint}#pr-{pull_request['id']}"
                    if resource_hint
                    else f"pr-{pull_request['id']}"
                )
            if isinstance(issue, dict) and issue.get("id"):
                resource_hint = (
                    f"{resource_hint}#issue-{issue['id']}"
                    if resource_hint
                    else f"issue-{issue['id']}"
                )
            sender = payload.get("sender", {})
            actor_hint = sender.get("login") if isinstance(sender, dict) else None
            return {
                "delivery_id": lowered_headers.get("x-github-delivery", fallback_delivery_id),
                "event_type": lowered_headers.get("x-github-event", "unknown"),
                "resource_hint": resource_hint,
                "actor_hint": actor_hint,
            }

        if provider == WebhookProvider.SLACK:
            event = payload.get("event", {})
            actor_hint = event.get("user") if isinstance(event, dict) else None
            channel = event.get("channel") if isinstance(event, dict) else None
            return {
                "delivery_id": str(payload.get("event_id") or fallback_delivery_id),
                "event_type": str(payload.get("type") or "event_callback"),
                "resource_hint": str(channel) if channel else None,
                "actor_hint": str(actor_hint) if actor_hint else None,
            }

        if provider == WebhookProvider.JIRA:
            issue = payload.get("issue", {})
            user = payload.get("user", {})
            resource_hint = None
            if isinstance(issue, dict):
                resource_hint = issue.get("key") or issue.get("id")
            actor_hint = user.get("displayName") if isinstance(user, dict) else None
            delivery_id = (
                lowered_headers.get("x-atlassian-webhook-identifier")
                or str(payload.get("timestamp") or fallback_delivery_id)
            )
            return {
                "delivery_id": delivery_id,
                "event_type": str(payload.get("webhookEvent") or "jira.updated"),
                "resource_hint": str(resource_hint) if resource_hint else None,
                "actor_hint": str(actor_hint) if actor_hint else None,
            }

        page = payload.get("page", {})
        user = payload.get("user", {})
        resource_hint = None
        if isinstance(page, dict):
            resource_hint = page.get("title") or page.get("id")
        actor_hint = user.get("displayName") if isinstance(user, dict) else None
        delivery_id = (
            lowered_headers.get("x-atlassian-webhook-identifier")
            or str(payload.get("timestamp") or fallback_delivery_id)
        )
        return {
            "delivery_id": delivery_id,
            "event_type": str(payload.get("eventType") or "confluence.updated"),
            "resource_hint": str(resource_hint) if resource_hint else None,
            "actor_hint": str(actor_hint) if actor_hint else None,
        }

    def normalize_envelope(
        self,
        provider: WebhookProvider,
        headers: Mapping[str, str],
        payload: dict[str, Any],
        verification: WebhookVerificationResult,
        raw_body: bytes,
    ) -> WebhookDeliveryEnvelope:
        payload_hash = hashlib.sha256(raw_body).hexdigest()
        metadata = self.extract_delivery_metadata(provider, headers, payload, payload_hash)
        return WebhookDeliveryEnvelope(
            provider=provider,
            delivery_id=str(metadata["delivery_id"]),
            event_type=str(metadata["event_type"]),
            verified=verification.verified,
            verification_method=verification.verification_method,
            verification_reason=verification.verification_reason,
            headers_json=self._compact_headers(headers),
            payload_hash=payload_hash,
            resource_hint=metadata["resource_hint"],
            actor_hint=metadata["actor_hint"],
            status="accepted" if verification.accepted else "rejected",
        )

    async def persist_delivery(self, envelope: WebhookDeliveryEnvelope) -> None:
        await self._store.persist_delivery(envelope)

    async def list_deliveries(
        self,
        provider: WebhookProvider | None = None,
        verified: bool | None = None,
        limit: int = 20,
    ) -> list[WebhookDeliveryEnvelope]:
        return await self._store.list_deliveries(provider, verified, limit)

    def _verify_github(
        self,
        raw_body: bytes,
        headers: dict[str, str],
    ) -> WebhookVerificationResult:
        if not self._settings.github_webhook_secret:
            return WebhookVerificationResult(
                accepted=True,
                verified=False,
                verification_method="optional_hmac_sha256",
                verification_reason="No GitHub webhook secret configured.",
            )

        signature = headers.get("x-hub-signature-256")
        if not signature:
            return WebhookVerificationResult(
                accepted=False,
                verified=False,
                verification_method="hmac_sha256",
                verification_reason="Missing X-Hub-Signature-256 header.",
                status_code=401,
            )
        expected = self._sha256_signature(self._settings.github_webhook_secret, raw_body)
        if not hmac.compare_digest(signature, expected):
            return WebhookVerificationResult(
                accepted=False,
                verified=False,
                verification_method="hmac_sha256",
                verification_reason="GitHub webhook signature did not match.",
                status_code=401,
            )
        return WebhookVerificationResult(
            accepted=True,
            verified=True,
            verification_method="hmac_sha256",
            verification_reason="GitHub webhook signature matched.",
        )

    def _verify_slack(
        self,
        raw_body: bytes,
        headers: dict[str, str],
    ) -> WebhookVerificationResult:
        if not self._settings.slack_signing_secret:
            return WebhookVerificationResult(
                accepted=True,
                verified=False,
                verification_method="optional_slack_signature",
                verification_reason="No Slack signing secret configured.",
            )

        timestamp = headers.get("x-slack-request-timestamp")
        signature = headers.get("x-slack-signature")
        if not timestamp or not signature:
            return WebhookVerificationResult(
                accepted=False,
                verified=False,
                verification_method="slack_signature",
                verification_reason="Missing Slack signature headers.",
                status_code=401,
            )

        try:
            request_age = abs(int(time.time()) - int(timestamp))
        except ValueError:
            return WebhookVerificationResult(
                accepted=False,
                verified=False,
                verification_method="slack_signature",
                verification_reason="Invalid Slack request timestamp.",
                status_code=401,
            )

        if request_age > SLACK_SIGNATURE_TTL_SECONDS:
            return WebhookVerificationResult(
                accepted=False,
                verified=False,
                verification_method="slack_signature",
                verification_reason="Slack request timestamp exceeded the allowed skew.",
                status_code=401,
            )

        basestring = f"v0:{timestamp}:{raw_body.decode()}".encode()
        expected = "v0=" + hmac.new(
            self._settings.slack_signing_secret.encode(),
            basestring,
            hashlib.sha256,
        ).hexdigest()
        if not hmac.compare_digest(signature, expected):
            return WebhookVerificationResult(
                accepted=False,
                verified=False,
                verification_method="slack_signature",
                verification_reason="Slack request signature did not match.",
                status_code=401,
            )
        return WebhookVerificationResult(
            accepted=True,
            verified=True,
            verification_method="slack_signature",
            verification_reason="Slack request signature matched.",
        )

    def _verify_jira(self, headers: dict[str, str]) -> WebhookVerificationResult:
        if not self._settings.jira_webhook_shared_secret:
            return WebhookVerificationResult(
                accepted=True,
                verified=False,
                verification_method="optional_shared_secret",
                verification_reason="No Jira shared secret configured.",
            )

        header_secret = headers.get("x-webhook-shared-secret")
        if header_secret and hmac.compare_digest(
            header_secret,
            self._settings.jira_webhook_shared_secret,
        ):
            return WebhookVerificationResult(
                accepted=True,
                verified=True,
                verification_method="shared_secret_header",
                verification_reason="Jira shared secret matched.",
            )
        return WebhookVerificationResult(
            accepted=True,
            verified=False,
            verification_method="shared_secret_header",
            verification_reason="Jira shared secret was missing or did not match.",
        )

    def _verify_confluence(
        self,
        raw_body: bytes,
        headers: dict[str, str],
    ) -> WebhookVerificationResult:
        if not self._settings.confluence_webhook_secret:
            return WebhookVerificationResult(
                accepted=True,
                verified=False,
                verification_method="optional_hmac_sha256",
                verification_reason="No Confluence webhook secret configured.",
            )

        signature = headers.get("x-hub-signature")
        if not signature:
            return WebhookVerificationResult(
                accepted=True,
                verified=False,
                verification_method="hmac_sha256",
                verification_reason="Missing X-Hub-Signature header.",
            )

        expected = self._sha256_signature(
            self._settings.confluence_webhook_secret,
            raw_body,
        )
        if not hmac.compare_digest(signature, expected):
            return WebhookVerificationResult(
                accepted=True,
                verified=False,
                verification_method="hmac_sha256",
                verification_reason="Confluence webhook signature did not match.",
            )
        return WebhookVerificationResult(
            accepted=True,
            verified=True,
            verification_method="hmac_sha256",
            verification_reason="Confluence webhook signature matched.",
        )

    def _sha256_signature(self, secret: str, raw_body: bytes) -> str:
        digest = hmac.new(secret.encode(), raw_body, hashlib.sha256).hexdigest()
        return f"sha256={digest}"

    def _normalize_headers(self, headers: Mapping[str, str]) -> dict[str, str]:
        return {key.lower(): value for key, value in headers.items()}

    def _compact_headers(self, headers: Mapping[str, str]) -> dict[str, str]:
        compact: dict[str, str] = {}
        for key, value in headers.items():
            lowered = key.lower()
            if lowered.startswith("x-") or lowered in {"content-type", "user-agent"}:
                compact[lowered] = value
        return compact
