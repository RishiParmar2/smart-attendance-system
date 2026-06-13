import secrets
import string
import hashlib
import base64
from datetime import datetime, timedelta
from cryptography.fernet import Fernet
import uuid

class TokenGenerator:
    """Cryptographically secure token generation for QR codes"""
    
    @staticmethod
    def generate_qr_token(length: int = 32) -> str:
        """
        Generate a cryptographically secure random token for QR code.
        Uses Python's secrets module for cryptographic randomness.
        
        Args:
            length: Token length in bytes
            
        Returns:
            Base64-encoded secure token string
        """
        # Generate random bytes and encode to base64
        random_bytes = secrets.token_bytes(length)
        token = base64.urlsafe_b64encode(random_bytes).decode('utf-8').rstrip('=')
        return token
    
    @staticmethod
    def generate_verification_code(length: int = 4) -> str:
        """
        Generate a human-readable alphanumeric verification code.
        Used for the code displayed on projector screen.
        
        Args:
            length: Code length (default 4 for format X7P4)
            
        Returns:
            Alphanumeric code string (uppercase)
        """
        # Use uppercase letters and digits, excluding confusing chars (0/O, 1/I/L)
        charset = 'ABCDEFGHJKMNPQRSTUVWXYZ23456789'
        code = ''.join(secrets.choice(charset) for _ in range(length))
        return code
    
    @staticmethod
    def generate_decoy_codes(correct_code: str, count: int = 3) -> list:
        """
        Generate randomized decoy verification codes for the 4-option grid.
        Ensures decoys don't accidentally match the correct code.
        
        Args:
            correct_code: The correct verification code
            count: Number of decoy codes to generate (default 3)
            
        Returns:
            List of unique decoy codes
        """
        decoys = set()
        charset = 'ABCDEFGHJKMNPQRSTUVWXYZ23456789'
        
        while len(decoys) < count:
            decoy = ''.join(secrets.choice(charset) for _ in range(len(correct_code)))
            # Ensure decoy is unique and doesn't match correct code
            if decoy != correct_code and decoy not in decoys:
                decoys.add(decoy)
        
        return list(decoys)
    
    @staticmethod
    def generate_session_id() -> str:
        """Generate a UUID-based session identifier"""
        return str(uuid.uuid4())
    
    @staticmethod
    def generate_record_id() -> str:
        """Generate a UUID-based record identifier"""
        return str(uuid.uuid4())


class PasswordHasher:
    """Secure password hashing and verification using bcrypt"""
    
    @staticmethod
    def hash_password(password: str) -> str:
        """
        Hash a password using bcrypt (use in production).
        NOTE: For production, use bcrypt library: 
              pip install bcrypt
              import bcrypt
              return bcrypt.hashpw(password.encode(), bcrypt.gensalt(rounds=12)).decode()
        
        Args:
            password: Plain text password
            
        Returns:
            Bcrypt hashed password string
        """
        try:
            import bcrypt
            salt = bcrypt.gensalt(rounds=12)
            hashed = bcrypt.hashpw(password.encode('utf-8'), salt)
            return hashed.decode('utf-8')
        except ImportError:
            # Fallback to SHA256 if bcrypt not installed (NOT RECOMMENDED FOR PRODUCTION)
            return hashlib.sha256(password.encode()).hexdigest()
    
    @staticmethod
    def verify_password(password: str, password_hash: str) -> bool:
        """
        Verify a plain text password against a bcrypt hash.
        
        Args:
            password: Plain text password to verify
            password_hash: Bcrypt hash from database
            
        Returns:
            True if password matches, False otherwise
        """
        try:
            import bcrypt
            return bcrypt.checkpw(password.encode('utf-8'), password_hash.encode('utf-8'))
        except ImportError:
            # Fallback comparison if bcrypt not installed (NOT RECOMMENDED FOR PRODUCTION)
            return hashlib.sha256(password.encode()).hexdigest() == password_hash


class DeviceFingerprint:
    """Device fingerprinting for forensic audit trail"""
    
    @staticmethod
    def generate_fingerprint(user_agent: str, accept_language: str = None, 
                           screen_resolution: str = None) -> str:
        """
        Generate a device fingerprint hash from browser and device characteristics.
        Used to detect proxy attempts and unusual access patterns.
        
        Args:
            user_agent: Browser User-Agent string
            accept_language: Accept-Language header
            screen_resolution: Screen resolution from JavaScript (WIDTHxHEIGHT)
            
        Returns:
            SHA256 hash of combined fingerprint data
        """
        fingerprint_data = user_agent
        
        if accept_language:
            fingerprint_data += f"|{accept_language}"
        if screen_resolution:
            fingerprint_data += f"|{screen_resolution}"
        
        # SHA256 hash of combined data
        fingerprint_hash = hashlib.sha256(fingerprint_data.encode()).hexdigest()
        return fingerprint_hash


