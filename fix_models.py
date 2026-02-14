# update_images_from_json.py
import json
import os
import shutil
from app import app, db, Recipe, RecipeImage


def update_images_from_json(json_file='recipes.json'):
    """Обновляет изображения в БД на основе JSON-файла с локальными файлами"""

    # Словарь для замены изображений
    image_replacements = {
        5: {  # ID рецепта "Курица терияки"
            'new_image': 'kuritsa.png',
            'title': 'Курица терияки'
        },
        15: {  # ID рецепта "Брауни с орехами"
            'new_image': 'brauni.png',
            'title': 'Брауни с орехами'
        }
    }

    # Папка для загрузки изображений
    upload_folder = 'static/uploads/recipes'
    os.makedirs(upload_folder, exist_ok=True)

    # Проверяем наличие файлов изображений
    for recipe_id, data in image_replacements.items():
        image_file = data['new_image']
        source_path = image_file  # Предполагаем, что файл в текущей папке
        dest_path = os.path.join(upload_folder, image_file)

        if os.path.exists(source_path):
            # Копируем файл в папку загрузок
            shutil.copy2(source_path, dest_path)
            print(f"✅ Файл {image_file} скопирован в {upload_folder}")
        elif os.path.exists(dest_path):
            print(f"✅ Файл {image_file} уже существует в {upload_folder}")
        else:
            print(f"❌ Файл {image_file} не найден! Поместите его в текущую папку.")
            return

    with app.app_context():
        print("\n🔄 Обновление изображений в базе данных...")

        updated_count = 0
        error_count = 0

        for recipe_id, data in image_replacements.items():
            try:
                # Находим рецепт по ID
                recipe = db.session.get(Recipe, recipe_id)

                if not recipe:
                    print(f"❌ Рецепт с ID {recipe_id} не найден в БД")
                    error_count += 1
                    continue

                print(f"\n📝 Обработка: {recipe.title} (ID: {recipe.id})")

                # Полный путь к файлу
                image_file = data['new_image']
                file_path = os.path.join(upload_folder, image_file)

                if not os.path.exists(file_path):
                    print(f"  ❌ Файл {image_file} не найден по пути {file_path}")
                    error_count += 1
                    continue

                # Удаляем старые изображения из RecipeImage
                old_images = RecipeImage.query.filter_by(recipe_id=recipe.id).all()
                for old_img in old_images:
                    # Удаляем старый файл, если это не то же самое изображение
                    if old_img.filename != image_file and os.path.exists(old_img.filepath):
                        try:
                            os.remove(old_img.filepath)
                            print(f"  🗑️ Удален старый файл: {old_img.filename}")
                        except:
                            pass
                    db.session.delete(old_img)

                # Создаем новую запись в RecipeImage
                new_image = RecipeImage(
                    recipe_id=recipe.id,
                    filename=image_file,
                    filepath=file_path,
                    is_primary=True
                )
                db.session.add(new_image)

                # Обновляем поля рецепта
                recipe.image = image_file
                recipe.has_local_image = True

                print(f"  ✓ Установлено новое изображение: {image_file}")
                updated_count += 1

            except Exception as e:
                print(f"  ❌ Ошибка при обработке рецепта ID {recipe_id}: {e}")
                error_count += 1

        # Сохраняем изменения
        try:
            db.session.commit()
            print(f"\n✅ Готово! Обновлено: {updated_count}, Ошибок: {error_count}")
        except Exception as e:
            db.session.rollback()
            print(f"\n❌ Ошибка при сохранении в БД: {e}")


def verify_updates():
    """Проверяет результаты обновления"""
    with app.app_context():
        print("\n🔍 Проверка обновлений:")
        print("-" * 40)

        recipes_to_check = [5, 15]
        for recipe_id in recipes_to_check:
            recipe = db.session.get(Recipe, recipe_id)
            if recipe:
                print(f"\nРецепт: {recipe.title}")
                print(f"  ID: {recipe.id}")
                print(f"  image поле: {recipe.image}")
                print(f"  has_local_image: {recipe.has_local_image}")

                images = RecipeImage.query.filter_by(recipe_id=recipe.id).all()
                if images:
                    print(f"  Изображения в БД:")
                    for img in images:
                        print(f"    • {img.filename} (primary: {img.is_primary})")
                        print(f"      путь: {img.filepath}")
                        if os.path.exists(img.filepath):
                            print(f"      ✅ файл существует")
                        else:
                            print(f"      ❌ файл НЕ существует")
                else:
                    print(f"  ❌ Нет записей в RecipeImage")


if __name__ == '__main__':
    print("=" * 50)
    print("🍳 ОБНОВЛЕНИЕ ИЗОБРАЖЕНИЙ РЕЦЕПТОВ")
    print("=" * 50)

    # Обновляем изображения
    update_images_from_json()

    # Проверяем результаты
    verify_updates()

    print("\n" + "=" * 50)
    print("✅ Скрипт завершен!")
    print("=" * 50)