import os
import sys
import logging
from flask import Flask, render_template, jsonify, request, redirect, url_for, session, make_response
import json
import cv2
import numpy as np
from datetime import datetime, timedelta
from werkzeug.utils import secure_filename
from werkzeug.security import generate_password_hash, check_password_hash
from PIL import Image
import pickle
from ultralytics import YOLO
import torch
import re
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from sqlalchemy import or_, and_, desc, func
from flask_dance.contrib.google import make_google_blueprint, google
from flask_dance.consumer import oauth_authorized
from sqlalchemy.orm import relationship
import secrets
import string
import requests
from dotenv import load_dotenv
from functools import wraps
import time

# Настройка логирования
logging.basicConfig(level=logging.INFO)

# Загружаем переменные окружения
load_dotenv()

app = Flask(__name__)

# Секретный ключ из переменных окружения
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', secrets.token_hex(32))

# Настройки для продакшена
app.config['SESSION_COOKIE_SECURE'] = True  # Для HTTPS
app.config['SESSION_COOKIE_HTTPONLY'] = True
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
app.config['SESSION_COOKIE_DOMAIN'] = None
app.config['SESSION_PERMANENT'] = True
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(days=7)
app.config['REMEMBER_COOKIE_DURATION'] = timedelta(days=7)
app.config['REMEMBER_COOKIE_SECURE'] = True
app.config['REMEMBER_COOKIE_HTTPONLY'] = True

# Конфигурация базы данных - используем абсолютный путь
basedir = os.path.abspath(os.path.dirname(__file__))
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URL',
                                                       'sqlite:///' + os.path.join(basedir, 'cookly.db'))

# Если используется PostgreSQL на Render
if app.config['SQLALCHEMY_DATABASE_URI'] and app.config['SQLALCHEMY_DATABASE_URI'].startswith('postgres://'):
    app.config['SQLALCHEMY_DATABASE_URI'] = app.config['SQLALCHEMY_DATABASE_URI'].replace('postgres://',
                                                                                          'postgresql://', 1)

app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {
    'pool_size': 10,
    'pool_recycle': 3600,
    'pool_pre_ping': True
}

db = SQLAlchemy(app)
migrate = Migrate(app, db)

# Инициализация Flask-Login
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login_page'
login_manager.login_message = 'Пожалуйста, войдите для доступа к этой странице'
login_manager.login_message_category = 'info'

# Конфигурация OAuth
app.config['GOOGLE_OAUTH_CLIENT_ID'] = os.environ.get('GOOGLE_OAUTH_CLIENT_ID')
app.config['GOOGLE_OAUTH_CLIENT_SECRET'] = os.environ.get('GOOGLE_OAUTH_CLIENT_SECRET')

# Конфигурация Telegram Bot
TELEGRAM_BOT_TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN')
TELEGRAM_BOT_USERNAME = os.environ.get('TELEGRAM_BOT_USERNAME', 'CooklyBot')

# Конфигурация загрузки файлов - используем абсолютные пути
UPLOAD_FOLDER = os.path.join(basedir, 'uploads')
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}
MAX_CONTENT_LENGTH = 16 * 1024 * 1024

app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = MAX_CONTENT_LENGTH

# Файлы для хранения данных - используем абсолютные пути
DATA_FOLDER = os.path.join(basedir, 'data')
USER_INGREDIENTS_FILE = os.path.join(DATA_FOLDER, 'user_ingredients.json')

# Пути к модели детекции - используем абсолютные пути
MODEL_FOLDER = os.path.join(basedir, 'model')
MODEL_PATH = os.path.join(MODEL_FOLDER, 'vegetable_detector.pt')
CLASS_NAMES_PATH = os.path.join(MODEL_FOLDER, 'class_names.pkl')

# Создаем необходимые папки
os.makedirs(DATA_FOLDER, exist_ok=True)
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(MODEL_FOLDER, exist_ok=True)
os.makedirs('templates', exist_ok=True)


