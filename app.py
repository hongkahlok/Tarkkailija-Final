import datetime
import json
import time
from flask import Blueprint, render_template, url_for, redirect, request, flash, make_response, \
    Response, jsonify, Markup
from flask_login import login_user, login_required, logout_user, current_user, LoginManager, UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from functools import wraps
from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from Run import Video
from datetime import datetime

# Initialize SQLAlchemy to use in the system.
db = SQLAlchemy()


# If DB does not exist, create DB based on the specifications below.
class Users(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), nullable=False)
    email = db.Column(db.String(50), nullable=False, unique=True)
    password = db.Column(db.String(100), nullable=False)
    role = db.Column(db.String(15), nullable=False, default="user")


class Logs(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    occupantcount = db.Column(db.Integer, nullable=False)
    datetime = db.Column(db.String(100), nullable=False)
    thresholdreached = db.Column(db.Boolean, nullable=False)


# Define Flask App Settings.
def create_app():
    app = Flask(__name__)
    app.register_error_handler(404, page_not_found)
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = True
    app.config['SECRET_KEY'] = 'secretkey'
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///db.sqlite'
    db.init_app(app)

    with app.app_context():
        db.create_all()
        db.session.commit()

    login_manager = LoginManager()
    login_manager.login_view = 'auth.userlogin'
    login_manager.init_app(app)

    @login_manager.user_loader
    def load_user(user_id):
        # since user_id is the primary key in the user table, use it in the query for the user
        return Users.query.get(int(user_id))

    # blueprint for auth routes in our app
    from app import auth as auth_blueprint
    app.register_blueprint(auth_blueprint)
    gen(Video())  # Start running OpenCV video.
    return app


# Define roles for the system to prevent unauthorised access on certain pages.
def requires_roles(*roles):
    def wrapper(f):
        @wraps(f)
        def wrapped(*args, **kwargs):
            if current_user.role not in roles and current_user.role == 'user':
                # Redirect the user to an unauthorized notice to user dashboard!
                flash('User is not authorised to access administrator services.')
                return redirect(url_for('auth.user_dashboard'))

            if current_user.role not in roles and current_user.role == 'admin':
                # Redirect the user to an unauthorized notice to staff dashboard!
                flash('Administrator is not authorised to access normal user services.')
                return redirect(url_for('auth.staff_dashboard'))
            return f(*args, **kwargs)

        return wrapped

    return wrapper


auth = Blueprint('auth', __name__)


# Route for the main Homepage.
@auth.route('/')
def index():
    if current_user.is_authenticated and current_user.role == 'admin':
        return redirect(url_for('auth.admindashboard'))
    elif current_user.is_authenticated and current_user.role == 'user':
        return redirect(url_for('auth.userdashboard'))
    else:
        return render_template('index.html')


@auth.route('/userlogin')
def userlogin():
    if current_user.is_authenticated and current_user.role == 'admin':
        return redirect(url_for('auth.admindashboard'))
    elif current_user.is_authenticated and current_user.role == 'user':
        return redirect(url_for('auth.userdashboard'))
    else:
        return render_template('userlogin.html')


# Route for the login page POST request, handle the user login logic.
@auth.route('/userlogin', methods=['POST'])
def userlogin_post():
    email = request.form.get('email')
    password = request.form.get('password')
    user = Users.query.filter_by(email=email).first()

    # Check if the user actually exists
    # Take the user-supplied password, hash it, and compare it to the hashed password in the database
    if user is None:
        flash('An user account does not exist in this email.')
        # If the user doesn't exist or password is wrong, reload the page
        return redirect(
            url_for('auth.userlogin'))

    elif user.role == "admin":
        flash(Markup(
            'Please use the <a href="/adminlogin"><span style="color:black; text-decoration: underline;">administrator login</span></a> to log into your account.'))
        return render_template('userlogin.html')

    elif not user or not check_password_hash(user.password, password):
        flash('Please check your login details and try again.')
        # if the user doesn't exist or password is wrong, reload the page
        return redirect(url_for('auth.userlogin'))

    # if the check pass, then the user has the right credentials
    elif user.role == "user":
        login_user(user)
        return redirect(url_for('auth.userdashboard'))


@auth.route('/adminlogin')
def adminlogin():
    if current_user.is_authenticated and current_user.role == 'admin':
        return redirect(url_for('auth.admindashboard'))
    elif current_user.is_authenticated and current_user.role == 'user':
        return redirect(url_for('auth.userdashboard'))
    else:
        return render_template('adminlogin.html')


# Route for the staff login page POST request, handle the staff login logic.
@auth.route('/adminlogin', methods=['POST'])
def adminlogin_post():
    email = request.form.get('email')
    password = request.form.get('password')
    user = Users.query.filter_by(email=email).first()

    # check if the staff actually exists
    # take the staff-supplied password, hash it, and compare it to the hashed password in the database
    if user is None:
        flash('An user account does not exist in this email.')
        return render_template('adminlogin.html')

    elif user.role == "user":
        flash(Markup(
            'Please use the <a href="/adminlogin"><span style="color:black; text-decoration: underline;">user login</span></a> to log into your account.'))
        return render_template('adminlogin.html')

    elif user.email == email and check_password_hash(user.password, password) and user.role == 'admin':
        # if the above check passes, then the staff has the right credentials
        login_user(user)
        return redirect(url_for('auth.admindashboard'))

    elif not user or not check_password_hash(user.password, password) or user is None:
        flash('Please check your login details and try again.')
        return render_template('adminlogin.html')


@auth.route('/userregister')
def userregister():
    if current_user.is_authenticated and current_user.role == 'admin':
        return redirect(url_for('auth.admindashboard'))
    elif current_user.is_authenticated and current_user.role == 'user':
        return redirect(url_for('auth.userdashboard'))
    else:
        return render_template('userregister.html')


@auth.route('/userregister', methods=['POST'])
def userregister_post():
    # Code to validate and add user to database goes here
    email = request.form.get('email')
    name = request.form.get('name')
    password = request.form.get('password')
    confirmpassword = request.form.get('new-password')

    # If this returns a user, then the email already exists in database
    user = Users.query.filter_by(email=email).first()

    # If a user is found, we want to redirect back to register page so user can try again
    if user:
        flash('Email address already exists!')
        return redirect(url_for('auth.userregister'))

    if password != confirmpassword:
        flash('The password and confirm password does not match!')
        return redirect(url_for('auth.userregister'))

    # Create a new user with the form data. Hash the password so the plaintext version isn't saved.
    new_user = Users(name=name, email=email, password=generate_password_hash(password, method='sha256'))

    # Add the new user to the database
    db.session.add(new_user)
    db.session.commit()

    flash('Log into your newly registered account below to continue!')
    return redirect(url_for('auth.userlogin'))


# temp testing
@auth.route('/dashboard')
def dashboard():
    return render_template('testdashboard.html')


@auth.route('/userdashboard')
def userdashboard():
    if current_user.is_authenticated and current_user.role == 'admin':
        return redirect(url_for('auth.admindashboard'))
    elif current_user.is_authenticated and current_user.role == 'user':
        return render_template('userdashboard.html', name=current_user.name)
    return redirect(url_for('auth.index'))


@auth.route('/admindashboard')
def admindashboard():
    if current_user.is_authenticated and current_user.role == 'admin':
        return render_template('admindashboard.html', name=current_user.name)
    elif current_user.is_authenticated and current_user.role == 'user':
        return redirect(url_for('auth.userdashboard'))
    return redirect(url_for('auth.index'))


# History Page
@auth.route('/history')
def history():
    log_list = Logs.query.all()
    if current_user.is_authenticated and current_user.role == 'admin':
        f_time = str(datetime.now().strftime("%d %B %Y - %H:%M:%S"))
        status = Video.get_crowd_count()
        demo = Logs(occupantcount=status[0], datetime=f_time, thresholdreached=status[3])

        # add the new log to the database
        db.session.add(demo)
        db.session.commit()
        return render_template('history.html', name=current_user.name, log_list=log_list)

    elif current_user.is_authenticated and current_user.role == 'user':
        f_time = str(datetime.now().strftime("%d %B %Y - %H:%M:%S"))
        status = Video.get_crowd_count()
        demo = Logs(occupantcount=status[0], datetime=f_time, thresholdreached=status[3])

        # add the new log to the database
        db.session.add(demo)
        db.session.commit()
        return render_template('history.html', name=current_user.name, log_list=log_list)
    return redirect(url_for('auth.index'))


# Settings Page
@auth.route('/settings')
def settings():
    if current_user.is_authenticated and current_user.role == 'admin':
        return render_template('settings.html', name=current_user.name, email=current_user.email)
    elif current_user.is_authenticated and current_user.role == 'user':
        return render_template('settings.html', name=current_user.name, email=current_user.email)
    return redirect(url_for('auth.index'))


# Help Page
@auth.route('/help')
def help():
    if current_user.is_authenticated and current_user.role == 'admin':
        return render_template('help.html', name=current_user.name)
    elif current_user.is_authenticated and current_user.role == 'user':
        return render_template('help.html', name=current_user.name)
    return redirect(url_for('auth.index'))


# Route for the custom 404: Page Not Found page.
@auth.errorhandler(404)
def page_not_found(e):
    # note that we set the 404 status explicitly
    return render_template('404.html'), 404


# Route for the registration with validation if the user is already logged in.
@auth.route('/register')
def register():
    if current_user.is_authenticated and current_user.role == 'admin':
        flash('Please log out from your account to create a new account!')
        return redirect(url_for('auth.staff_dashboard'))
    elif current_user.is_authenticated and current_user.role == 'user':
        flash('Please log out from your account to create a new account!')
        return redirect(url_for('auth.user_dashboard'))
    else:
        return render_template('register.html')


# Route for the registration page POST request, handle the user registration logic.
@auth.route('/register', methods=['POST'])
def register_post():
    # code to validate and add user to database goes here
    email = request.form.get('email')
    name = request.form.get('name')
    password = request.form.get('password')
    # if this returns a user, then the email already exists in database
    user = Users.query.filter_by(
        email=email).first()

    if user:  # if a user is found, we want to redirect back to register page so user can try again
        flash('Email address already exists!')
        return redirect(url_for('auth.register'))

    # create a new user with the form data. Hash the password so the plaintext version isn't saved.
    new_user = Users(name=name, email=email, password=generate_password_hash(password, method='sha256'))

    # add the new user to the database
    db.session.add(new_user)
    db.session.commit()

    flash('Log into your newly registered account below to continue!')
    return redirect(url_for('auth.userlogin'))


# Route for logout which would delete the session token and redirect the user to the homepage.
@auth.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('auth.index'))


