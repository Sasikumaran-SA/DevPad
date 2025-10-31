import json
import boto3
import os
from flask import render_template, redirect, url_for, flash, request, Blueprint, current_app, abort, jsonify
from extensions import db
from models import User, CodingProblem, UserRole, TestCase, Submission # <-- Import new models
from flask_login import login_user, logout_user, current_user, login_required
from functools import wraps # <-- Import for decorators

# --- Form Imports (Updated) ---
from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, SubmitField, IntegerField, RadioField, TextAreaField, SelectMultipleField, BooleanField, FormField, FieldList
from wtforms.validators import DataRequired, Email, EqualTo, ValidationError, NumberRange, Optional
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

class TestCaseForm(FlaskForm):                                                      ####
    """Sub-form for a single test case."""
    public_input = TextAreaField('Public Input', render_kw={'rows': 3})
    public_output = TextAreaField('Public Output', render_kw={'rows': 3})
    hidden_input = TextAreaField('Hidden Input', validators=[Optional()], render_kw={'rows': 3})
    hidden_output = TextAreaField('Hidden Output', validators=[Optional()], render_kw={'rows': 3})

# class CodingProblemForm(FlaskForm):
#     """Form for instructors to create a new coding problem."""
#     title = StringField('Problem Title', validators=[DataRequired()])
#     description = TextAreaField('Problem Description', validators=[DataRequired()])
#     submit = SubmitField('Create Problem')

class CodingProblemForm(FlaskForm):                                                  ####
    """Form for instructors to create a new coding problem."""
    title = StringField('Problem Title', validators=[DataRequired()])
    description = TextAreaField('Problem Description', validators=[DataRequired()])
    
    # --- New: Language Selection ---
    allowed_languages = SelectMultipleField(
        'Allowed Languages',
        choices=[('python', 'Python'), ('c', 'C (coming soon)'), ('cpp', 'C++ (coming soon)')],
        validators=[DataRequired()],
        widget=widgets.ListWidget(prefix_label=False), 
        option_widget=widgets.CheckboxInput()
    )
    
    # --- New: Dynamic Test Cases ---
    test_cases = FieldList(FormField(TestCaseForm), min_entries=1)
    
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

# --- New: Submission Form (for student) ---
class SubmissionForm(FlaskForm):
    code = TextAreaField('Your Code', validators=[DataRequired()])
    language = RadioField('Language', choices=[], validators=[DataRequired()])
    submit = SubmitField('Run Code')

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

# # --- New: Create Problem Route (Instructor) ---
# @main_bp.route('/create_problem', methods=['GET', 'POST'])
# @login_required
# @instructor_required
# def create_problem():
#     form = CodingProblemForm()
#     if form.validate_on_submit():
#         problem = CodingProblem(
#             title=form.title.data,
#             description=form.description.data,
#             creator=current_user  # Assign the creator
#         )
#         try:
#             db.session.add(problem)
#             db.session.commit()
#             flash('New coding problem has been created!', 'success')
#             return redirect(url_for('main.instructor_dashboard'))
#         except Exception as e:
#             db.session.rollback()
#             flash(f'Error creating problem: {e}', 'danger')
            
#     return render_template('create_problem.html', title='Create Problem', form=form)


# --- Updated: Create Problem Route (Instructor) ---
@main_bp.route('/create_problem', methods=['GET', 'POST'])               ####
@login_required
@instructor_required
def create_problem():
    form = CodingProblemForm()
    
    if form.validate_on_submit():
        problem = CodingProblem(
            title=form.title.data,
            description=form.description.data,
            # Store selected languages as a JSON string
            allowed_languages=json.dumps(form.allowed_languages.data),
            creator=current_user
        )
        
        # Add test cases
        for test_case_form in form.test_cases.data:
            test_case = TestCase(
                public_input=test_case_form['public_input'],
                public_output=test_case_form['public_output'],
                hidden_input=test_case_form['hidden_input'],
                hidden_output=test_case_form['hidden_output'],
                problem=problem
            )
            db.session.add(test_case)
            
        try:
            db.session.add(problem)
            db.session.commit()
            flash('New coding problem has been created!', 'success')
            return redirect(url_for('main.instructor_dashboard'))
        except Exception as e:
            db.session.rollback()
            flash(f'Error creating problem: {e}', 'danger')
            current_app.logger.error(f"Error creating problem: {e}")
            
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


# # --- New: View Problem Route (Student) ---
# @main_bp.route('/problem/<int:problem_id>')
# @login_required
# @student_required
# def view_problem(problem_id):
#     problem = CodingProblem.query.get_or_404(problem_id)
    
#     # Check if this student is actually assigned this problem
#     if problem not in current_user.assigned_problems:
#         flash('You are not authorized to view this problem.', 'danger')
#         return redirect(url_for('main.student_dashboard'))
        
#     return render_template('view_problem.html', title=problem.title, problem=problem)

