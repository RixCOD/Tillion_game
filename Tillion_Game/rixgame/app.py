from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
from pymongo import MongoClient
import jwt
import datetime
from functools import wraps
import re
import os
from werkzeug.utils import secure_filename

# --- Setup ---
app = Flask(__name__)
CORS(app)
app.config['SECRET_KEY'] = 'your_secret_key'
app.config['UPLOAD_FOLDER'] = 'uploads'
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

client = MongoClient("mongodb://localhost:27017/")
db = client['gameDB']
users = db['users']

# --- Helpers ---
def token_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        token = request.headers.get('Authorization')
        if not token:
            return jsonify({'error': 'Token is missing!'}), 401
        try:
            data = jwt.decode(token, app.config['SECRET_KEY'], algorithms=['HS256'])
            current_user = users.find_one({'username': data['username']})
            if not current_user:
                raise Exception("User not found")
        except Exception:
            return jsonify({'error': 'Invalid or expired token!'}), 401
        return f(current_user, *args, **kwargs)
    return decorated

def is_valid_email(email):
    return re.match(r'^[\w\.-]+@[\w\.-]+\.\w+$', email)

# --- Routes ---

@app.route('/signup', methods=['POST'])
def signup():
    data = request.get_json()
    username = data.get('username')
    password = data.get('password')
    email = data.get('email')
    avatar = data.get('avatar', '')

    if not username or not password or not email:
        return jsonify({'error': 'All fields are required'}), 400
    if not is_valid_email(email):
        return jsonify({'error': 'Invalid email address'}), 400
    if users.find_one({'username': username}):
        return jsonify({'error': 'Username already exists'}), 400

    users.insert_one({
        'username': username,
        'password': password,
        'email': email,
        'avatar': avatar,
        'score': 0,
        'wins': 0,
        'joined': datetime.datetime.utcnow(),
        'achievements': ['Joined the game']
    })
    return jsonify({'message': 'Signup successful'}), 200

@app.route('/signin', methods=['POST'])
def signin():
    data = request.get_json()
    user = users.find_one({'username': data.get('username'), 'password': data.get('password')})
    if not user:
        return jsonify({'error': 'Invalid credentials'}), 401

    token = jwt.encode({
        'username': user['username'],
        'exp': datetime.datetime.utcnow() + datetime.timedelta(hours=3)
    }, app.config['SECRET_KEY'], algorithm='HS256')

    return jsonify({'message': 'Login successful', 'token': token}), 200

@app.route('/profile.html', methods=['GET'])
@token_required
def profile(current_user):
    return jsonify({
        'username': current_user['username'],
        'email': current_user.get('email'),
        'avatar': current_user.get('avatar', ''),
        'score': current_user.get('score', 0),
        'wins': current_user.get('wins', 0),
        'joined': current_user.get('joined').strftime('%Y-%m-%d'),
        'achievements': current_user.get('achievements', [])
    })

@app.route('/update-username', methods=['POST'])
@token_required
def update_username(current_user):
    data = request.get_json()
    new_username = data.get('username')
    if not new_username:
        return jsonify({'error': 'New username is required'}), 400
    if users.find_one({'username': new_username}):
        return jsonify({'error': 'Username already taken'}), 400

    users.update_one({'username': current_user['username']}, {'$set': {'username': new_username}})
    
    token = jwt.encode({
        'username': new_username,
        'exp': datetime.datetime.utcnow() + datetime.timedelta(hours=3)
    }, app.config['SECRET_KEY'], algorithm='HS256')

    return jsonify({'message': 'Username updated', 'token': token}), 200

@app.route('/upload-avatar', methods=['POST'])
@token_required
def upload_avatar(current_user):
    if 'avatar' not in request.files:
        return jsonify({'error': 'No avatar file provided'}), 400
    file = request.files['avatar']
    filename = secure_filename(file.filename)
    filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
    file.save(filepath)

    avatar_url = f'/uploads/{filename}'
    users.update_one({'username': current_user['username']}, {'$set': {'avatar': avatar_url}})
    return jsonify({'message': 'Avatar uploaded', 'avatar': avatar_url}), 200

@app.route('/uploads/<filename>')
def serve_file(filename):
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

@app.route('/update_score', methods=['POST'])
@token_required
def update_score(current_user):
    result = request.json.get('result')  # 'win', 'loss', 'tie'
    update = {}
    if result == 'win':
        update = {'$inc': {'score': 1, 'wins': 1}}
    elif result == 'loss':
        update = {'$inc': {'score': -1}}
    if update:
        users.update_one({'username': current_user['username']}, update)
    return jsonify({'message': 'Score updated'}), 200

@app.route('/leaderboard', methods=['GET'])
def leaderboard():
    top_users = list(users.find({}, {
        '_id': 0,
        'username': 1,
        'score': 1,
        'wins': 1,
        'avatar': 1
    }).sort('score', -1).limit(10))
    return jsonify(top_users), 200

# --- Run App ---
if __name__ == '__main__':
    app.run(debug=True)
