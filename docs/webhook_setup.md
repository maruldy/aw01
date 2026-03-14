# 웹훅 수신 설정

하네스는 GitHub, Slack, Jira, Confluence용 수신 전용 웹훅 엔드포인트를 제공합니다. 현재 단계에서 엔드포인트는 수신을 검증, 정규화, 로깅, 확인 응답만 합니다. 작업 항목을 생성하지 않습니다.

## localhost를 외부 서비스에 노출하기

외부 서비스는 `localhost`에 직접 접근할 수 없습니다. 다음 방법 중 하나를 선택하여 하네스를 접근 가능하게 만드세요.

### 방법 A — 터널 (로컬 개발)

터널링 도구를 사용하여 로컬 서버로 포워딩되는 공개 URL을 얻습니다.

**ngrok**

```bash
# 설치: https://ngrok.com/download
ngrok http 8000
# 출력: https://xxxx-xx-xx.ngrok-free.app -> http://localhost:8000
```

**cloudflared (Cloudflare Tunnel)**

```bash
# 설치: brew install cloudflared
cloudflared tunnel --url http://localhost:8000
# 출력: https://xxxx.trycloudflare.com -> http://localhost:8000
```

터널을 시작한 후 `.env`의 `WEBHOOK_BASE_URL`을 공개 URL로 설정합니다:

```
WEBHOOK_BASE_URL=https://xxxx-xx-xx.ngrok-free.app
```

그런 다음 각 외부 서비스의 웹훅 설정에 해당 URL을 등록합니다.

### 방법 B — 서버 배포

공개 IP 또는 도메인이 있는 서버에 하네스를 배포합니다. 예:

```bash
docker compose up -d
# 서버 접근: https://harness.your-company.com
```

`WEBHOOK_BASE_URL`을 서버의 공개 URL로 설정합니다.

### 방법 C — 로컬 시뮬레이션 (외부 서비스 없이)

외부 서비스를 건너뛰고 `curl`로 웹훅을 시뮬레이션합니다:

```bash
# GitHub PR 웹훅 시뮬레이션
curl -X POST http://localhost:8000/webhooks/github \
  -H "Content-Type: application/json" \
  -H "X-GitHub-Event: pull_request" \
  -H "X-GitHub-Delivery: local-test-001" \
  -d '{"action":"opened","pull_request":{"id":1,"number":42,"title":"test PR","body":"description"},"repository":{"full_name":"owner/repo"},"sender":{"login":"dev"}}'

# 이벤트 수집 시뮬레이션 (웹훅 검증 우회)
curl -X POST http://localhost:8000/ingress/slack \
  -H "Content-Type: application/json" \
  -d '{"event_type":"slack.mention","title":"test","body":"hello","external_id":"t1","actor":"U123"}'
```

## 공통 사전 요구사항

- `.env`의 `WEBHOOK_BASE_URL`을 외부에서 접근 가능한 서버 기본 URL로 설정합니다.
- 시크릿은 `.env`에 보관합니다. 현재 단계에서는 UI를 통한 웹훅 시크릿 저장을 지원하지 않습니다.
- 각 외부 시스템에서 수동으로 웹훅을 등록합니다.

## GitHub Enterprise Cloud

- 콜백 URL: `WEBHOOK_BASE_URL/webhooks/github`
- 시크릿 환경변수: `GITHUB_WEBHOOK_SECRET`
- 검증: 시크릿이 설정된 경우 `X-Hub-Signature-256` HMAC SHA-256
- 권장 이벤트:
  - `pull_request`
  - `pull_request_review`
  - `pull_request_review_comment`
  - `issues`
  - `issue_comment`

## Slack Enterprise Grid

- 콜백 URL: `WEBHOOK_BASE_URL/webhooks/slack/events`
- 시크릿 환경변수: `SLACK_SIGNING_SECRET`
- 검증: `X-Slack-Signature` + `X-Slack-Request-Timestamp`
- 권장 이벤트:
  - `app_mention`
  - `message.im`
  - `message.channels`
- 참고:
  - Slack은 라이브 이벤트 콜백 시작 전에 `url_verification` 챌린지를 보냅니다.

## Jira 자체 호스팅 Enterprise

- 콜백 URL: `WEBHOOK_BASE_URL/webhooks/jira`
- 선택적 시크릿 환경변수: `JIRA_WEBHOOK_SHARED_SECRET`
- 검증: `X-Webhook-Shared-Secret`를 통한 선택적 공유 시크릿
- 권장 이벤트:
  - `jira:issue_created`
  - `jira:issue_updated`
  - `comment_created`
  - `issue_generic`

## Confluence 자체 호스팅 Enterprise

- 콜백 URL: `WEBHOOK_BASE_URL/webhooks/confluence`
- 선택적 시크릿 환경변수: `CONFLUENCE_WEBHOOK_SECRET`
- 검증: 시크릿이 설정된 경우 `X-Hub-Signature` HMAC SHA-256
- 권장 이벤트:
  - `page_created`
  - `page_updated`
  - `comment_created`