# ========== ДЕКОРАТОР ДЛЯ JSON ОТВЕТОВ ==========
def json_response(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        try:
            if request.path.startswith('/api/') and not request.accept_mimetypes.accept_json:
                return jsonify({'error': 'Endpoint requires JSON response'}), 406
            return f(*args, **kwargs)
        except Exception as e:
            print(f"❌ Ошибка в {f.__name__}: {e}")
            import traceback
            traceback.print_exc()
            return jsonify({
                'success': False,
                'error': str(e)
            }), 500

    return decorated_function


# ========== СОЗДАЕМ БАЗОВЫЕ ШАБЛОНЫ ==========
def create_error_templates():
    """Создает базовые шаблоны для ошибок, если они отсутствуют"""

    templates_dir = os.path.join(basedir, 'templates')
    os.makedirs(templates_dir, exist_ok=True)

    # Шаблон 404.html
    if not os.path.exists(os.path.join(templates_dir, '404.html')):
        with open(os.path.join(templates_dir, '404.html'), 'w', encoding='utf-8') as f:
            f.write('''<!DOCTYPE html>
<html lang="ru">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Страница не найдена | Cookly</title>
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css">
    <style>
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
        }
        :root {
            --primary-green: #2E7D32;
            --light-green: #E8F5E9;
            --dark-green: #1B5E20;
            --accent-teal: #009688;
        }
        body {
            background: linear-gradient(135deg, var(--light-green), #F5F7FA);
            min-height: 100vh;
            display: flex;
            align-items: center;
            justify-content: center;
            padding: 20px;
        }
        .error-container {
            text-align: center;
            max-width: 600px;
            background: white;
            padding: 50px 40px;
            border-radius: 30px;
            box-shadow: 0 20px 50px rgba(46, 125, 50, 0.15);
            animation: slideUp 0.6s ease;
        }
        @keyframes slideUp {
            from { opacity: 0; transform: translateY(30px); }
            to { opacity: 1; transform: translateY(0); }
        }
        .error-code {
            font-size: 8rem;
            font-weight: 800;
            color: var(--primary-green);
            line-height: 1;
            margin-bottom: 20px;
            text-shadow: 5px 5px 0 var(--light-green);
        }
        .error-title {
            font-size: 2rem;
            color: var(--dark-green);
            margin-bottom: 20px;
        }
        .error-message {
            color: #546E7A;
            margin-bottom: 30px;
            font-size: 1.1rem;
        }
        .btn {
            display: inline-flex;
            align-items: center;
            gap: 10px;
            background: linear-gradient(135deg, var(--primary-green), var(--accent-teal));
            color: white;
            text-decoration: none;
            padding: 15px 30px;
            border-radius: 50px;
            font-weight: 700;
            transition: all 0.3s;
            border: none;
            cursor: pointer;
        }
        .btn:hover {
            transform: translateY(-3px);
            box-shadow: 0 10px 25px rgba(0, 150, 136, 0.3);
        }
        .btn i {
            font-size: 1.1rem;
        }
    </style>
</head>
<body>
    <div class="error-container">
        <div class="error-code">404</div>
        <h1 class="error-title">Страница не найдена</h1>
        <p class="error-message">Извините, запрашиваемая страница не существует или была перемещена.</p>
        <a href="/" class="btn">
            <i class="fas fa-home"></i>
            Вернуться на главную
        </a>
    </div>
</body>
</html>''')

    # Шаблон 500.html
    if not os.path.exists(os.path.join(templates_dir, '500.html')):
        with open(os.path.join(templates_dir, '500.html'), 'w', encoding='utf-8') as f:
            f.write('''<!DOCTYPE html>
<html lang="ru">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Ошибка сервера | Cookly</title>
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css">
    <style>
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
        }
        :root {
            --primary-green: #2E7D32;
            --light-green: #E8F5E9;
            --dark-green: #1B5E20;
            --accent-teal: #009688;
            --error-red: #F44336;
        }
        body {
            background: linear-gradient(135deg, var(--light-green), #F5F7FA);
            min-height: 100vh;
            display: flex;
            align-items: center;
            justify-content: center;
            padding: 20px;
        }
        .error-container {
            text-align: center;
            max-width: 600px;
            background: white;
            padding: 50px 40px;
            border-radius: 30px;
            box-shadow: 0 20px 50px rgba(46, 125, 50, 0.15);
            animation: slideUp 0.6s ease;
        }
        @keyframes slideUp {
            from { opacity: 0; transform: translateY(30px); }
            to { opacity: 1; transform: translateY(0); }
        }
        .error-code {
            font-size: 8rem;
            font-weight: 800;
            color: var(--error-red);
            line-height: 1;
            margin-bottom: 20px;
            text-shadow: 5px 5px 0 #FFEBEE;
        }
        .error-title {
            font-size: 2rem;
            color: var(--dark-green);
            margin-bottom: 20px;
        }
        .error-message {
            color: #546E7A;
            margin-bottom: 30px;
            font-size: 1.1rem;
        }
        .btn {
            display: inline-flex;
            align-items: center;
            gap: 10px;
            background: linear-gradient(135deg, var(--primary-green), var(--accent-teal));
            color: white;
            text-decoration: none;
            padding: 15px 30px;
            border-radius: 50px;
            font-weight: 700;
            transition: all 0.3s;
            border: none;
            cursor: pointer;
        }
        .btn:hover {
            transform: translateY(-3px);
            box-shadow: 0 10px 25px rgba(0, 150, 136, 0.3);
        }
        .btn i {
            font-size: 1.1rem;
        }
    </style>
</head>
<body>
    <div class="error-container">
        <div class="error-code">500</div>
        <h1 class="error-title">Ошибка сервера</h1>
        <p class="error-message">Извините, на сервере произошла ошибка. Мы уже работаем над её исправлением.</p>
        <a href="/" class="btn">
            <i class="fas fa-home"></i>
            Вернуться на главную
        </a>
    </div>
</body>
</html>''')

    print("✅ Базовые шаблоны ошибок созданы")


# Создаем шаблоны при запуске
create_error_templates()


# ========== МОДЕЛИ БАЗЫ ДАННЫХ ==========
class User(UserMixin, db.Model):
    """Модель пользователя"""
    __tablename__ = 'users'

    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(120), unique=True, nullable=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(200), nullable=True)
    avatar = db.Column(db.String(500), nullable=True)

    google_id = db.Column(db.String(100), unique=True, nullable=True)
    telegram_id = db.Column(db.String(100), unique=True, nullable=True)

    is_active = db.Column(db.Boolean, default=True)
    is_admin = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    last_login = db.Column(db.DateTime, nullable=True)

    # Отношения
    recipes = db.relationship('Recipe', backref='author', lazy=True, foreign_keys='Recipe.user_id')
    favorites = db.relationship('Favorite', backref='user', cascade='all, delete-orphan', lazy=True)
    user_ingredients = db.relationship('UserIngredient', backref='user', cascade='all, delete-orphan', lazy=True)
    telegram_chats = db.relationship('TelegramChat', backref='user', lazy=True)

    # Изменяем имя backref для likes, чтобы избежать конфликта
    given_likes = db.relationship('Like', backref='liking_user', cascade='all, delete-orphan', lazy=True,
                                  foreign_keys='Like.user_id')

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        if self.password_hash:
            return check_password_hash(self.password_hash, password)
        return False

    def to_dict(self):
        return {
            'id': self.id,
            'email': self.email,
            'username': self.username,
            'avatar': self.avatar,
            'is_admin': self.is_admin,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'last_login': self.last_login.isoformat() if self.last_login else None,
            'google_id': self.google_id,
            'telegram_id': self.telegram_id
        }


class Recipe(db.Model):
    """Модель рецепта"""
    __tablename__ = 'recipes'

    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    image = db.Column(db.String(500), nullable=True)
    time = db.Column(db.String(50), nullable=False)
    difficulty = db.Column(db.String(20), nullable=False)
    calories = db.Column(db.String(50), nullable=False)
    servings = db.Column(db.String(50), nullable=False)
    is_user_recipe = db.Column(db.Boolean, default=False)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Новые поля
    author_name = db.Column(db.String(80), default='Cookly')
    likes_count = db.Column(db.Integer, default=0)

    ingredients = db.relationship('Ingredient', backref='recipe', cascade='all, delete-orphan', lazy=True)
    instructions = db.relationship('Instruction', backref='recipe', cascade='all, delete-orphan', lazy=True)

    # Изменяем имя backref для likes
    received_likes = db.relationship('Like', backref='liked_recipe', cascade='all, delete-orphan', lazy=True,
                                     foreign_keys='Like.recipe_id')

    def to_dict(self):
        return {
            'id': self.id,
            'title': self.title,
            'image': self.image or 'https://images.unsplash.com/photo-1546069901-ba9599a7e63c',
            'time': self.time,
            'difficulty': self.difficulty,
            'calories': self.calories,
            'servings': self.servings,
            'isUserRecipe': self.is_user_recipe,
            'author': self.author.username if self.author else self.author_name,
            'author_id': self.user_id,
            'author_name': self.author_name,
            'likes_count': self.likes_count,
            'ingredients': [ing.to_dict() for ing in self.ingredients],
            'instructions': [inst.to_dict() for inst in self.instructions]
        }