class GPSCoordinateHandler:
    """Secure GPS coordinate handling with privacy safeguards"""
    
    @staticmethod
    def sanitize_gps_coordinates(latitude: float, longitude: float, 
                                 precision: int = 4) -> str:
        """
        Sanitize GPS coordinates to reduce precision (privacy-preserving).
        Reduces tracking granularity while maintaining geo-location verification.
        
        Args:
            latitude: Latitude value
            longitude: Longitude value
            precision: Decimal places to retain (default 4 = ~11m accuracy)
            
        Returns:
            Formatted coordinate string "LAT,LON"
        """
        try:
            lat = round(float(latitude), precision)
            lon = round(float(longitude), precision)
            return f"{lat},{lon}"
        except (ValueError, TypeError):
            return None
    
    @staticmethod
    def is_within_campus(latitude: float, longitude: float, 
                         campus_center_lat: float = 28.5355,
                         campus_center_lon: float = 77.1910,
                         radius_km: float = 1.0) -> bool:
        """
        Check if GPS coordinates are within campus boundaries (haversine formula).
        Helps detect proxy attempts from students outside campus.
        
        Args:
            latitude: Student device latitude
            longitude: Student device longitude
            campus_center_lat: College campus center latitude (default: Delhi)
            campus_center_lon: College campus center longitude
            radius_km: Campus radius in kilometers
            
        Returns:
            True if within campus, False otherwise
        """
        from math import radians, sin, cos, sqrt, atan2
        
        R = 6371  # Earth's radius in kilometers
        
        lat1, lon1 = radians(campus_center_lat), radians(campus_center_lon)
        lat2, lon2 = radians(latitude), radians(longitude)
        
        dlat = lat2 - lat1
        dlon = lon2 - lon1
        
        a = sin(dlat/2)**2 + cos(lat1) * cos(lat2) * sin(dlon/2)**2
        c = 2 * atan2(sqrt(a), sqrt(1-a))
        distance = R * c
        
        return distance <= radius_km


class RequestValidator:
    """Request validation and anti-CSRF measures"""
    
    @staticmethod
    def extract_client_ip(request) -> str:
        """
        Extract client IP address from Flask request object.
        Handles X-Forwarded-For header for proxied requests.
        
        Args:
            request: Flask request object
            
        Returns:
            Client IP address string
        """
        if request.environ.get('HTTP_X_FORWARDED_FOR'):
            # Behind a proxy
            return request.environ['HTTP_X_FORWARDED_FOR'].split(',')[0].strip()
        return request.remote_addr
    
    @staticmethod
    def is_valid_ipv4(ip: str) -> bool:
        """Validate IPv4 address format"""
        parts = ip.split('.')
        if len(parts) != 4:
            return False
        try:
            return all(0 <= int(part) <= 255 for part in parts)
        except ValueError:
            return False
    
    @staticmethod
    def is_valid_ipv6(ip: str) -> bool:
        """Validate IPv6 address format"""
        try:
            import ipaddress
            ipaddress.IPv6Address(ip)
            return True
        except (ValueError, ImportError):
            return False


class AuditLogger:
    """Forensic event logging for compliance and security auditing"""
    
    @staticmethod
    def log_attendance_event(session_id: str, enrollment_no: str, event_type: str,
                            event_data: dict, ip_address: str) -> dict:
        """
        Create a structured audit log entry for attendance events.
        
        Args:
            session_id: Attendance session identifier
            enrollment_no: Student enrollment number
            event_type: Type of event (e.g., "QR_SCANNED", "CODE_SUBMITTED", "TOKEN_EXPIRED")
            event_data: Dictionary of event-specific data
            ip_address: Client IP address
            
        Returns:
            Log entry dictionary
        """
        log_entry = {
            'timestamp': datetime.utcnow().isoformat(),
            'session_id': session_id,
            'enrollment_no': enrollment_no,
            'event_type': event_type,
            'ip_address': ip_address,
            'event_data': event_data,
        }
        return log_entry
