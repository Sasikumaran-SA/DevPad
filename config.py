import os
from dotenv import load_dotenv  # <-- Import this

# Get the directory of the current file
basedir = os.path.abspath(os.path.dirname(__file__))

# --- Load the .env file ---
# This line looks for a .env file in the current directory and loads it
load_dotenv()
# -------------------------

class Config:
    """
    Configuration class for the Flask app.
    Loads settings from environment variables or sets defaults.
    """
    
    # Secret key is crucial for sessions, cookies, and forms (CSRF protection)
    # Get it from an environment variable (now loaded from .env)
    SECRET_KEY = os.environ.get('SECRET_KEY')
    
    # --- Database Configuration ---
    
    # Get the database URL from an environment variable (now loaded from .env)
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL')
        
    # Disable modification tracking as it's deprecated and adds overhead
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # --- New: Execution Service Config ---
    # These will be loaded from environment variables on the EC2 instance
    EXECUTION_API_URL = os.environ.get('EXECUTION_API_URL')
    EXECUTION_API_KEY = os.environ.get('EXECUTION_API_KEY')
    EXECUTION_LAMBDA_NAME = os.environ.get('EXECUTION_LAMBDA_NAME')
    AWS_REGION = os.environ.get('AWS_REGION', 'us-east-1')
