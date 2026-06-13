import os
from dotenv import load_dotenv
from datetime import timedelta

load_dotenv()

class Config:
    """Base configuration class"""
    
    # Flask Configuration
    SECRET_KEY = os.getenv('FLASK_SECRET_KEY', 'dev-secret-key-change-in-production')
    FLASK_ENV = os.getenv('FLASK_ENV', 'development')
    DEBUG = os.getenv('FLASK_DEBUG', 'False').lower() == 'true'
    
    # MySQL Database Configuration
    MYSQL_HOST = os.getenv('MYSQL_HOST', 'localhost')
    MYSQL_USER = os.getenv('MYSQL_USER', 'attendance_user')
    MYSQL_PASSWORD = os.getenv('MYSQL_PASSWORD', 'secure_password')
    MYSQL_DATABASE = os.getenv('MYSQL_DATABASE', 'smart_attendance_db')
    MYSQL_PORT = int(os.getenv('MYSQL_PORT', 3306))
    
    # SQLAlchemy Configuration
    SQLALCHEMY_DATABASE_URI = (
        f'mysql+pymysql://{MYSQL_USER}:{MYSQL_PASSWORD}@'
        f'{MYSQL_HOST}:{MYSQL_PORT}/{MYSQL_DATABASE}'
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ENGINE_OPTIONS = {
        'pool_size': 10,
        'pool_recycle': 3600,
        'pool_pre_ping': True,
    }
    
    # Attendance System Settings
    QR_TOKEN_EXPIRY_SECONDS = int(os.getenv('QR_TOKEN_EXPIRY_SECONDS', 5))
    SESSION_GRACE_BUFFER_SECONDS = int(os.getenv('SESSION_GRACE_BUFFER_SECONDS', 10))
    SESSION_DURATION_MINUTES = int(os.getenv('SESSION_DURATION_MINUTES', 60))
    VERIFICATION_CODE_LENGTH = int(os.getenv('VERIFICATION_CODE_LENGTH', 4))
    
    # Session & Cookie Settings
    PERMANENT_SESSION_LIFETIME = timedelta(minutes=SESSION_DURATION_MINUTES)
    SESSION_COOKIE_SECURE = True
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = 'Lax'
    
    # CORS & Security
    ALLOWED_ORIGINS = ['http://localhost:5000', 'http://localhost:3000']


class DevelopmentConfig(Config):
    """Development environment configuration"""
    DEBUG = True
    SESSION_COOKIE_SECURE = False
    SQLALCHEMY_ECHO = True


class ProductionConfig(Config):
    """Production environment configuration"""
    DEBUG = False
    SQLALCHEMY_ECHO = False


class TestingConfig(Config):
    """Testing environment configuration"""
    TESTING = True
    SQLALCHEMY_DATABASE_URI = 'sqlite:///:memory:'
    SESSION_COOKIE_SECURE = False


# Configuration selector
config_by_name = {
    'development': DevelopmentConfig,
    'production': ProductionConfig,
    'testing': TestingConfig,
}

def get_config():
    """Get configuration based on environment"""
    env = os.getenv('FLASK_ENV', 'development')
    return config_by_name.get(env, DevelopmentConfig)
