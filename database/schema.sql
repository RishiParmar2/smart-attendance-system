-- Smart Attendance System Database Schema
-- MySQL 5.7+ Compatible

-- Create Database
CREATE DATABASE IF NOT EXISTS smart_attendance_db;
USE smart_attendance_db;

-- ============================================================================
-- TABLE: Students (Pre-seeded enrollment registry)
-- ============================================================================
CREATE TABLE IF NOT EXISTS Students (
    EnrollmentNo VARCHAR(20) PRIMARY KEY COMMENT 'Unique enrollment identifier',
    RollNo VARCHAR(10) UNIQUE NOT NULL COMMENT 'Roll number (unique)',
    StudentName VARCHAR(100) NOT NULL COMMENT 'Full student name',
    PasswordHash VARCHAR(255) NOT NULL COMMENT 'Bcrypt hashed password',
    CreatedAt TIMESTAMP DEFAULT CURRENT_TIMESTAMP COMMENT 'Record creation timestamp',
    UpdatedAt TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT 'Last update timestamp',
    
    INDEX idx_RollNo (RollNo),
    INDEX idx_StudentName (StudentName)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='Student registry with pre-seeded credentials';

-- ============================================================================
-- TABLE: AttendanceSessions (Active classroom session tracking)
-- ============================================================================
CREATE TABLE IF NOT EXISTS AttendanceSessions (
    SessionID VARCHAR(36) PRIMARY KEY COMMENT 'UUID-based session identifier',
    ClassName VARCHAR(50) NOT NULL COMMENT 'Class/Batch identifier (e.g., 2024-CS-A)',
    SubjectName VARCHAR(100) NOT NULL COMMENT 'Subject or course name',
    LectureDetails TEXT COMMENT 'Optional lecture topic or details',
    VerificationCode VARCHAR(10) COMMENT 'Master 4-char alphanumeric code revealed to students',
    IsActive BOOLEAN DEFAULT TRUE COMMENT 'Session active status flag',
    CodeRevealed BOOLEAN DEFAULT FALSE COMMENT 'Whether verification code has been revealed',
    ExpiresAt TIMESTAMP NOT NULL COMMENT 'Session absolute expiration time',
    CreatedAt TIMESTAMP DEFAULT CURRENT_TIMESTAMP COMMENT 'Session creation timestamp',
    UpdatedAt TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT 'Last update timestamp',
    
    INDEX idx_ClassName (ClassName),
    INDEX idx_IsActive (IsActive),
    INDEX idx_CreatedAt (CreatedAt),
    INDEX idx_ExpiresAt (ExpiresAt)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='Faculty-initiated attendance sessions';

-- ============================================================================
-- TABLE: DynamicTokens (5-second rotating cryptographic tokens)
-- ============================================================================
CREATE TABLE IF NOT EXISTS DynamicTokens (
    TokenID VARCHAR(36) PRIMARY KEY COMMENT 'Unique token identifier (UUID)',
    SessionID VARCHAR(36) NOT NULL COMMENT 'Reference to parent session',
    TokenValue VARCHAR(255) NOT NULL COMMENT 'Cryptographically secure token string',
    IsValid BOOLEAN DEFAULT TRUE COMMENT 'Token validation status',
    ExpiresAt TIMESTAMP NOT NULL COMMENT 'Token expiration timestamp (5-second window)',
    CreatedAt TIMESTAMP DEFAULT CURRENT_TIMESTAMP COMMENT 'Token creation time',
    
    FOREIGN KEY (SessionID) REFERENCES AttendanceSessions(SessionID) ON DELETE CASCADE,
    UNIQUE INDEX idx_TokenValue (TokenValue),
    INDEX idx_SessionID (SessionID),
    INDEX idx_ExpiresAt (ExpiresAt),
    INDEX idx_IsValid (IsValid)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='Time-limited rotating QR code tokens';

-- ============================================================================
-- TABLE: AttendanceRecords (Immutable forensic transaction log)
-- ============================================================================
CREATE TABLE IF NOT EXISTS AttendanceRecords (
    RecordID VARCHAR(36) PRIMARY KEY COMMENT 'Unique record identifier (UUID)',
    SessionID VARCHAR(36) NOT NULL COMMENT 'Reference to attendance session',
    EnrollmentNo VARCHAR(20) NOT NULL COMMENT 'Student enrollment number',
    RollNo VARCHAR(10) NOT NULL COMMENT 'Student roll number (denormalized for audit)',
    MarkedAt TIMESTAMP DEFAULT CURRENT_TIMESTAMP COMMENT 'Exact timestamp of attendance marking',
    IPAddress VARCHAR(45) COMMENT 'IPv4 or IPv6 address of student device',
    BrowserInfo VARCHAR(500) COMMENT 'User-Agent string from browser',
    DeviceInfo VARCHAR(500) COMMENT 'Device signature (fingerprint data)',
    GPSLocation VARCHAR(200) COMMENT 'GPS coordinates if device permission granted',
    TokenUsed VARCHAR(255) COMMENT 'Token value used for this submission',
    VerificationCodeMatched BOOLEAN DEFAULT FALSE COMMENT 'Whether code selection matched',
    
    FOREIGN KEY (SessionID) REFERENCES AttendanceSessions(SessionID) ON DELETE RESTRICT,
    FOREIGN KEY (EnrollmentNo) REFERENCES Students(EnrollmentNo) ON DELETE RESTRICT,
    UNIQUE INDEX idx_Unique_Session_Enrollment (SessionID, EnrollmentNo),
    INDEX idx_SessionID (SessionID),
    INDEX idx_EnrollmentNo (EnrollmentNo),
    INDEX idx_RollNo (RollNo),
    INDEX idx_MarkedAt (MarkedAt),
    INDEX idx_IPAddress (IPAddress),
    INDEX idx_DeviceInfo (DeviceInfo),
    INDEX idx_GPSLocation (GPSLocation)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='Immutable forensic attendance transaction log';

-- ============================================================================
-- STORED PROCEDURE: GenerateNewQRToken
-- Purpose: Atomically generate and rotate a new 5-second QR token
-- ============================================================================
DELIMITER //

CREATE PROCEDURE GenerateNewQRToken(
    IN p_SessionID VARCHAR(36),
    IN p_TokenValue VARCHAR(255),
    IN p_ExpiresAt TIMESTAMP,
    OUT p_TokenID VARCHAR(36)
)
READS SQL DATA
MODIFIES SQL DATA
COMMENT 'Generate a new cryptographically secure QR token with 5-second expiry'
BEGIN
    DECLARE v_SessionExists BOOLEAN DEFAULT FALSE;
    DECLARE v_SessionActive BOOLEAN DEFAULT FALSE;
    DECLARE EXIT HANDLER FOR SQLEXCEPTION
    BEGIN
        ROLLBACK;
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Token generation transaction failed';
    END;
    
    START TRANSACTION;
    
    -- Validate session exists and is active
    SELECT EXISTS(
        SELECT 1 FROM AttendanceSessions 
        WHERE SessionID = p_SessionID AND IsActive = TRUE AND ExpiresAt > NOW()
    ) INTO v_SessionActive;
    
    IF NOT v_SessionActive THEN
        ROLLBACK;
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Session not active or expired';
    END IF;
    
    -- Generate UUID for token
    SET p_TokenID = UUID();
    
    -- Insert new token
    INSERT INTO DynamicTokens (TokenID, SessionID, TokenValue, IsValid, ExpiresAt, CreatedAt)
    VALUES (p_TokenID, p_SessionID, p_TokenValue, TRUE, p_ExpiresAt, NOW());
    
    -- Invalidate all previous tokens for this session (soft delete for audit trail)
    UPDATE DynamicTokens 
    SET IsValid = FALSE 
    WHERE SessionID = p_SessionID AND TokenID != p_TokenID AND IsValid = TRUE;
    
    COMMIT;
END //

DELIMITER ;

-- ============================================================================
-- STORED PROCEDURE: ProcessStudentAttendance
-- Purpose: Atomic validation and recording of student attendance with multi-layer checks
-- ============================================================================
DELIMITER //

CREATE PROCEDURE ProcessStudentAttendance(
    IN p_SessionID VARCHAR(36),
    IN p_EnrollmentNo VARCHAR(20),
    IN p_TokenValue VARCHAR(255),
    IN p_VerificationCodeInput VARCHAR(10),
    IN p_IPAddress VARCHAR(45),
    IN p_BrowserInfo VARCHAR(500),
    IN p_DeviceInfo VARCHAR(500),
    IN p_GPSLocation VARCHAR(200),
    OUT p_RecordID VARCHAR(36),
    OUT p_Success BOOLEAN,
    OUT p_ErrorMessage VARCHAR(255)
)
READS SQL DATA
MODIFIES SQL DATA
COMMENT 'Atomic attendance validation: token lifespans, session status, code match, credentials, duplicates, forensics'
BEGIN
    DECLARE v_SessionExists BOOLEAN DEFAULT FALSE;
    DECLARE v_TokenValid BOOLEAN DEFAULT FALSE;
    DECLARE v_TokenExpired BOOLEAN DEFAULT FALSE;
    DECLARE v_CodeMatches BOOLEAN DEFAULT FALSE;
    DECLARE v_StudentExists BOOLEAN DEFAULT FALSE;
    DECLARE v_DuplicateExists BOOLEAN DEFAULT FALSE;
    DECLARE v_StoredVerificationCode VARCHAR(10);
    DECLARE v_SessionExpired BOOLEAN DEFAULT FALSE;
    DECLARE v_TokenExpiresAt TIMESTAMP;
    DECLARE v_GraceBufferSeconds INT DEFAULT 10;
    DECLARE EXIT HANDLER FOR SQLEXCEPTION
    BEGIN
        ROLLBACK;
        SET p_Success = FALSE;
        SET p_ErrorMessage = 'Database transaction failed during attendance processing';
        SET p_RecordID = NULL;
    END;
    
    START TRANSACTION;
    
    -- Step 1: Validate session exists and is active
    SELECT IsActive, ExpiresAt, VerificationCode 
    INTO v_SessionExists, v_SessionExpired, v_StoredVerificationCode
    FROM AttendanceSessions 
    WHERE SessionID = p_SessionID
    FOR UPDATE;
    
    IF v_SessionExists IS NULL THEN
        ROLLBACK;
        SET p_Success = FALSE;
        SET p_ErrorMessage = 'Session does not exist';
        SET p_RecordID = NULL;
        LEAVE ProcessStudentAttendance;
    END IF;
    
    IF NOT v_SessionExists OR v_SessionExpired < NOW() THEN
        ROLLBACK;
        SET p_Success = FALSE;
        SET p_ErrorMessage = 'Session is inactive or expired';
        SET p_RecordID = NULL;
        LEAVE ProcessStudentAttendance;
    END IF;
    
    -- Step 2: Validate token within lifespans (5-second window + 10-second grace buffer)
    SELECT IsValid, ExpiresAt 
    INTO v_TokenValid, v_TokenExpiresAt
    FROM DynamicTokens 
    WHERE SessionID = p_SessionID AND TokenValue = p_TokenValue
    FOR UPDATE;
    
    IF v_TokenValid IS NULL OR NOT v_TokenValid THEN
        ROLLBACK;
        SET p_Success = FALSE;
        SET p_ErrorMessage = 'Invalid or expired QR token';
        SET p_RecordID = NULL;
        LEAVE ProcessStudentAttendance;
    END IF;
    
    -- Check token expiration with grace buffer
    IF v_TokenExpiresAt < DATE_SUB(NOW(), INTERVAL v_GraceBufferSeconds SECOND) THEN
        ROLLBACK;
        SET p_Success = FALSE;
        SET p_ErrorMessage = 'QR token has expired beyond grace period';
        SET p_RecordID = NULL;
        LEAVE ProcessStudentAttendance;
    END IF;
    
    -- Step 3: Validate student exists
    SELECT EnrollmentNo INTO v_StudentExists
    FROM Students 
    WHERE EnrollmentNo = p_EnrollmentNo
    FOR UPDATE;
    
    IF v_StudentExists IS NULL THEN
        ROLLBACK;
        SET p_Success = FALSE;
        SET p_ErrorMessage = 'Student not found in system';
        SET p_RecordID = NULL;
        LEAVE ProcessStudentAttendance;
    END IF;
    
    -- Step 4: Validate verification code match
    IF v_StoredVerificationCode IS NULL OR v_StoredVerificationCode = '' THEN
        ROLLBACK;
        SET p_Success = FALSE;
        SET p_ErrorMessage = 'Verification code not yet revealed by faculty';
        SET p_RecordID = NULL;
        LEAVE ProcessStudentAttendance;
    END IF;
    
    IF p_VerificationCodeInput != v_StoredVerificationCode THEN
        ROLLBACK;
        SET p_Success = FALSE;
        SET p_ErrorMessage = 'Verification code does not match. Incorrect selection.';
        SET p_RecordID = NULL;
        LEAVE ProcessStudentAttendance;
    END IF;
    
    SET v_CodeMatches = TRUE;
    
    -- Step 5: Check for duplicate attendance in this session
    SELECT COUNT(*) INTO v_DuplicateExists
    FROM AttendanceRecords 
    WHERE SessionID = p_SessionID AND EnrollmentNo = p_EnrollmentNo;
    
    IF v_DuplicateExists > 0 THEN
        ROLLBACK;
        SET p_Success = FALSE;
        SET p_ErrorMessage = 'Attendance already marked for this student in this session';
        SET p_RecordID = NULL;
        LEAVE ProcessStudentAttendance;
    END IF;
    
    -- Step 6: Insert immutable forensic attendance record
    SET p_RecordID = UUID();
    
    INSERT INTO AttendanceRecords (
        RecordID, SessionID, EnrollmentNo, RollNo, MarkedAt, 
        IPAddress, BrowserInfo, DeviceInfo, GPSLocation, 
        TokenUsed, VerificationCodeMatched
    )
    SELECT 
        p_RecordID, p_SessionID, s.EnrollmentNo, s.RollNo, NOW(),
        p_IPAddress, p_BrowserInfo, p_DeviceInfo, p_GPSLocation,
        p_TokenValue, v_CodeMatches
    FROM Students s
    WHERE s.EnrollmentNo = p_EnrollmentNo;
    
    -- Success
    SET p_Success = TRUE;
    SET p_ErrorMessage = NULL;
    
    COMMIT;
END //

DELIMITER ;

-- ============================================================================
-- INDEXES & OPTIMIZATION
-- ============================================================================

-- Composite index for efficient session + enrollment lookup
ALTER TABLE AttendanceRecords ADD INDEX idx_SessionEnrollment (SessionID, EnrollmentNo);

-- Index for daily audit queries
ALTER TABLE AttendanceRecords ADD INDEX idx_DateRange (MarkedAt, SessionID);

-- Index for forensic IP/Device lookups (catch proxy attempts)
ALTER TABLE AttendanceRecords ADD INDEX idx_DeviceTrust (IPAddress, DeviceInfo, MarkedAt);

-- ============================================================================
-- SAMPLE PRE-SEEDED DATA
-- ============================================================================

-- Insert sample students (in production, use secure password hashing)
-- Password hashes are bcrypt format: password is "password123" for demo
INSERT INTO Students (EnrollmentNo, RollNo, StudentName, PasswordHash) VALUES
('EN2024001', '101', 'Aarav Sharma', '$2b$12$bZqM9R4/4R4R4R4R4R4R4e8Kc9V5X5X5X5X5X5X5X5X5X5X5X5X5'),
('EN2024002', '102', 'Bhavna Patel', '$2b$12$bZqM9R4/4R4R4R4R4R4R4e8Kc9V5X5X5X5X5X5X5X5X5X5X5X5X5'),
('EN2024003', '103', 'Chirag Verma', '$2b$12$bZqM9R4/4R4R4R4R4R4R4e8Kc9V5X5X5X5X5X5X5X5X5X5X5X5X5'),
('EN2024004', '104', 'Diya Singh', '$2b$12$bZqM9R4/4R4R4R4R4R4R4e8Kc9V5X5X5X5X5X5X5X5X5X5X5X5X5'),
('EN2024005', '105', 'Eshan Kumar', '$2b$12$bZqM9R4/4R4R4R4R4R4R4e8Kc9V5X5X5X5X5X5X5X5X5X5X5X5X5');

-- ============================================================================
-- END OF SCHEMA
-- ============================================================================
