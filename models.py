import enum
from extensions import db # Import the db instance from extensions (no app import)
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash

# --- New: Association table for Many-to-Many relationship ---
# This table links Students (Users) to the CodingProblems they are assigned.
assignments = db.Table('assignments',
    db.Column('user_id', db.Integer, db.ForeignKey('users.id'), primary_key=True),
    db.Column('problem_id', db.Integer, db.ForeignKey('coding_problems.id'), primary_key=True)
)

# --- New: Enum for user roles ---
class UserRole(enum.Enum):
    STUDENT = 'student'
    INSTRUCTOR = 'instructor'

class User(UserMixin, db.Model):
    """
    User model for storing user information.
    """
    
    __tablename__ = 'users'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    username = db.Column(db.String(120), unique=True, nullable=False, index=True) # This is the email
    age = db.Column(db.Integer, nullable=False)
    password_hash = db.Column(db.String(256), nullable=False)
    
    # --- New: Role column ---
    role = db.Column(db.Enum(UserRole), nullable=False, default=UserRole.STUDENT)

    # --- New: Relationships ---

    # For Instructors: One-to-Many relationship
    # The problems this instructor has created.
    created_problems = db.relationship(
        'CodingProblem', 
        back_populates='creator', 
        lazy='dynamic', 
        foreign_keys='CodingProblem.creator_id'
    )

    # For Students: Many-to-Many relationship
    # The problems this student has been assigned.
    assigned_problems = db.relationship(
        'CodingProblem', 
        secondary=assignments,
        lazy='dynamic',
        back_populates='assigned_students'
    )
    
    # ... existing set_password and check_password methods ...
    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    # --- New: Helper properties for role checking ---
    @property
    def is_student(self):
        return self.role == UserRole.STUDENT

    @property
    def is_instructor(self):
        return self.role == UserRole.INSTRUCTOR

    def __repr__(self):
        return f'<User {self.username} ({self.role.value})>'

# --- New: CodingProblem Model ---
class CodingProblem(db.Model):
    """
    Model for storing coding problems created by instructors.
    """
    __tablename__ = 'coding_problems'
    
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text, nullable=False)
    
    # Foreign key to the User (Instructor) who created this
    creator_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)

    # Relationship back to the User model (Instructor)
    creator = db.relationship(
        'User', 
        back_populates='created_problems', 
        foreign_keys=[creator_id]
    )

    # Many-to-Many relationship for assigned students
    assigned_students = db.relationship(
        'User', 
        secondary=assignments,
        lazy='dynamic',
        back_populates='assigned_problems'
    )
    
    def __repr__(self):
        return f'<CodingProblem {self.title}>'