# prplbry Server Access

## Server Details
- **IP Address**: 69.164.201.191
- **Username**: root
- **Password**: `boogerBitersRpKewl26!`

## Quick Access
```bash
# SSH directly
ssh root@69.164.201.191
# Password: boogerBitersRpKewl26!

# SSH with sshpass (one-liner)
sshpass -p 'boogerBitersRpKewl26!' ssh -o StrictHostKeyChecking=no root@69.164.201.191

## App Location
- **Path**: /var/www/prplbry
- **Runs on**: Port 8000
- **Proxy**: nginx on port 80 → 8000

## App Management
```bash
# Check if app is running
ps aux | grep 'python.*app.py' | grep -v grep

# Kill the app
pkill -f 'python.*app.py'

# Restart the app
cd /var/www/prplbry && nohup ./venv/bin/python app.py > /dev/null 2>&1 &

# View logs
journalctl -u prplbry -f
# or
tail -f /var/www/prplbry/app.log
```

## Git Deployment
```bash
# Pull latest changes
cd /var/www/prplbry && git pull

# Or force reset if conflicts
cd /var/www/prplbry && git fetch origin && git reset --hard origin/main

# Then restart app
pkill -f 'python.*app.py' && nohup ./venv/bin/python app.py > /dev/null 2>&1 &
```

## Nginx Config
```bash
# Reload nginx
nginx -s reload

# Check nginx status
systemctl status nginx

# View nginx error logs
tail -f /var/log/nginx/error.log
```
