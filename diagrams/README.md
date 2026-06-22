# CiteVyn Diagrams

## 1. Purpose

This folder contains the canonical architecture diagrams for CiteVyn.

The diagrams are written as Markdown files with Mermaid blocks so they remain:

- version-control friendly
- readable in pull requests
- easy to update with architecture changes
- renderable in GitHub, GitLab, VS Code, and Mermaid-compatible documentation tools

These diagrams describe the MVP architecture while keeping the design extensible for later enterprise scale.

## 2. Diagram Index

| Diagram | File | Primary Audience |
|---|---|---|
| System Context | [01-system-context.md](01-system-context.md) | Product, architecture, security reviewers |
| Container Architecture | [02-container-architecture.md](02-container-architecture.md) | Engineers, DevOps, platform reviewers |
| Backend Component Architecture | [03-backend-component-architecture.md](03-backend-component-architecture.md) | Backend engineers, Staff+ reviewers |
| Main Request Sequence | [04-main-request-sequence.md](04-main-request-sequence.md) | Backend engineers, QA, SRE |
| Data Model ERD | [05-data-model-erd.md](05-data-model-erd.md) | Backend engineers, data reviewers |
| Deployment Architecture | [06-deployment-architecture.md](06-deployment-architecture.md) | DevOps, SRE, release owners |
| Observability and Alerting Flow | [07-observability-and-alerting-flow.md](07-observability-and-alerting-flow.md) | SRE, QA, engineering leadership |

## 3. When Each Diagram Should Be Updated

| Diagram | Update When |
|---|---|
| System Context | Supported products, external systems, trust boundaries, or user personas change |
| Container Architecture | Deployable services, stores, queues, model providers, or runtime boundaries change |
| Backend Component Architecture | Backend modules, routing flow, retrieval responsibilities, or quality gates change |
| Main Request Sequence | Runtime request flow, answer-generation policy, cache behavior, or no-answer path changes |
| Data Model ERD | Tables, relationships, ownership boundaries, or retention needs change |
| Deployment Architecture | Hosting model, Docker Compose layout, networking, secrets, or scaling approach changes |
| Observability and Alerting Flow | Logs, traces, metrics, alerts, dashboards, or evaluation reporting changes |

## 4. Mermaid Rendering Notes

1. These diagrams intentionally use simple Mermaid syntax for broad renderer compatibility.
2. Architecture diagrams use `flowchart LR` or `flowchart TD`.
3. The runtime flow uses `sequenceDiagram`.
4. The data model uses `erDiagram`.
5. Node labels are kept short to avoid Mermaid rendering issues.
6. Detailed explanations are placed below diagrams instead of inside nodes.
7. A later visual polish pass may improve layout without changing canonical filenames.

## 5. Canonical Diagram Filename Rule

Only the canonical diagram filenames listed in the diagram index should be used.

Do not introduce alternate sequence or observability diagram filenames without explicit approval.
