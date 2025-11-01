import enum
from extensions import db
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from sqlalchemy.ext.associationproxy import association_proxy
from sqlalchemy.orm import joinedload
from sqlalchemy import func, distinct # <-- Import func and distinct
import datetime

# --- Enums ---
class UserRole(enum.Enum):
    STUDENT = 'student'
    INSTRUCTOR = 'instructor'

class ScoringType(enum.Enum):
    EQUAL = 'equal'
    CUSTOM = 'custom'

# --- Association Table for Assignments ---
# This is now a full model to store the best score
class ProblemAssignment(db.Model):
    __tablename__ = 'problem_assignments'
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), primary_key=True)
    problem_id = db.Column(db.Integer, db.ForeignKey('coding_problems.id'), primary_key=True)
    
    # Store the best score for this user/problem pair
    best_score = db.Column(db.Integer, default=0)
    best_submission_id = db.Column(db.Integer, db.ForeignKey('code_submissions.id'), nullable=True)

    # Relationships
    student = db.relationship('User', back_populates='assignments')
    problem = db.relationship('CodingProblem', back_populates='assignments')
    best_submission = db.relationship('CodeSubmission', foreign_keys=[best_submission_id])

class User(UserMixin, db.Model):
    __tablename__ = 'users'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    username = db.Column(db.String(120), unique=True, nullable=False, index=True)
    age = db.Column(db.Integer, nullable=False)
    password_hash = db.Column(db.String(256), nullable=False)
    role = db.Column(db.Enum(UserRole), nullable=False, default=UserRole.STUDENT)

    # --- Relationships ---
    
    # For Instructors: Problems they created
    created_problems = db.relationship(
        'CodingProblem', 
        back_populates='creator', 
        lazy='dynamic', 
        foreign_keys='CodingProblem.creator_id'
    )
    
    # For Students: Problems they are assigned
    assignments = db.relationship(
        'ProblemAssignment', 
        back_populates='student', 
        cascade='all, delete-orphan'
    )
    
    # For Students: All their submissions
    submissions = db.relationship(
        'CodeSubmission', 
        back_populates='student', 
        lazy='dynamic', 
        foreign_keys='CodeSubmission.user_id'
    )

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    def get_assignment(self, problem_id):
        """Helper to get a specific assignment object."""
        return db.session.get(ProblemAssignment, (self.id, problem_id))
        
    def get_best_score(self, problem_id):
        """Helper to get the best score for a problem."""
        assignment = self.get_assignment(problem_id)
        return assignment.best_score if assignment else 0

    @property
    def is_student(self):
        return self.role == UserRole.STUDENT

    @property
    def is_instructor(self):
        return self.role == UserRole.INSTRUCTOR

    # --- Student Dashboard Properties ---
    @property
    def total_score_achieved(self):
        """Sum of best scores for all assigned problems."""
        return db.session.query(db.func.sum(ProblemAssignment.best_score))\
                         .filter(ProblemAssignment.user_id == self.id)\
                         .scalar() or 0

    @property
    def total_score_possible(self):
        """Sum of all assigned problems' total scores."""
        return db.session.query(db.func.sum(CodingProblem.total_score))\
                         .join(ProblemAssignment, ProblemAssignment.problem_id == CodingProblem.id)\
                         .filter(ProblemAssignment.user_id == self.id)\
                         .scalar() or 0

    @property
    def overall_percentage(self):
        """Overall score percentage."""
        possible = self.total_score_possible
        if not possible:
            return 0
        return (self.total_score_achieved / possible) * 100

    @property
    def problems_attempted_count(self):
        """Count of distinct problems attempted."""
        # --- THIS IS THE FIX ---
        # Old: return self.submissions.group_by(CodeSubmission.problem_id).count()
        # New:
        return db.session.query(db.func.count(db.distinct(CodeSubmission.problem_id)))\
                         .filter_by(user_id=self.id)\
                         .scalar() or 0
        
    def __repr__(self):
        return f'<User {self.username} ({self.role.value})>'

