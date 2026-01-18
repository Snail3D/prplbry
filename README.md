# 🍇 prplbry - Purple Berry PRD Creator

Chat-based PRD creator. No AI API keys required - just conversation.

## Features

- 💬 **Chat interface** - Build your PRD through natural conversation
- 📋 **Task priorities** - Toggle features between Medium/High priority
- 🗑️ **Delete to rebuild** - Remove any message and PRD updates automatically
- 📋 **PRD restore** - Copy a PRD, paste it later, continue building
- 🔄 **Fresh sessions** - Browser refresh = completely new start
- 🎯 **Multi-stack support** - Python, Flask, Node, React, ESP32, Arduino, and more
- 💾 **Copy-ready PRD** - Export in compressed format ready for Claude Code

## Quick Start

### Use prplbry.com
Visit https://prplbry.com and start building!

### Run Locally

```bash
# Install dependencies
pip install -r requirements.txt

# Generate secret key
python -c 'import secrets; print(secrets.token_urlsafe(32))'

# Run the app
SECRET_KEY=<your-key> python app.py
```

Visit http://localhost:8000

## How It Works

1. Tell Ralph what you're building (one sentence)
2. Add your tech stack (or say "I don't know")
3. Describe features and requirements
4. Set priorities on each feature
5. Export your PRD

## PRD Format

The exported PRD uses compressed keys for efficiency:

```
pn = project_name
pd = project_description
ts = tech_stack
p  = prds (categories)
t  = tasks
pr = priority
```

## Server Deployment

```bash
# Clone repo
git clone https://github.com/Snail3D/prplbry.git
cd prplbry

# Setup
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# Run with gunicorn
gunicorn -w 4 -b 0.0.0.0:8000 app:app
```

Set `SECRET_KEY` environment variable.

## License

MIT

## Support

https://buymeacoffee.com/snail3d
