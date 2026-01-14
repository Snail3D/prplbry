# 🍇 prplbry - Purple Berry PRD Creator

AI-powered PRD creator that helps you build product requirements documents through natural conversation.

## Features

- 🗣️ **Natural conversation flow** - Chat with Ralph to build your PRD
- 🎯 **7-step guided process** - From vision to technical constraints
- 🎨 **Aesthetics tracking** - Color schemes, inspiration sites, design vibes
- 🔑 **Service tracking** - Automatically detects API keys you'll need
- 📥 **One-click launch scripts** - Download shell scripts for Mac/Windows/Linux
- 🐙 **GitHub integration** - Auto-init repos and configure remotes
- 💾 **No login required** - Just open and use
- 🆓 **Free AI** - Uses GROQ API (or Ollama for local)

## Quick Start

### Option 1: Use prplbry.com (easiest)
Just visit https://prplbry.com and start building!

### Option 2: Run locally

```bash
# Install dependencies
pip install -r requirements.txt

# Set up environment
cp .env.example .env
# Edit .env and add your GROQ API key

# Run the app
python app.py
```

Visit http://localhost:5000

## Environment Variables

| Variable | Description | Required |
|----------|-------------|----------|
| `GROQ_API_KEY` | Your GROQ API key | Yes* |
| `SECRET_KEY` | Flask secret key | Yes |
| `DEBUG` | Debug mode | No (default: True) |
| `PORT` | Port to run on | No (default: 5000) |
| `OLLAMA_BASE_URL` | Local Ollama URL | No* |

*Either GROQ_API_KEY or Ollama is required

## Get a GROQ API Key

1. Visit https://groq.com
2. Sign up for free account
3. Get your API key from the dashboard
4. Add it to your `.env` file

## Development

```bash
# Install dev dependencies
pip install -r requirements.txt

# Run with debug mode
DEBUG=True python app.py

# Run tests
pytest tests/
```

## Deployment

### Render.com (recommended)

1. Push code to GitHub
2. Connect repo to Render.com
3. Add environment variables:
   - `GROQ_API_KEY`: Your GROQ API key
   - `SECRET_KEY`: Generate a random string
   - `DEBUG`: `False`
   - `PORT`: `5000`

4. Deploy! Render will auto-deploy from GitHub

### Docker

```bash
docker build -t prplbry .
docker run -p 5000:5000 --env-file .env prplbry
```

## License

MIT - go wild!

## Support

If prplbry helps you build something cool, consider supporting the creator:

https://buymeacoffee.com/snail3d

☕ Your support keeps prplbry free and improving!
