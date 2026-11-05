# ChessPulse roles

Operating manuals for a specific kind of work. Read the role that matches the task; the shared rules stay in `AGENT.md`, `process.md` and `spec.md`.

| Role | File | Owns |
|---|---|---|
| Product Manager | [`pm.md`](pm.md) | problem → testable spec, scope, priorities, issue quality |
| DevOps Engineer | [`devops-engineer.md`](devops-engineer.md) | Docker, Compose, CI/CD, Render/AWS, deployment verification |
| UI/UX Developer | [`ui-ux-developer.md`](ui-ux-developer.md) | React surfaces, theme, accessibility, board and game-details UX |

## How roles interact

- A role describes a boundary, not a silo. A change that crosses boundaries follows every role it touches and says so in the report.
- Role docs must stay true to the repository. When a command, path or deploy shape changes, update the matching role in the same pull request.
- No role overrides `AGENT.md` or an approved product decision. If a role and the specification disagree, stop and surface the conflict instead of silently choosing one.
