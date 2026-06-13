import pymysql
import json
from contextlib import contextmanager
from datetime import datetime, timedelta
from config import get_config

config = get_config()

class DatabaseConnection:
    """MySQL database connection manager with connection pooling"""
    
    _instance = None
    _connections = []
    _max_connections = 10
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(DatabaseConnection, cls).__new__(cls)
        return cls._instance
    
    def __init__(self):
        """Initialize connection pool"""
        self.config = get_config()
    
    @contextmanager
    def get_connection(self):
        """
        Context manager for database connections.
        Ensures proper connection closure and error handling.
        
        Usage:
            with db.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(query, params)
                results = cursor.fetchall()
        """
        connection = None
        try:
            connection = pymysql.connect(
                host=self.config.MYSQL_HOST,
                user=self.config.MYSQL_USER,
                password=self.config.MYSQL_PASSWORD,
                database=self.config.MYSQL_DATABASE,
                port=self.config.MYSQL_PORT,
                charset='utf8mb4',
                cursorclass=pymysql.cursors.DictCursor,
                autocommit=False
            )
            yield connection
        except pymysql.Error as e:
            if connection:
                connection.rollback()
            raise Exception(f"Database connection error: {str(e)}")
        finally:
            if connection:
                connection.close()
    
    def execute_query(self, query: str, params: tuple = None, fetch_one: bool = False):
        """
        Execute a SELECT query and return results.
        
        Args:
            query: SQL query string with %s placeholders
            params: Tuple of parameters to bind
            fetch_one: If True, return single row; otherwise return all rows
            
        Returns:
            Query result(s) or None
        """
        with self.get_connection() as conn:
            try:
                with conn.cursor() as cursor:
                    cursor.execute(query, params or ())
                    if fetch_one:
                        return cursor.fetchone()
                    return cursor.fetchall()
            except pymysql.Error as e:
                raise Exception(f"Query execution error: {str(e)}")
    
    def execute_update(self, query: str, params: tuple = None) -> int:
        """
        Execute an INSERT, UPDATE, or DELETE query.
        
        Args:
            query: SQL query string with %s placeholders
            params: Tuple of parameters to bind
            
        Returns:
            Number of rows affected
        """
        with self.get_connection() as conn:
            try:
                with conn.cursor() as cursor:
                    cursor.execute(query, params or ())
                    conn.commit()
                    return cursor.rowcount
            except pymysql.Error as e:
                conn.rollback()
                raise Exception(f"Update execution error: {str(e)}")
    
    def call_stored_procedure(self, proc_name: str, params: tuple = None) -> dict:
        """
        Call a stored procedure and retrieve results.
        
        Args:
            proc_name: Name of stored procedure
            params: Tuple of procedure parameters
            
        Returns:
            Dictionary of output parameters and results
        """
        with self.get_connection() as conn:
            try:
                with conn.cursor() as cursor:
                    # Build param placeholders
                    placeholders = ','.join(['%s'] * (len(params) if params else 0))
                    query = f"CALL {proc_name}({placeholders})"
                    
                    cursor.execute(query, params or ())
                    
                    # Get results
                    results = cursor.fetchall()
                    
                    conn.commit()
                    
                    return {
                        'success': True,
                        'results': results,
                        'rows_affected': cursor.rowcount
                    }
            except pymysql.Error as e:
                conn.rollback()
                return {
                    'success': False,
                    'error': str(e)
                }


