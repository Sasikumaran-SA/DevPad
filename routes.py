from flask import render_template, redirect, url_for, flash, request, Blueprint, current_app, abort, jsonify
from extensions import db
from models import User, CodingProblem, UserRole, TestCase, CodeSubmission, ProblemAssignment, ScoringType
from flask_login import login_user, logout_user, current_user, login_required
from functools import wraps
import boto3  # <-- Keep this import
import json
import os
from sqlalchemy.orm import joinedload
from sqlalchemy import func

# --- Form Imports ---
from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, SubmitField, IntegerField, RadioField, TextAreaField, SelectMultipleField, BooleanField, FormField, FieldList
from wtforms.validators import DataRequired, Email, EqualTo, ValidationError, NumberRange, Optional
from wtforms import widgets

# --- Create a Blueprint ---
main_bp = Blueprint('main', __name__)

# --- Boto3 Client ---
# lambda_client = boto3.client('lambda') # <-- BUG WAS HERE! We moved it.

# --- Role-Based Decorators ---
def instructor_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated or not current_user.is_instructor:
            abort(403)
        return f(*args, **kwargs)
    return decorated_function

def student_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated or not current_user.is_student:
            abort(403)
        return f(*args, **kwargs)
    return decorated_function

# --- Form Definitions ---

class LoginForm(FlaskForm):
    username = StringField('Email (Username)', validators=[DataRequired(), Email()])
    password = PasswordField('Password', validators=[DataRequired()])
    submit = SubmitField('Sign In')

class RegistrationForm(FlaskForm):
    name = StringField('Full Name', validators=[DataRequired()])
    username = StringField('Email (Username)', validators=[DataRequired(), Email()])
    age = IntegerField('Age', validators=[DataRequired(), NumberRange(min=13, max=120)])
    password = PasswordField('Password', validators=[DataRequired()])
    confirm_password = PasswordField('Confirm Password', validators=[DataRequired(), EqualTo('password')])
    role = RadioField('Register as:', 
        choices=[(UserRole.STUDENT.value, 'Student'), (UserRole.INSTRUCTOR.value, 'Instructor')],
        validators=[DataRequired()],
        default=UserRole.STUDENT.value
    )
    submit = SubmitField('Register')

    def validate_username(self, username):
        user = User.query.filter_by(username=username.data).first()
        if user:
            raise ValidationError('That email is already in use.')

# --- New Dynamic Forms for Test Cases ---

class PublicTestCaseForm(FlaskForm):
    """Sub-form for a single public test case."""
    input_data = TextAreaField('Input', validators=[Optional()])
    expected_output = TextAreaField('Expected Output', validators=[Optional()])

class PrivateTestCaseForm(FlaskForm):
    """Sub-form for a single private test case."""
    input_data = TextAreaField('Input', validators=[DataRequired()])
    expected_output = TextAreaField('Expected Output', validators=[DataRequired()])
    score = IntegerField('Score', validators=[Optional(), NumberRange(min=0)])

class CodingProblemForm(FlaskForm):
    """Main form for creating/editing a problem."""
    title = StringField('Problem Title', validators=[DataRequired()])
    description = TextAreaField('Problem Description', validators=[DataRequired()])
    is_open = BooleanField('Accepting Submissions', default=True)
    
    scoring_type = RadioField('Scoring for Private Test Cases',
        choices=[(ScoringType.EQUAL.value, 'Distribute Total Score Equally'), 
                 (ScoringType.CUSTOM.value, 'Set Custom Score per Test Case')],
        default=ScoringType.EQUAL.value,
        validators=[DataRequired()]
    )
    total_score = IntegerField('Total Score (if distributed equally)', 
        default=100, 
        validators=[Optional(), NumberRange(min=0)]
    )
    
    public_test_cases = FieldList(FormField(PublicTestCaseForm), min_entries=1)
    private_test_cases = FieldList(FormField(PrivateTestCaseForm), min_entries=1)
    
    submit = SubmitField('Save Problem')

