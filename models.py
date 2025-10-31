import enum
from extensions import db # Import the db instance from extensions (no app import)
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
import json

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

    # newly added relationship to submissions
    submissions = db.relationship('Submission', back_populates='student', lazy='dynamic')     ####
    
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
    
    allowed_languages = db.Column(db.String(200), nullable=False, default='["python"]')    #####

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

    # --- New: Relationship to TestCases ---
    test_cases = db.relationship('TestCase', back_populates='problem', cascade='all, delete-orphan')      ##*

    # --- New: Relationship to Submissions ---
    submissions = db.relationship('Submission', back_populates='problem', cascade='all, delete-orphan')   ##*
    
    def __repr__(self):
        return f'<CodingProblem {self.title}>'
    
    @property
    def languages_list(self):                                                          ## *
        try:
            return json.loads(self.allowed_languages)
        except:
            return ['python'] # Fallback

# --- New: TestCase Model ---
class TestCase(db.Model):
    """
    Model for storing a single test case (input and expected output).
    """
    __tablename__ = 'test_cases'
    
    id = db.Column(db.Integer, primary_key=True)
    public_input = db.Column(db.Text, nullable=True)  # Input shown to student
    public_output = db.Column(db.Text, nullable=True) # Expected output for public test
    
    hidden_input = db.Column(db.Text, nullable=True)   # Hidden input
    hidden_output = db.Column(db.Text, nullable=True)  # Expected output for hidden test
    
    problem_id = db.Column(db.Integer, db.ForeignKey('coding_problems.id'), nullable=False)
    problem = db.relationship('CodingProblem', back_populates='test_cases')
    
    def __repr__(self):
        return f'<TestCase {self.id} for Problem {self.problem_id}>'

# --- New: Submission Model ---
class Submission(db.Model):
    """
    Model for storing a student's code submission.
    """
    __tablename__ = 'submissions'
    
    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.Text, nullable=False)
    language = db.Column(db.String(50), nullable=False)
    
    # Status: 'Pending', 'Running', 'Passed', 'Failed'
    status = db.Column(db.String(50), nullable=False, default='Pending')
    
    # Output from the execution
    output = db.Column(db.Text, nullable=True) 
    
    timestamp = db.Column(db.DateTime, index=True, default=db.func.now())
    
    student_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    problem_id = db.Column(db.Integer, db.ForeignKey('coding_problems.id'), nullable=False)
    
    student = db.relationship('User', back_populates='submissions')
    problem = db.relationship('CodingProblem', back_populates='submissions')
    
    def __repr__(self):
        return f'<Submission {self.id} by {self.student.name}>'
