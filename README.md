# LangGraph Work Harness

엔터프라이즈 운영을 위한 이벤트 기반 AI 작업 하네스. Jira, Confluence, Slack, GitHub에서 들어오는 활동을 채팅 응답 대신 운영자 대면 작업 항목(work item)으로 변환하는 LangGraph supervisor를 중심으로 구축되었습니다.

## 포함 내용

- LangGraph supervisor 그래프가 포함된 FastAPI 백엔드
- 자체 호스팅 Jira/Confluence 어댑터, Slack Enterprise Grid 및 GitHub Enterprise Cloud 어댑터
- 도구 허용 목록과 승인 기반 액션 정책을 갖춘 안전 하네스
- SQLite 기반 지식 저장소 및 스케줄러 서비스
- SQLite를 원본으로, ChromaDB를 시맨틱 인덱스로 사용하는 하이브리드 지식 검색
- 인박스, 실행, 지식, 설정 뷰가 있는 React + Vite 프론트엔드
- 로컬 개발 도구: `.env.example`, `Makefile`, Docker, GitHub Actions CI

## 로컬 개발

```bash
cp .env.example .env
make setup
make setup-web
make run-api
make run-web
```

프론트엔드는 `http://localhost:5173`, 백엔드는 `http://localhost:8000`에서 실행됩니다.

## 아키텍처 참고

- Jira와 Confluence는 자체 호스팅 엔터프라이즈 배포를 전제로 합니다.
- Slack과 GitHub는 클라우드 엔터프라이즈 제품을 전제로 합니다.
- MCP는 코어 런타임에 필요하지 않습니다. SaaS 및 자체 호스팅 시스템 접근은 타입이 지정된 커넥터 어댑터를 통하고, 로컬 사이드 이펙트는 허용 목록에 등록된 CLI 레지스트리를 통합니다.
- UI는 push-first 방식입니다: 에이전트가 작업 항목을 생성하면, 운영자가 `accept`, `reject`, `advise`, `defer`로 응답합니다.
- 지식 검색은 local-first 방식입니다. 하네스는 범위 지정된 로컬 지식을 먼저 확인한 후 단일 리소스 원격 폴백을 사용합니다.

지식 동기화 정책은 [knowledge_strategy.md](docs/knowledge_strategy.md)와 [webhook_setup.md](docs/webhook_setup.md)에 문서화되어 있습니다.
