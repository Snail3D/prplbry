# 🍇 prplbry - Purple Berry PRD Creator

Chat-based PRD creator. No AI API keys required - just conversation.

## Features

- 💬 **Chat interface** - Build your PRD through natural conversation with Ralph
- 📋 **PRD restore** - Copy a PRD, paste it later, continue building
- 🔄 **Fresh sessions** - Browser refresh = completely new start
- 🎯 **Multi-stack support** - Python, Flask, Node, React, ESP32, Arduino, and more
- 💾 **Copy-ready PRD** - Export in compressed format ready for Claude Code
- 🔒 **Privacy-focused** - Nothing stored, nothing tracked

## Quick Start

### Use prplbry.com
Visit https://prplbry.com and start building!

### Run Locally

```bash
# Clone repo
git clone https://github.com/Snail3D/prplbry.git
cd prplbry

# Create virtual environment
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Generate secret key
python -c 'import secrets; print(secrets.token_urlsafe(32))'

# Set environment variable (Linux/Mac)
export SECRET_KEY=<your-key>

# Set environment variable (Windows)
set SECRET_KEY=<your-key>

# Run the app
python app.py
```

Visit http://localhost:8000

## How It Works

1. Tell Ralph what you're building (one sentence)
2. Add your tech stack (or say "I don't know")
3. Describe features and requirements
4. Export your PRD

## PRD Format

The exported PRD uses compressed keys for efficiency:

```
pn = project_name
pd = project_description
ts = tech_stack
p  = prds (categories)
t  = tasks
```

## Production Deployment

```bash
# Install dependencies
pip install -r requirements.txt

# Run with gunicorn (recommended)
gunicorn -w 8 --threads 2 --bind 0.0.0.0:8000 app:app
```

Required environment variable:
- `SECRET_KEY` - Generate with: `python -c 'import secrets; print(secrets.token_urlsafe(32))'`

Optional (for Redis sessions/rate limiting):
- `REDIS_URL` - Default: `redis://localhost:6379`

## Architecture

- **8 gunicorn workers** with 2 threads each = ~16 concurrent handlers
- **Redis** for shared session storage and rate limiting
- **Rate limiting**: 10000/day, 1000/hour per IP
- Handles hundreds of concurrent users easily

## Contributing

Contributions are welcome, but please note:

**No tracking ever.**

Pull requests that add any form of tracking, analytics, or user surveillance will be automatically rejected. This includes but is not limited to:

- Analytics scripts (Google Analytics, Plausible, Fathom, etc.)
- Telemetry or data collection
- User fingerprinting
- Behavioral tracking
- Third-party trackers

If your contribution adds tracking of any kind, it will not be merged. Ever.

## License

MIT

## Support

https://buymeacoffee.com/snail3d