class Like(db.Model):
    """Модель лайка рецепта"""
    __tablename__ = 'likes'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='CASCADE'), nullable=False)
    recipe_id = db.Column(db.Integer, db.ForeignKey('recipes.id', ondelete='CASCADE'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    __table_args__ = (db.UniqueConstraint('user_id', 'recipe_id', name='unique_user_recipe_like'),)

    # Явно указываем foreign_keys для избежания конфликтов
    user = db.relationship('User', foreign_keys=[user_id])
    recipe = db.relationship('Recipe', foreign_keys=[recipe_id])

    def to_dict(self):
        return {
            'id': self.id,
            'user_id': self.user_id,
            'recipe_id': self.recipe_id,
            'created_at': self.created_at.isoformat() if self.created_at else None
        }


class Ingredient(db.Model):
    """Модель ингредиента"""
    __tablename__ = 'ingredients'

    id = db.Column(db.Integer, primary_key=True)
    recipe_id = db.Column(db.Integer, db.ForeignKey('recipes.id', ondelete='CASCADE'), nullable=False)
    name = db.Column(db.String(100), nullable=False)
    amount = db.Column(db.String(50), nullable=False)

    def to_dict(self):
        return {
            'id': self.id,
            'name': self.name,
            'amount': self.amount
        }


class Instruction(db.Model):
    """Модель шага приготовления"""
    __tablename__ = 'instructions'

    id = db.Column(db.Integer, primary_key=True)
    recipe_id = db.Column(db.Integer, db.ForeignKey('recipes.id', ondelete='CASCADE'), nullable=False)
    step_number = db.Column(db.Integer, nullable=False)
    description = db.Column(db.Text, nullable=False)

    def to_dict(self):
        return {
            'id': self.id,
            'step_number': self.step_number,
            'description': self.description
        }


class Favorite(db.Model):
    """Модель избранного рецепта"""
    __tablename__ = 'favorites'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='CASCADE'), nullable=False)
    recipe_id = db.Column(db.Integer, db.ForeignKey('recipes.id', ondelete='CASCADE'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    __table_args__ = (db.UniqueConstraint('user_id', 'recipe_id', name='unique_user_recipe_favorite'),)


class UserIngredient(db.Model):
    """Модель пользовательского ингредиента"""
    __tablename__ = 'user_ingredients'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='CASCADE'), nullable=False)
    name = db.Column(db.String(100), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    __table_args__ = (db.UniqueConstraint('user_id', 'name', name='unique_user_ingredient'),)


class TelegramChat(db.Model):
    """Модель чата Telegram для авторизации"""
    __tablename__ = 'telegram_chats'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='CASCADE'), nullable=True)
    chat_id = db.Column(db.String(100), nullable=False)
    telegram_username = db.Column(db.String(100), nullable=True)
    auth_code = db.Column(db.String(50), nullable=True)
    auth_code_expires = db.Column(db.DateTime, nullable=True)
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    __table_args__ = (db.UniqueConstraint('user_id', 'chat_id', name='unique_user_chat'),)


class RecipeImage(db.Model):
    """Модель для хранения изображений рецептов"""
    __tablename__ = 'recipe_images'

    id = db.Column(db.Integer, primary_key=True)
    recipe_id = db.Column(db.Integer, db.ForeignKey('recipes.id', ondelete='CASCADE'), nullable=False)
    filename = db.Column(db.String(255), nullable=False)
    filepath = db.Column(db.String(500), nullable=False)
    is_primary = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    recipe = db.relationship('Recipe', backref='images')

    def to_dict(self):
        return {
            'id': self.id,
            'recipe_id': self.recipe_id,
            'filename': self.filename,
            'url': f'/static/uploads/recipes/{self.filename}',
            'is_primary': self.is_primary
        }


# ========== ЗАГРУЗЧИК ПОЛЬЗОВАТЕЛЯ ==========

@login_manager.user_loader
def load_user(user_id):
    try:
        return db.session.get(User, int(user_id))
    except:
        return None


# ========== ФУНКЦИИ ДЛЯ ТЕЛЕГРАМ ==========

def generate_auth_code(length=6):
    return ''.join(secrets.choice(string.digits) for _ in range(length))


def send_telegram_auth_code(chat_id, auth_code):
    if not TELEGRAM_BOT_TOKEN:
        return False

    try:
        message = f"🔐 Ваш код для входа в Cookly: *{auth_code}*\n\nКод действителен 5 минут"
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
        payload = {
            'chat_id': chat_id,
            'text': message,
            'parse_mode': 'Markdown'
        }
        response = requests.post(url, json=payload, timeout=10)
        return response.status_code == 200
    except Exception as e:
        print(f"❌ Ошибка отправки Telegram сообщения: {e}")
        return False


# ========== ИНИЦИАЛИЗАЦИЯ МОДЕЛИ ДЕТЕКЦИИ ==========

_model = None
_class_names = None


def get_model():
    global _model, _class_names

    if _model is None and os.path.exists(MODEL_PATH):
        try:
            print("Загрузка модели детекции продуктов...")
            _model = YOLO(MODEL_PATH)

            model_size = os.path.getsize(MODEL_PATH)
            print(f"Размер модели: {model_size / (1024 * 1024):.2f} MB")

            if model_size < 1024:
                print("⚠️  Обнаружена демо-модель. Реальное детектирование не будет работать.")

            device = 'cuda' if torch.cuda.is_available() else 'cpu'
            _model.to(device)

            if os.path.exists(CLASS_NAMES_PATH):
                with open(CLASS_NAMES_PATH, 'rb') as f:
                    loaded_classes = pickle.load(f)

                if loaded_classes and isinstance(loaded_classes[0], str):
                    _class_names = translate_classes_to_russian(loaded_classes)
                    print(f"✅ Модель загружена. Доступно классов: {len(_class_names)}")
                    print(f"   Устройство: {device}")
                else:
                    _class_names = ["морковь", "картофель", "помидор", "огурец", "лук", "перец", "капуста"]
                    print(f"⚠️  Неверный формат классов. Используются демо-классы")
            else:
                _class_names = ["морковь", "картофель", "помидор", "огурец", "лук", "перец", "капуста"]
                print(f"⚠️  Файл классов не найден. Используются демо-классы")

        except Exception as e:
            print(f"❌ Ошибка загрузки модели: {e}")
            _model = None
            _class_names = []

    return _model, _class_names


def translate_classes_to_russian(english_classes):
    translation_dict = {
        'carrot': 'морковь', 'carrots': 'морковь',
        'potato': 'картофель', 'potatoes': 'картофель',
        'tomato': 'помидор', 'tomatoes': 'помидоры',
        'cucumber': 'огурец', 'cucumbers': 'огурцы',
        'onion': 'лук', 'onions': 'лук',
        'pepper': 'перец', 'peppers': 'перец',
        'bell pepper': 'болгарский перец',
        'cabbage': 'капуста', 'broccoli': 'брокколи',
        'cauliflower': 'цветная капуста', 'garlic': 'чеснок',
        'ginger': 'имбирь', 'lettuce': 'салат',
        'spinach': 'шпинат', 'zucchini': 'кабачок',
        'eggplant': 'баклажан', 'eggplants': 'баклажаны',
        'pumpkin': 'тыква', 'beet': 'свекла',
        'apple': 'яблоко', 'apples': 'яблоки',
        'banana': 'банан', 'bananas': 'бананы',
        'orange': 'апельсин', 'oranges': 'апельсины',
        'lemon': 'лимон', 'lemons': 'лимоны'
    }

    russian_classes = []
    for cls in english_classes:
        cls_lower = cls.lower().strip()
        if cls_lower in translation_dict:
            russian_classes.append(translation_dict[cls_lower])
        else:
            russian_classes.append(cls)

    return russian_classes


def load_json_file(filename, default_data=None):
    if default_data is None:
        default_data = []

    try:
        if os.path.exists(filename):
            with open(filename, 'r', encoding='utf-8') as f:
                return json.load(f)
        return default_data
    except:
        return default_data


