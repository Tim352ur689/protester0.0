-- Для курицы (ID: 5)
UPDATE recipes
SET image = 'kuritsa.png',
    has_local_image = 1
WHERE id = 5;

-- Для брауни (ID: 15)
UPDATE recipes
SET image = 'brauni.png',
    has_local_image = 1
WHERE id = 15;

-- Проверить результат
SELECT id, title, image, has_local_image FROM recipes WHERE id IN (5, 15);

-- Выйти
.exit