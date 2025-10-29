from flask import render_template, redirect, url_for, flash, request, Blueprint, current_app
from extensions import db # Import ONLY db from extensions
from models import User
from flask_login import login_user, logout_user, current_user, login_required
# ...existing code...

# --- Form Imports (from old forms.py) ---
from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, SubmitField, IntegerField
from wtforms.validators import DataRequired, Email, EqualTo, ValidationError, NumberRange

# --- Create a Blueprint ---
# We'll register all our routes with this blueprint instead of 'app'
main_bp = Blueprint('main', __name__)

# --- Form Definitions (from old forms.py) ---

class LoginForm(FlaskForm):
    """
    Form for user login.
    'username' field is used for email.
    """
    username = StringField('Email (Username)', validators=[DataRequired(), Email()])
    password = PasswordField('Password', validators=[DataRequired()])
    submit = SubmitField('Sign In')

class RegistrationForm(FlaskForm):
    """
    Form for new user registration.
    """
    name = StringField('Full Name', validators=[DataRequired()])
    username = StringField('Email (Username)', validators=[DataRequired(), Email()])
    age = IntegerField('Age', validators=[DataRequired(), NumberRange(min=13, max=120, message="You must be at least 13 years old.")])
    password = PasswordField('Password', validators=[DataRequired()])
    confirm_password = PasswordField(
        'Confirm Password', 
        validators=[DataRequired(), EqualTo('password', message='Passwords must match.')]
    )
    submit = SubmitField('Register')

    def validate_username(self, username):
        """
        Custom validator to check if the email (username) is already in use.
        """
        user = User.query.filter_by(username=username.data).first()
        if user:
            raise ValidationError('That email is already in use. Please choose a different one.')

# --- Route Definitions ---
# *** IMPORTANT: Change all '@app.route' to '@main_bp.route' ***

@main_bp.route('/')
@main_bp.route('/index')
@login_required  # Protect this route
def index():
    """
    Homepage for logged-in users.
    """
    # current_user is available thanks to Flask-Login
    return render_template('index.html', title='Home', user=current_user)

@main_bp.route('/login', methods=['GET', 'POST'])
def login():
    """
    Login page route.
    Handles both displaying the form (GET) and processing the login (POST).
    """
    # If user is already logged in, redirect to index
    if current_user.is_authenticated:
        return redirect(url_for('main.index'))
        
    form = LoginForm()
    
    # This block runs when the form is submitted and passes validation
    if form.validate_on_submit():
        # Find the user by their email (stored in 'username' field)
        user = User.query.filter_by(username=form.username.data).first()
        
        # Check if user exists and password is correct
        if user is None or not user.check_password(form.password.data):
            flash('Invalid username or password', 'danger') # 'danger' is a bootstrap class
            return redirect(url_for('main.login'))
        
        # User is valid, log them in
        login_user(user)
        
        # Check for 'next' parameter (for redirecting after login)
        next_page = request.args.get('next')
        if not next_page:
            next_page = url_for('main.index')
            
        flash('Login successful!', 'success')
        return redirect(next_page)

    # Render the login template for GET requests or if validation failed
    return render_template('login.html', title='Sign In', form=form)

@main_bp.route('/logout')
def logout():
    """
    Logs the user out.
    """
    logout_user()
    flash('You have been logged out.', 'info')
    return redirect(url_for('main.login'))

@main_bp.route('/register', methods=['GET', 'POST'])
def register():
    """
    Registration page route.
    Handles both displaying the form (GET) and processing registration (POST).
    """
    # If user is already logged in, redirect to index
    if current_user.is_authenticated:
        return redirect(url_for('main.index'))
        
    form = RegistrationForm()
    
    if form.validate_on_submit():
        # Create a new user instance
        user = User(
            name=form.name.data,
            username=form.username.data,  # This is the email
            age=form.age.data
        )
        # Set the hashed password
        user.set_password(form.password.data)
        
        # Add to database session and commit
        try:
            db.session.add(user)
            db.session.commit()
            flash('Congratulations, you are now a registered user!', 'success')
            return redirect(url_for('main.login'))
        except Exception as e:
            db.session.rollback()
            flash(f'An error occurred. Could not register user. {e}', 'danger')
            # FIXED: Use current_app.logger instead of app.logger
            current_app.logger.error(f"Error on registration: {e}")

    # Render the registration template
    return render_template('register.html', title='Register', form=form)

