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
# SSH and deploy
sshpass -p 'boogerBitersRpKewl26!' ssh -o StrictHostKeyChecking=no root@69.164.201.191 "cd /var/www/prplbry && git pull && pkill -f 'python.*app.py' && sleep 1 && cd /var/www/prplbry && nohup ./venv/bin/python app.py > /dev/null 2>&1 &"
```

## Key Features
- Chat-based PRD generation
- Task priority management (medium/high)
- PRD copy/paste restore functionality
- Browser refresh creates new session
- Delete messages and rebuild PRD
- Support for multiple tech stacks (Python, Flask, Node, React, ESP32, Arduino)