class AssignmentForm(FlaskForm):
    students = SelectMultipleField('Assign to Specific Students', coerce=int,
        widget=widgets.ListWidget(prefix_label=False), 
        option_widget=widgets.CheckboxInput()
    )
    assign_to_all = BooleanField('Assign to ALL Students')
    submit = SubmitField('Update Assignments')

class SubmissionForm(FlaskForm):
    # Hard-coded to Python for now as Lambda only supports that
    language = RadioField('Language', 
        choices=[('python', 'Python')], 
        default='python', 
        validators=[DataRequired()]
    )
    code = TextAreaField('Code', validators=[DataRequired()])
    submit = SubmitField('Run Code')

# --- Helper Function ---
def get_user_from_header():
    """Authenticates a user from an API key in the header."""
    sent_key = request.headers.get('X-Api-Key')
    if not sent_key:
        return None
    
    if sent_key == current_app.config.get('EXECUTION_API_KEY'):
        return True
    return None

# --- Main Routes ---

@main_bp.route('/')
@main_bp.route('/index')
@login_required
def index():
    if current_user.is_instructor:
        return redirect(url_for('main.instructor_dashboard'))
    elif current_user.is_student:
        return redirect(url_for('main.student_dashboard'))
    return "Role not set.", 403

# --- Student Routes ---

@main_bp.route('/student_dashboard')
@login_required
@student_required
def student_dashboard():
    assignments = current_user.assignments
    assignments = db.session.query(ProblemAssignment)\
                            .filter_by(user_id=current_user.id)\
                            .options(joinedload(ProblemAssignment.problem))\
                            .all()
    
    return render_template('student_dashboard.html', title='My Dashboard', user=current_user, assignments=assignments)

@main_bp.route('/problem/<int:problem_id>', methods=['GET', 'POST'])
@login_required
@student_required
def view_problem(problem_id):
    problem = CodingProblem.query.get_or_404(problem_id)
    assignment = current_user.get_assignment(problem_id)
    
    if not assignment:
        flash('You are not assigned this problem.', 'danger')
        return redirect(url_for('main.student_dashboard'))

    form = SubmissionForm()
    
    if form.validate_on_submit():
        if not problem.is_open:
            flash('This problem is no longer accepting submissions.', 'warning')
            return redirect(url_for('main.view_problem', problem_id=problem_id))

        submission = CodeSubmission(
            student=current_user,
            problem=problem,
            language=form.language.data,
            code=form.code.data,
            status='Pending'
        )
        db.session.add(submission)
        db.session.commit() # Commit to get a submission.id

        # --- Prepare Lambda Payload ---
        private_test_cases = problem.private_test_cases
        total_possible_score = 0
        
        if problem.scoring_type == ScoringType.EQUAL:
            num_private = len(private_test_cases)
            score_per_case = (problem.total_score / num_private) if num_private > 0 else 0
            total_possible_score = problem.total_score
            
            for tc in private_test_cases:
                tc.score = score_per_case 
        else:
            total_possible_score = sum(tc.score for tc in private_test_cases)

        all_test_cases = [
            {'id': tc.id, 'input': tc.input_data, 'output': tc.expected_output, 'is_public': True, 'score': 0}
            for tc in problem.public_test_cases
        ] + [
            {'id': tc.id, 'input': tc.input_data, 'output': tc.expected_output, 'is_public': False, 'score': tc.score}
            for tc in private_test_cases
        ]
        
        payload = {
            'submission_id': submission.id,
            'language': submission.language,
            'code': submission.code,
            'test_cases': all_test_cases,
            'total_score': total_possible_score, 
            'callback_url': url_for('main.submission_callback', _external=True),
            'api_key': current_app.config.get('EXECUTION_API_KEY')
        }
        
        try:
            # --- FIX IS HERE ---
            # Create the client *inside* the route, not globally.
            lambda_client = boto3.client('lambda', region_name=current_app.config.get('AWS_REGION'))
            
            lambda_client.invoke(
                FunctionName=current_app.config.get('EXECUTION_LAMBDA_NAME'),
                InvocationType='Event', # Asynchronous
                Payload=json.dumps(payload)
            )
            flash('Your code has been submitted and is running!', 'info')
        except Exception as e:
            current_app.logger.error(f"Lambda invocation failed: {e}")
            submission.status = 'Error'
            submission.execution_output = f'Failed to start execution: {e}'
            db.session.commit()
            flash('There was an error submitting your code.', 'danger')

        return redirect(url_for('main.view_problem', problem_id=problem_id))

    # --- GET Request ---
    submissions = CodeSubmission.query.filter_by(
        user_id=current_user.id, 
        problem_id=problem_id
    ).order_by(CodeSubmission.timestamp.desc()).all()
    
    best_submission = assignment.best_submission

    return render_template(
        'view_problem.html', 
        title=problem.title, 
        problem=problem, 
        form=form,
        submissions=submissions,
        best_submission=best_submission,
        assignment=assignment
    )