class StudentQueries:
    """Database queries for student operations"""
    
    def __init__(self):
        self.db = DatabaseConnection()
    
    def get_student_by_enrollment(self, enrollment_no: str) -> dict:
        """Retrieve student record by enrollment number"""
        query = """
            SELECT EnrollmentNo, RollNo, StudentName, PasswordHash, CreatedAt
            FROM Students
            WHERE EnrollmentNo = %s
        """
        return self.db.execute_query(query, (enrollment_no,), fetch_one=True)
    
    def get_student_by_roll(self, roll_no: str) -> dict:
        """Retrieve student record by roll number"""
        query = """
            SELECT EnrollmentNo, RollNo, StudentName, PasswordHash, CreatedAt
            FROM Students
            WHERE RollNo = %s
        """
        return self.db.execute_query(query, (roll_no,), fetch_one=True)
    
    def create_student(self, enrollment_no: str, roll_no: str, 
                      student_name: str, password_hash: str) -> bool:
        """Create a new student record"""
        query = """
            INSERT INTO Students (EnrollmentNo, RollNo, StudentName, PasswordHash)
            VALUES (%s, %s, %s, %s)
        """
        try:
            rows = self.db.execute_update(query, (enrollment_no, roll_no, student_name, password_hash))
            return rows > 0
        except Exception:
            return False


class SessionQueries:
    """Database queries for attendance session operations"""
    
    def __init__(self):
        self.db = DatabaseConnection()
    
    def create_session(self, session_id: str, class_name: str, subject_name: str,
                       lecture_details: str = None, duration_minutes: int = 60) -> bool:
        """Create a new attendance session"""
        expires_at = datetime.utcnow() + timedelta(minutes=duration_minutes)
        
        query = """
            INSERT INTO AttendanceSessions 
            (SessionID, ClassName, SubjectName, LectureDetails, IsActive, ExpiresAt, CreatedAt)
            VALUES (%s, %s, %s, %s, TRUE, %s, NOW())
        """
        try:
            rows = self.db.execute_update(query, (session_id, class_name, subject_name, 
                                                   lecture_details, expires_at))
            return rows > 0
        except Exception:
            return False
    
    def get_active_session(self, session_id: str) -> dict:
        """Retrieve active session by ID"""
        query = """
            SELECT SessionID, ClassName, SubjectName, LectureDetails, 
                   VerificationCode, IsActive, CodeRevealed, ExpiresAt, CreatedAt
            FROM AttendanceSessions
            WHERE SessionID = %s AND IsActive = TRUE AND ExpiresAt > NOW()
        """
        return self.db.execute_query(query, (session_id,), fetch_one=True)
    
    def update_verification_code(self, session_id: str, verification_code: str) -> bool:
        """Update and reveal verification code for a session"""
        query = """
            UPDATE AttendanceSessions
            SET VerificationCode = %s, CodeRevealed = TRUE, UpdatedAt = NOW()
            WHERE SessionID = %s AND IsActive = TRUE
        """
        try:
            rows = self.db.execute_update(query, (verification_code, session_id))
            return rows > 0
        except Exception:
            return False
    
    def end_session(self, session_id: str) -> bool:
        """Mark a session as inactive"""
        query = """
            UPDATE AttendanceSessions
            SET IsActive = FALSE, UpdatedAt = NOW()
            WHERE SessionID = %s
        """
        try:
            rows = self.db.execute_update(query, (session_id,))
            return rows > 0
        except Exception:
            return False
    
    def get_session_attendance_count(self, session_id: str) -> int:
        """Get count of students marked present in a session"""
        query = """
            SELECT COUNT(*) as count
            FROM AttendanceRecords
            WHERE SessionID = %s AND VerificationCodeMatched = TRUE
        """
        result = self.db.execute_query(query, (session_id,), fetch_one=True)
        return result['count'] if result else 0
    
    def get_session_attendance_records(self, session_id: str) -> list:
        """Retrieve all attendance records for a session"""
        query = """
            SELECT RecordID, SessionID, EnrollmentNo, RollNo, MarkedAt,
                   IPAddress, BrowserInfo, DeviceInfo, GPSLocation
            FROM AttendanceRecords
            WHERE SessionID = %s
            ORDER BY MarkedAt DESC
        """
        return self.db.execute_query(query, (session_id,))


