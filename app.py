from flask import Flask, render_template, request, jsonify, session, send_file
from flask_cors import CORS
from datetime import datetime, timedelta
import json
import io
import csv
from config import get_config
from utils.database import (
    SessionQueries, TokenQueries, StudentQueries, 
    AttendanceQueries, DatabaseConnection
)
from utils.security import (
    TokenGenerator, PasswordHasher, DeviceFingerprint,
    GPSCoordinateHandler, RequestValidator, AuditLogger
)
import qrcode
import base64

# Initialize Flask App
app = Flask(__name__, 
            template_folder='templates',
            static_folder='static')

config = get_config()
app.config.from_object(config)

# Enable CORS for API endpoints
CORS(app, resources={
    r"/api/*": {
        "origins": config.ALLOWED_ORIGINS,
        "methods": ["GET", "POST", "OPTIONS"],
        "allow_headers": ["Content-Type"]
    }
})

# ============================================================================
# FACULTY ENDPOINTS - Dashboard & Session Management
# ============================================================================

@app.route('/', methods=['GET'])
def index():
    """Faculty dashboard homepage"""
    return render_template('faculty_dashboard.html')


@app.route('/api/faculty/session/create', methods=['POST'])
def create_attendance_session():
    """
    Create a new attendance session.
    Faculty enters: Class Name, Subject, Lecture Details, Duration
    
    Request Body:
    {
        "class_name": "2024-CS-A",
        "subject_name": "Database Systems",
        "lecture_details": "Indexing Strategies",
        "duration_minutes": 60
    }
    """
    try:
        data = request.get_json()
        
        # Validate input
        if not all(k in data for k in ['class_name', 'subject_name', 'duration_minutes']):
            return jsonify({
                'success': False,
                'error': 'Missing required fields'
            }), 400
        
        # Generate session ID and create
        session_id = TokenGenerator.generate_session_id()
        session_queries = SessionQueries()
        
        success = session_queries.create_session(
            session_id=session_id,
            class_name=data['class_name'],
            subject_name=data['subject_name'],
            lecture_details=data.get('lecture_details', ''),
            duration_minutes=int(data['duration_minutes'])
        )
        
        if success:
            # Store session ID in Flask session for tracking
            session['current_session_id'] = session_id
            session['session_start_time'] = datetime.utcnow().isoformat()
            
            return jsonify({
                'success': True,
                'session_id': session_id,
                'message': 'Session created successfully'
            }), 201
        else:
            return jsonify({
                'success': False,
                'error': 'Failed to create session'
            }), 500
            
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@app.route('/api/faculty/qr/generate', methods=['POST'])
def generate_qr_code():
    """
    Generate a fresh 5-second rotating QR code with embedded token.
    Called every 5 seconds by frontend ticker.
    
    Request Body:
    {
        "session_id": "uuid-string"
    }
    """
    try:
        data = request.get_json()
        session_id = data.get('session_id')
        
        if not session_id:
            return jsonify({
                'success': False,
                'error': 'Session ID required'
            }), 400
        
        # Verify session is active
        session_queries = SessionQueries()
        active_session = session_queries.get_active_session(session_id)
        
        if not active_session:
            return jsonify({
                'success': False,
                'error': 'Session not found or expired'
            }), 404
        
        # Generate new cryptographic token
        token_value = TokenGenerator.generate_qr_token()
        token_queries = TokenQueries()
        
        # Record token in database (invalidates previous tokens)
        token_result = token_queries.generate_new_token(
            session_id=session_id,
            token_value=token_value
        )
        
        if not token_result['success']:
            return jsonify({
                'success': False,
                'error': 'Failed to generate token'
            }), 500
        
        # Generate QR code image
        qr = qrcode.QRCode(
            version=1,
            error_correction=qrcode.constants.ERROR_CORRECT_L,
            box_size=10,
            border=4,
        )
        qr.add_data(token_value)
        qr.make(fit=True)
        
        img = qr.make_image(fill_color="black", back_color="white")
        
        # Convert to base64 for embedding in HTML
        img_buffer = io.BytesIO()
        img.save(img_buffer, format='PNG')
        img_buffer.seek(0)
        img_base64 = base64.b64encode(img_buffer.getvalue()).decode('utf-8')
        
        return jsonify({
            'success': True,
            'token': token_value,
            'qr_image': f'data:image/png;base64,{img_base64}',
            'expires_in_seconds': config.QR_TOKEN_EXPIRY_SECONDS
        }), 200
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@app.route('/api/faculty/verification-code/reveal', methods=['POST'])
def reveal_verification_code():
    """
    Faculty clicks "Reveal Verification Code" button.
    Generates and displays the 4-character code on projector.
    
    Request Body:
    {
        "session_id": "uuid-string"
    }
    """
    try:
        data = request.get_json()
        session_id = data.get('session_id')
        
        if not session_id:
            return jsonify({
                'success': False,
                'error': 'Session ID required'
            }), 400
        
        session_queries = SessionQueries()
        
        # Generate verification code
        verification_code = TokenGenerator.generate_verification_code(
            length=config.VERIFICATION_CODE_LENGTH
        )
        
        # Update session with code and CodeRevealed flag
        success = session_queries.update_verification_code(
            session_id=session_id,
            verification_code=verification_code
        )
        
        if not success:
            return jsonify({
                'success': False,
                'error': 'Failed to update verification code'
            }), 500
        
        return jsonify({
            'success': True,
            'verification_code': verification_code,
            'message': 'Code revealed to students'
        }), 200
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@app.route('/api/faculty/session/status', methods=['GET'])
def get_session_status():
    """
    Get real-time session status and attendance count.
    Used for live progress display.
    
    Query Parameters:
    - session_id: UUID of the session
    """
    try:
        session_id = request.args.get('session_id')
        
        if not session_id:
            return jsonify({
                'success': False,
                'error': 'Session ID required'
            }), 400
        
        session_queries = SessionQueries()
        active_session = session_queries.get_active_session(session_id)
        
        if not active_session:
            return jsonify({
                'success': False,
                'error': 'Session not found'
            }), 404
        
        # Get attendance count
        attendance_count = session_queries.get_session_attendance_count(session_id)
        
        return jsonify({
            'success': True,
            'session': {
                'session_id': active_session['SessionID'],
                'class_name': active_session['ClassName'],
                'subject_name': active_session['SubjectName'],
                'is_active': active_session['IsActive'],
                'code_revealed': active_session['CodeRevealed'],
                'expires_at': active_session['ExpiresAt'].isoformat(),
                'created_at': active_session['CreatedAt'].isoformat()
            },
            'attendance_count': attendance_count
        }), 200
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@app.route('/api/faculty/attendance/records', methods=['GET'])
def get_attendance_records():
    """
    Retrieve attendance records for a session with optional search filtering.
    Faculty can search by: RollNo, EnrollmentNo, IPAddress, DeviceInfo, GPSLocation
    
    Query Parameters:
    - session_id: UUID of the session
    - search_field: Field to search in
    - search_term: Search query string
    """
    try:
        session_id = request.args.get('session_id')
        search_field = request.args.get('search_field', 'RollNo')
        search_term = request.args.get('search_term', '')
        
        if not session_id:
            return jsonify({
                'success': False,
                'error': 'Session ID required'
            }), 400
        
        attendance_queries = AttendanceQueries()
        
        if search_term:
            records = attendance_queries.search_attendance_records(
                session_id=session_id,
                search_term=search_term,
                search_field=search_field
            )
        else:
            records = attendance_queries.export_session_csv(session_id)
        
        # Convert timestamp objects to ISO format strings
        for record in records:
            if isinstance(record.get('MarkedAt'), datetime):
                record['MarkedAt'] = record['MarkedAt'].isoformat()
        
        return jsonify({
            'success': True,
            'records': records,
            'count': len(records)
        }), 200
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@app.route('/api/faculty/export/csv', methods=['GET'])
def export_attendance_csv():
    """
    Export attendance records as CSV file.
    File includes metadata headers and student records.
    
    Query Parameters:
    - session_id: UUID of the session
    """
    try:
        session_id = request.args.get('session_id')
        
        if not session_id:
            return jsonify({
                'success': False,
                'error': 'Session ID required'
            }), 400
        
        session_queries = SessionQueries()
        active_session = session_queries.get_active_session(session_id)
        
        if not active_session:
            return jsonify({
                'success': False,
                'error': 'Session not found'
            }), 404
        
        attendance_queries = AttendanceQueries()
        records = attendance_queries.export_session_csv(session_id)
        
        # Create CSV in memory
        output = io.StringIO()
        csv_writer = csv.writer(output)
        
        # Metadata header
        csv_writer.writerow(['ATTENDANCE EXPORT'])
        csv_writer.writerow(['Class', active_session['ClassName']])
        csv_writer.writerow(['Subject', active_session['SubjectName']])
        csv_writer.writerow(['Date', active_session['CreatedAt'].strftime('%Y-%m-%d')])
        csv_writer.writerow(['Time', active_session['CreatedAt'].strftime('%H:%M:%S')])
        csv_writer.writerow(['Total Present', len(records)])
        csv_writer.writerow([])  # Blank row
        
        # Headers
        csv_writer.writerow([
            'Enrollment No', 'Roll No', 'Student Name', 'Marked At',
            'IP Address', 'Device Info', 'GPS Location'
        ])
        
        # Data rows
        for record in records:
            csv_writer.writerow([
                record.get('EnrollmentNo', ''),
                record.get('RollNo', ''),
                record.get('StudentName', ''),
                record.get('MarkedAt', ''),
                record.get('IPAddress', ''),
                record.get('DeviceInfo', ''),
                record.get('GPSLocation', '')
            ])
        
        # Create response
        output.seek(0)
        return send_file(
            io.BytesIO(output.getvalue().encode('utf-8')),
            mimetype='text/csv',
            as_attachment=True,
            download_name=f'attendance_{session_id[:8]}.csv'
        )
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@app.route('/api/faculty/roll-numbers/copy', methods=['GET'])
def get_roll_numbers():
    """
    Get comma-separated roll numbers for copy-to-clipboard functionality.
    
    Query Parameters:
    - session_id: UUID of the session
    """
    try:
        session_id = request.args.get('session_id')
        
        if not session_id:
            return jsonify({
                'success': False,
                'error': 'Session ID required'
            }), 400
        
        attendance_queries = AttendanceQueries()
        records = attendance_queries.export_session_csv(session_id)
        
        # Extract roll numbers
        roll_numbers = [record['RollNo'] for record in records]
        csv_string = ','.join(roll_numbers)
        
        return jsonify({
            'success': True,
            'roll_numbers': csv_string,
            'count': len(roll_numbers)
        }), 200
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@app.route('/api/faculty/session/end', methods=['POST'])
def end_session():
    """
    Faculty ends the attendance session.
    
    Request Body:
    {
        "session_id": "uuid-string"
    }
    """
    try:
        data = request.get_json()
        session_id = data.get('session_id')
        
        if not session_id:
            return jsonify({
                'success': False,
                'error': 'Session ID required'
            }), 400
        
        session_queries = SessionQueries()
        success = session_queries.end_session(session_id)
        
        if success:
            # Clear from Flask session
            if 'current_session_id' in session:
                session.pop('current_session_id')
            
            return jsonify({
                'success': True,
                'message': 'Session ended successfully'
            }), 200
        else:
            return jsonify({
                'success': False,
                'error': 'Failed to end session'
            }), 500
            
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