def save_json_file(filename, data):
    with open(filename, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


def detect_products(image_path, confidence_threshold=0.25):
    model, class_names = get_model()

    if model is None:
        return {"error": "Модель не загружена"}, []

    try:
        model_size = os.path.getsize(MODEL_PATH) if os.path.exists(MODEL_PATH) else 0

        if model_size < 1024:
            print("⚠️ Обнаружена демо-модель, но пытаемся её использовать")

        results = model(image_path, conf=confidence_threshold, imgsz=640, verbose=False)

        if not results or not results[0].boxes:
            return {"message": "На фото не найдены продукты"}, []

        result = results[0]
        detections = []
        detected_products = []

        for box in result.boxes:
            confidence = float(box.conf[0])
            if confidence < confidence_threshold:
                continue

            class_id = int(box.cls[0])
            class_name = class_names[class_id] if class_id < len(class_names) else f"class_{class_id}"
            x1, y1, x2, y2 = map(int, box.xyxy[0])

            detections.append({
                "product": class_name,
                "confidence": round(confidence, 3),
                "bbox": [x1, y1, x2, y2],
                "area": (x2 - x1) * (y2 - y1)
            })
            detected_products.append(class_name)

        if not detections:
            return {"message": "На фото не найдены продукты"}, []

        product_stats = {}
        for product in set(detected_products):
            product_detections = [d for d in detections if d["product"] == product]
            if product_detections:
                confidences = [d["confidence"] for d in product_detections]
                product_stats[product] = {
                    "count": len(product_detections),
                    "max_confidence": max(confidences),
                    "avg_confidence": round(sum(confidences) / len(product_detections), 3)
                }

        return product_stats, detections

    except Exception as e:
        print(f"❌ Ошибка детекции: {e}")
        return {"error": f"Ошибка обработки: {str(e)}"}, []


def normalize_product_name(product_name):
    name = product_name.lower().strip()
    synonyms = {
        'морковка': 'морковь', 'картошка': 'картофель',
        'помидорка': 'помидор', 'помидорчик': 'помидор',
        'огурчик': 'огурец', 'огурцы': 'огурец',
        'луковица': 'лук', 'перчик': 'перец',
        'капустка': 'капуста', 'яблочко': 'яблоки',
        'бананчик': 'банан', 'апельсинчик': 'апельсин',
        'лимончик': 'лимон'
    }
    return synonyms.get(name, name)


def normalize_ingredient_name(ingredient_name):
    name = ingredient_name.lower().strip()
    name = re.sub(r'^\d+\s*', '', name)
    name = re.sub(r'\s*\d+\s*(гр?|шт|мл|кг|ст\.?\s*л\.?|ч\.?\s*л\.?)\b', '', name)
    name = re.sub(r'\([^)]*\)', '', name)

    stop_words = ['свежий', 'свежая', 'свежее', 'свежие', 'мелко', 'крупно',
                  'нарезанный', 'очищенный', 'по', 'вкусу', 'для']
    for word in stop_words:
        name = name.replace(word, '').strip()

    synonyms = {
        'морковка': 'морковь', 'картошка': 'картофель',
        'помидор': 'помидоры', 'помидорка': 'помидоры',
        'огурчик': 'огурец', 'огурцы': 'огурец',
        'лук репчатый': 'лук', 'луковица': 'лук',
        'перчик': 'перец', 'капустка': 'капуста',
        'яблоко': 'яблоки', 'бананы': 'банан',
        'апельсин': 'апельсины', 'лимон': 'лимоны'
    }

    return synonyms.get(name, name)


def find_recipes_by_products(detected_products):
    if not detected_products:
        return []

    if isinstance(detected_products, dict):
        search_products = list(detected_products.keys())
    else:
        search_products = list(set(detected_products))

    if not search_products:
        return []

    normalized_products = [normalize_product_name(p) for p in search_products]
    all_recipes = Recipe.query.all()
    matching_recipes = []

    for recipe in all_recipes:
        recipe_dict = recipe.to_dict()
        normalized_ingredients = [normalize_ingredient_name(ing['name']) for ing in recipe_dict['ingredients']]

        matches = 0
        matched_products = []

        for product, norm_product in zip(search_products, normalized_products):
            for norm_ingredient in normalized_ingredients:
                if norm_product == norm_ingredient or \
                        (norm_product in norm_ingredient and len(norm_product) > 2) or \
                        (norm_ingredient in norm_product and len(norm_ingredient) > 2):
                    matches += 1
                    matched_products.append(product)
                    break

        if matches > 0:
            match_percentage = round((matches / len(search_products)) * 100, 1)
            matching_recipes.append({
                "recipe": recipe_dict,
                "matches": matches,
                "total_products": len(search_products),
                "match_percentage": match_percentage,
                "matched_products": list(set(matched_products))
            })

    matching_recipes.sort(key=lambda x: (x["matches"], x["match_percentage"]), reverse=True)
    return matching_recipes[:12]


def migrate_recipes_from_json():
    try:
        RECIPES_FILE = os.path.join(basedir, 'recipes.json')
        USER_RECIPES_FILE = os.path.join(DATA_FOLDER, 'user_recipes.json')

        main_recipes = load_json_file(RECIPES_FILE, [])
        user_recipes = load_json_file(USER_RECIPES_FILE, [])
        recipes_count = 0

        for recipe_data in main_recipes:
            if not Recipe.query.filter_by(title=recipe_data.get('title')).first():
                recipe = Recipe(
                    title=recipe_data.get('title', 'Рецепт'),
                    image=recipe_data.get('image'),
                    time=recipe_data.get('time', '30 мин'),
                    difficulty=recipe_data.get('difficulty', 'Средне'),
                    calories=recipe_data.get('calories', '350 ккал'),
                    servings=recipe_data.get('servings', '2 порции'),
                    is_user_recipe=False,
                    author_name='Cookly',
                    likes_count=0
                )
                db.session.add(recipe)
                db.session.flush()

                for ing_data in recipe_data.get('ingredients', []):
                    db.session.add(Ingredient(
                        recipe_id=recipe.id,
                        name=ing_data.get('name', 'Ингредиент'),
                        amount=ing_data.get('amount', 'по вкусу')
                    ))

                for i, inst_data in enumerate(recipe_data.get('instructions', []), 1):
                    db.session.add(Instruction(
                        recipe_id=recipe.id,
                        step_number=i,
                        description=inst_data if isinstance(inst_data, str) else str(inst_data)
                    ))
                recipes_count += 1

        for recipe_data in user_recipes:
            if not Recipe.query.filter_by(title=recipe_data.get('title')).first():
                recipe = Recipe(
                    title=recipe_data.get('title', 'Рецепт'),
                    image=recipe_data.get('image'),
                    time=recipe_data.get('time', '30 мин'),
                    difficulty=recipe_data.get('difficulty', 'Средне'),
                    calories=recipe_data.get('calories', '350 ккал'),
                    servings=recipe_data.get('servings', '2 порции'),
                    is_user_recipe=True,
                    author_name='Пользователь',
                    likes_count=0
                )
                db.session.add(recipe)
                db.session.flush()

                for ing_data in recipe_data.get('ingredients', []):
                    db.session.add(Ingredient(
                        recipe_id=recipe.id,
                        name=ing_data.get('name', 'Ингредиент'),
                        amount=ing_data.get('amount', 'по вкусу')
                    ))

                for i, inst_data in enumerate(recipe_data.get('instructions', []), 1):
                    db.session.add(Instruction(
                        recipe_id=recipe.id,
                        step_number=i,
                        description=inst_data if isinstance(inst_data, str) else str(inst_data)
                    ))
                recipes_count += 1

        if recipes_count > 0:
            db.session.commit()
            print(f"✅ Перенесено {recipes_count} рецептов")
        return recipes_count

    except Exception as e:
        db.session.rollback()
        print(f"❌ Ошибка миграции: {e}")
        return 0


# ========== ОБРАБОТЧИКИ ОШИБОК ==========

@app.errorhandler(404)
def not_found_error(error):
    if request.path.startswith('/api/'):
        return jsonify({'error': 'API endpoint not found'}), 404
    return render_template('404.html'), 404


@app.errorhandler(500)
def internal_error(error):
    db.session.rollback()
    if request.path.startswith('/api/'):
        return jsonify({'error': 'Internal server error'}), 500
    return render_template('500.html'), 500


@app.after_request
def after_request(response):
    response.headers.add('Access-Control-Allow-Origin', '*')
    response.headers.add('Access-Control-Allow-Headers', 'Content-Type,Authorization')
    response.headers.add('Access-Control-Allow-Methods', 'GET,PUT,POST,DELETE,OPTIONS')
    response.headers.add('Cache-Control', 'no-store, no-cache, must-revalidate, max-age=0')
    return response


# ========== СТРАНИЦЫ ==========

@app.route('/')
def index():
    return render_template('index.html')


@app.route('/login')
def login_page():
    if current_user.is_authenticated:
        return redirect(url_for('index'))
    return render_template('login.html', telegram_bot_username=TELEGRAM_BOT_USERNAME)


@app.route('/register')
def register_page():
    if current_user.is_authenticated:
        return redirect(url_for('index'))
    return render_template('register.html')


@app.route('/profile')
@login_required
def profile_page():
    return render_template('profile.html')


# ========== API АВТОРИЗАЦИИ ==========
@app.route('/api/auth/register', methods=['POST'])
@json_response
def api_register():
    data = request.json

    email = data.get('email', '').strip()
    username = data.get('username', '').strip()
    password = data.get('password', '').strip()
    remember = data.get('remember', True)

    if not email or not username or not password:
        return jsonify({'error': 'Все поля обязательны для заполнения'}), 400

    if User.query.filter_by(email=email).first():
        return jsonify({'error': 'Пользователь с таким email уже существует'}), 400

    if User.query.filter_by(username=username).first():
        return jsonify({'error': 'Пользователь с таким именем уже существует'}), 400

    user = User(
        email=email,
        username=username,
        avatar=f'https://ui-avatars.com/api/?name={username}&background=2E7D32&color=fff&size=200'
    )
    user.set_password(password)

    db.session.add(user)
    db.session.commit()

    session.clear()

    login_user(user, remember=remember)
    user.last_login = datetime.utcnow()
    db.session.commit()

    session['user_id'] = user.id
    session['authenticated'] = True
    session.permanent = True

    print(f"✅ Пользователь {username} зарегистрирован и вошел в систему")
    print(f"   Session ID: {session.sid if hasattr(session, 'sid') else 'N/A'}")
    print(f"   User ID в сессии: {session.get('user_id')}")

    return jsonify({'success': True, 'user': user.to_dict()})


@app.route('/api/auth/login', methods=['POST'])
@json_response
def api_login():
    data = request.json

    login = data.get('login', '').strip()
    password = data.get('password', '').strip()
    remember = data.get('remember', False)

    if not login or not password:
        return jsonify({'error': 'Введите логин и пароль'}), 400

    user = User.query.filter(
        or_(User.email == login, User.username == login)
    ).first()

    if not user or not user.check_password(password):
        return jsonify({'error': 'Неверный логин или пароль'}), 401

    session.clear()

    login_user(user, remember=remember)
    user.last_login = datetime.utcnow()
    db.session.commit()

    session['user_id'] = user.id
    session['authenticated'] = True
    session.permanent = True

    print(f"✅ Пользователь {user.username} вошел в систему")
    print(f"   Session ID: {session.sid if hasattr(session, 'sid') else 'N/A'}")
    print(f"   User ID в сессии: {session.get('user_id')}")

    return jsonify({'success': True, 'user': user.to_dict()})


@app.route('/api/auth/logout', methods=['POST'])
@login_required
@json_response
def api_logout():
    logout_user()
    return jsonify({'success': True})


@app.route('/api/auth/user')
@json_response
def api_get_current_user():
    print(f"🔍 Проверка пользователя. Сессия: {dict(session)}")
    print(f"   current_user.is_authenticated: {current_user.is_authenticated}")
    print(f"   current_user: {current_user}")

    if current_user.is_authenticated:
        user_dict = current_user.to_dict()
        print(f"✅ Пользователь авторизован: {user_dict['username']}")
        return jsonify({
            'authenticated': True,
            'user': user_dict
        })

    print("❌ Пользователь не авторизован")
    return jsonify({
        'authenticated': False,
        'user': None
    })


# ========== GOOGLE OAUTH ==========

@app.route('/login/google')
def google_login():
    if not app.config['GOOGLE_OAUTH_CLIENT_ID'] or not app.config['GOOGLE_OAUTH_CLIENT_SECRET']:
        print("⚠️ Google OAuth не настроен")
        return redirect(url_for('login_page'))

    if not google.authorized:
        return redirect(url_for('google.login'))

    try:
        resp = google.get('/oauth2/v1/userinfo')
        if not resp.ok:
            return redirect(url_for('login_page'))

        user_info = resp.json()
        google_id = user_info['id']
        email = user_info['email']
        name = user_info.get('name', email.split('@')[0])
        avatar = user_info.get('picture')

        user = User.query.filter(
            or_(User.google_id == google_id, User.email == email)
        ).first()

        if not user:
            username = name
            counter = 1
            while User.query.filter_by(username=username).first():
                username = f"{name}{counter}"
                counter += 1

            user = User(
                email=email,
                username=username,
                google_id=google_id,
                avatar=avatar or f'https://ui-avatars.com/api/?name={username}&background=2E7D32&color=fff&size=200'
            )
            db.session.add(user)
            db.session.commit()
        elif not user.google_id:
            user.google_id = google_id
            db.session.commit()

        login_user(user, remember=True)
        user.last_login = datetime.utcnow()
        db.session.commit()

        return redirect(url_for('index'))

    except Exception as e:
        print(f"❌ Ошибка Google авторизации: {e}")
        return redirect(url_for('login_page'))


# ========== TELEGRAM AUTH ==========

@app.route('/login/telegram')
def telegram_login_page():
    """Страница для входа через Telegram"""
    return render_template('telegram_login.html', telegram_bot_username=TELEGRAM_BOT_USERNAME)


@app.route('/api/auth/telegram/request-code', methods=['POST'])
@json_response
def api_telegram_request_code():
    data = request.json
    chat_id = data.get('chat_id', '').strip()

    if not chat_id:
        return jsonify({'error': 'Не указан chat_id'}), 400

    if not TELEGRAM_BOT_TOKEN:
        return jsonify({'error': 'Telegram бот не настроен'}), 503

    auth_code = generate_auth_code()
    expires_at = datetime.utcnow() + timedelta(minutes=5)

    telegram_chat = TelegramChat.query.filter_by(chat_id=str(chat_id)).first()

    if telegram_chat:
        telegram_chat.auth_code = auth_code
        telegram_chat.auth_code_expires = expires_at
        telegram_chat.is_active = True
    else:
        telegram_chat = TelegramChat(
            user_id=None,
            chat_id=str(chat_id),
            auth_code=auth_code,
            auth_code_expires=expires_at,
            is_active=True
        )
        db.session.add(telegram_chat)

    db.session.commit()

    if send_telegram_auth_code(chat_id, auth_code):
        return jsonify({'success': True, 'message': 'Код отправлен в Telegram'})
    else:
        return jsonify({'error': 'Не удалось отправить код'}), 500


@app.route('/api/auth/telegram/verify-code', methods=['POST'])
@json_response
def api_telegram_verify_code():
    data = request.json
    chat_id = data.get('chat_id', '').strip()
    auth_code = data.get('code', '').strip()

    if not chat_id or not auth_code:
        return jsonify({'error': 'Не указан chat_id или код'}), 400

    telegram_chat = TelegramChat.query.filter_by(
        chat_id=str(chat_id),
        auth_code=auth_code,
        is_active=True
    ).first()

    if not telegram_chat:
        return jsonify({'error': 'Неверный код'}), 401

    if telegram_chat.auth_code_expires < datetime.utcnow():
        return jsonify({'error': 'Код истек'}), 401

    if telegram_chat.user_id:
        user = db.session.get(User, telegram_chat.user_id)
        if user:
            login_user(user, remember=True)
            user.last_login = datetime.utcnow()
            db.session.commit()
            return jsonify({'success': True, 'user': user.to_dict()})

    user = User.query.filter_by(telegram_id=str(chat_id)).first()

    if not user:
        username = f"tg_{chat_id[-8:]}"
        counter = 1
        while User.query.filter_by(username=username).first():
            username = f"tg_{chat_id[-8:]}{counter}"
            counter += 1

        user = User(
            username=username,
            telegram_id=str(chat_id),
            avatar=f'https://ui-avatars.com/api/?name=Telegram&background=2E7D32&color=fff&size=200'
        )
        db.session.add(user)
        db.session.flush()

    telegram_chat.user_id = user.id
    telegram_chat.auth_code = None
    telegram_chat.auth_code_expires = None

    db.session.commit()

    login_user(user, remember=True)
    user.last_login = datetime.utcnow()
    db.session.commit()

    return jsonify({'success': True, 'user': user.to_dict()})


# ========== API РЕЦЕПТОВ ==========

@app.route('/api/recipes')
@json_response
def get_recipes():
    recipes = Recipe.query.filter_by(is_user_recipe=False).order_by(desc(Recipe.created_at)).all()
    return jsonify([recipe.to_dict() for recipe in recipes])


@app.route('/api/user-recipes')
@json_response
def get_user_recipes():
    if current_user.is_authenticated:
        recipes = Recipe.query.filter_by(
            is_user_recipe=True,
            user_id=current_user.id
        ).order_by(desc(Recipe.created_at)).all()
    else:
        recipes = Recipe.query.filter_by(
            is_user_recipe=True,
            user_id=None
        ).order_by(desc(Recipe.created_at)).all()
    return jsonify([recipe.to_dict() for recipe in recipes])


@app.route('/api/user-recipes', methods=['POST'])
@login_required
@json_response
def save_user_recipe():
    data = request.json

    required_fields = ['title', 'time', 'difficulty', 'calories', 'servings']
    for field in required_fields:
        if field not in data:
            return jsonify({'error': f'Missing required field: {field}'}), 400

    if not data.get('ingredients'):
        return jsonify({'error': 'Recipe must have at least one ingredient'}), 400

    if not data.get('instructions'):
        return jsonify({'error': 'Recipe must have at least one instruction step'}), 400

    recipe_id = data.get('id')

    if recipe_id:
        recipe = db.session.get(Recipe, recipe_id)

        if not recipe:
            return jsonify({'error': 'Recipe not found'}), 404

        if recipe.user_id != current_user.id:
            return jsonify({'error': 'You can only edit your own recipes'}), 403

        recipe.title = data['title']
        recipe.image = data.get('image', recipe.image)
        recipe.time = data['time']
        recipe.difficulty = data['difficulty']
        recipe.calories = data['calories']
        recipe.servings = data['servings']
        recipe.author_name = current_user.username

        Ingredient.query.filter_by(recipe_id=recipe.id).delete()
        Instruction.query.filter_by(recipe_id=recipe.id).delete()

        for ing_data in data['ingredients']:
            db.session.add(Ingredient(
                recipe_id=recipe.id,
                name=ing_data['name'],
                amount=ing_data['amount']
            ))

        for i, step_text in enumerate(data['instructions'], 1):
            db.session.add(Instruction(
                recipe_id=recipe.id,
                step_number=i,
                description=step_text
            ))

    else:
        recipe = Recipe(
            title=data['title'],
            image=data.get('image'),
            time=data['time'],
            difficulty=data['difficulty'],
            calories=data['calories'],
            servings=data['servings'],
            is_user_recipe=True,
            user_id=current_user.id,
            author_name=current_user.username,
            likes_count=0
        )
        db.session.add(recipe)
        db.session.flush()

        for ing_data in data['ingredients']:
            db.session.add(Ingredient(
                recipe_id=recipe.id,
                name=ing_data['name'],
                amount=ing_data['amount']
            ))

            if not UserIngredient.query.filter_by(
                    user_id=current_user.id,
                    name=ing_data['name']
            ).first():
                db.session.add(UserIngredient(
                    user_id=current_user.id,
                    name=ing_data['name']
                ))

        for i, step_text in enumerate(data['instructions'], 1):
            db.session.add(Instruction(
                recipe_id=recipe.id,
                step_number=i,
                description=step_text
            ))

    db.session.commit()
    return jsonify({'success': True, 'recipe': recipe.to_dict()})


@app.route('/api/user-recipes/<int:recipe_id>', methods=['DELETE'])
@login_required
@json_response
def delete_user_recipe(recipe_id):
    recipe = db.session.get(Recipe, recipe_id)

    if not recipe:
        return jsonify({'error': 'Recipe not found'}), 404

    if not recipe.is_user_recipe:
        return jsonify({'error': 'Cannot delete non-user recipe'}), 403

    if recipe.user_id != current_user.id:
        return jsonify({'error': 'You can only delete your own recipes'}), 403

    db.session.delete(recipe)
    db.session.commit()

    return jsonify({'success': True, 'deletedId': recipe_id})


@app.route('/api/all-recipes')
@json_response
def get_all_recipes():
    recipes = Recipe.query.order_by(desc(Recipe.created_at)).all()
    return jsonify([recipe.to_dict() for recipe in recipes])


# ========== API ЛАЙКОВ ==========

@app.route('/api/recipe/<int:recipe_id>/like', methods=['POST'])
@login_required
@json_response
def like_recipe(recipe_id):
    """Поставить/убрать лайк"""
    try:
        recipe = db.session.get(Recipe, recipe_id)

        if not recipe:
            return jsonify({'error': 'Рецепт не найден'}), 404

        # Проверяем, есть ли уже лайк от этого пользователя
        like = Like.query.filter_by(
            user_id=current_user.id,
            recipe_id=recipe_id
        ).first()

        if like:
            # Убираем лайк
            db.session.delete(like)
            recipe.likes_count = max(0, recipe.likes_count - 1)
            action = 'unliked'
            message = 'Лайк убран'
        else:
            # Ставим лайк
            new_like = Like(
                user_id=current_user.id,
                recipe_id=recipe_id
            )
            db.session.add(new_like)
            recipe.likes_count += 1
            action = 'liked'
            message = 'Лайк поставлен'

        db.session.commit()

        return jsonify({
            'success': True,
            'action': action,
            'likes_count': recipe.likes_count,
            'message': message
        })

    except Exception as e:
        db.session.rollback()
        print(f"❌ Ошибка в like_recipe: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@app.route('/api/recipe/<int:recipe_id>/likes', methods=['GET'])
@json_response
def get_recipe_likes_info(recipe_id):
    """Получить количество лайков и информацию о лайке текущего пользователя"""
    try:
        recipe = db.session.get(Recipe, recipe_id)

        if not recipe:
            return jsonify({'error': 'Рецепт не найден'}), 404

        user_liked = False
        if current_user.is_authenticated:
            like = Like.query.filter_by(
                user_id=current_user.id,
                recipe_id=recipe_id
            ).first()
            user_liked = like is not None

        return jsonify({
            'success': True,
            'likes_count': recipe.likes_count,
            'user_liked': user_liked
        })

    except Exception as e:
        print(f"❌ Ошибка в get_recipe_likes_info: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


# Добавьте тестовый эндпоинт для проверки
@app.route('/api/test/likes', methods=['GET'])
@json_response
def test_likes_system():
    """Тестовый эндпоинт для проверки работы лайков"""
    try:
        recipes = Recipe.query.limit(5).all()
        result = []
        for recipe in recipes:
            likes_count = Like.query.filter_by(recipe_id=recipe.id).count()
            result.append({
                'recipe_id': recipe.id,
                'title': recipe.title,
                'likes_count_in_recipe': recipe.likes_count,
                'actual_likes_count': likes_count,
                'match': recipe.likes_count == likes_count
            })

        # Информация о текущем пользователе
        user_info = None
        if current_user.is_authenticated:
            user_info = {
                'id': current_user.id,
                'username': current_user.username
            }

        return jsonify({
            'success': True,
            'message': 'Тест лайков выполнен',
            'user': user_info,
            'data': result
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


# ========== API ИЗБРАННОГО ==========

@app.route('/api/favorites')
@login_required
@json_response
def get_favorites():
    favorites = Favorite.query.filter_by(user_id=current_user.id).all()
    return jsonify([fav.recipe_id for fav in favorites])


@app.route('/api/favorites', methods=['POST'])
@login_required
@json_response
def toggle_favorite():
    data = request.json
    recipe_id = data.get('recipeId')

    if not recipe_id:
        return jsonify({'error': 'No recipeId provided'}), 400

    favorite = Favorite.query.filter_by(
        user_id=current_user.id,
        recipe_id=recipe_id
    ).first()

    if favorite:
        db.session.delete(favorite)
        action = 'removed'
    else:
        db.session.add(Favorite(
            user_id=current_user.id,
            recipe_id=recipe_id
        ))
        action = 'added'

    db.session.commit()

    favorites = [fav.recipe_id for fav in Favorite.query.filter_by(user_id=current_user.id).all()]

    return jsonify({'success': True, 'action': action, 'favorites': favorites})


# ========== API ИНГРЕДИЕНТОВ ==========

@app.route('/api/user-ingredients')
@login_required
@json_response
def get_user_ingredients_api():
    ingredients = UserIngredient.query.filter_by(user_id=current_user.id).all()
    return jsonify([ing.name for ing in ingredients])


@app.route('/api/user-ingredients', methods=['POST'])
@login_required
@json_response
def save_user_ingredient_api():
    data = request.json
    ingredient = data.get('ingredient', '').strip()

    if not ingredient:
        return jsonify({'error': 'No ingredient provided'}), 400

    if not UserIngredient.query.filter_by(
            user_id=current_user.id,
            name=ingredient
    ).first():
        db.session.add(UserIngredient(
            user_id=current_user.id,
            name=ingredient
        ))
        db.session.commit()

    ingredients = [ing.name for ing in UserIngredient.query.filter_by(user_id=current_user.id).all()]

    return jsonify({'success': True, 'ingredients': ingredients})


@app.route('/api/common-ingredients')
@json_response
def get_common_ingredients():
    common_ingredients = [
        "Мука", "Сахар", "Соль", "Перец", "Оливковое масло", "Подсолнечное масло",
        "Яйца", "Молоко", "Сливки", "Сметана", "Масло сливочное", "Сыр",
        "Пармезан", "Моцарелла", "Чеснок", "Лук репчатый", "Лук зеленый",
        "Морковь", "Картофель", "Помидоры", "Огурцы", "Перец болгарский",
        "Капуста белокочанная", "Капуста цветная", "Брокколи", "Шпинат",
        "Салат листовой", "Петрушка", "Укроп", "Базилик", "Кинза",
        "Куриное филе", "Говядина", "Свинина", "Бекон", "Ветчина",
        "Колбаса", "Сосиски", "Рыба белая", "Лосось", "Креветки",
        "Рис", "Гречка", "Макароны", "Спагетти", "Лапша", "Хлеб",
        "Мед", "Шоколад", "Какао", "Корица", "Лимон", "Апельсин", "Яблоки",
        "Бананы", "Клубника", "Малина", "Авокадо", "Тыква", "Кабачки",
        "Баклажаны", "Грибы", "Фасоль", "Горох", "Чечевица", "Кукуруза"
    ]
    return jsonify(common_ingredients)


@app.route('/api/all-ingredients')
@json_response
def get_all_ingredients():
    common = [
        "Мука", "Сахар", "Соль", "Перец", "Оливковое масло", "Подсолнечное масло",
        "Яйца", "Молоко", "Сливки", "Сметана", "Масло сливочное", "Сыр",
        "Пармезан", "Моцарелла", "Чеснок", "Лук репчатый", "Лук зеленый",
        "Морковь", "Картофель", "Помидоры", "Огурцы", "Перец болгарский",
        "Капуста белокочанная", "Капуста цветная", "Брокколи", "Шпинат",
        "Салат листовой", "Петрушка", "Укроп", "Базилик", "Кинза",
        "Куриное филе", "Говядина", "Свинина", "Бекон", "Ветчина",
        "Колбаса", "Сосиски", "Рыба белая", "Лосось", "Креветки",
        "Рис", "Гречка", "Макароны", "Спагетти", "Лапша", "Хлеб",
        "Мед", "Шоколад", "Какао", "Корица", "Лимон", "Апельсин", "Яблоки",
        "Бананы", "Клубника", "Малина", "Авокадо", "Тыква", "Кабачки",
        "Баклажаны", "Грибы", "Фасоль", "Горох", "Чечевица", "Кукуруза"
    ]

    if current_user.is_authenticated:
        user_ingredients = [ing.name for ing in UserIngredient.query.filter_by(user_id=current_user.id).all()]
        all_ingredients = list(set(common + user_ingredients))
    else:
        all_ingredients = common

    all_ingredients.sort()
    return jsonify(all_ingredients)


# ========== API ПОИСКА ПО ФОТО ==========

@app.route('/api/photo-search', methods=['POST'])
@json_response
def photo_search():
    if 'file' not in request.files:
        return jsonify({'error': 'No file part'}), 400

    file = request.files['file']

    if file.filename == '':
        return jsonify({'error': 'No selected file'}), 400

    if not allowed_file(file.filename):
        return jsonify({'error': 'File type not allowed'}), 400

    filename = secure_filename(file.filename)
    filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
    file.save(filepath)

    try:
        product_stats, detections = detect_products(filepath, confidence_threshold=0.25)

        if "error" in product_stats:
            return jsonify({
                'success': False,
                'message': product_stats["error"],
                'detected_products': [],
                'recipes': []
            })

        if "message" in product_stats:
            return jsonify({
                'success': True,
                'message': product_stats["message"],
                'detected_products': [],
                'recipes': [],
                'total_products': 0,
                'total_recipes': 0
            })

        if not product_stats:
            return jsonify({
                'success': True,
                'message': "На фото не найдены продукты",
                'detected_products': [],
                'recipes': [],
                'total_products': 0,
                'total_recipes': 0
            })

        search_products = list(product_stats.keys())
        matching_recipes = find_recipes_by_products(search_products)

        formatted_recipes = []
        for match in matching_recipes:
            recipe = match["recipe"].copy()
            recipe["match_score"] = match["match_percentage"]
            recipe["matched_products"] = match["matched_products"]
            formatted_recipes.append(recipe)

        formatted_products = []
        for product, stats in product_stats.items():
            formatted_products.append({
                "name": product,
                "count": stats["count"],
                "confidence": stats["avg_confidence"],
                "max_confidence": stats["max_confidence"]
            })

        formatted_products.sort(key=lambda x: x["confidence"], reverse=True)

        message = f'Найдено {len(formatted_products)} продуктов и {len(formatted_recipes)} подходящих рецептов' if formatted_recipes else \
            f'Найдено {len(formatted_products)} продуктов, но подходящих рецептов нет'

        return jsonify({
            'success': True,
            'message': message,
            'detected_products': formatted_products,
            'recipes': formatted_recipes,
            'total_products': len(formatted_products),
            'total_recipes': len(formatted_recipes)
        })

    finally:
        if os.path.exists(filepath):
            os.remove(filepath)


# ========== API ПРОФИЛЯ ==========

@app.route('/api/profile', methods=['PUT'])
@login_required
@json_response
def update_profile():
    data = request.json

    if 'username' in data:
        username = data['username'].strip()
        if username and username != current_user.username:
            if User.query.filter_by(username=username).first():
                return jsonify({'error': 'Пользователь с таким именем уже существует'}), 400
            current_user.username = username

    if 'avatar' in data:
        avatar = data['avatar'].strip()
        if avatar:
            current_user.avatar = avatar

    db.session.commit()
    return jsonify({'success': True, 'user': current_user.to_dict()})


@app.route('/api/profile/stats')
@login_required
@json_response
def get_profile_stats():
    recipes_count = Recipe.query.filter_by(user_id=current_user.id).count()
    favorites_count = Favorite.query.filter_by(user_id=current_user.id).count()
    ingredients_count = UserIngredient.query.filter_by(user_id=current_user.id).count()

    return jsonify({
        'recipes_count': recipes_count,
        'favorites_count': favorites_count,
        'ingredients_count': ingredients_count
    })


# ========== API СТАТУСОВ ==========

@app.route('/api/model-status')
@json_response
def model_status():
    model, class_names = get_model()

    if model is None:
        return jsonify({
            'loaded': False,
            'message': 'Модель не загружена',
            'class_count': 0,
            'device': 'none',
            'classes': [],
            'is_demo': False
        })

    device = next(model.model.parameters()).device.type if hasattr(model, 'model') else 'cpu'
    model_size = os.path.getsize(MODEL_PATH) if os.path.exists(MODEL_PATH) else 0
    is_demo = model_size < 1024

    return jsonify({
        'loaded': True,
        'message': 'Демо-модель готова' if is_demo else 'Модель готова к работе',
        'class_count': len(class_names) if class_names else 0,
        'device': device,
        'is_demo': is_demo,
        'classes': class_names if class_names else []
    })


@app.route('/api/db-status')
@json_response
def db_status():
    try:
        recipes_count = Recipe.query.count()
        user_recipes_count = Recipe.query.filter_by(is_user_recipe=True).count()
        users_count = User.query.count()

        return jsonify({
            'connected': True,
            'total_recipes': recipes_count,
            'user_recipes': user_recipes_count,
            'users': users_count
        })
    except Exception as e:
        return jsonify({
            'connected': False,
            'error': str(e)
        })


@app.route('/api/db-migrate', methods=['POST'])
@json_response
def db_migrate():
    migrated = migrate_recipes_from_json()
    return jsonify({
        'success': True,
        'migrated': migrated,
        'message': f'Перенесено {migrated} рецептов'
    })


# ========== ТЕСТОВЫЕ ЭНДПОИНТЫ ==========

@app.route('/api/quick-test', methods=['POST'])
@json_response
def quick_test():
    model, class_names = get_model()

    if model is None:
        return jsonify({'success': False, 'error': 'Модель не загружена'})

    test_path = os.path.join(UPLOAD_FOLDER, 'test_image.jpg')
    test_image = np.zeros((640, 640, 3), dtype=np.uint8)
    cv2.putText(test_image, 'Test Image', (200, 320), cv2.FONT_HERSHEY_SIMPLEX, 1, (255, 255, 255), 2)
    cv2.imwrite(test_path, test_image)

    try:
        product_stats, detections = detect_products(test_path, confidence_threshold=0.1)
        return jsonify({
            'success': True,
            'model_working': 'error' not in product_stats and 'message' not in product_stats,
            'detections_count': len(detections),
            'product_stats': product_stats,
            'class_count': len(class_names) if class_names else 0,
            'is_demo': os.path.getsize(MODEL_PATH) < 1024 if os.path.exists(MODEL_PATH) else True
        })
    finally:
        if os.path.exists(test_path):
            os.remove(test_path)


@app.route('/api/test-search')
@json_response
def test_search():
    test_products = ["морковь", "картофель", "лук"]
    matching_recipes = find_recipes_by_products(test_products)

    formatted_recipes = []
    for match in matching_recipes:
        recipe = match["recipe"].copy()
        recipe["match_score"] = match["match_percentage"]
        recipe["matched_products"] = match["matched_products"]
        formatted_recipes.append(recipe)

    return jsonify({
        'success': True,
        'message': f'Тестовый поиск: {len(formatted_recipes)} рецептов найдено',
        'test_products': test_products,
        'recipes': formatted_recipes
    })


# ========== ЗАПУСК ПРИЛОЖЕНИЯ ==========

if __name__ == '__main__':
    with app.app_context():
        # Создаем таблицы
        db.create_all()
        print("✅ Таблицы базы данных созданы")

        # Создаем шаблоны ошибок
        create_error_templates()

        # Проверяем наличие рецептов
        recipes_count = Recipe.query.count()
        if recipes_count == 0:
            print("ℹ️  База данных пуста. Выполняем миграцию из JSON...")
            migrated = migrate_recipes_from_json()
            print(f"✅ Миграция завершена. Перенесено {migrated} рецептов")
        else:
            print(f"📚 В базе данных уже есть {recipes_count} рецептов")

        users_count = User.query.count()
        print(f"👥 Зарегистрировано пользователей: {users_count}")

    # Загружаем модель
    try:
        model, class_names = get_model()
        if model:
            print(f"✅ Модель детекции продуктов загружена ({len(class_names)} классов)")
        else:
            print("⚠️  Модель детекции продуктов НЕ загружена")
    except Exception as e:
        print(f"⚠️ Ошибка при загрузке модели: {e}")

    # Получаем порт из переменных окружения для Render
    port = int(os.environ.get('PORT', 5000))
    debug = os.environ.get('FLASK_DEBUG', 'false').lower() == 'true'

    print(f"🚀 Запуск сервера на порту {port}")
    app.run(host='0.0.0.0', port=port, debug=debug)