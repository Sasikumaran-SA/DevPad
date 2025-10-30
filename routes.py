from flask import render_template, redirect, url_for, flash, request, Blueprint, current_app, abort
from extensions import db
from models import User, CodingProblem, UserRole # <-- Import new models
from flask_login import login_user, logout_user, current_user, login_required
from functools import wraps # <-- Import for decorators

# --- Form Imports (Updated) ---
from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, SubmitField, IntegerField, RadioField, TextAreaField, SelectMultipleField, BooleanField
from wtforms.validators import DataRequired, Email, EqualTo, ValidationError, NumberRange
from wtforms import widgets # <-- For checkbox widget

# --- Create a Blueprint ---
main_bp = Blueprint('main', __name__)

# --- Role-Based Decorators (New) ---

def instructor_required(f):
    """Ensures the current user is an instructor."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated or not current_user.is_instructor:
            abort(403) # Forbidden
        return f(*args, **kwargs)
    return decorated_function

def student_required(f):
    """Ensures the current user is a student."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated or not current_user.is_student:
            abort(403) # Forbidden
        return f(*args, **kwargs)
    return decorated_function

# --- Form Definitions (Updated) ---

class LoginForm(FlaskForm):
    username = StringField('Email (Username)', validators=[DataRequired(), Email()])
    password = PasswordField('Password', validators=[DataRequired()])
    submit = SubmitField('Sign In')

class RegistrationForm(FlaskForm):
    """
    Form for new user registration (Updated).
    """
    name = StringField('Full Name', validators=[DataRequired()])
    username = StringField('Email (Username)', validators=[DataRequired(), Email()])
    age = IntegerField('Age', validators=[DataRequired(), NumberRange(min=13, max=120, message="You must be at least 13 years old.")])
    password = PasswordField('Password', validators=[DataRequired()])
    confirm_password = PasswordField(
        'Confirm Password', 
        validators=[DataRequired(), EqualTo('password', message='Passwords must match.')]
    )
    # --- New: Role selection field ---
    role = RadioField('Register as:', 
        choices=[(UserRole.STUDENT.value, 'Student'), (UserRole.INSTRUCTOR.value, 'Instructor')],
        validators=[DataRequired()],
        default=UserRole.STUDENT.value
    )
    submit = SubmitField('Register')

    def validate_username(self, username):
        user = User.query.filter_by(username=username.data).first()
        if user:
            raise ValidationError('That email is already in use. Please choose a different one.')

# --- New Forms ---

class CodingProblemForm(FlaskForm):
    """Form for instructors to create a new coding problem."""
    title = StringField('Problem Title', validators=[DataRequired()])
    description = TextAreaField('Problem Description', validators=[DataRequired()])
    submit = SubmitField('Create Problem')

class AssignmentForm(FlaskForm):
    """Form for an instructor to assign a problem to students."""
    # We will populate choices dynamically in the route
    students = SelectMultipleField('Assign to Specific Students', coerce=int,
        widget=widgets.ListWidget(prefix_label=False), 
        option_widget=widgets.CheckboxInput()
    )
    assign_to_all = BooleanField('Assign to ALL Students')
    submit = SubmitField('Update Assignments')


# --- Route Definitions (Updated) ---

@main_bp.route('/')
@main_bp.route('/index')
@login_required
def index():
    """
    Main entry point after login.
    Redirects user to their specific dashboard based on role.
    """
    if current_user.is_instructor:
        return redirect(url_for('main.instructor_dashboard'))
    elif current_user.is_student:
        return redirect(url_for('main.student_dashboard'))
    else:
        # Fallback, though should not be reached if roles are set
        return "Role not set.", 403

# --- New: Student Dashboard ---
@main_bp.route('/student_dashboard')
@login_required
@student_required
def student_dashboard():
    """Homepage for logged-in students."""
    assigned_problems = current_user.assigned_problems.all()
    return render_template('student_dashboard.html', title='My Dashboard', user=current_user, problems=assigned_problems)

# --- New: Instructor Dashboard ---
@main_bp.route('/instructor_dashboard')
@login_required
@instructor_required
def instructor_dashboard():
    """Homepage for logged-in instructors."""
    created_problems = current_user.created_problems.all()
    return render_template('instructor_dashboard.html', title='Instructor Dashboard', user=current_user, problems=created_problems)

