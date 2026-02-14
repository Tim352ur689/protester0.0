# migrate_db.py
from app import app, db
from sqlalchemy import inspect, text
import os


def add_column_if_not_exists(engine, table_name, column_name, column_type):
    """Добавляет колонку в таблицу, если её нет"""
    inspector = inspect(engine)

    # Проверяем существование таблицы
    if table_name not in inspector.get_table_names():
        print(f"❌ Таблица {table_name} не найдена. Пропускаем...")
        return False

    columns = [col['name'] for col in inspector.get_columns(table_name)]

    if column_name not in columns:
        print(f"➕ Добавляем колонку {column_name} в таблицу {table_name}...")
        try:
            with engine.connect() as conn:
                # Для SQLite нужно использовать простой ALTER TABLE
                conn.execute(text(f'ALTER TABLE {table_name} ADD COLUMN {column_name} {column_type}'))
                conn.commit()
            print(f"✓ Колонка {column_name} добавлена")
            return True
        except Exception as e:
            print(f"❌ Ошибка при добавлении колонки {column_name}: {e}")
            return False
    else:
        print(f"✓ Колонка {column_name} уже существует в таблице {table_name}")
        return False


def create_tables_if_not_exist(engine):
    """Создает недостающие таблицы"""
    inspector = inspect(engine)
    existing_tables = inspector.get_table_names()

    # Список таблиц, которые должны быть
    required_tables = [
        'users', 'recipes', 'ingredients', 'instructions',
        'favorites', 'user_ingredients', 'telegram_chats',
        'likes', 'recipe_images'
    ]

    missing_tables = []
    for table in required_tables:
        if table not in existing_tables:
            missing_tables.append(table)
            print(f"➕ Таблица {table} будет создана...")

    if missing_tables:
        # Создаем все таблицы
        db.create_all()
        print(f"✓ Созданы таблицы: {', '.join(missing_tables)}")
    else:
        print("✓ Все необходимые таблицы уже существуют")


def migrate_database():
    """Выполняет миграцию базы данных"""
    with app.app_context():
        engine = db.engine
        inspector = inspect(engine)

        print("🔄 Начинаем миграцию базы данных...")
        print("=" * 60)

        # 1. Создаем все недостающие таблицы
        create_tables_if_not_exist(engine)

        print("-" * 60)

        # 2. Добавляем недостающие колонки в таблицу recipes
        if 'recipes' in inspector.get_table_names():
            recipes_columns = inspector.get_columns('recipes')
            recipes_column_names = [col['name'] for col in recipes_columns]

            print("\n📝 Проверка таблицы recipes:")

            # Стандартные поля
            add_column_if_not_exists(engine, 'recipes', 'user_id', 'INTEGER REFERENCES users(id)')
            add_column_if_not_exists(engine, 'recipes', 'is_user_recipe', 'BOOLEAN DEFAULT 0')
            add_column_if_not_exists(engine, 'recipes', 'author_name', 'VARCHAR(80) DEFAULT "Cookly"')
            add_column_if_not_exists(engine, 'recipes', 'likes_count', 'INTEGER DEFAULT 0')

            # НОВОЕ ПОЛЕ для локальных изображений
            add_column_if_not_exists(engine, 'recipes', 'has_local_image', 'BOOLEAN DEFAULT 0')

        else:
            print("❌ Таблица recipes не найдена!")

        print("-" * 60)

        # 3. Добавляем недостающие колонки в таблицу users
        if 'users' in inspector.get_table_names():
            users_columns = inspector.get_columns('users')
            users_column_names = [col['name'] for col in users_columns]

            print("\n👤 Проверка таблицы users:")

            add_column_if_not_exists(engine, 'users', 'google_id', 'VARCHAR(100) UNIQUE')
            add_column_if_not_exists(engine, 'users', 'telegram_id', 'VARCHAR(100) UNIQUE')
            add_column_if_not_exists(engine, 'users', 'avatar', 'VARCHAR(500)')
            add_column_if_not_exists(engine, 'users', 'last_login', 'DATETIME')
        else:
            print("➕ Создаем таблицу users...")
            db.create_all()

        print("-" * 60)

        # 4. Проверяем наличие таблицы likes
        if 'likes' not in inspector.get_table_names():
            print("\n❤️ Создаем таблицу likes...")
            db.create_all()
        else:
            print("\n❤️ Таблица likes уже существует")
            # Проверяем структуру likes
            likes_columns = inspector.get_columns('likes')
            likes_column_names = [col['name'] for col in likes_columns]
            print(f"   Колонки: {', '.join(likes_column_names)}")

        print("-" * 60)

        # 5. Проверяем наличие таблицы recipe_images
        if 'recipe_images' not in inspector.get_table_names():
            print("\n🖼️ Создаем таблицу recipe_images...")
            db.create_all()
        else:
            print("\n🖼️ Таблица recipe_images уже существует")
            images_columns = inspector.get_columns('recipe_images')
            images_column_names = [col['name'] for col in images_columns]
            print(f"   Колонки: {', '.join(images_column_names)}")

        print("=" * 60)
        print("✅ Миграция базы данных завершена!")