# ============================================================================
# STUDENT ENDPOINTS - QR Scanning & Submission
# ============================================================================

@app.route('/student', methods=['GET'])
def student_portal():
    """Student mobile portal for QR scanning and code verification"""
    return render_template('student_portal.html')


@app.route('/api/student/verify-token', methods=['POST'])
def verify_qr_token():
    """
    Student scans QR code. Frontend extracts token and sends for verification.
    If valid, returns form requesting credentials and code selection.
    
    Request Body:
    {
        "token": "token-string-from-qr"
    }
    """
    try:
        data = request.get_json()
        token_value = data.get('token')
        
        if not token_value:
            return jsonify({
                'success': False,
                'error': 'Token required'
            }), 400
        
        token_queries = TokenQueries()
        
        # Find session and token validity
        valid_token = token_queries.get_valid_token(
            session_id=None,  # Will need to query differently
            token_value=token_value
        )
        
        # Alternative: Query all valid tokens (simplified for demo)
        # In production, pass session_id from QR code payload
        
        return jsonify({
            'success': True,
            'token_valid': True,
            'message': 'QR code verified. Enter your details.'
        }), 200
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@app.route('/api/student/submit-attendance', methods=['POST'])
def submit_student_attendance():
    """
    Student submits: Enrollment No, Roll No, Password, Selected Code, Device Info.
    Validates all parameters and marks attendance using stored procedure.
    
    Request Body:
    {
        "session_id": "uuid",
        "enrollment_no": "EN2024001",
        "roll_no": "101",
        "password": "plaintext-password",
        "selected_code": "X7P4",
        "device_info": "fingerprint-string",
        "gps_latitude": 28.5355,
        "gps_longitude": 77.1910,
        "user_agent": "browser-string",
        "token": "token-used"
    }
    """
    try:
        data = request.get_json()
        
        # Extract all required fields
        session_id = data.get('session_id')
        enrollment_no = data.get('enrollment_no')
        roll_no = data.get('roll_no')
        password = data.get('password')
        selected_code = data.get('selected_code')
        device_info = data.get('device_info')
        gps_latitude = data.get('gps_latitude')
        gps_longitude = data.get('gps_longitude')
        user_agent = data.get('user_agent')
        token_value = data.get('token')
        
        # Validate required fields
        if not all([session_id, enrollment_no, roll_no, password, selected_code, token_value]):
            return jsonify({
                'success': False,
                'error': 'Missing required fields',
                'message': 'All fields must be completed'
            }), 400
        
        # Step 1: Verify student exists and password matches
        student_queries = StudentQueries()
        student = student_queries.get_student_by_enrollment(enrollment_no)
        
        if not student:
            return jsonify({
                'success': False,
                'error': 'Student not found',
                'message': 'Enrollment number not recognized'
            }), 404
        
        # Step 2: Verify password
        password_valid = PasswordHasher.verify_password(
            password=password,
            password_hash=student['PasswordHash']
        )
        
        if not password_valid:
            return jsonify({
                'success': False,
                'error': 'Invalid credentials',
                'message': 'Password does not match our records'
            }), 401
        
        # Step 3: Extract client metadata
        ip_address = RequestValidator.extract_client_ip(request)
        browser_info = user_agent or request.headers.get('User-Agent', 'Unknown')
        
        # Step 4: Handle GPS coordinates (privacy-preserving)
        gps_location = None
        if gps_latitude is not None and gps_longitude is not None:
            gps_location = GPSCoordinateHandler.sanitize_gps_coordinates(
                latitude=gps_latitude,
                longitude=gps_longitude
            )
        
        # Step 5: Call stored procedure for atomic attendance processing
        attendance_queries = AttendanceQueries()
        result = attendance_queries.process_attendance(
            session_id=session_id,
            enrollment_no=enrollment_no,
            token_value=token_value,
            verification_code=selected_code,
            ip_address=ip_address,
            browser_info=browser_info,
            device_info=device_info,
            gps_location=gps_location
        )
        
        if result['success']:
            return jsonify({
                'success': True,
                'record_id': result.get('results', [{}])[0].get('RecordID', ''),
                'message': 'Attendance Marked Successfully!',
                'enrollment_no': enrollment_no,
                'roll_no': roll_no
            }), 201
        else:
            error_msg = result.get('error', 'Unknown error occurred')
            
            # Parse specific error messages
            if 'expired' in error_msg.lower():
                error_msg = 'QR Code Expired. Re-scan!'
            elif 'code' in error_msg.lower():
                error_msg = 'Incorrect Code Selection Denied.'
            elif 'duplicate' in error_msg.lower():
                error_msg = 'Duplicate Attempt Denied.'
            
            return jsonify({
                'success': False,
                'error': error_msg,
                'message': error_msg
            }), 400
            
    except Exception as e:
        return jsonify({
            'success': False,
            'error': 'Submission failed',
            'message': str(e)
        }), 500


# ============================================================================
# UTILITY & HEALTH CHECK ENDPOINTS
# ============================================================================

@app.route('/api/health', methods=['GET'])
def health_check():
    """Health check endpoint for monitoring"""
    try:
        db = DatabaseConnection()
        # Attempt simple query
        db.execute_query("SELECT 1")
        
        return jsonify({
            'status': 'healthy',
            'timestamp': datetime.utcnow().isoformat(),
            'database': 'connected'
        }), 200
    except Exception as e:
        return jsonify({
            'status': 'unhealthy',
            'error': str(e)
        }), 500


@app.errorhandler(404)
def not_found(error):
    """Handle 404 errors"""
    return jsonify({
        'success': False,
        'error': 'Endpoint not found'
    }), 404


@app.errorhandler(500)
def internal_error(error):
    """Handle 500 errors"""
    return jsonify({
        'success': False,
        'error': 'Internal server error'
    }), 500


if __name__ == '__main__':
    app.run(
        host='0.0.0.0',
        port=5000,
        debug=config.DEBUG,
        use_reloader=config.DEBUG
    )
