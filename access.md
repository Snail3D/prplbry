# prplbry Server Access

## Server Details
- **IP Address**: 69.164.201.191
- **Username**: root
- **Password**: `boogerBitersRpKewl26!`

## Quick Access
```bash
# SSH directly (enter password when prompted)
ssh root@69.164.201.191

# SSH with sshpass (use double quotes for password with !)
sshpass -p "boogerBitersRpKewl26!" ssh -o StrictHostKeyChecking=no root@69.164.201.191
```

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

# Restart the app (run in background)
cd /var/www/prplbry && ./venv/bin/python app.py &

# View logs
journalctl -u prplbry -f
# or
tail -f /var/www/prplbry/app.log
```

## Git Deployment
```bash
# Pull latest changes (set git remote to SSH first)
cd /var/www/prplbry && git remote set-url origin git@github.com:Snail3D/prplbry.git
git pull

# Or force reset if conflicts
git fetch origin && git reset --hard origin/main

# Then restart app
cd /var/www/prplbry && ./venv/bin/python app.py &
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
