from extensions import db # Import the db instance from extensions (no app import)
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
# ...existing code...

class User(UserMixin, db.Model):
    """
    User model for storing user information.
    Inherits from UserMixin to get default implementations for
    Flask-Login (is_authenticated, is_active, etc.)
    """
    
    # Set the table name explicitly (optional, Flask defaults to 'user')
    __tablename__ = 'users'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    # We use 'username' to store the email as requested
    username = db.Column(db.String(120), unique=True, nullable=False, index=True)
    age = db.Column(db.Integer, nullable=False)
    password_hash = db.Column(db.String(256), nullable=False)

    def set_password(self, password):
        """
        Creates a password hash from the provided password string.
        """
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        """
        Checks if the provided password matches the stored hash.
        """
        return check_password_hash(self.password_hash, password)

    def __repr__(self):
        # Helpful representation for debugging
        return f'<User {self.username}>'
# ...existing code...