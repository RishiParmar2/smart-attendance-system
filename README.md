# QR-Based Smart Attendance System

## 🎯 Overview

A production-ready, hyper-secure QR-based attendance tracking system designed for colleges and educational institutions. This system bridges the gap between faculty and student portals with cryptographic security, forensic audit logging, and a premium "Neon-Dark" UI aesthetic.

**Key Highlights:**
- ⚡ Dynamic 5-second rotating QR codes with cryptographic tokens
- 🔐 Multi-layer security: Token validation, code verification, credential authentication
- 📊 Real-time attendance tracking and forensic audit logging
- 🎨 Premium "Neon-Dark" dashboard with modern Semantic HTML5 + Vanilla JS
- 📱 Mobile-first student portal optimized for smartphones
- 🗄️ MySQL with transactional stored procedures for atomic operations
- 🚀 Flask microservices architecture for scalability

---

## 📋 Table of Contents

1. [System Architecture](#system-architecture)
2. [Installation & Setup](#installation--setup)
3. [Database Schema](#database-schema)
4. [API Documentation](#api-documentation)
5. [Usage Workflow](#usage-workflow)
6. [Security Features](#security-features)
7. [Deployment Guide](#deployment-guide)

---

## 🏗️ System Architecture

### Technology Stack

```
┌─────────────────────────────────────────────────────┐
│              Flask Web Application (Python)         │
│  - RESTful API endpoints for session & attendance   │
│  - QR code generation and token rotation            │
│  - CORS-enabled for cross-domain requests           │
└─────────────────────────────────────────────────────┘
                          ↓
┌─────────────────────────────────────────────────────┐
│         MySQL 5.7+ Database with Stored Procs       │
│  - Atomic transaction handling                      │
│  - Forensic audit trail logging                     │
│  - Composite indexing for performance               │
└─────────────────────────────────────────────────────┘
                          ↓
┌────────────────────────────────────────────────────┐
│  Frontend Layer (HTML5 + Vanilla JS + Bootstrap)   │
│  - Faculty Dashboard (Desktop): Session mgmt       │
│  - Student Portal (Mobile): QR scan & verify       │
└────────────────────────────────────────────────────┘
```

### File Structure

```
smart-attendance-system/
├── app.py                          # Main Flask application
├── config.py                       # Configuration management
├── requirements.txt                # Python dependencies
├── .env.example                    # Environment variables template
│
├── database/
│   └── schema.sql                  # Complete MySQL DDL + stored procedures
│
├── utils/
│   ├── __init__.py
│   ├── database.py                 # Database connection & queries
│   └── security.py                 # Cryptographic utilities
│
├── templates/
│   ├── faculty_dashboard.html      # Faculty control panel
│   └── student_portal.html         # Student mobile interface
│
├── static/
│   └── (CSS/JS served inline in templates)
│
└── README.md                       # This file
```

---

## 🚀 Installation & Setup

### Prerequisites

- Python 3.10+
- MySQL 5.7+ or MariaDB 10.3+
- Node.js 16+ (optional, for frontend build tools)
- Git

### Step 1: Clone Repository

```bash
git clone https://github.com/RishiParmar2/smart-attendance-system.git
cd smart-attendance-system
```

### Step 2: Set Up Python Environment

```bash
# Create virtual environment
python3 -m venv venv

# Activate virtual environment
# On Linux/macOS:
source venv/bin/activate
# On Windows:
venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
```

### Step 3: Set Up MySQL Database

```bash
# Login to MySQL
mysql -u root -p

# Run schema initialization
source database/schema.sql

# Verify tables created
USE smart_attendance_db;
SHOW TABLES;
```

### Step 4: Configure Environment Variables

```bash
# Copy template
cp .env.example .env

# Edit .env with your credentials
nano .env
```

**Required Variables:**

```env
FLASK_ENV=production
FLASK_SECRET_KEY=your-secure-random-key-here
FLASK_DEBUG=False

MYSQL_HOST=localhost
MYSQL_USER=attendance_user
MYSQL_PASSWORD=your-secure-password
MYSQL_DATABASE=smart_attendance_db
MYSQL_PORT=3306

QR_TOKEN_EXPIRY_SECONDS=5
SESSION_GRACE_BUFFER_SECONDS=10
SESSION_DURATION_MINUTES=60
VERIFICATION_CODE_LENGTH=4
```

### Step 5: Run Application

```bash
python app.py
```

Access the system:
- **Faculty Dashboard:** http://localhost:5000/
- **Student Portal:** http://localhost:5000/student
- **Health Check:** http://localhost:5000/api/health

---

## 🗄️ Database Schema

### Tables

#### 1. `Students`
Pre-seeded student registry with credentials.

```sql
CREATE TABLE Students (
    EnrollmentNo VARCHAR(20) PRIMARY KEY,
    RollNo VARCHAR(10) UNIQUE NOT NULL,
    StudentName VARCHAR(100) NOT NULL,
    PasswordHash VARCHAR(255) NOT NULL,  -- Bcrypt hashed
    CreatedAt TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

#### 2. `AttendanceSessions`
Faculty-initiated attendance sessions.

```sql
CREATE TABLE AttendanceSessions (
    SessionID VARCHAR(36) PRIMARY KEY,
    ClassName VARCHAR(50) NOT NULL,
    SubjectName VARCHAR(100) NOT NULL,
    LectureDetails TEXT,
    VerificationCode VARCHAR(10),           -- Revealed code
    IsActive BOOLEAN DEFAULT TRUE,
    CodeRevealed BOOLEAN DEFAULT FALSE,
    ExpiresAt TIMESTAMP NOT NULL,
    CreatedAt TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

#### 3. `DynamicTokens`
5-second rotating QR code tokens.

```sql
CREATE TABLE DynamicTokens (
    TokenID VARCHAR(36) PRIMARY KEY,
    SessionID VARCHAR(36) NOT NULL,
    TokenValue VARCHAR(255) NOT NULL UNIQUE,
    IsValid BOOLEAN DEFAULT TRUE,
    ExpiresAt TIMESTAMP NOT NULL,           -- 5-second window
    CreatedAt TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (SessionID) REFERENCES AttendanceSessions(SessionID)
);
```

#### 4. `AttendanceRecords`
Immutable forensic audit trail.

```sql
CREATE TABLE AttendanceRecords (
    RecordID VARCHAR(36) PRIMARY KEY,
    SessionID VARCHAR(36) NOT NULL,
    EnrollmentNo VARCHAR(20) NOT NULL,
    RollNo VARCHAR(10) NOT NULL,
    MarkedAt TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    IPAddress VARCHAR(45),                  -- IPv4 or IPv6
    BrowserInfo VARCHAR(500),               -- User-Agent
    DeviceInfo VARCHAR(500),                -- Device fingerprint
    GPSLocation VARCHAR(200),               -- Sanitized coordinates
    TokenUsed VARCHAR(255),
    VerificationCodeMatched BOOLEAN DEFAULT FALSE,
    UNIQUE KEY (SessionID, EnrollmentNo),   -- Prevent duplicates
    FOREIGN KEY (SessionID) REFERENCES AttendanceSessions(SessionID),
    FOREIGN KEY (EnrollmentNo) REFERENCES Students(EnrollmentNo)
);
```

### Stored Procedures

#### `GenerateNewQRToken`
Atomically generates and rotates 5-second tokens. Invalidates previous tokens.

```sql
CALL GenerateNewQRToken(session_id, token_value, expires_at, @token_id);
```

#### `ProcessStudentAttendance`
Atomic multi-layer validation:
1. Session validity check
2. Token lifespan verification (5s window + 10s grace)
3. Student credential verification
4. Verification code match
5. Duplicate detection
6. Immutable record insertion

```sql
CALL ProcessStudentAttendance(
    session_id, enrollment_no, token_value, 
    verification_code, ip_address, browser_info, 
    device_info, gps_location,
    @record_id, @success, @error_msg
);
```

---

## 📡 API Documentation

### Faculty Endpoints

#### POST `/api/faculty/session/create`
Create a new attendance session.

**Request:**
```json
{
  "class_name": "2024-CS-A",
  "subject_name": "Database Systems",
  "lecture_details": "Indexing Strategies",
  "duration_minutes": 60
}
```

**Response:**
```json
{
  "success": true,
  "session_id": "uuid-string",
  "message": "Session created successfully"
}
```

---

#### POST `/api/faculty/qr/generate`
Generate fresh QR code (called every 5 seconds).

**Request:**
```json
{ "session_id": "uuid-string" }
```

**Response:**
```json
{
  "success": true,
  "token": "cryptographic-token",
  "qr_image": "data:image/png;base64,...",
  "expires_in_seconds": 5
}
```

---

#### POST `/api/faculty/verification-code/reveal`
Reveal the 4-character code on projector.

**Request:**
```json
{ "session_id": "uuid-string" }
```

**Response:**
```json
{
  "success": true,
  "verification_code": "X7P4",
  "message": "Code revealed to students"
}
```

---

#### GET `/api/faculty/session/status`
Get real-time session status and attendance count.

**Query Parameters:**
- `session_id` (required): UUID of session

**Response:**
```json
{
  "success": true,
  "session": {
    "session_id": "uuid",
    "class_name": "2024-CS-A",
    "subject_name": "Database Systems",
    "is_active": true,
    "code_revealed": true,
    "expires_at": "2024-01-15T10:30:00Z",
    "created_at": "2024-01-15T09:00:00Z"
  },
  "attendance_count": 342
}
```

---

#### GET `/api/faculty/attendance/records`
Retrieve attendance records with optional search filtering.

**Query Parameters:**
- `session_id` (required)
- `search_field` (optional): RollNo, EnrollmentNo, IPAddress, DeviceInfo, GPSLocation
- `search_term` (optional): Search string

**Response:**
```json
{
  "success": true,
  "records": [
    {
      "RecordID": "uuid",
      "RollNo": "101",
      "EnrollmentNo": "EN2024001",
      "MarkedAt": "2024-01-15T09:15:30Z",
      "IPAddress": "192.168.1.100",
      "DeviceInfo": "fingerprint-hash",
      "GPSLocation": "28.5355,77.1910"
    }
  ],
  "count": 342
}
```

---

#### GET `/api/faculty/roll-numbers/copy`
Get comma-separated roll numbers for clipboard.

**Query Parameters:**
- `session_id` (required)

**Response:**
```json
{
  "success": true,
  "roll_numbers": "101,102,103,104,...",
  "count": 342
}
```

---

#### GET `/api/faculty/export/csv`
Download attendance records as CSV.

**Query Parameters:**
- `session_id` (required)

**Returns:** CSV file with metadata headers and attendance records

---

#### POST `/api/faculty/session/end`
End attendance session.

**Request:**
```json
{ "session_id": "uuid-string" }
```

**Response:**
```json
{
  "success": true,
  "message": "Session ended successfully"
}
```

---

### Student Endpoints

#### POST `/api/student/verify-token`
Verify QR token from scanned code.

**Request:**
```json
{ "token": "token-from-qr" }
```

**Response:**
```json
{
  "success": true,
  "token_valid": true,
  "message": "QR code verified. Enter your details."
}
```

---

#### POST `/api/student/submit-attendance`
Submit attendance with credentials and code selection.

**Request:**
```json
{
  "session_id": "uuid",
  "enrollment_no": "EN2024001",
  "roll_no": "101",
  "password": "plaintext-password",
  "selected_code": "X7P4",
  "device_info": "fingerprint",
  "gps_latitude": 28.5355,
  "gps_longitude": 77.1910,
  "user_agent": "browser-string",
  "token": "qr-token-value"
}
```

**Response (Success):**
```json
{
  "success": true,
  "record_id": "uuid",
  "message": "Attendance Marked Successfully!",
  "enrollment_no": "EN2024001",
  "roll_no": "101"
}
```

**Response (Error):**
```json
{
  "success": false,
  "error": "QR Code Expired. Re-scan!",
  "message": "QR Code Expired. Re-scan!"
}
```

---

## 🔄 Usage Workflow

### Faculty Workflow

1. **Start Session**
   - Access faculty dashboard at `/`
   - Enter Class Name, Subject, Lecture Details, Duration
   - Click "Start Attendance"

2. **Display QR Code**
   - QR code auto-refreshes every 5 seconds on projector
   - Students scan the code

3. **Reveal Verification Code**
   - Click "Reveal Verification Code" button
   - 4-character code (e.g., X7P4) displays on projector
   - Students select matching code in their app

4. **Monitor Attendance**
   - Real-time counter shows students marked present
   - Search attendance records by Roll No, IP, Device, GPS
   - Identify proxy attempts from foreign IPs/locations

5. **Export Results**
   - Copy roll numbers to clipboard for CMS import
   - Download CSV with forensic metadata (IP, Device, GPS, Browser)

6. **End Session**
   - Click "End Session" to lock attendance

### Student Workflow

1. **Scan QR Code**
   - Use smartphone camera to scan QR displayed on projector
   - Alternatively, enter token manually if camera unavailable

2. **Enter Credentials**
   - Input: Enrollment Number, Roll Number, Password
   - Pre-seeded students authenticate against bcrypt hashes

3. **Select Verification Code**
   - 4-option radio button grid appears
   - Match the code displayed on projector (1 correct, 3 decoys)
   - Select the correct option

4. **Submit & Confirm**
   - Click "Mark Attendance"
   - Splash confirmation screen: "Attendance Successfully Marked!"
   - Display confirmation details (Enrollment, Roll No, Timestamp)

---

## 🔒 Security Features

### 1. Token Security
- **5-Second Rotation**: Cryptographically secure tokens rotate every 5 seconds
- **Grace Buffer**: 10-second buffer handles network latency
- **One-Time Use**: Tokens invalidated after first scan attempt

### 2. Code Verification
- **Server-Generated**: Verification code generated server-side, not client-side
- **Randomized Decoys**: 3 random decoys prevent brute-force guessing
- **Single Reveal**: Code revealed only once per session to prevent replay attacks

### 3. Credential Authentication
- **Bcrypt Hashing**: Passwords hashed with bcrypt (12 rounds)
- **No Plaintext Storage**: Never store plain passwords
- **Timing-Safe Comparison**: Prevent timing attacks

### 4. Forensic Logging
- **Immutable Records**: All attendance records are append-only
- **Device Fingerprinting**: Browser User-Agent + Hardware signature
- **IP Address Logging**: Detect proxy attempts from off-campus locations
- **GPS Coordinates**: Optional location data (privacy-preserving precision: ~11m)
- **Composite Unique Key**: Prevent duplicate submissions from same student

### 5. Database Security
- **Transactional Integrity**: Stored procedures ensure atomic operations
- **SQL Injection Prevention**: Parameterized queries via PyMySQL
- **Foreign Key Constraints**: Referential integrity enforcement
- **Composite Indexes**: Optimize forensic queries without full scans

### 6. API Security
- **CORS**: Restricted to allowed origins
- **HTTPS-Ready**: Configure `SESSION_COOKIE_SECURE=True` in production
- **Rate Limiting**: (Optional) Add Flask-Limiter for DDoS protection
- **Input Validation**: All user inputs sanitized and validated

---

## 🚀 Deployment Guide

### Production Checklist

```bash
# 1. Set production environment
export FLASK_ENV=production
export FLASK_DEBUG=False

# 2. Generate secure secret key
python -c "import secrets; print(secrets.token_urlsafe(32))"
# Copy output to FLASK_SECRET_KEY in .env

# 3. Install production WSGI server
pip install gunicorn

# 4. Run with Gunicorn
gunicorn -w 4 -b 0.0.0.0:5000 app:app

# 5. (Optional) Use systemd service
# Create /etc/systemd/system/attendance.service
# Configure reverse proxy (Nginx/Apache)
# Enable SSL/TLS with Let's Encrypt
```

### Environment Variables (Production)

```env
FLASK_ENV=production
FLASK_SECRET_KEY=<generated-secure-key>
FLASK_DEBUG=False

MYSQL_HOST=<database-server-ip>
MYSQL_USER=attendance_user
MYSQL_PASSWORD=<strong-password>
MYSQL_DATABASE=smart_attendance_db
MYSQL_PORT=3306

QR_TOKEN_EXPIRY_SECONDS=5
SESSION_GRACE_BUFFER_SECONDS=10
SESSION_DURATION_MINUTES=60
VERIFICATION_CODE_LENGTH=4
```

### Nginx Configuration (Reverse Proxy)

```nginx
server {
    listen 443 ssl http2;
    server_name attendance.college.edu;

    ssl_certificate /etc/letsencrypt/live/attendance.college.edu/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/attendance.college.edu/privkey.pem;

    location / {
        proxy_pass http://localhost:5000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

---

## 📈 Performance Optimization

- **QR Code Caching**: Regenerate only when token expires
- **Database Indexing**: Composite indexes on (SessionID, EnrollmentNo)
- **Connection Pooling**: Configured with 10 max connections
- **Async API**: AJAX submissions prevent page reloads
- **Real-time Updates**: WebSocket polling (3-second intervals)

---

## 🐛 Troubleshooting

### "Database connection error"
- Verify MySQL is running: `mysql -u root -p`
- Check credentials in `.env`
- Ensure `smart_attendance_db` database exists

### "QR code not displaying"
- Verify `qrcode` library installed: `pip install qrcode[pil]`
- Check Flask app logs for errors

### "Token expired" errors
- Increase `SESSION_GRACE_BUFFER_SECONDS` in `.env`
- Verify server time synchronization (NTP)

### "Duplicate attendance rejected"
- This is intentional! Prevents double-marking
- Check if student already submitted earlier

---

## 📄 License

This project is provided as-is for educational institutions. Modify and deploy freely.

---

## 👥 Support & Contributions

For issues or feature requests, open a GitHub issue or contact the development team.

**System Version:** 1.0.0  
**Last Updated:** January 2024