class CodingProblem(db.Model):
    __tablename__ = 'coding_problems'
    
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text, nullable=False)
    creator_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    
    # --- New Fields ---
    is_open = db.Column(db.Boolean, default=True, nullable=False)
    total_score = db.Column(db.Integer, default=100, nullable=False)
    scoring_type = db.Column(db.Enum(ScoringType), default=ScoringType.EQUAL, nullable=False)
    
    # --- Relationships ---
    creator = db.relationship('User', back_populates='created_problems', foreign_keys=[creator_id])
    
    # One-to-Many for Test Cases
    test_cases = db.relationship(
        'TestCase', 
        back_populates='problem', 
        cascade='all, delete-orphan'
    )
    
    # Assignments (list of students)
    assignments = db.relationship(
        'ProblemAssignment', 
        back_populates='problem', 
        cascade='all, delete-orphan'
    )
    
    # Submissions
    submissions = db.relationship(
        'CodeSubmission', 
        back_populates='problem', 
        lazy='dynamic', 
        foreign_keys='CodeSubmission.problem_id'
    )
    
    # Association proxy for easy access to assigned students
    assigned_students = association_proxy(
        'assignments', 
        'student', 
        creator=lambda student: ProblemAssignment(student=student)
    )

    @property
    def public_test_cases(self):
        return [tc for tc in self.test_cases if tc.is_public]

    @property
    def private_test_cases(self):
        return [tc for tc in self.test_cases if not tc.is_public]

    @property
    def calculated_total_score(self):
        """The actual total score based on private test cases."""
        if self.scoring_type == ScoringType.EQUAL:
            return self.total_score
        else:
            return db.session.query(db.func.sum(TestCase.score))\
                             .filter(TestCase.problem_id == self.id, TestCase.is_public == False)\
                             .scalar() or 0

    @property
    def average_score(self):
        """Average score of all assigned students."""
        num_assigned = len(self.assignments)
        if not num_assigned:
            return 0
        total_best_scores = db.session.query(db.func.sum(ProblemAssignment.best_score))\
                                    .filter(ProblemAssignment.problem_id == self.id)\
                                    .scalar() or 0
        return total_best_scores / num_assigned

    def is_assigned_to(self, user):
        """Check if a user is assigned this problem."""
        return db.session.get(ProblemAssignment, (user.id, self.id)) is not None

    def __repr__(self):
        return f'<CodingProblem {self.title}>'

class TestCase(db.Model):
    __tablename__ = 'test_cases'
    
    id = db.Column(db.Integer, primary_key=True)
    problem_id = db.Column(db.Integer, db.ForeignKey('coding_problems.id'), nullable=False)
    
    is_public = db.Column(db.Boolean, default=False, nullable=False)
    input_data = db.Column(db.Text, nullable=True)
    expected_output = db.Column(db.Text, nullable=True)
    score = db.Column(db.Integer, nullable=True, default=0) # Only for private custom

    problem = db.relationship('CodingProblem', back_populates='test_cases')
    
    def __repr__(self):
        type = "Public" if self.is_public else "Private"
        return f'<{type} TestCase {self.id} for Problem {self.problem_id}>'

class CodeSubmission(db.Model):
    __tablename__ = 'code_submissions'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    problem_id = db.Column(db.Integer, db.ForeignKey('coding_problems.id'), nullable=False)
    
    language = db.Column(db.String(20), nullable=False)
    code = db.Column(db.Text, nullable=False)
    status = db.Column(db.String(20), default='Pending', nullable=False)
    timestamp = db.Column(db.DateTime, default=datetime.datetime.utcnow, nullable=False)
    
    # --- New Fields ---
    score_achieved = db.Column(db.Integer, nullable=True, default=0)
    total_score = db.Column(db.Integer, nullable=True, default=0) # Total possible at time of submission
    execution_output = db.Column(db.Text, nullable=True) # Safe output (public results + private summary)

    # --- Relationships ---
    student = db.relationship('User', back_populates='submissions', foreign_keys=[user_id])
    problem = db.relationship('CodingProblem', back_populates='submissions', foreign_keys=[problem_id])

    def __repr__(self):
        return f'<Submission {self.id} by {self.student.username}>'