@main_bp.route('/submission/<int:submission_id>')
@login_required
def view_submission(submission_id):
    submission = CodeSubmission.query.options(
        joinedload(CodeSubmission.problem),
        joinedload(CodeSubmission.student)
    ).get_or_404(submission_id)
    
    # Security check
    if current_user.is_student and submission.user_id != current_user.id:
        abort(403)
    if current_user.is_instructor and submission.problem.creator_id != current_user.id:
        abort(403)
        
    return render_template('view_submission.html', title=f"Submission {submission.id}", submission=submission)


# --- Instructor Routes ---

@main_bp.route('/instructor_dashboard')
@login_required
@instructor_required
def instructor_dashboard():
    created_problems = current_user.created_problems.order_by(CodingProblem.id.desc()).all()
    return render_template('instructor_dashboard.html', title='Instructor Dashboard', user=current_user, problems=created_problems)

@main_bp.route('/create_problem', methods=['GET', 'POST'])
@login_required
@instructor_required
def create_problem():
    form = CodingProblemForm()
    
    if form.validate_on_submit():
        problem = CodingProblem(
            title=form.title.data,
            description=form.description.data,
            creator=current_user,
            is_open=form.is_open.data,
            scoring_type=ScoringType(form.scoring_type.data),
            total_score=form.total_score.data if form.scoring_type.data == ScoringType.EQUAL.value else 0
        )
        db.session.add(problem)
        
        # Public
        for tc_form in form.public_test_cases.data:
            if tc_form['input_data'] or tc_form['expected_output']: 
                problem.test_cases.append(TestCase(
                    is_public=True,
                    input_data=tc_form['input_data'],
                    expected_output=tc_form['expected_output'],
                    score=0
                ))
        
        # Private
        custom_total = 0
        for tc_form in form.private_test_cases.data:
            if not tc_form['input_data'] or not tc_form['expected_output']:
                flash('All private test cases must have input and output.', 'danger')
                return render_template('create_problem.html', title='Create Problem', form=form)
            
            score = tc_form['score'] if problem.scoring_type == ScoringType.CUSTOM else 0
            if problem.scoring_type == ScoringType.CUSTOM:
                custom_total += (score or 0) # Handle None

            problem.test_cases.append(TestCase(
                is_public=False,
                input_data=tc_form['input_data'],
                expected_output=tc_form['expected_output'],
                score=score or 0
            ))
        
        if problem.scoring_type == ScoringType.CUSTOM:
            problem.total_score = custom_total
        
        try:
            db.session.commit()
            flash('New coding problem created!', 'success')
            return redirect(url_for('main.problem_dashboard', problem_id=problem.id))
        except Exception as e:
            db.session.rollback()
            current_app.logger.error(f"Error creating problem: {e}")
            flash(f'Error creating problem: {e}', 'danger')
            
    return render_template('create_problem.html', title='Create Problem', form=form)


