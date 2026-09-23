# LibLocker - Quick Start Guide

A self-service E-library locker management system using RFID and Raspberry Pi.

## Quick Setup (5 minutes)

### On Raspberry Pi

```bash
# Clone or copy project to liblocker home
cd /home/liblocker/liblocker

# Run automated setup
bash deploy/setup.sh

# Edit configuration
nano .env

# Reboot if SPI was enabled
sudo reboot

# Test RFID reader
python3 scripts/test-rfid.py

# Test GPIO relay
python3 scripts/test-gpio.py

# Start web interface
python3 run.py
```

Access the web interface at: `http://raspberrypi.local:5000`

## Full Setup Guide

For detailed setup instructions including:
- Hardware wiring (RC522 RFID reader)
- GPIO relay connection
- Nginx configuration
- SSL/HTTPS setup
- Database backup
- Troubleshooting

See: [RASPBERRY_PI_SETUP.md](RASPBERRY_PI_SETUP.md)

## Project Structure

```
liblocker/
├── app/                    # Flask application
│   ├── hardware/           # RFID reader, GPIO, camera
│   ├── services/           # Business logic (users, lockers, RFID)
│   ├── routes/             # API endpoints
│   ├── admin/              # Admin dashboard
│   ├── templates/          # HTML templates
│   └── static/             # Admin CSS/JS
├── assets/                 # Frontend CSS/JS/images
├── pages/                  # Kiosk HTML pages
├── deploy/                 # Deployment scripts
│   ├── setup.sh            # Automated setup
│   ├── setup-systemd.sh    # Service installation
│   ├── setup-nginx.sh      # Web server setup
│   ├── liblocker.service   # Systemd unit file
│   └── nginx-liblocker.conf # Nginx config
├── scripts/                # Utility scripts
│   ├── init-db.py          # Database initialization
│   ├── test-rfid.py        # RFID reader test
│   └── test-gpio.py        # GPIO relay test
├── instance/               # Runtime data (database)
├── requirements.txt        # Python dependencies
├── .env.example            # Configuration template
├── run.py                  # Development server
└── wsgi.py                 # Production server
```

## Key Files

| File | Purpose |
|------|---------|
| `.env.example` | Configuration template - copy to `.env` and customize |
| `requirements.txt` | Python dependencies |
| `deploy/setup.sh` | One-command automated setup |
| `scripts/test-rfid.py` | Test RFID reader |
| `scripts/test-gpio.py` | Test GPIO relay control |
| `RASPBERRY_PI_SETUP.md` | Detailed setup guide |

## Features

✅ **User Registration** - RFID card registration  
✅ **Bag Storage** - Select locker location and store  
✅ **Bag Retrieval** - RFID authentication and automatic unlock  
✅ **Admin Dashboard** - Real-time locker status and logs  
✅ **Bilingual UI** - English and Filipino support  
✅ **Hardware Abstraction** - Mock mode for development, real hardware on Pi  
✅ **Transaction Safety** - Database locks prevent race conditions  
✅ **Audit Trail** - Complete logging of all operations  

## Requirements

- **Hardware**: Raspberry Pi 4 or higher (4GB+ RAM)
- **RFID**: RC522 reader (13.56 MHz)
- **Relay**: 24-channel relay module or individual relay circuits
- **Software**: Raspberry Pi OS (Bullseye or newer)

## Configuration

Edit `.env` file (created from `.env.example`):

```env
HARDWARE_MODE=PI
ACTIVE_LOCKER_COUNT=24
HF_RFID_ENABLED=true
GPIO_USE_I2C=true
GPIO_I2C_DRIVER=mcp23017
GPIO_RELAY_I2C_ADDRESSES=0x20,0x21
GPIO_SENSOR_I2C_ADDRESSES=0x22,0x23
REED_SWITCH_NORMALLY_CLOSED=true
GPIO_PULSE_DURATION=0.5
SECRET_KEY=change-to-random-value
ADMIN_TOKEN=change-to-random-value
```

## Web Interface