class TokenQueries:
    """Database queries for dynamic token operations"""
    
    def __init__(self):
        self.db = DatabaseConnection()
    
    def generate_new_token(self, session_id: str, token_value: str, 
                          token_id: str = None) -> dict:
        """Generate a new QR token using stored procedure"""
        from utils.security import TokenGenerator
        
        if token_id is None:
            token_id = TokenGenerator.generate_session_id()
        
        expires_at = datetime.utcnow() + timedelta(seconds=5)
        
        # Use stored procedure
        result = self.db.call_stored_procedure(
            'GenerateNewQRToken',
            (session_id, token_value, expires_at)
        )
        
        return result
    
    def get_valid_token(self, session_id: str, token_value: str) -> dict:
        """Retrieve a valid token for verification"""
        query = """
            SELECT TokenID, SessionID, TokenValue, IsValid, ExpiresAt, CreatedAt
            FROM DynamicTokens
            WHERE SessionID = %s AND TokenValue = %s AND IsValid = TRUE
                  AND ExpiresAt > NOW()
        """
        return self.db.execute_query(query, (session_id, token_value), fetch_one=True)
    
    def get_latest_token(self, session_id: str) -> dict:
        """Get the most recent valid token for a session"""
        query = """
            SELECT TokenID, SessionID, TokenValue, IsValid, ExpiresAt, CreatedAt
            FROM DynamicTokens
            WHERE SessionID = %s AND IsValid = TRUE
            ORDER BY CreatedAt DESC
            LIMIT 1
        """
        return self.db.execute_query(query, (session_id,), fetch_one=True)


class AttendanceQueries:
    """Database queries for attendance record operations"""
    
    def __init__(self):
        self.db = DatabaseConnection()
    
    def process_attendance(self, session_id: str, enrollment_no: str, token_value: str,
                          verification_code: str, ip_address: str, browser_info: str,
                          device_info: str, gps_location: str = None) -> dict:
        """Process student attendance using stored procedure"""
        result = self.db.call_stored_procedure(
            'ProcessStudentAttendance',
            (session_id, enrollment_no, token_value, verification_code,
             ip_address, browser_info, device_info, gps_location)
        )
        return result
    
    def check_duplicate_attendance(self, session_id: str, enrollment_no: str) -> bool:
        """Check if student already marked present in this session"""
        query = """
            SELECT COUNT(*) as count
            FROM AttendanceRecords
            WHERE SessionID = %s AND EnrollmentNo = %s
        """
        result = self.db.execute_query(query, (session_id, enrollment_no), fetch_one=True)
        return result['count'] > 0 if result else False
    
    def search_attendance_records(self, session_id: str, search_term: str, 
                                 search_field: str = 'RollNo') -> list:
        """
        Search attendance records by various fields.
        Supports: RollNo, EnrollmentNo, IPAddress, DeviceInfo, GPSLocation
        """
        allowed_fields = ['RollNo', 'EnrollmentNo', 'IPAddress', 'DeviceInfo', 'GPSLocation']
        
        if search_field not in allowed_fields:
            search_field = 'RollNo'
        
        query = f"""
            SELECT RecordID, SessionID, EnrollmentNo, RollNo, MarkedAt,
                   IPAddress, BrowserInfo, DeviceInfo, GPSLocation
            FROM AttendanceRecords
            WHERE SessionID = %s AND {search_field} LIKE %s
            ORDER BY MarkedAt DESC
        """
        
        search_pattern = f"%{search_term}%"
        return self.db.execute_query(query, (session_id, search_pattern))
    
    def export_session_csv(self, session_id: str) -> list:
        """Export attendance records in CSV format"""
        query = """
            SELECT 
                ar.EnrollmentNo,
                ar.RollNo,
                s.StudentName,
                ar.MarkedAt,
                ar.IPAddress,
                ar.DeviceInfo,
                ar.GPSLocation
            FROM AttendanceRecords ar
            JOIN Students s ON ar.EnrollmentNo = s.EnrollmentNo
            WHERE ar.SessionID = %s
            ORDER BY ar.MarkedAt ASC
        """
        return self.db.execute_query(query, (session_id,))
