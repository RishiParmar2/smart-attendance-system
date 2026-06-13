# Deployment Instructions

## Local Development

```bash
# Setup virtual environment
python3 -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Initialize database
mysql -u root -p < database/schema.sql

# Configure environment
cp .env.example .env
# Edit .env with your MySQL credentials

# Run development server
python app.py
```

## Production Deployment

### Using Gunicorn + Nginx

```bash
# Install production WSGI server
pip install gunicorn

# Generate secure secret key
python -c "import secrets; print(secrets.token_urlsafe(32))"

# Start Gunicorn (4 worker processes)
gunicorn -w 4 -b 0.0.0.0:5000 --timeout 120 app:app

# Configure systemd service
sudo tee /etc/systemd/system/attendance.service << EOF
[Unit]
Description=Smart Attendance System
After=network.target

[Service]
User=www-data
WorkingDirectory=/path/to/smart-attendance-system
ExecStart=/path/to/venv/bin/gunicorn -w 4 -b 0.0.0.0:5000 app:app
Restart=always

[Install]
WantedBy=multi-user.target
EOF

# Enable service
sudo systemctl daemon-reload
sudo systemctl enable attendance.service
sudo systemctl start attendance.service
```

### Nginx Configuration

```bash
sudo tee /etc/nginx/sites-available/attendance << 'EOF'
upstream attendance_app {
    server 127.0.0.1:5000;
}

server {
    listen 80;
    server_name attendance.college.edu;
    return 301 https://$server_name$request_uri;
}

server {
    listen 443 ssl http2;
    server_name attendance.college.edu;

    ssl_certificate /etc/letsencrypt/live/attendance.college.edu/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/attendance.college.edu/privkey.pem;
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers HIGH:!aNULL:!MD5;

    client_max_body_size 10M;

    location / {
        proxy_pass http://attendance_app;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 120s;
    }
}
EOF

# Enable site
sudo ln -s /etc/nginx/sites-available/attendance /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl restart nginx
```

## Docker Deployment (Optional)

```bash
# Create Dockerfile
cat > Dockerfile << 'EOF'
FROM python:3.10-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 5000
CMD ["gunicorn", "-w", "4", "-b", "0.0.0.0:5000", "app:app"]
EOF

# Build and run
docker build -t smart-attendance:latest .
docker run -e FLASK_ENV=production -e MYSQL_HOST=mysql-db -p 5000:5000 smart-attendance:latest
```

## SSL/TLS Setup

```bash
# Using Let's Encrypt Certbot
sudo apt install certbot python3-certbot-nginx
sudo certbot certonly --nginx -d attendance.college.edu

# Auto-renewal
sudo systemctl enable certbot.timer
sudo systemctl start certbot.timer
```

## Monitoring

```bash
# Check service status
systemctl status attendance.service

# View logs
journalctl -u attendance.service -f

# Monitor Gunicorn
ps aux | grep gunicorn

# Health check endpoint
curl https://attendance.college.edu/api/health
```

## Database Backup

```bash
# Daily backup script
cat > /usr/local/bin/backup-attendance.sh << 'EOF'
#!/bin/bash
DATE=$(date +%Y%m%d_%H%M%S)
mysqldump -u attendance_user -p smart_attendance_db | gzip > /backups/attendance_$DATE.sql.gz
EOF

chmod +x /usr/local/bin/backup-attendance.sh

# Add to crontab
(crontab -l 2>/dev/null; echo "0 2 * * * /usr/local/bin/backup-attendance.sh") | crontab -
```