def reset_database():
    """Сброс базы данных (только для разработки!)"""
    with app.app_context():
        print("\n⚠️  ВНИМАНИЕ: Выполняется полный сброс базы данных!")
        confirm = input("Вы уверены? Это удалит все данные! (yes/no): ")

        if confirm.lower() != 'yes':
            print("❌ Отменено")
            return

        # Удаляем все таблицы
        db.drop_all()
        print("🗑️ Все таблицы удалены")

        # Создаем таблицы заново
        db.create_all()
        print("✅ Таблицы созданы заново")

        print("\n📊 Структура базы данных:")
        inspector = inspect(db.engine)
        for table_name in inspector.get_table_names():
            print(f"  - {table_name}")
            columns = inspector.get_columns(table_name)
            for col in columns:
                print(f"      • {col['name']}: {col['type']}")

        # Мигрируем рецепты из JSON
        try:
            from app import migrate_recipes_from_json
            migrated = migrate_recipes_from_json()
            print(f"\n✅ Перенесено {migrated} рецептов из JSON")
        except Exception as e:
            print(f"\n⚠️ Ошибка при миграции рецептов: {e}")
            print("Вы можете импортировать рецепты позже через API /api/db-migrate")


def show_db_structure():
    """Показывает структуру базы данных"""
    with app.app_context():
        inspector = inspect(db.engine)

        print("\n📊 СТРУКТУРА БАЗЫ ДАННЫХ")
        print("=" * 60)

        for table_name in inspector.get_table_names():
            print(f"\n📋 Таблица: {table_name}")
            print("-" * 30)

            columns = inspector.get_columns(table_name)
            for col in columns:
                nullable = "NOT NULL" if not col['nullable'] else "NULL"
                default = f"DEFAULT {col['default']}" if col['default'] else ""
                print(f"  • {col['name']}: {col['type']} {nullable} {default}")

            # Показываем индексы
            indexes = inspector.get_indexes(table_name)
            if indexes:
                print(f"\n  Индексы:")
                for idx in indexes:
                    print(f"    • {idx['name']}: {', '.join(idx['column_names'])}")

            # Показываем внешние ключи
            foreign_keys = inspector.get_foreign_keys(table_name)
            if foreign_keys:
                print(f"\n  Внешние ключи:")
                for fk in foreign_keys:
                    print(f"    • {fk['constrained_columns']} -> {fk['referred_table']}.{fk['referred_columns']}")

        print("\n" + "=" * 60)