# Function that grabs frames from OpenCV which runs on a separate thread from the main web application.
def gen(video):
    while True:
        frame = video.get_frame()
        yield (b'--frame\r\n'
               b'Content-Type: image/jpeg\r\n\r\n' + frame + b'\r\n')


# Route for the video feed that grab the image frames from a separate thread.
@auth.route('/video-feed', methods=['GET'])
@login_required
@requires_roles('admin')
def video_feed():
    # Return video frames as images
    return Response(gen(Video()),
                    mimetype='multipart/x-mixed-replace; boundary=frame')


# Route for data that stores current time as epoch and crowd status as an array for charting using Highcharts.
@auth.route('/data')
@login_required
def data():
    status = Video.get_crowd_count()
    graph_data = [(time.time() + 28800) * 1000, status[0]]  # 28800 is offset for GMT+8
    response = make_response(json.dumps(graph_data))
    response.content_type = 'application/json'
    return response


# Route for data that stores the crowd level, crowd status as a JSON file.
@auth.route('/crowd-data', methods=['GET'])
@login_required
def crowd_data():
    status = Video.get_crowd_count()

    return jsonify(
        currentTotal=status[0],
        totalIn=status[1],
        totalOut=status[2]
    )


# Specifies the Flask settings to the create app function.
application = create_app()

# Initialise the Flask debug server based on the application settings and runs on :5000
if __name__ == '__main__':
    application.run(host='127.0.0.1')