@main_bp.route('/problem/<int:problem_id>/edit', methods=['GET', 'POST'])
@login_required
@instructor_required
def edit_problem(problem_id):
    problem = CodingProblem.query.options(joinedload(CodingProblem.test_cases)).get_or_404(problem_id)
    if problem.creator_id != current_user.id:
        abort(403)

    form = CodingProblemForm(obj=problem)

    if form.validate_on_submit():
        problem.title = form.title.data
        problem.description = form.description.data
        problem.is_open = form.is_open.data
        problem.scoring_type = ScoringType(form.scoring_type.data)
        problem.total_score = form.total_score.data if problem.scoring_type == ScoringType.EQUAL else 0

        for tc in problem.test_cases:
            db.session.delete(tc)
        
        problem.test_cases = [] 
        
        for tc_form in form.public_test_cases.data:
            if tc_form['input_data'] or tc_form['expected_output']:
                problem.test_cases.append(TestCase(
                    is_public=True,
                    input_data=tc_form['input_data'],
                    expected_output=tc_form['expected_output'],
                    score=0
                ))
        
        custom_total = 0
        for tc_form in form.private_test_cases.data:
            if not tc_form['input_data'] or not tc_form['expected_output']:
                flash('All private test cases must have input and output.', 'danger')
                return render_template('create_problem.html', title='Edit Problem', form=form, problem=problem)
            
            score = tc_form['score'] if problem.scoring_type == ScoringType.CUSTOM else 0
            if problem.scoring_type == ScoringType.CUSTOM:
                custom_total += (score or 0)

            problem.test_cases.append(TestCase(
                is_public=False,
                input_data=tc_form['input_data'],
                expected_output=tc_form['expected_output'],
                score=score or 0
            ))
            
        if problem.scoring_type == ScoringType.CUSTOM:
            problem.total_score = custom_total
            
        try:
            db.session.commit()
            flash('Problem updated successfully!', 'success')
            return redirect(url_for('main.problem_dashboard', problem_id=problem.id))
        except Exception as e:
            db.session.rollback()
            current_app.logger.error(f"Error updating problem: {e}")
            flash(f'Error updating problem: {e}', 'danger')

    elif request.method == 'GET':
        form.title.data = problem.title
        form.description.data = problem.description
        form.is_open.data = problem.is_open
        form.scoring_type.data = problem.scoring_type.value
        form.total_score.data = problem.total_score

        form.public_test_cases.pop_entry()
        form.private_test_cases.pop_entry()
        
        for tc in problem.public_test_cases:
            form.public_test_cases.append_entry(tc)
        for tc in problem.private_test_cases:
            form.private_test_cases.append_entry(tc)
        
        if not form.public_test_cases:
            form.public_test_cases.append_entry()
        if not form.private_test_cases:
            form.private_test_cases.append_entry()

    return render_template('create_problem.html', title='Edit Problem', form=form, problem=problem)