def fix_recipes_author_names():
    """Обновляет имена авторов для существующих рецептов"""
    with app.app_context():
        from app import Recipe

        print("\n🔄 Обновление имен авторов для рецептов...")

        # Для рецептов Cookly (не пользовательских)
        cookly_recipes = Recipe.query.filter_by(is_user_recipe=False).all()
        for recipe in cookly_recipes:
            if not recipe.author_name or recipe.author_name == 'Пользователь':
                recipe.author_name = 'Cookly'
                print(f"  ✓ Рецепт '{recipe.title}' - автор Cookly")

        # Для пользовательских рецептов без автора
        user_recipes = Recipe.query.filter_by(is_user_recipe=True).all()
        for recipe in user_recipes:
            if not recipe.author_name:
                if recipe.recipe_author:
                    recipe.author_name = recipe.recipe_author.username
                else:
                    recipe.author_name = 'Пользователь'
                print(f"  ✓ Рецепт '{recipe.title}' - автор {recipe.author_name}")

        db.session.commit()
        print(f"\n✅ Обновлено {len(cookly_recipes) + len(user_recipes)} рецептов")


def reset_likes_count():
    """Сбрасывает счетчики лайков и пересчитывает их заново"""
    with app.app_context():
        from app import Recipe, Like

        print("\n🔄 Пересчет лайков...")

        # Обнуляем все счетчики
        Recipe.query.update({Recipe.likes_count: 0})
        db.session.commit()

        # Пересчитываем лайки
        recipes = Recipe.query.all()
        for recipe in recipes:
            likes_count = Like.query.filter_by(recipe_id=recipe.id).count()
            recipe.likes_count = likes_count
            print(f"  ✓ Рецепт '{recipe.title}' - {likes_count} лайков")

        db.session.commit()
        print(f"\n✅ Счетчики лайков обновлены для {len(recipes)} рецептов")


def fix_relationship_conflicts():
    """Исправляет конфликты в отношениях (если нужно)"""
    with app.app_context():
        print("🔄 Проверка целостности данных...")

        # Проверяем внешние ключи
        inspector = inspect(db.engine)

        for table_name in ['likes', 'recipe_images', 'favorites']:
            if table_name in inspector.get_table_names():
                foreign_keys = inspector.get_foreign_keys(table_name)
                if not foreign_keys:
                    print(f"⚠️ В таблице {table_name} отсутствуют внешние ключи")

        print("✅ Проверка завершена")


if __name__ == '__main__':
    import sys

    print("🐍 Cookly Database Migration Tool")
    print("=" * 60)

    if len(sys.argv) > 1:
        if sys.argv[1] == '--reset':
            reset_database()

        elif sys.argv[1] == '--structure':
            show_db_structure()

        elif sys.argv[1] == '--fix-authors':
            with app.app_context():
                fix_recipes_author_names()

        elif sys.argv[1] == '--reset-likes':
            with app.app_context():
                reset_likes_count()

        elif sys.argv[1] == '--fix-relations':
            with app.app_context():
                fix_relationship_conflicts()

        elif sys.argv[1] == '--full':
            print("🔄 Выполняется полная миграция...")
            migrate_database()
            with app.app_context():
                fix_recipes_author_names()
                reset_likes_count()
                fix_relationship_conflicts()
            show_db_structure()

        else:
            print(f"❌ Неизвестная команда: {sys.argv[1]}")
            print("\nДоступные команды:")
            print("  python migrate_db.py                  - обычная миграция")
            print("  python migrate_db.py --reset          - полный сброс БД")
            print("  python migrate_db.py --structure      - показать структуру БД")
            print("  python migrate_db.py --fix-authors    - исправить имена авторов")
            print("  python migrate_db.py --reset-likes    - пересчитать лайки")
            print("  python migrate_db.py --fix-relations  - проверить целостность")
            print("  python migrate_db.py --full           - полная миграция + исправления")
    else:
        # Обычная миграция
        migrate_database()

        # После миграции спрашиваем, нужно ли исправить авторов
        with app.app_context():
            from app import Recipe

            need_fix = Recipe.query.filter(
                (Recipe.author_name == None) |
                (Recipe.author_name == '')
            ).count() > 0

            if need_fix:
                print("\n⚠️  Обнаружены рецепты без указания автора.")
                fix = input("Исправить имена авторов? (yes/no): ")
                if fix.lower() == 'yes':
                    fix_recipes_author_names()

        print("\n💡 Для просмотра структуры БД выполните: python migrate_db.py --structure")