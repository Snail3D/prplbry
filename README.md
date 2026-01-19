# 🫐 prplbry

**[**prplbry.com**](https://prplbry.com)** — Chat with Ralph. Build a PRD. Done.

*The hamster tastes like chicken.* — Hee hee.

---

## The Ralph Loop

**Ralph pre-builds your PRD while you chat.**

He starts with the exact structure Claude Code's agent loop expects:

```
00_security → 01_setup → 02_core → 03_api → 04_test
```

Every task gets an ID: `SEC-001`, `SET-001`, `CORE-100`

That's the secret sauce.

When you export, Claude Code reads the IDs and runs the loop automatically.

**You chat → Ralph fills structure → Agent executes**

---

## How

1. Go to **prplbry.com**
2. Tell Ralph your idea
3. Watch the PRD build itself live
4. Copy, paste into Claude Code

*My cat's breath smells like cat food.* — Hee hee.

---

## Functions

| What | How |
|------|-----|
| **Chat** | Natural conversation |
| **Live PRD** | Updates in real-time |
| **Restore** | Paste any PRD, keep building |
| **Export** | Claude Code ready |

---

## Privacy

We store nothing.

- No analytics
- No tracking
- No persistent cookies
- No data sold
- No logs

Your PRD generates in real-time. Once you copy, it's gone. Forever.

---

## Self-Deployment

```bash
git clone https://github.com/Snail3D/prplbry.git
cd prplbry && pip install -r requirements.txt
export SECRET_KEY=$(python -c 'import secrets; print(secrets.token_urlsafe(32))')
python app.py
```

Visit `localhost:8000`

---

## Contributing

**No tracking. Ever.**

PRs adding analytics, telemetry, or surveillance will be rejected.

---

MIT License • [Buy Me a Coffee](https://buymeacoffee.com/snail3d) • [YouTube](https://www.youtube.com/playlist?list=PLJB4l6OZ0E3FvDzSlb6RZLNnB5CHcLu4S)