@main_bp.route('/problem/<int:problem_id>/assign', methods=['GET', 'POST'])
@login_required
@instructor_required
def assign_problem(problem_id):
    problem = CodingProblem.query.get_or_404(problem_id)
    if problem.creator_id != current_user.id:
        abort(403)

    form = AssignmentForm()
    
    all_students = User.query.filter_by(role=UserRole.STUDENT).all()
    form.students.choices = [(s.id, s.name) for s in all_students]

    if form.validate_on_submit():
        if form.assign_to_all.data:
            selected_students = all_students
        else:
            selected_student_ids = form.students.data
            selected_students = User.query.filter(User.id.in_(selected_student_ids)).all()
        
        current_assignments = {pa.user_id: pa for pa in problem.assignments}
        selected_student_ids = {s.id for s in selected_students}
        
        for student_id in selected_student_ids:
            if student_id not in current_assignments:
                new_assignment = ProblemAssignment(student=User.query.get(student_id), problem=problem)
                db.session.add(new_assignment)
                
        for student_id, assignment in current_assignments.items():
            if student_id not in selected_student_ids:
                db.session.delete(assignment)
        
        try:
            db.session.commit()
            flash(f'Assignments for "{problem.title}" updated!', 'success')
            return redirect(url_for('main.problem_dashboard', problem_id=problem.id))
        except Exception as e:
            db.session.rollback()
            current_app.logger.error(f"Error assigning problem: {e}")
            flash(f'Error updating assignments: {e}', 'danger')

    elif request.method == 'GET':
        assigned_student_ids = [pa.user_id for pa in problem.assignments]
        form.students.data = assigned_student_ids

    return render_template('assign_problem.html', title='Assign Problem', form=form, problem=problem)

@main_bp.route('/problem/<int:problem_id>/dashboard')
@login_required
@instructor_required
def problem_dashboard(problem_id):
    
    # --- THIS IS THE FIX ---
    # We must tell SQLAlchemy the *path* to the relationships:
    # CodingProblem -> assignments -> student
    # CodingProblem -> assignments -> best_submission
    problem = CodingProblem.query.options(
        joinedload(CodingProblem.assignments).options(
            joinedload(ProblemAssignment.student),
            joinedload(ProblemAssignment.best_submission)
        )
    ).get_or_404(problem_id)
    # --- END FIX ---
    
    if problem.creator_id != current_user.id:
        abort(403)
        
    assignments = problem.assignments
    average_score = problem.average_score
    
    return render_template(
        'problem_dashboard.html', 
        title=f"Dashboard: {problem.title}", 
        problem=problem,
        assignments=assignments,
        average_score=average_score
    )

# --- API Routes ---

@main_bp.route('/api/submission_callback', methods=['POST'])
def submission_callback():
    """
    API endpoint for the Lambda function to post results back.
    """
    if not get_user_from_header():
        abort(403) 
    
    data = request.json
    
    try:
        submission_id = data['submission_id']
        submission = CodeSubmission.query.get(submission_id)
        
        if not submission:
            current_app.logger.warning(f"Callback received for unknown submission ID: {submission_id}")
            return jsonify({'status': 'error', 'message': 'Submission not found'}), 404
            
        submission.status = data['status']
        submission.score_achieved = data['score_achieved']
        submission.total_score = data['total_score']
        submission.execution_output = data['output']
        
        assignment = ProblemAssignment.query.get((submission.user_id, submission.problem_id))
        if assignment:
            if submission.score_achieved > assignment.best_score:
                assignment.best_score = submission.score_achieved
                assignment.best_submission_id = submission.id
        else:
            current_app.logger.error(f"No assignment found for user {submission.user_id}, problem {submission.problem_id}")
            
        db.session.commit()
        
        return jsonify({'status': 'success'}), 200

    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error in submission_callback: {e}\nData: {data}")
        return jsonify({'status': 'error', 'message': str(e)}), 500


# --- NEW FIX: API Route for Polling ---
@main_bp.route('/api/submission_status/<int:submission_id>')
@login_required
def get_submission_status(submission_id):
    """
    API endpoint for the view_submission.html page to poll.
    """
    submission = CodeSubmission.query.get_or_404(submission_id)
    
    # Security check: Only the student who made it or the instructor can view
    if current_user.is_student and submission.user_id != current_user.id:
        abort(403)
    if current_user.is_instructor and submission.problem.creator_id != current_user.id:
        abort(403)

    return jsonify({
        'status': submission.status,
        'output': submission.execution_output,
        'score': submission.score_a_chieved
    })

# --- Auth Routes ---

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
        next_page = request.args.get('next')
        if not next_page:
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
        user = User(
            name=form.name.data,
            username=form.username.data,
            age=form.age.data,
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

