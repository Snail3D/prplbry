# Claude Code Project - prplbry

## Project Overview
prplbry is a PRD (Product Requirements Document) generator that helps developers quickly create project specifications through an interactive chat interface.

## Development

### Local Development
```bash
# Install dependencies
pip install -r requirements.txt

# Run the app
python app.py
```

### Server Deployment
Server: 69.164.201.191
Path: /var/www/prplbry
Password: `boogerBitersRpKewl26!`

### Deploy Commands
```bash
# SSH and deploy (use double quotes for password with special character)
sshpass -p "boogerBitersRpKewl26!" ssh -o StrictHostKeyChecking=no root@69.164.201.191 "cd /var/www/prplbry && git pull"

# Restart app (kill and run in background)
sshpass -p "boogerBitersRpKewl26!" ssh -o StrictHostKeyChecking=no root@69.164.201.191 "cd /var/www/prplbry && ./venv/bin/python app.py"
```

## Key Features
- Chat-based PRD generation (no AI required for chat)
- All tasks set to high priority
- PRD copy/paste restore functionality
- Browser refresh creates new session
- Support for multiple tech stacks (Python, Flask, Node, React, ESP32, Arduino)