@main_bp.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('main.index'))
        
    form = LoginForm()
    
    if form.validate_on_submit():
        user = User.query.filter_by(username=form.username.data).first()
        
        if user is None or not user.check_password(form.password.data):
            flash('Invalid username or password', 'danger')
            return redirect(url_for('main.login'))
        
        login_user(user)
        
        # --- Updated: Redirect to role-based index ---
        next_page = request.args.get('next')
        if not next_page:
            # The 'index' route will handle the role-based redirect
            next_page = url_for('main.index')
            
        flash('Login successful!', 'success')
        return redirect(next_page)

    return render_template('login.html', title='Sign In', form=form)

@main_bp.route('/logout')
def logout():
    logout_user()
    flash('You have been logged out.', 'info')
    return redirect(url_for('main.login'))

@main_bp.route('/register', methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated:
        return redirect(url_for('main.index'))
        
    form = RegistrationForm()
    
    if form.validate_on_submit():
        # --- Updated: Create user with role ---
        user = User(
            name=form.name.data,
            username=form.username.data,
            age=form.age.data,
            # Get the role from the form
            role=UserRole(form.role.data) 
        )
        user.set_password(form.password.data)
        
        try:
            db.session.add(user)
            db.session.commit()
            flash('Congratulations, you are now a registered user!', 'success')
            return redirect(url_for('main.login'))
        except Exception as e:
            db.session.rollback()
            flash(f'An error occurred. Could not register user. {e}', 'danger')
            current_app.logger.error(f"Error on registration: {e}")

    return render_template('register.html', title='Register', form=form)

# --- New: Create Problem Route (Instructor) ---
@main_bp.route('/create_problem', methods=['GET', 'POST'])
@login_required
@instructor_required
def create_problem():
    form = CodingProblemForm()
    if form.validate_on_submit():
        problem = CodingProblem(
            title=form.title.data,
            description=form.description.data,
            creator=current_user  # Assign the creator
        )
        try:
            db.session.add(problem)
            db.session.commit()
            flash('New coding problem has been created!', 'success')
            return redirect(url_for('main.instructor_dashboard'))
        except Exception as e:
            db.session.rollback()
            flash(f'Error creating problem: {e}', 'danger')
            
    return render_template('create_problem.html', title='Create Problem', form=form)

# --- New: Assign Problem Route (Instructor) ---
@main_bp.route('/problem/<int:problem_id>/assign', methods=['GET', 'POST'])
@login_required
@instructor_required
def assign_problem(problem_id):
    problem = CodingProblem.query.get_or_404(problem_id)
    
    # Ensure instructor can only assign problems they created
    if problem.creator_id != current_user.id:
        abort(403)

    form = AssignmentForm()
    
    # Get all students and set them as choices for the form field
    all_students = User.query.filter_by(role=UserRole.STUDENT).all()
    form.students.choices = [(s.id, s.name) for s in all_students]

    if form.validate_on_submit():
        if form.assign_to_all.data:
            # Assign to all students
            problem.assigned_students = all_students
        else:
            # Assign to selected students
            selected_student_ids = form.students.data
            selected_students = User.query.filter(User.id.in_(selected_student_ids)).all()
            problem.assigned_students = selected_students
        
        try:
            db.session.commit()
            flash(f'Assignments for "{problem.title}" updated!', 'success')
            return redirect(url_for('main.instructor_dashboard'))
        except Exception as e:
            db.session.rollback()
            flash(f'Error updating assignments: {e}', 'danger')

    elif request.method == 'GET':
        # Pre-populate the form with currently assigned students
        assigned_student_ids = [s.id for s in problem.assigned_students]
        form.students.data = assigned_student_ids

    return render_template('assign_problem.html', title='Assign Problem', form=form, problem=problem)


# --- New: View Problem Route (Student) ---
@main_bp.route('/problem/<int:problem_id>')
@login_required
@student_required
def view_problem(problem_id):
    problem = CodingProblem.query.get_or_404(problem_id)
    
    # Check if this student is actually assigned this problem
    if problem not in current_user.assigned_problems:
        flash('You are not authorized to view this problem.', 'danger')
        return redirect(url_for('main.student_dashboard'))
        
    return render_template('view_problem.html', title=problem.title, problem=problem)