# --- Updated: View Problem Route (Student) ---
@main_bp.route('/problem/<int:problem_id>', methods=['GET', 'POST'])                    ####
@login_required
@student_required
def view_problem(problem_id):
    problem = CodingProblem.query.get_or_404(problem_id)
    
    if problem not in current_user.assigned_problems:
        flash('You are not authorized to view this problem.', 'danger')
        return redirect(url_for('main.student_dashboard'))
    
    form = SubmissionForm()
    # Dynamically set language choices
    form.language.choices = [(lang, lang.capitalize()) for lang in problem.languages_list]
    
    if form.validate_on_submit():
        # --- This is where we call the Lambda ---
        try:
            # 1. Create a "Pending" submission
            submission = Submission(
                code=form.code.data,
                language=form.language.data,
                student=current_user,
                problem=problem,
                status='Pending'
            )
            db.session.add(submission)
            db.session.commit()

            # 2. Get Lambda/API Gateway info from environment
            api_url = os.environ.get('EXECUTION_API_URL')
            api_key = os.environ.get('EXECUTION_API_KEY')
            
            if not api_url or not api_key:
                flash('Code execution service is not configured. Please contact the instructor.', 'danger')
                return redirect(url_for('main.view_problem', problem_id=problem_id))
            
            # 3. Get test cases
            test_cases = [{
                'public_input': tc.public_input,
                'public_output': tc.public_output,
                'hidden_input': tc.hidden_input,
                'hidden_output': tc.hidden_output
            } for tc in problem.test_cases]
            
            # 4. Prepare payload for Lambda
            payload = {
                'submission_id': submission.id,
                'language': submission.language,
                'code': submission.code,
                'test_cases': test_cases,
                # This is the URL Lambda will call when done
                'callback_url': url_for('main.submission_callback', _external=True),
                'api_key': api_key # This key proves the call is from our Lambda
            }
            
            # 5. Invoke the Lambda asynchronously using boto3
            # We use 'Event' to invoke asynchronously (fire-and-forget)
            lambda_client = boto3.client('lambda', region_name=os.environ.get('AWS_REGION', 'us-east-1'))
            
            lambda_client.invoke(
                FunctionName=os.environ.get('EXECUTION_LAMBDA_NAME'),
                InvocationType='Event', # Asynchronous
                Payload=json.dumps(payload)
            )

            flash('Submission received! Your code is being tested.', 'info')
            return redirect(url_for('main.view_submission', submission_id=submission.id))

        except Exception as e:
            db.session.rollback()
            flash(f'Error submitting code: {e}', 'danger')
            current_app.logger.error(f"Error on submission: {e}")

    # On GET request, populate form with choices
    if not form.language.data:
        form.language.data = problem.languages_list[0]
        
    return render_template('view_problem.html', title=problem.title, problem=problem, form=form)

# --- New: Callback route for Lambda ---
@main_bp.route('/api/submission/callback', methods=['POST'])
def submission_callback():
    """
    This secure, internal-only endpoint is called by our Lambda
    to update the status of a submission.
    """
    try:
        data = request.json
        
        # 1. Authenticate the Lambda
        expected_key = os.environ.get('EXECUTION_API_KEY')
        received_key = data.get('api_key')
        
        if not expected_key or received_key != expected_key:
            abort(403) # Forbidden
            
        # 2. Get submission
        submission_id = data.get('submission_id')
        submission = Submission.query.get(submission_id)
        
        if not submission:
            return jsonify({'status': 'error', 'message': 'Submission not found'}), 404
            
        # 3. Update status and output
        submission.status = data.get('status') # 'Passed' or 'Failed'
        submission.output = data.get('output') # Detailed log
        
        db.session.commit()
        
        return jsonify({'status': 'success'})

    except Exception as e:
        current_app.logger.error(f"Callback error: {e}")
        db.session.rollback()
        return jsonify({'status': 'error', 'message': str(e)}), 500

# --- New: View Submission Result route ---
@main_bp.route('/submission/<int:submission_id>')
@login_required
def view_submission(submission_id):
    submission = Submission.query.get_or_404(submission_id)
    
    # Student can only see their own, Instructor can see any for their problem
    if (current_user.is_student and submission.student_id != current_user.id):
        abort(403)
    if (current_user.is_instructor and submission.problem.creator_id != current_user.id):
        abort(403)
        
    return render_template('view_submission.html', title=f'Submission {submission.id}', submission=submission)

# --- New: API route for student to poll for results ---
@main_bp.route('/api/submission/<int:submission_id>/status')
@login_required
def get_submission_status(submission_id):
    submission = Submission.query.get_or_404(submission_id)
    
    if (submission.student_id != current_user.id):
         abort(403)
         
    return jsonify({
        'id': submission.id,
        'status': submission.status,
        'output': submission.output,
        'timestamp': submission.timestamp.isoformat()
    })
