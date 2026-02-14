# import_images.py
import os
import json
import requests
from app import app, db, Recipe, RecipeImage
from werkzeug.utils import secure_filename
import uuid
import time

# Создаем папку для загрузок
UPLOAD_FOLDER = 'static/uploads/recipes'
os.makedirs(UPLOAD_FOLDER, exist_ok=True)


def download_image(url, recipe_id):
    """Скачивает изображение по URL и сохраняет локально"""
    max_retries = 3
    for attempt in range(max_retries):
        try:
            # Генерируем уникальное имя файла
            ext = '.jpg'  # По умолчанию
            if '?' in url:
                base_url = url.split('?')[0]
                if '.' in base_url:
                    possible_ext = os.path.splitext(base_url)[1]
                    if possible_ext in ['.jpg', '.jpeg', '.png', '.gif', '.webp']:
                        ext = possible_ext

            filename = f"recipe_{recipe_id}_{uuid.uuid4().hex}{ext}"
            filepath = os.path.join(UPLOAD_FOLDER, filename)

            # Скачиваем изображение
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
            }
            response = requests.get(url, timeout=30, stream=True, headers=headers)
            response.raise_for_status()

            # Проверяем content-type
            content_type = response.headers.get('content-type', '')
            if 'image' not in content_type:
                print(f"  ⚠️ Не изображение: {content_type}")
                return None, None

            with open(filepath, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)

            # Проверяем, что файл действительно скачался
            if os.path.getsize(filepath) > 1024:  # Больше 1KB
                print(f"  ✓ Скачано: {filename} ({os.path.getsize(filepath)} bytes)")
                return filename, filepath
            else:
                os.remove(filepath)
                print(f"  ⚠️ Файл слишком мал, пробуем снова...")

        except Exception as e:
            print(f"  ⚠️ Попытка {attempt + 1}/{max_retries} не удалась: {e}")
            if attempt < max_retries - 1:
                time.sleep(2)  # Ждем перед повторной попыткой
            else:
                print(f"  ❌ Не удалось скачать {url}")

    return None, None


def import_images_from_json(json_file='recipes.json'):
    """Импортирует изображения из JSON-файла"""
    with app.app_context():
        print("🔄 Импорт изображений из JSON...")

        # Загружаем JSON
        try:
            with open(json_file, 'r', encoding='utf-8') as f:
                recipes_data = json.load(f)
            print(f"📊 Загружено {len(recipes_data)} рецептов из JSON")
        except FileNotFoundError:
            print(f"❌ Файл {json_file} не найден")
            return
        except json.JSONDecodeError as e:
            print(f"❌ Ошибка парсинга JSON: {e}")
            return

        success_count = 0
        error_count = 0
        skipped_count = 0

        for recipe_data in recipes_data:
            recipe_id = recipe_data.get('id')
            image_url = recipe_data.get('image')
            title = recipe_data.get('title', 'Unknown')

            if not recipe_id or not image_url:
                print(f"⚠️ Пропуск: нет ID или URL")
                skipped_count += 1
                continue

            # Находим рецепт в БД
            recipe = db.session.get(Recipe, recipe_id)
            if not recipe:
                print(f"❌ Рецепт с ID {recipe_id} не найден в БД")
                error_count += 1
                continue

            print(f"\n📝 Обработка рецепта #{recipe_id}: {title}")

            # Проверяем, есть ли уже локальное изображение
            existing_image = RecipeImage.query.filter_by(recipe_id=recipe.id).first()
            if existing_image:
                print(f"  ✓ Уже есть локальное изображение: {existing_image.filename}")
                skipped_count += 1
                continue

            # Скачиваем изображение
            filename, filepath = download_image(image_url, recipe_id)

            if filename and filepath:
                try:
                    # Сохраняем информацию о файле
                    recipe_image = RecipeImage(
                        recipe_id=recipe.id,
                        filename=filename,
                        filepath=filepath,
                        is_primary=True
                    )
                    db.session.add(recipe_image)

                    # Обновляем рецепт
                    recipe.has_local_image = True
                    recipe.image = filename

                    db.session.commit()
                    success_count += 1
                    print(f"  ✅ Изображение сохранено для рецепта #{recipe_id}")
                except Exception as e:
                    db.session.rollback()
                    print(f"  ❌ Ошибка сохранения в БД: {e}")
                    error_count += 1
            else:
                error_count += 1
                print(f"  ⚠️ Не удалось скачать изображение для рецепта #{recipe_id}")

        print(f"\n📊 ИТОГИ:")
        print(f"  ✅ Успешно: {success_count}")
        print(f"  ⚠️ Пропущено: {skipped_count}")
        print(f"  ❌ Ошибки: {error_count}")


def fix_image_urls_in_db():
    """Исправляет ссылки на изображения в БД"""
    with app.app_context():
        print("🔄 Проверка ссылок на изображения...")

        recipes = Recipe.query.all()
        fixed_count = 0
        error_count = 0

        for recipe in recipes:
            try:
                if recipe.has_local_image and recipe.recipe_images:
                    # Уже есть локальное изображение
                    continue

                if recipe.image and not recipe.image.startswith(('http://', 'https://')):
                    # Это может быть имя файла
                    file_path = os.path.join(UPLOAD_FOLDER, recipe.image)
                    if os.path.exists(file_path):
                        # Файл существует, добавляем запись в RecipeImage
                        recipe_image = RecipeImage(
                            recipe_id=recipe.id,
                            filename=recipe.image,
                            filepath=file_path,
                            is_primary=True
                        )
                        db.session.add(recipe_image)
                        recipe.has_local_image = True
                        fixed_count += 1
                        print(f"  ✓ Рецепт #{recipe.id}: добавлена запись о локальном файле")
            except Exception as e:
                error_count += 1
                print(f"  ❌ Ошибка при обработке рецепта #{recipe.id}: {e}")

        try:
            db.session.commit()
            print(f"\n✅ Исправлено: {fixed_count}, Ошибки: {error_count}")
        except Exception as e:
            db.session.rollback()
            print(f"❌ Ошибка при сохранении: {e}")


if __name__ == '__main__':
    print("=" * 50)
    print("📷 ИМПОРТ ИЗОБРАЖЕНИЙ РЕЦЕПТОВ")
    print("=" * 50)

    # Импортируем изображения
    import_images_from_json()

    print("\n" + "=" * 50)
    print("🔍 ПРОВЕРКА ССЫЛОК")
    print("=" * 50)
    fix_image_urls_in_db()

    print("\n" + "=" * 50)
    print("✅ ГОТОВО!")
    print("=" * 50)