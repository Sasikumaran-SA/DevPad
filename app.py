import os
from flask import Flask
from config import Config
from extensions import db, migrate, login_manager
# ...existing code...

# Configure login manager defaults
login_manager.login_view = 'main.login'
login_manager.login_message_category = 'info'

def create_app(config_class=Config):
    """
    Application factory pattern.
    Initializes and configures the Flask application.
    """
    app = Flask(__name__)
    app.config.from_object(config_class)
    
    # Add a templates folder
    app.template_folder = 'templates'

    # Initialize extensions with the app
    db.init_app(app)
    migrate.init_app(app, db)
    login_manager.init_app(app)

    # --- Import and register blueprints/routes ---
    # We import here to avoid circular dependencies
    
    # Import the blueprint from routes.py
    from routes import main_bp
    # Register the blueprint with the app
    app.register_blueprint(main_bp)
    
    with app.app_context():
        # Import models so Flask-Migrate can see them
        import models

    # --- User loader for Flask-Login ---
    @login_manager.user_loader
    def load_user(user_id):
        # Flask-Login uses this to reload the user object from the user ID stored in the session
        from models import User # Import here to avoid circular import
        return User.query.get(int(user_id))

    return app

# Create the app instance
app = create_app()

if __name__ == '__main__':
    # Get port from environment variable or default to 5000
    port = int(os.environ.get('PORT', 5000))
    # Run the app
    # Use 0.0.0.0 to make it accessible on your network, not just localhost
    app.run(debug=True, host='0.0.0.0', port=port)
# ...existing code...