### User Kiosk
- **Homepage** (http://raspberrypi.local): Start screen
- **Register** (/pages/register.html): Register new user
- **Store Bag** (/pages/store_select.html → /pages/deposit.html): Store items
- **Get Bag** (/pages/retrieve.html): Retrieve items

### Admin Dashboard
- **Dashboard** (http://raspberrypi.local/admin): Summary and stats
- **Lockers** (/admin/lockers): Locker status grid
- **Logs** (/admin/logs): Activity audit logs

## Testing

### RFID Reader Test
```bash
python3 scripts/test-rfid.py
# Place RFID fob near reader when prompted
```

### GPIO Relay Test
```bash
python3 scripts/test-gpio.py
# Listen for relay click sounds
```

### Manual API Test
```bash
curl http://raspberrypi.local/api/health
```

## Development

### Local Development (Windows/Mac/Linux)

```bash
# Setup
python -m venv .venv
source .venv/bin/activate  # or .venv\Scripts\activate on Windows
pip install -r requirements.txt

# Run
python run.py
```

Set in `.env`:
```env
HARDWARE_MODE=DEV
RFID_MOCK_MODE=true
```

### Production Deployment

See [RASPBERRY_PI_SETUP.md](RASPBERRY_PI_SETUP.md) for full production setup with:
- Nginx reverse proxy
- systemd service
- SSL/HTTPS
- Firewall configuration
- Automatic backups

## Troubleshooting

### RFID Not Working
1. Check RC522 power (VCC/GND) - should be 3.3V
2. Verify SPI wiring (MOSI, MISO, CLK, CS)
3. Enable SPI: `sudo raspi-config` → Interfaces → SPI
4. Test: `python3 scripts/test-rfid.py`

### GPIO Not Working
1. Check relay module power supply
2. Verify GPIO pin wiring
3. Add pi user to gpio group: `sudo usermod -a -G gpio pi`
4. Test: `python3 scripts/test-gpio.py`

### Service Not Starting
```bash
sudo systemctl status liblocker
sudo journalctl -u liblocker -n 50
```

## Database

SQLite database located at: `/home/pi/liblocker/instance/liblocker.sqlite`

### Backup
```bash
cp instance/liblocker.sqlite instance/liblocker.sqlite.bak
```

### Reset Database
```bash
rm instance/liblocker.sqlite
python3 scripts/init-db.py
```

## API Documentation

### Health Check
```
GET /api/health
```

### User Registration
```
POST /api/register {full_name, student_id, rfid_uid}
```

### Deposit (Store Bag)
```
POST /api/deposit/assign {rfid_uid, locker_group}
```

### Retrieve (Get Bag)
```
POST /api/retrieve/release {rfid_uid}
```

### Admin API
```
GET /api/admin/summary        # Locker statistics
GET /api/admin/lockers        # All locker details
GET /api/admin/activity       # Activity logs
PATCH /api/admin/lockers/{id} # Update locker status
```

## Security Notes

1. **Change default tokens** in `.env`:
   - `SECRET_KEY`
   - `ADMIN_TOKEN`

2. **Use HTTPS in production**:
   - Follow [RASPBERRY_PI_SETUP.md](RASPBERRY_PI_SETUP.md) for Certbot/Let's Encrypt setup

3. **Database permissions**:
   - SQLite database not exposed via web interface
   - Instance directory blocked in Nginx config

4. **Firewall**:
   - Allow only necessary ports (22 SSH, 80 HTTP, 443 HTTPS)

## Support & Issues

1. Check logs: `sudo journalctl -u liblocker -f`
2. Review [RASPBERRY_PI_SETUP.md](RASPBERRY_PI_SETUP.md) troubleshooting section
3. Test individual components with script tools

## Version

- **LibLocker**: 1.0
- **Python**: 3.7+ (tested on 3.9, 3.11)
- **Flask**: 3.0.3
- **Last Updated**: March 2026

## License

Refer to project license file if present.

## Quick Commands

```bash
# Start development server
python3 run.py

# Start production service
sudo systemctl start liblocker

# View logs
sudo journalctl -u liblocker -f

# Run tests
python3 scripts/test-rfid.py
python3 scripts/test-gpio.py

# Initialize database
python3 scripts/init-db.py

# Access web interface
http://liblocker:5000
```
