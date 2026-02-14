// ========== ГЛОБАЛЬНЫЕ ПЕРЕМЕННЫЕ ==========
let recipesCache = null;
let userRecipesCache = null;
let favoritesCache = null;
let ingredientsCache = null;
let lastFetchTime = 0;
const CACHE_DURATION = 30000;
let isModalOpening = false;
let lastCardClickTime = 0;
let authCheckInProgress = false;
let lastAuthCheck = 0;
const AUTH_CHECK_INTERVAL = 2000;

// ========== ГЛОБАЛЬНЫЙ ПЕРЕХВАТ КЛИКОВ ==========
document.addEventListener('click', function(e) {
    let target = e.target;
    while (target && target !== document.body) {
        // Кнопка выхода
        if (target.id === 'logout-btn' ||
            (target.classList && target.classList.contains('logout-btn')) ||
            (target.tagName === 'A' && target.href && target.href.includes('logout'))) {

            e.preventDefault();
            e.stopPropagation();
            console.log('🛑 Глобальный перехват: выход');

            fetch('/api/auth/logout', {
                method: 'POST',
                credentials: 'same-origin'
            })
            .then(response => response.json())
            .then(data => {
                if (data.success) {
                    window.location.href = '/';
                }
            })
            .catch(() => { window.location.href = '/'; });

            return false;
        }

        // Кнопка профиля
        if (target.id === 'profile-link' ||
            (target.tagName === 'A' && target.href && target.href.includes('/profile'))) {

            e.preventDefault();
            e.stopPropagation();
            console.log('🛑 Глобальный перехват: профиль');
            window.location.href = '/profile';
            return false;
        }

        // Кнопка создания рецепта
        if (target.id === 'add-recipe-btn' ||
            target.closest('#add-recipe-btn') ||
            (target.classList && target.classList.contains('add-recipe-btn'))) {

            e.preventDefault();
            e.stopPropagation();
            console.log('🛑 Глобальный перехват: создать рецепт');
            if (typeof window.openCreateRecipeForm === 'function') {
                window.openCreateRecipeForm();
            } else {
                window.location.href = '/#create';
            }
            return false;
        }

        target = target.parentNode;
    }
}, true);

// ========== ФУНКЦИИ АВТОРИЗАЦИИ ==========

async function checkAuth(forceRefresh = false) {
    // Если уже выполняется проверка, ждем
    if (authCheckInProgress) {
        console.log('⏳ Проверка авторизации уже выполняется, ждем...');
        // Ждем максимум 2 секунды
        for (let i = 0; i < 20; i++) {
            await new Promise(resolve => setTimeout(resolve, 100));
            if (!authCheckInProgress) break;
        }
    }

    const now = Date.now();
    if (!forceRefresh && lastAuthCheck && (now - lastAuthCheck < AUTH_CHECK_INTERVAL)) {
        console.log('⏳ Используем кэшированную проверку авторизации');
        // Пытаемся получить из sessionStorage
        try {
            const cached = sessionStorage.getItem('cookly_auth_check');
            if (cached) {
                const data = JSON.parse(cached);
                if (data.timestamp && (now - data.timestamp < AUTH_CHECK_INTERVAL)) {
                    return data.data;
                }
            }
        } catch (e) {}
        return null;
    }

    try {
        authCheckInProgress = true;
        console.log('🔍 Проверка авторизации...');

        const response = await fetch('/api/auth/user', {
            method: 'GET',
            headers: {
                'Accept': 'application/json',
                'Content-Type': 'application/json',
                'Cache-Control': 'no-cache, no-store, must-revalidate',
                'Pragma': 'no-cache'
            },
            cache: 'no-store',
            credentials: 'same-origin'
        });

        let data;
        try {
            data = await response.json();
        } catch (e) {
            console.error('❌ Ошибка парсинга JSON:', e);
            return { authenticated: false };
        }

        if (!response.ok) {
            console.error('❌ Сервер вернул ошибку:', response.status);
            return { authenticated: false };
        }

        console.log('📊 Статус авторизации:', data.authenticated ? '✅ Авторизован' : '❌ Не авторизован');

        if (data.authenticated && data.user) {
            console.log('👤 Пользователь:', data.user.username);
            // Сохраняем в sessionStorage
            try {
                sessionStorage.setItem('cookly_auth_check', JSON.stringify({
                    timestamp: now,
                    data: data
                }));
            } catch (e) {}
        } else {
            // Очищаем кэш если не авторизован
            try {
                sessionStorage.removeItem('cookly_auth_check');
            } catch (e) {}
        }

        lastAuthCheck = now;
        return data;
    } catch (error) {
        console.error('❌ Ошибка проверки авторизации:', error);
        return { authenticated: false };
    } finally {
        authCheckInProgress = false;
    }
}

function updateAuthUI(data) {
    console.log('🎨 Обновление UI авторизации...', data);

    const authButtons = document.getElementById('auth-buttons');
    const userMenu = document.getElementById('user-menu');

    if (!authButtons || !userMenu) {
        console.warn('⚠️ Элементы авторизации не найдены в DOM');
        return;
    }

    if (data && data.authenticated && data.user) {
        console.log('👤 Пользователь авторизован, показываем меню');

        authButtons.style.cssText = 'display: none !important';
        userMenu.style.cssText = 'display: flex !important';

        const userName = document.getElementById('user-name');
        const userAvatar = document.getElementById('user-avatar');
        const avatarPlaceholder = document.getElementById('user-avatar-placeholder');

        if (userName) {
            userName.textContent = data.user.username || 'Пользователь';
        }

        if (data.user.avatar && userAvatar) {
            userAvatar.src = data.user.avatar;
            userAvatar.style.display = 'block';
            if (avatarPlaceholder) avatarPlaceholder.style.display = 'none';
        } else {
            if (userAvatar) userAvatar.style.display = 'none';
            if (avatarPlaceholder) {
                avatarPlaceholder.style.display = 'flex';
                avatarPlaceholder.textContent = (data.user.username || 'U').charAt(0).toUpperCase();
            }
        }

        const profileLink = document.getElementById('profile-link');
        if (profileLink) {
            profileLink.href = '/profile';
            profileLink.style.pointerEvents = 'auto';
            profileLink.style.cursor = 'pointer';
        }

        try {
            localStorage.setItem('cookly_auth', JSON.stringify({
                authenticated: true,
                username: data.user.username,
                timestamp: Date.now()
            }));
        } catch (e) {
            console.warn('⚠️ Не удалось сохранить состояние в localStorage:', e);
        }

    } else {
        console.log('👤 Пользователь не авторизован, показываем кнопки входа');

        authButtons.style.cssText = 'display: flex !important';
        userMenu.style.cssText = 'display: none !important';

        try {
            localStorage.removeItem('cookly_auth');
        } catch (e) {
            console.warn('⚠️ Не удалось очистить localStorage:', e);
        }
    }
}

async function logout() {
    console.log('🚪 Выход из системы...');

    try {
        const response = await fetch('/api/auth/logout', {
            method: 'POST',
            headers: {
                'Accept': 'application/json',
                'Content-Type': 'application/json',
                'Cache-Control': 'no-cache'
            },
            credentials: 'same-origin'
        });

        const data = await response.json();

        if (data.success) {
            console.log('✅ Выход выполнен успешно');
            showNotification('Вы вышли из системы', 'check-circle');

            recipesCache = null;
            userRecipesCache = null;
            favoritesCache = null;
            ingredientsCache = null;
            lastFetchTime = 0;
            lastAuthCheck = 0;

            try {
                localStorage.removeItem('cookly_auth');
                localStorage.removeItem('cookly_likes');
                sessionStorage.removeItem('auth_success');
                sessionStorage.removeItem('auth_timestamp');
                sessionStorage.removeItem('cookly_auth_check');
            } catch (e) {
                console.warn('⚠️ Не удалось очистить localStorage:', e);
            }

            updateAuthUI({ authenticated: false });
            window.location.href = '/';
        }
    } catch (error) {
        console.error('❌ Ошибка выхода:', error);
        showNotification('Ошибка при выходе из системы', 'exclamation-triangle');
    }
}

function restoreAuthFromStorage() {
    try {
        const saved = localStorage.getItem('cookly_auth');
        if (saved) {
            const data = JSON.parse(saved);
            const now = Date.now();

            if (data.authenticated && (now - data.timestamp < 86400000)) {
                console.log('🔄 Восстанавливаем состояние авторизации из localStorage');
                return { authenticated: true, user: { username: data.username } };
            } else {
                localStorage.removeItem('cookly_auth');
            }
        }
    } catch (e) {
        console.warn('⚠️ Ошибка восстановления из localStorage:', e);
    }
    return { authenticated: false };
}

// ========== API ФУНКЦИИ ==========

async function apiRequest(endpoint, method = 'GET', data = null, isFormData = false) {
    const url = `/api${endpoint}`;
    const options = {
        method,
        headers: {
            'Accept': 'application/json',
            'Cache-Control': 'no-cache'
        },
        credentials: 'same-origin'
    };

    if (!isFormData && data) {
        options.headers['Content-Type'] = 'application/json';
        options.body = JSON.stringify(data);
    } else if (data) {
        options.body = data;
    }

    try {
        const response = await fetch(url, options);
        const contentType = response.headers.get('content-type');

        if (!contentType || !contentType.includes('application/json')) {
            const text = await response.text();
            console.error('❌ Сервер вернул не JSON:', text.substring(0, 200));
            throw new Error('Сервер вернул некорректный ответ');
        }

        const result = await response.json();

        if (!response.ok) {
            throw new Error(result.error || result.message || 'Ошибка запроса');
        }

        return result;
    } catch (error) {
        console.error('❌ API Error:', error);
        showNotification(`Ошибка: ${error.message}`, 'exclamation-triangle');
        throw error;
    }
}

// ========== ФУНКЦИИ ДЛЯ РЕЦЕПТОВ ==========

async function loadAllRecipes(forceRefresh = false) {
    const now = Date.now();
    if (!forceRefresh && recipesCache && (now - lastFetchTime < CACHE_DURATION)) {
        return recipesCache;
    }

    try {
        const response = await apiRequest('/all-recipes');
        recipesCache = response;
        lastFetchTime = now;
        return response;
    } catch (error) {
        console.error('❌ Ошибка загрузки рецептов:', error);
        return recipesCache || [];
    }
}

async function loadUserRecipes(forceRefresh = false) {
    if (!forceRefresh && userRecipesCache) {
        return userRecipesCache;
    }

    try {
        const response = await apiRequest('/user-recipes');
        userRecipesCache = response;
        return response;
    } catch (error) {
        console.error('❌ Ошибка загрузки пользовательских рецептов:', error);
        return userRecipesCache || [];
    }
}

async function saveUserRecipe(recipeData) {
    try {
        const response = await apiRequest('/user-recipes', 'POST', recipeData);
        if (response && response.success) {
            recipesCache = null;
            userRecipesCache = null;
            showNotification('Рецепт успешно сохранен!', 'check-circle');
        }
        return response;
    } catch (error) {
        console.error('❌ Ошибка сохранения рецепта:', error);
        showNotification('Ошибка при сохранении рецепта', 'exclamation-triangle');
        return null;
    }
}

async function deleteUserRecipe(recipeId) {
    try {
        const response = await apiRequest(`/user-recipes/${recipeId}`, 'DELETE');
        if (response && response.success) {
            recipesCache = null;
            userRecipesCache = null;
            favoritesCache = null;
            showNotification('Рецепт удален', 'trash');
        }
        return response;
    } catch (error) {
        console.error('❌ Ошибка удаления рецепта:', error);
        showNotification('Ошибка при удалении рецепта', 'exclamation-triangle');
        return null;
    }
}

// ========== ФУНКЦИИ ДЛЯ ИЗБРАННОГО ==========

async function loadFavorites(forceRefresh = false) {
    try {
        const authData = await checkAuth();
        if (!authData || !authData.authenticated) {
            return [];
        }

        if (!forceRefresh && favoritesCache) {
            return favoritesCache;
        }

        const response = await apiRequest('/favorites');
        favoritesCache = response;
        return response;
    } catch (error) {
        console.error('❌ Ошибка загрузки избранного:', error);
        return [];
    }
}

async function toggleFavorite(recipeId) {
    try {
        const authData = await checkAuth(true);
        if (!authData || !authData.authenticated) {
            showNotification('Войдите, чтобы добавлять в избранное', 'info-circle');
            return null;
        }

        const response = await apiRequest('/favorites', 'POST', { recipeId });
        if (response && response.success) {
            favoritesCache = null;
            await renderFavorites();

            document.querySelectorAll(`.favorite-btn[data-recipe-id="${recipeId}"]`).forEach(btn => {
                const isFavorite = response.favorites.includes(recipeId);
                btn.classList.toggle('active', isFavorite);
                btn.innerHTML = `<i class="${isFavorite ? 'fas' : 'far'} fa-bookmark"></i>`;
            });

            const modalBtn = document.getElementById(`modal-favorite-btn-${recipeId}`);
            if (modalBtn) {
                const isFavorite = response.favorites.includes(recipeId);
                modalBtn.classList.toggle('active', isFavorite);
                modalBtn.innerHTML = `<i class="${isFavorite ? 'fas' : 'far'} fa-bookmark"></i> ${isFavorite ? 'В избранном' : 'В избранное'}`;
            }

            showNotification(isFavorite ? 'Добавлено в избранное' : 'Удалено из избранного', 'bookmark');
        }
        return response;
    } catch (error) {
        console.error('❌ Ошибка добавления в избранное:', error);
        return null;
    }
}

// ========== ФУНКЦИИ ДЛЯ ИНГРЕДИЕНТОВ ==========

async function loadAllIngredients(forceRefresh = false) {
    if (!forceRefresh && ingredientsCache) {
        return ingredientsCache;
    }

    try {
        const response = await apiRequest('/all-ingredients');
        ingredientsCache = response;
        return response;
    } catch (error) {
        console.error('❌ Ошибка загрузки ингредиентов:', error);
        return ingredientsCache || [];
    }
}

async function saveUserIngredient(ingredient) {
    try {
        const authData = await checkAuth();
        if (!authData || !authData.authenticated) {
            return null;
        }

        const response = await apiRequest('/user-ingredients', 'POST', { ingredient });
        if (response && response.success) {
            ingredientsCache = null;
        }
        return response;
    } catch (error) {
        console.error('❌ Ошибка сохранения ингредиента:', error);
        return null;
    }
}// ========== ФУНКЦИИ ДЛЯ ОТОБРАЖЕНИЯ РЕЦЕПТОВ ==========

async function renderRecipes(recipesArray, containerId, showFavoriteBtn = true, showUserBadge = false) {
    const container = document.getElementById(containerId);
    if (!container) return false;

    container.innerHTML = '';

    if (!recipesArray || recipesArray.length === 0) {
        return false;
    }

    const authData = await checkAuth();
    const favorites = authData && authData.authenticated ? await loadFavorites() : [];

    // Загружаем информацию о лайках для каждого рецепта
    const likesData = {};

    // Сначала пробуем загрузить из кэша
    try {
        const cachedLikes = JSON.parse(localStorage.getItem('cookly_likes') || '{}');
        recipesArray.forEach(recipe => {
            if (cachedLikes[recipe.id]) {
                likesData[recipe.id] = cachedLikes[recipe.id];
            } else {
                likesData[recipe.id] = { likes_count: recipe.likes_count || 0, user_liked: false };
            }
        });
    } catch (e) {
        recipesArray.forEach(recipe => {
            likesData[recipe.id] = { likes_count: recipe.likes_count || 0, user_liked: false };
        });
    }

    // Обновляем с сервера для авторизованных пользователей
    if (authData && authData.authenticated) {
        for (const recipe of recipesArray) {
            try {
                const response = await fetch(`/api/recipe/${recipe.id}/likes`, {
                    credentials: 'same-origin',
                    headers: {
                        'Cache-Control': 'no-cache'
                    }
                });
                if (response.ok) {
                    const data = await response.json();
                    likesData[recipe.id] = data;
                    // Сохраняем в кэш
                    try {
                        const cachedLikes = JSON.parse(localStorage.getItem('cookly_likes') || '{}');
                        cachedLikes[recipe.id] = data;
                        localStorage.setItem('cookly_likes', JSON.stringify(cachedLikes));
                    } catch (e) {}
                }
            } catch (error) {
                console.error('Error loading likes:', error);
            }
        }
    }

    recipesArray.forEach(recipe => {
        const recipeCard = document.createElement('div');
        recipeCard.className = 'recipe-card';
        recipeCard.dataset.id = recipe.id;
        recipeCard.dataset.recipeId = recipe.id;

        recipeCard.dataset.recipeData = JSON.stringify({
            id: recipe.id,
            title: recipe.title,
            image: recipe.image,
            time: recipe.time,
            difficulty: recipe.difficulty,
            calories: recipe.calories,
            servings: recipe.servings,
            ingredients: recipe.ingredients || [],
            instructions: recipe.instructions || [],
            match_score: recipe.match_score || null,
            matched_products: recipe.matched_products || null,
            isUserRecipe: recipe.isUserRecipe || false,
            author_name: recipe.author_name || (recipe.isUserRecipe ? 'Пользователь' : 'Cookly'),
            likes_count: recipe.likes_count || 0
        });

        const isFavorite = favorites && favorites.includes(recipe.id);
        const favoriteClass = isFavorite ? 'active' : '';

        const likesInfo = likesData[recipe.id] || { likes_count: recipe.likes_count || 0, user_liked: false };

        const matchScore = recipe.match_score ?
            `<div class="match-badge">
                ${recipe.match_score}% совпадение
            </div>` : '';

        // Определяем имя автора
        let authorName = recipe.author_name || (recipe.isUserRecipe ? 'Пользователь' : 'Cookly');
        if (recipe.author) {
            authorName = recipe.author;
        }

        // Создаем карточку с лайками в самом низу, БЕЗ кнопок редактирования/удаления
        recipeCard.innerHTML = `
            <div class="recipe-img-container">
                <img src="${recipe.image}" alt="${recipe.title}" class="recipe-img" onerror="this.onerror=null; this.src='https://images.unsplash.com/photo-1546069901-ba9599a7e63c?ixlib=rb-4.0.3&auto=format&fit=crop&w=800&q=80'">
                <div class="recipe-overlay"></div>
                ${showFavoriteBtn ? `<button class="favorite-btn ${favoriteClass}" data-recipe-id="${recipe.id}">
                    <i class="${isFavorite ? 'fas' : 'far'} fa-bookmark"></i>
                </button>` : ''}
                ${showUserBadge && recipe.isUserRecipe ? '<div class="user-recipe-badge">Мой рецепт</div>' : ''}
                ${matchScore}
            </div>
            <div class="recipe-content">
                <div class="recipe-title">${recipe.title}</div>
                <div class="recipe-author">
                    <i class="fas fa-user"></i> ${authorName}
                </div>
                <div class="recipe-info">
                    <span><i class="far fa-clock"></i> ${recipe.time}</span>
                    <span><i class="fas fa-signal"></i> ${recipe.difficulty}</span>
                    <span><i class="fas fa-fire"></i> ${recipe.calories}</span>
                </div>
            </div>
            <div class="recipe-footer">
                <div class="recipe-likes-container">
                    <button class="like-btn ${likesInfo.user_liked ? 'liked' : ''}" data-recipe-id="${recipe.id}" data-liked="${likesInfo.user_liked}">
                        <i class="${likesInfo.user_liked ? 'fas' : 'far'} fa-heart"></i>
                        <span class="likes-count">${likesInfo.likes_count}</span>
                    </button>
                </div>
            </div>
        `;

        container.appendChild(recipeCard);
    });

    attachRecipeCardHandlers(containerId);
    attachLikeHandlers(containerId);
    return true;
}
async function renderAllRecipes() {
    const allRecipes = await loadAllRecipes();
    const hasRecipes = await renderRecipes(allRecipes, 'recipes-list');

    if (!hasRecipes) {
        const container = document.getElementById('recipes-list');
        if (container) {
            container.innerHTML = `
                <div style="text-align: center; padding: 50px 20px; color: var(--text-light);">
                    <i class="fas fa-utensils" style="font-size: 4rem; margin-bottom: 20px;"></i>
                    <h3>Пока нет рецептов</h3>
                    <p style="margin-top: 15px;">Добавьте рецепты через панель администратора</p>
                </div>
            `;
        }
    }
}

async function renderFavorites() {
    const authData = await checkAuth(true);

    const container = document.getElementById('favorites-list');
    const emptyMessage = document.getElementById('empty-favorites');

    if (!authData || !authData.authenticated) {
        if (container) container.innerHTML = '';
        if (emptyMessage) {
            emptyMessage.innerHTML = `
                <i class="far fa-bookmark" style="font-size: 4rem; color: var(--cool-light); margin-bottom: 20px;"></i>
                <h3 style="color: var(--text-light); margin-bottom: 15px;">Войдите, чтобы видеть избранное</h3>
                <p style="color: var(--text-light); max-width: 300px; margin: 0 auto;">
                    <a href="/login" style="color: var(--primary-green); font-weight: 600;">Войдите</a> или
                    <a href="/register" style="color: var(--primary-green); font-weight: 600;">зарегистрируйтесь</a>
                </p>
            `;
            emptyMessage.style.display = 'block';
        }
        return;
    }

    const favorites = await loadFavorites(true);
    const allRecipes = await loadAllRecipes();
    const favoriteRecipes = allRecipes.filter(recipe => favorites.includes(recipe.id));

    if (favoriteRecipes.length > 0) {
        await renderRecipes(favoriteRecipes, 'favorites-list', true);
        if (emptyMessage) emptyMessage.style.display = 'none';
    } else {
        if (container) container.innerHTML = '';
        if (emptyMessage) {
            emptyMessage.innerHTML = `
                <i class="far fa-bookmark" style="font-size: 4rem; color: var(--cool-light); margin-bottom: 20px;"></i>
                <h3 style="color: var(--text-light); margin-bottom: 15px;">Избранное пусто</h3>
                <p style="color: var(--text-light); max-width: 300px; margin: 0 auto;">Добавляйте рецепты в избранное, нажимая на закладку</p>
            `;
            emptyMessage.style.display = 'block';
        }
    }
}

async function renderMyRecipes() {
    const authData = await checkAuth(true);

    const container = document.getElementById('my-recipes-list');
    const emptyMessage = document.getElementById('empty-my-recipes');

    if (!authData || !authData.authenticated) {
        if (container) container.innerHTML = '';
        if (emptyMessage) {
            emptyMessage.innerHTML = `
                <i class="fas fa-edit" style="font-size: 4rem; color: var(--cool-light); margin-bottom: 20px;"></i>
                <h3 style="color: var(--text-light); margin-bottom: 15px;">Войдите, чтобы создавать рецепты</h3>
                <p style="color: var(--text-light); max-width: 300px; margin: 0 auto;">
                    <a href="/login" style="color: var(--primary-green); font-weight: 600;">Войдите</a> или
                    <a href="/register" style="color: var(--primary-green); font-weight: 600;">зарегистрируйтесь</a>
                </p>
            `;
            emptyMessage.style.display = 'block';
        }
        return;
    }

    const userRecipes = await loadUserRecipes(true);

    if (userRecipes.length > 0) {
        await renderRecipes(userRecipes, 'my-recipes-list', true, true);
        if (emptyMessage) emptyMessage.style.display = 'none';
    } else {
        if (container) container.innerHTML = '';
        if (emptyMessage) {
            emptyMessage.innerHTML = `
                <i class="fas fa-edit" style="font-size: 4rem; color: var(--cool-light); margin-bottom: 20px;"></i>
                <h3 style="color: var(--text-light); margin-bottom: 15px;">У вас пока нет своих рецептов</h3>
                <p style="color: var(--text-light); max-width: 300px; margin: 0 auto;">Создайте свой первый рецепт, нажав на кнопку "+" внизу</p>
            `;
            emptyMessage.style.display = 'block';
        }
    }
}
// ========== ФУНКЦИИ ДЛЯ ЛАЙКОВ ==========

function attachLikeHandlers(containerId = null) {
    const likeButtons = containerId
        ? document.querySelectorAll(`#${containerId} .like-btn`)
        : document.querySelectorAll('.like-btn');

    likeButtons.forEach(btn => {
        // Удаляем старый обработчик
        btn.onclick = null;

        btn.onclick = async function(e) {
            e.preventDefault();
            e.stopPropagation();

            const recipeId = this.dataset.recipeId;

            // Проверяем авторизацию
            const authData = await checkAuth();
            if (!authData || !authData.authenticated) {
                showNotification('Войдите, чтобы ставить лайки', 'info-circle');
                return;
            }

            // Сохраняем оригинальное содержимое для восстановления в случае ошибки
            const originalHtml = this.innerHTML;

            // Блокируем кнопку на время запроса
            this.disabled = true;
            this.innerHTML = '<i class="fas fa-spinner fa-spin"></i>';

            try {
                console.log(`🔄 Отправка лайка для рецепта ${recipeId}`);

                const response = await fetch(`/api/recipe/${recipeId}/like`, {
                    method: 'POST',
                    credentials: 'same-origin',
                    headers: {
                        'Content-Type': 'application/json',
                        'Accept': 'application/json'
                    }
                });

                if (!response.ok) {
                    throw new Error(`HTTP ошибка: ${response.status}`);
                }

                const data = await response.json();
                console.log('✅ Ответ от сервера:', data);

                if (data.success) {
                    // Обновляем иконку и счетчик
                    const icon = this.querySelector('i');
                    const countSpan = this.querySelector('.likes-count');

                    // Обновляем классы и иконку
                    if (data.action === 'liked') {
                        this.classList.add('liked');
                        this.dataset.liked = 'true';
                        // Заменяем иконку на solid heart
                        this.innerHTML = `<i class="fas fa-heart"></i> <span class="likes-count">${data.likes_count}</span>`;
                    } else {
                        this.classList.remove('liked');
                        this.dataset.liked = 'false';
                        // Заменяем иконку на regular heart
                        this.innerHTML = `<i class="far fa-heart"></i> <span class="likes-count">${data.likes_count}</span>`;
                    }

                    // Анимация
                    const newIcon = this.querySelector('i');
                    newIcon.style.animation = 'likePop 0.3s ease';
                    setTimeout(() => {
                        newIcon.style.animation = '';
                    }, 300);

                    // Обновляем данные в localStorage для синхронизации
                    updateLikesInLocalStorage(recipeId, data.likes_count, data.action === 'liked');

                    // Обновляем лайк в модальном окне, если оно открыто
                    const modalLikeBtn = document.getElementById(`modal-like-btn-${recipeId}`);
                    if (modalLikeBtn) {
                        if (data.action === 'liked') {
                            modalLikeBtn.classList.add('liked');
                            modalLikeBtn.innerHTML = `<i class="fas fa-heart"></i> <span class="likes-count">${data.likes_count}</span>`;
                        } else {
                            modalLikeBtn.classList.remove('liked');
                            modalLikeBtn.innerHTML = `<i class="far fa-heart"></i> <span class="likes-count">${data.likes_count}</span>`;
                        }
                    }

                    showNotification(data.message || (data.action === 'liked' ? 'Лайк поставлен' : 'Лайк убран'), 'heart');
                } else {
                    throw new Error(data.error || 'Неизвестная ошибка');
                }

            } catch (error) {
                console.error('❌ Ошибка при оценке рецепта:', error);
                showNotification(`Ошибка: ${error.message}`, 'exclamation-triangle');
                // Возвращаем исходное содержимое
                this.innerHTML = originalHtml;
            } finally {
                this.disabled = false;
            }
        };
    });
}

function updateLikesInLocalStorage(recipeId, likesCount, userLiked) {
    try {
        const likesData = JSON.parse(localStorage.getItem('cookly_likes') || '{}');
        likesData[recipeId] = { likes_count: likesCount, user_liked: userLiked };
        localStorage.setItem('cookly_likes', JSON.stringify(likesData));
    } catch (e) {
        console.warn('Failed to save likes to localStorage:', e);
    }
}

// ========== ФУНКЦИИ ДЛЯ ФОРМЫ СОЗДАНИЯ РЕЦЕПТА ==========

async function addIngredient(ingredientName = '', amount = '', isCustom = false) {
    const container = document.getElementById('ingredients-container');
    const message = document.getElementById('no-ingredients-message');

    if (!container) return;

    if (message) message.style.display = 'none';

    const row = document.createElement('div');
    row.className = 'ingredient-row';

    const allIngredients = await loadAllIngredients();
    let options = '<option value="">Выберите ингредиент...</option>';

    if (allIngredients && allIngredients.length > 0) {
        allIngredients.forEach(ingredient => {
            const selected = ingredient === ingredientName ? 'selected' : '';
            options += `<option value="${ingredient}" ${selected}>${ingredient}</option>`;
        });
    }

    row.innerHTML = `
        <div class="ingredient-name-container">
            <select class="form-select ingredient-select" ${isCustom ? 'style="display:none"' : ''}>
                ${options}
            </select>
            <input type="text" class="form-input ingredient-name-input"
                   placeholder="Введите свой ингредиент"
                   value="${isCustom ? ingredientName : ''}"
                   ${isCustom ? '' : 'style="display:none"'}>
            <button type="button" class="custom-ingredient-toggle" onclick="window.toggleIngredientMode(this)">
                <i class="fas ${isCustom ? 'fa-list' : 'fa-edit'}"></i>
            </button>
        </div>
        <input type="text" class="form-input ingredient-amount-input" placeholder="Количество" value="${amount}" required>
        <button type="button" class="remove-ingredient" onclick="window.removeIngredient(this)">
            <i class="fas fa-times"></i>
        </button>
    `;

    container.appendChild(row);
}

function removeIngredient(button) {
    const row = button.closest('.ingredient-row');
    if (row) {
        row.remove();

        const container = document.getElementById('ingredients-container');
        const message = document.getElementById('no-ingredients-message');
        if (container && container.children.length === 0 && message) {
            message.style.display = 'block';
        }
    }
}

function toggleIngredientMode(button) {
    const row = button.closest('.ingredient-row');
    const select = row.querySelector('.ingredient-select');
    const input = row.querySelector('.ingredient-name-input');
    const icon = button.querySelector('i');

    if (select.style.display === 'none') {
        select.style.display = 'block';
        input.style.display = 'none';
        icon.className = 'fas fa-edit';
    } else {
        select.style.display = 'none';
        input.style.display = 'block';
        icon.className = 'fas fa-list';
    }
}

function addStep(stepText = '') {
    const container = document.getElementById('steps-container');
    if (!container) return;

    const rowCount = container.children.length;

    const row = document.createElement('div');
    row.className = 'step-row';
    row.innerHTML = `
        <div class="step-number">${rowCount + 1}</div>
        <textarea class="form-input step-input" placeholder="Опишите шаг приготовления" required>${stepText}</textarea>
        <button type="button" class="remove-ingredient" onclick="window.removeStep(this)">
            <i class="fas fa-times"></i>
        </button>
    `;

    container.appendChild(row);
}

function removeStep(button) {
    const row = button.closest('.step-row');
    const container = document.getElementById('steps-container');
    if (row && container && container.children.length > 1) {
        row.remove();

        document.querySelectorAll('.step-row .step-number').forEach((number, index) => {
            number.textContent = index + 1;
        });
    }
}

function cancelCreate() {
    const form = document.getElementById('recipe-form');
    if (!form) return;

    form.reset();
    form.removeAttribute('data-edit-id');

    const ingredientsContainer = document.getElementById('ingredients-container');
    if (ingredientsContainer) ingredientsContainer.innerHTML = '';

    const noIngredientsMessage = document.getElementById('no-ingredients-message');
    if (noIngredientsMessage) noIngredientsMessage.style.display = 'block';

    const stepsContainer = document.getElementById('steps-container');
    if (stepsContainer) {
        stepsContainer.innerHTML = '';
        addStep();
    }

    const saveBtn = form.querySelector('.save-btn');
    if (saveBtn) {
        saveBtn.innerHTML = '<i class="fas fa-save"></i> Сохранить рецепт';
    }

    switchTab('recipes');
}

async function openCreateRecipeForm() {
    console.log('📝 Открытие формы создания рецепта');

    const authData = await checkAuth(true);
    if (!authData || !authData.authenticated) {
        showNotification('Войдите, чтобы создавать рецепты', 'info-circle');
        return;
    }

    cancelCreate();
    switchTab('create');
    window.scrollTo({ top: 0, behavior: 'smooth' });
}

async function editRecipe(recipeId) {
    const authData = await checkAuth(true);
    if (!authData || !authData.authenticated) {
        showNotification('Войдите, чтобы редактировать рецепты', 'info-circle');
        return;
    }

    const userRecipes = await loadUserRecipes(true);
    const recipe = userRecipes.find(r => r.id === recipeId);

    if (!recipe) return;

    closeRecipeModal();
    await openCreateRecipeForm();

    document.getElementById('recipe-title').value = recipe.title;
    document.getElementById('recipe-image').value = recipe.image || '';
    document.getElementById('recipe-time').value = recipe.time;
    document.getElementById('recipe-difficulty').value = recipe.difficulty;
    document.getElementById('recipe-calories').value = recipe.calories;
    document.getElementById('recipe-servings').value = recipe.servings;

    const ingredientsContainer = document.getElementById('ingredients-container');
    ingredientsContainer.innerHTML = '';

    const allIngredients = await loadAllIngredients();
    recipe.ingredients.forEach(async (ingredient) => {
        const isCustom = !allIngredients.includes(ingredient.name);
        addIngredient(ingredient.name, ingredient.amount, isCustom);
    });

    const stepsContainer = document.getElementById('steps-container');
    stepsContainer.innerHTML = '';

    recipe.instructions.forEach(step => {
        addStep(step.description || step);
    });

    const form = document.getElementById('recipe-form');
    form.dataset.editId = recipeId;

    const saveBtn = form.querySelector('.save-btn');
    saveBtn.innerHTML = '<i class="fas fa-save"></i> Обновить рецепт';
}

async function deleteRecipeHandler(recipeId) {
    if (!confirm('Вы уверены, что хотите удалить этот рецепт?')) {
        return;
    }

    const result = await deleteUserRecipe(recipeId);

    if (result && result.success) {
        closeRecipeModal();
        await renderMyRecipes();
        await renderAllRecipes();
    }
}// ========== ФУНКЦИИ ДЛЯ МОДАЛЬНОГО ОКНА ==========

async function openRecipeModal(recipe) {
    if (isModalOpening) return;
    isModalOpening = true;

    if (!recipe || !recipe.title) {
        console.error('❌ Invalid recipe data:', recipe);
        showNotification('Ошибка загрузки рецепта', 'exclamation-triangle');
        isModalOpening = false;
        return;
    }

    const modal = document.getElementById('recipe-modal');
    if (!modal) {
        isModalOpening = false;
        return;
    }

    if (modal.style.display === 'block') {
        closeRecipeModal();
        await new Promise(resolve => setTimeout(resolve, 100));
    }

    // Скрываем кнопки аккаунта и выхода при открытии модального окна
    const authButtons = document.getElementById('auth-buttons');
    const userMenu = document.getElementById('user-menu');
    const addRecipeBtn = document.getElementById('add-recipe-btn');
    const bottomNav = document.querySelector('.bottom-nav');

    if (authButtons) authButtons.style.opacity = '0';
    if (userMenu) userMenu.style.opacity = '0';
    if (addRecipeBtn) addRecipeBtn.style.opacity = '0';
    if (bottomNav) bottomNav.style.opacity = '0';

    let modalContent = modal.querySelector('.modal-content');
    if (!modalContent) {
        modalContent = document.createElement('div');
        modalContent.className = 'modal-content';
        modal.appendChild(modalContent);
    }

    const authData = await checkAuth();
    const favorites = authData && authData.authenticated ? await loadFavorites() : [];
    const isFavorite = favorites && favorites.includes(recipe.id);

    // Получаем информацию о лайках
    let likesData = { likes_count: recipe.likes_count || 0, user_liked: false };

    // Сначала пробуем из кэша
    try {
        const cachedLikes = JSON.parse(localStorage.getItem('cookly_likes') || '{}');
        if (cachedLikes[recipe.id]) {
            likesData = cachedLikes[recipe.id];
        }
    } catch (e) {}

    // Обновляем с сервера для авторизованных пользователей
    if (authData && authData.authenticated) {
        try {
            const response = await fetch(`/api/recipe/${recipe.id}/likes`, {
                credentials: 'same-origin',
                headers: {
                    'Cache-Control': 'no-cache'
                }
            });
            if (response.ok) {
                likesData = await response.json();
                updateLikesInLocalStorage(recipe.id, likesData.likes_count, likesData.user_liked);
            }
        } catch (error) {
            console.error('Error loading likes:', error);
        }
    }

    let authorName = recipe.author_name || (recipe.isUserRecipe ? 'Пользователь' : 'Cookly');
    if (recipe.author) {
        authorName = recipe.author;
    }

    // Проверяем, является ли текущий пользователь автором рецепта
    const isAuthor = authData && authData.authenticated && authData.user &&
                     ((recipe.isUserRecipe && recipe.user_id === authData.user.id) ||
                      (recipe.author === authData.user.username));

    modalContent.innerHTML = `
        <div class="modal-header">
            <img src="${recipe.image || 'https://images.unsplash.com/photo-1546069901-ba9599a7e63c'}"
                 alt="${recipe.title}"
                 class="modal-img"
                 onerror="this.onerror=null; this.src='https://images.unsplash.com/photo-1546069901-ba9599a7e63c'">
            <button class="close-modal" id="close-modal">
                <i class="fas fa-times"></i>
            </button>
        </div>
        <div class="modal-body">
            <h2 class="modal-title">${recipe.title}</h2>

            <div class="modal-meta">
                <div class="meta-item">
                    <div class="meta-icon">
                        <i class="far fa-clock"></i>
                    </div>
                    <div class="meta-value">${recipe.time}</div>
                    <div class="meta-label">Время</div>
                </div>
                <div class="meta-item">
                    <div class="meta-icon">
                        <i class="fas fa-signal"></i>
                    </div>
                    <div class="meta-value">${recipe.difficulty}</div>
                    <div class="meta-label">Сложность</div>
                </div>
                <div class="meta-item">
                    <div class="meta-icon">
                        <i class="fas fa-fire"></i>
                    </div>
                    <div class="meta-value">${recipe.calories}</div>
                    <div class="meta-label">Калории</div>
                </div>
                <div class="meta-item">
                    <div class="meta-icon">
                        <i class="fas fa-utensils"></i>
                    </div>
                    <div class="meta-value">${recipe.servings}</div>
                    <div class="meta-label">Порции</div>
                </div>
            </div>

            <div class="recipe-author-modal" style="display: flex; align-items: center; gap: 10px; margin-bottom: 20px; padding: 10px; background: var(--light-green); border-radius: 10px;">
                <i class="fas fa-user-circle" style="font-size: 1.5rem; color: var(--primary-green);"></i>
                <div>
                    <span style="font-weight: 600; color: var(--dark-green);">Автор:</span>
                    <span style="color: var(--text-dark);"> ${authorName}</span>
                </div>
            </div>

            <div class="modal-likes" style="display: flex; align-items: center; gap: 15px; margin-bottom: 20px;">
                <button class="modal-like-btn ${likesData.user_liked ? 'liked' : ''}" id="modal-like-btn-${recipe.id}" data-recipe-id="${recipe.id}">
                    <i class="${likesData.user_liked ? 'fas' : 'far'} fa-heart"></i>
                    <span class="likes-count">${likesData.likes_count}</span>
                </button>
                <span style="color: var(--text-light);">оценок</span>
            </div>

            ${recipe.match_score ? `
            <div class="modal-section">
                <h3 class="section-heading">
                    <i class="fas fa-check-circle"></i>
                    <span>Совпадение с поиском</span>
                </h3>
                <div style="display: flex; flex-wrap: wrap; gap: 10px; margin-top: 10px;">
                    ${recipe.matched_products ? recipe.matched_products.map(product => `
                        <span style="background: linear-gradient(135deg, var(--light-green), #C8E6C9); padding: 8px 15px; border-radius: 20px; font-size: 0.9rem; color: var(--dark-green); font-weight: 600;">
                            ${product}
                        </span>
                    `).join('') : ''}
                </div>
                <div style="margin-top: 15px; padding: 12px; background: rgba(46, 125, 50, 0.1); border-radius: 10px; color: var(--dark-green);">
                    <i class="fas fa-chart-line"></i> Совпадение: <strong>${recipe.match_score}%</strong> с вашими продуктами
                </div>
            </div>
            ` : ''}

            <div class="modal-section">
                <h3 class="section-heading">
                    <i class="fas fa-shopping-basket"></i>
                    <span>Ингредиенты</span>
                </h3>
                <ul class="ingredients-list">
                    ${(recipe.ingredients || []).map(ing => `
                        <li>
                            <span class="ingredient-name">${ing.name}</span>
                            <span class="ingredient-amount">${ing.amount}</span>
                        </li>
                    `).join('')}
                </ul>
            </div>

            <div class="modal-section">
                <h3 class="section-heading">
                    <i class="fas fa-list-ol"></i>
                    <span>Приготовление</span>
                </h3>
                <ol class="instructions-list">
                    ${(recipe.instructions || []).map(step => `
                        <li>${step.description || step}</li>
                    `).join('')}
                </ol>
            </div>

            <div class="modal-actions">
                <button class="modal-favorite-btn ${isFavorite ? 'active' : ''}" id="modal-favorite-btn-${recipe.id}">
                    <i class="${isFavorite ? 'fas' : 'far'} fa-bookmark"></i> ${isFavorite ? 'В избранном' : 'В избранное'}
                </button>
                ${isAuthor ? `
                    <button class="modal-edit-btn" id="modal-edit-btn-${recipe.id}">
                        <i class="fas fa-edit"></i> Редактировать
                    </button>
                    <button class="modal-delete-btn" id="modal-delete-btn-${recipe.id}">
                        <i class="fas fa-trash"></i> Удалить
                    </button>
                ` : ''}
            </div>
        </div>
    `;

    modal.style.display = 'block';
    document.body.style.overflow = 'hidden';

    // Закрытие модального окна
    const closeBtn = document.getElementById('close-modal');
    if (closeBtn) {
        closeBtn.onclick = closeRecipeModal;
    }

    // Обработчик для кнопки избранного
    const favoriteBtn = document.getElementById(`modal-favorite-btn-${recipe.id}`);
    if (favoriteBtn) {
        favoriteBtn.onclick = (e) => {
            e.preventDefault();
            e.stopPropagation();
            toggleFavorite(recipe.id);
        };
    }

    // Обработчик для кнопки лайка
    const likeBtn = document.getElementById(`modal-like-btn-${recipe.id}`);
    if (likeBtn) {
        likeBtn.onclick = async (e) => {
            e.preventDefault();
            e.stopPropagation();

            const recipeId = recipe.id;

            // Проверяем авторизацию
            if (!authData || !authData.authenticated) {
                showNotification('Войдите, чтобы ставить лайки', 'info-circle');
                return;
            }

            // Сохраняем оригинальное содержимое
            const originalHtml = likeBtn.innerHTML;

            // Блокируем кнопку
            likeBtn.disabled = true;
            likeBtn.innerHTML = '<i class="fas fa-spinner fa-spin"></i>';

            try {
                console.log(`🔄 Отправка лайка из модального окна для рецепта ${recipeId}`);

                const response = await fetch(`/api/recipe/${recipeId}/like`, {
                    method: 'POST',
                    credentials: 'same-origin',
                    headers: {
                        'Content-Type': 'application/json',
                        'Accept': 'application/json'
                    }
                });

                if (!response.ok) {
                    throw new Error(`HTTP ошибка: ${response.status}`);
                }

                const data = await response.json();
                console.log('✅ Ответ от сервера:', data);

                if (data.success) {
                    // Обновляем кнопку в модальном окне
                    const newLikesCount = data.likes_count;

                    if (data.action === 'liked') {
                        likeBtn.classList.add('liked');
                        likeBtn.innerHTML = `<i class="fas fa-heart"></i> <span class="likes-count">${newLikesCount}</span>`;
                    } else {
                        likeBtn.classList.remove('liked');
                        likeBtn.innerHTML = `<i class="far fa-heart"></i> <span class="likes-count">${newLikesCount}</span>`;
                    }

                    // Анимация
                    const icon = likeBtn.querySelector('i');
                    icon.style.animation = 'likePop 0.3s ease';
                    setTimeout(() => {
                        icon.style.animation = '';
                    }, 300);

                    // Обновляем лайк на карточке
                    const cardLikeBtn = document.querySelector(`.like-btn[data-recipe-id="${recipeId}"]`);
                    if (cardLikeBtn) {
                        if (data.action === 'liked') {
                            cardLikeBtn.classList.add('liked');
                            cardLikeBtn.dataset.liked = 'true';
                            cardLikeBtn.innerHTML = `<i class="fas fa-heart"></i> <span class="likes-count">${newLikesCount}</span>`;
                        } else {
                            cardLikeBtn.classList.remove('liked');
                            cardLikeBtn.dataset.liked = 'false';
                            cardLikeBtn.innerHTML = `<i class="far fa-heart"></i> <span class="likes-count">${newLikesCount}</span>`;
                        }
                    }

                    // Обновляем localStorage
                    updateLikesInLocalStorage(recipeId, newLikesCount, data.action === 'liked');

                    showNotification(data.message || (data.action === 'liked' ? 'Лайк поставлен' : 'Лайк убран'), 'heart');
                } else {
                    throw new Error(data.error || 'Неизвестная ошибка');
                }
            } catch (error) {
                console.error('❌ Ошибка при оценке рецепта:', error);
                showNotification(`Ошибка: ${error.message}`, 'exclamation-triangle');
                likeBtn.innerHTML = originalHtml;
            } finally {
                likeBtn.disabled = false;
            }
        };
    }

    // Обработчики для редактирования и удаления (только для автора)
    if (isAuthor) {
        const editBtn = document.getElementById(`modal-edit-btn-${recipe.id}`);
        if (editBtn) {
            editBtn.onclick = (e) => {
                e.preventDefault();
                e.stopPropagation();
                editRecipe(recipe.id);
            };
        }

        const deleteBtn = document.getElementById(`modal-delete-btn-${recipe.id}`);
        if (deleteBtn) {
            deleteBtn.onclick = (e) => {
                e.preventDefault();
                e.stopPropagation();
                deleteRecipeHandler(recipe.id);
            };
        }
    }

    // Закрытие модального окна при клике на фон
    modal.onclick = function(e) {
        if (e.target === modal) {
            closeRecipeModal();
        }
    };

    isModalOpening = false;
}

function closeRecipeModal() {
    const modal = document.getElementById('recipe-modal');
    if (modal) {
        modal.style.display = 'none';
        document.body.style.overflow = 'auto';
    }

    // Возвращаем кнопки аккаунта и выхода при закрытии модального окна
    const authButtons = document.getElementById('auth-buttons');
    const userMenu = document.getElementById('user-menu');
    const addRecipeBtn = document.getElementById('add-recipe-btn');
    const bottomNav = document.querySelector('.bottom-nav');

    if (authButtons) authButtons.style.opacity = '1';
    if (userMenu) userMenu.style.opacity = '1';
    if (addRecipeBtn) addRecipeBtn.style.opacity = '1';
    if (bottomNav) bottomNav.style.opacity = '1';
}

// ========== ФУНКЦИИ ДЛЯ ПОИСКА ПО ФОТО ==========

async function photoSearch(file) {
    try {
        const formData = new FormData();
        formData.append('file', file);

        const response = await apiRequest('/photo-search', 'POST', formData, true);
        return response;
    } catch (error) {
        return {
            success: false,
            message: error.message,
            detected_products: [],
            recipes: []
        };
    }
}

async function realPhotoSearch(file) {
    const searchResults = document.getElementById('search-results');
    const uploadArea = document.getElementById('upload-area');
    const uploadProgress = document.getElementById('upload-progress');
    const progressBar = document.getElementById('upload-progress-bar');

    if (!searchResults || !uploadArea) return;

    // Показываем прогресс
    if (uploadProgress) uploadProgress.style.display = 'block';
    if (progressBar) progressBar.style.width = '30%';

    let previewUrl = '';
    const reader = new FileReader();
    reader.onload = function(e) {
        previewUrl = e.target.result;

        uploadArea.innerHTML = `
            <div style="position: relative; z-index: 5; text-align: center;">
                <img src="${previewUrl}" alt="Превью" style="max-width: 100%; max-height: 250px; border-radius: 15px; margin-bottom: 15px; box-shadow: 0 10px 30px rgba(0,0,0,0.2);">
                <div class="upload-text" style="margin-top: 10px;">Фото загружено!</div>
                <div class="upload-subtext" style="font-weight: 600; color: var(--primary-green);">
                    <i class="fas fa-spinner fa-spin"></i> Идет анализ изображения...
                </div>
            </div>
        `;

        uploadArea.className = 'upload-area upload-area-processing';
    };
    reader.readAsDataURL(file);

    searchResults.innerHTML = `
        <div class="section-title">
            <i class="fas fa-search"></i>
            <span>Анализ изображения</span>
        </div>
        <div style="text-align: center; padding: 70px 20px;">
            <div class="loading" style="width: 50px; height: 50px; margin: 0 auto 25px; border-width: 4px;"></div>
            <p style="margin-top: 15px; color: var(--text-dark); font-size: 1.1rem; font-weight: 700;">Идет распознавание продуктов на фото...</p>
        </div>
    `;

    searchResults.scrollIntoView({ behavior: 'smooth' });

    try {
        const result = await photoSearch(file);

        if (progressBar) progressBar.style.width = '100%';
        setTimeout(() => {
            if (uploadProgress) uploadProgress.style.display = 'none';
            if (progressBar) progressBar.style.width = '0%';
        }, 500);

        updateUploadAreaWithProducts(result, previewUrl);
        displayPhotoSearchResults(result);
    } catch (error) {
        console.error('❌ Photo search error:', error);

        if (uploadProgress) uploadProgress.style.display = 'none';

        searchResults.innerHTML = `
            <div style="text-align: center; padding: 50px 20px;">
                <i class="fas fa-exclamation-circle" style="font-size: 4rem; color: var(--accent-teal); margin-bottom: 20px;"></i>
                <p style="color: var(--text-dark); font-size: 1.2rem; margin-bottom: 15px; font-weight: 700;">${error.message}</p>
                <button onclick="window.resetPhotoSearch()" style="margin-top: 25px; background: var(--primary-green); color: white; border: none; padding: 15px 30px; border-radius: 12px; font-weight: 700; cursor: pointer;">
                    <i class="fas fa-redo"></i> Попробовать снова
                </button>
            </div>
        `;
        resetUploadArea();
    }
}

function updateUploadAreaWithProducts(result, imagePreviewUrl = null) {
    const uploadArea = document.getElementById('upload-area');
    if (!uploadArea) return;

    if (!result.detected_products || result.detected_products.length === 0) {
        if (imagePreviewUrl) {
            uploadArea.innerHTML = `
                <div style="position: relative; z-index: 5; text-align: center;">
                    <img src="${imagePreviewUrl}" alt="Превью" style="max-width: 100%; max-height: 250px; border-radius: 15px; margin-bottom: 15px; box-shadow: 0 10px 30px rgba(0,0,0,0.2);">
                    <div class="upload-text" style="color: var(--text-light);">Продукты не обнаружены</div>
                    <div class="upload-subtext" style="color: var(--text-light); font-size: 0.9rem;">
                        Попробуйте другое фото
                    </div>
                </div>
            `;
        }
        return;
    }

    const productNames = result.detected_products.map(p => p.name);
    const productList = formatProductList(productNames);

    let contentHTML = '';
    if (imagePreviewUrl) {
        contentHTML = `
            <div style="position: relative; z-index: 5; text-align: center;">
                <img src="${imagePreviewUrl}" alt="Превью" style="max-width: 100%; max-height: 200px; border-radius: 15px; margin-bottom: 15px; box-shadow: 0 10px 30px rgba(0,0,0,0.2);">
                <div style="display: flex; align-items: center; justify-content: center; gap: 15px; margin-bottom: 20px;">
                    <i class="fas fa-check-circle" style="font-size: 2.5rem; color: var(--primary-green);"></i>
                    <div style="text-align: left;">
                        <div class="upload-text" style="color: var(--dark-green); margin-bottom: 5px;">Анализ завершен!</div>
                        <div class="upload-subtext" style="color: var(--text-dark); font-weight: 600;">
                            Найдено ${result.total_products} ${getProductWord(result.total_products)}
                        </div>
                    </div>
                </div>
                <div style="margin-top: 20px; padding: 15px; background: rgba(232, 245, 233, 0.5); border-radius: 12px; border-left: 3px solid var(--primary-green);">
                    <div class="upload-subtext" style="color: var(--dark-green); font-weight: 700; margin-bottom: 8px;">
                        <i class="fas fa-carrot"></i> Обнаруженные продукты:
                    </div>
                    <div class="upload-subtext" style="color: var(--text-dark); line-height: 1.5;">
                        ${productList}
                    </div>
                </div>
                <button onclick="window.resetPhotoSearch()" style="margin-top: 20px; background: var(--primary-green); color: white; border: none; padding: 10px 20px; border-radius: 10px; cursor: pointer;">
                    <i class="fas fa-redo"></i> Новый поиск
                </button>
            </div>
        `;
    }

    uploadArea.innerHTML = contentHTML;
    uploadArea.className = 'upload-area upload-area-completed';
}

function formatProductList(products) {
    if (!products || products.length === 0) return 'Нет продуктов';
    if (products.length === 1) {
        return `<span style="color: var(--dark-green); font-weight: 700;">${products[0]}</span>`;
    }
    if (products.length === 2) {
        return `<span style="color: var(--dark-green); font-weight: 700;">${products[0]}</span> и <span style="color: var(--dark-green); font-weight: 700;">${products[1]}</span>`;
    }
    const firstProducts = products.slice(0, -1);
    const lastProduct = products[products.length - 1];
    const firstList = firstProducts.map(p => `<span style="color: var(--dark-green); font-weight: 700;">${p}</span>`).join(', ');
    return `${firstList} и <span style="color: var(--dark-green); font-weight: 700;">${lastProduct}</span>`;
}

function getProductWord(count) {
    if (count === 1) return 'продукт';
    if (count >= 2 && count <= 4) return 'продукта';
    return 'продуктов';
}

function resetUploadArea() {
    const uploadArea = document.getElementById('upload-area');
    if (!uploadArea) return;

    uploadArea.innerHTML = `
        <i class="fas fa-camera upload-icon"></i>
        <div class="upload-text">Загрузите фото продуктов</div>
        <div class="upload-subtext">Перетащите сюда фото или нажмите для выбора файла</div>
    `;
    uploadArea.className = 'upload-area';
}

function resetPhotoSearch() {
    const searchResults = document.getElementById('search-results');
    const fileInput = document.getElementById('file-input');
    const uploadProgress = document.getElementById('upload-progress');

    resetUploadArea();
    if (searchResults) searchResults.innerHTML = '';
    if (fileInput) fileInput.value = '';
    if (uploadProgress) uploadProgress.style.display = 'none';
}

function displayPhotoSearchResults(result) {
    const searchResults = document.getElementById('search-results');
    if (!searchResults) return;

    let recipesHtml = '';
    if (result.recipes && result.recipes.length > 0) {
        recipesHtml = `
            <div class="section-title">
                <i class="fas fa-utensils"></i>
                <span>Доступные рецепты (${result.recipes.length})</span>
            </div>
            <div class="recipes-container" id="search-recipes"></div>
        `;
        setTimeout(() => {
            renderRecipes(result.recipes, 'search-recipes');
        }, 10);
    } else {
        recipesHtml = `
            <div style="text-align: center; padding: 50px 20px;">
                <i class="fas fa-search" style="font-size: 4rem; color: var(--cool-light); margin-bottom: 20px;"></i>
                <p style="color: var(--text-dark); font-size: 1.2rem; margin-bottom: 15px; font-weight: 700;">Рецепты не найдены</p>
                <p style="color: var(--text-light); font-size: 0.95rem;">Попробуйте добавить больше ингредиентов или создайте свой рецепт!</p>
                <button onclick="window.openCreateRecipeForm()" style="margin-top: 25px; background: var(--edit-blue); color: white; border: none; padding: 15px 30px; border-radius: 12px; font-weight: 700; cursor: pointer;">
                    <i class="fas fa-plus"></i> Создать рецепт
                </button>
            </div>
        `;
    }

    searchResults.innerHTML = recipesHtml;
}

// ========== ФУНКЦИИ ДЛЯ ПРОФИЛЯ ==========

async function loadProfile() {
    try {
        const authData = await checkAuth(true);

        if (!authData || !authData.authenticated) {
            window.location.href = '/login';
            return;
        }

        const user = authData.user;
        console.log('👤 Загружен профиль пользователя:', user);

        const profileUsername = document.getElementById('profile-username');
        if (profileUsername) profileUsername.textContent = user.username || 'Пользователь';

        const profileEmail = document.getElementById('profile-email');
        if (profileEmail) {
            const emailSpan = profileEmail.querySelector('span');
            if (emailSpan) emailSpan.textContent = user.email || 'Email не указан';
        }

        const profileAvatar = document.getElementById('profile-avatar');
        const profileAvatarPlaceholder = document.getElementById('profile-avatar-placeholder');

        if (user.avatar && profileAvatar) {
            profileAvatar.src = user.avatar;
            profileAvatar.style.display = 'block';
            if (profileAvatarPlaceholder) profileAvatarPlaceholder.style.display = 'none';
        } else if (profileAvatarPlaceholder) {
            profileAvatarPlaceholder.style.display = 'flex';
            profileAvatarPlaceholder.textContent = (user.username || 'U').charAt(0).toUpperCase();
            if (profileAvatar) profileAvatar.style.display = 'none';
        }

        const editUsername = document.getElementById('edit-username');
        if (editUsername) editUsername.value = user.username || '';

        const editEmail = document.getElementById('edit-email');
        if (editEmail) editEmail.value = user.email || '';

        const editAvatar = document.getElementById('edit-avatar');
        if (editAvatar) editAvatar.value = user.avatar || '';

        const badgesContainer = document.getElementById('profile-badges');
        if (badgesContainer) {
            badgesContainer.innerHTML = '';
            if (user.is_admin) {
                badgesContainer.innerHTML += '<span class="profile-badge"><i class="fas fa-crown"></i> Администратор</span>';
            }
            if (user.created_at) {
                const date = new Date(user.created_at);
                badgesContainer.innerHTML += `<span class="profile-badge"><i class="fas fa-calendar"></i> С ${date.toLocaleDateString()}</span>`;
            }
        }

        await loadStats();
        await loadConnectedAccounts(user);
        await loadMyRecipesForProfile();

    } catch (error) {
        console.error('❌ Ошибка загрузки профиля:', error);
        showNotification('Ошибка загрузки профиля', 'exclamation-triangle');
    }
}

async function loadStats() {
    try {
        const stats = await apiRequest('/profile/stats');

        const statRecipes = document.getElementById('stat-recipes');
        if (statRecipes) statRecipes.textContent = stats.recipes_count || 0;

        const statFavorites = document.getElementById('stat-favorites');
        if (statFavorites) statFavorites.textContent = stats.favorites_count || 0;

        const statIngredients = document.getElementById('stat-ingredients');
        if (statIngredients) statIngredients.textContent = stats.ingredients_count || 0;

    } catch (error) {
        console.error('❌ Ошибка загрузки статистики:', error);
    }
}

async function loadConnectedAccounts(user) {
    const container = document.getElementById('connected-accounts');
    if (!container) return;

    container.innerHTML = '';

    const emailItem = document.createElement('div');
    emailItem.className = 'account-item account-email';
    emailItem.innerHTML = `
        <div class="account-info">
            <div class="account-icon">
                <i class="fas fa-envelope"></i>
            </div>
            <div>
                <div class="account-name">${user.email || 'Email не указан'}</div>
                <div class="account-status">
                    <i class="fas fa-check-circle"></i>
                    Подключен
                </div>
            </div>
        </div>
    `;
    container.appendChild(emailItem);

    const googleItem = document.createElement('div');
    googleItem.className = 'account-item account-google';
    googleItem.innerHTML = `
        <div class="account-info">
            <div class="account-icon">
                <i class="fab fa-google"></i>
            </div>
            <div>
                <div class="account-name">Google</div>
                <div class="account-status">
                    <i class="fas ${user.google_id ? 'fa-check-circle' : 'fa-times-circle'}"></i>
                    ${user.google_id ? 'Подключен' : 'Не подключен'}
                </div>
            </div>
        </div>
        ${!user.google_id ? '<a href="/login/google" class="btn btn-outline" style="padding: 8px 15px; text-decoration: none;">Подключить</a>' : ''}
    `;
    container.appendChild(googleItem);

    const telegramItem = document.createElement('div');
    telegramItem.className = 'account-item account-telegram';
    telegramItem.innerHTML = `
        <div class="account-info">
            <div class="account-icon">
                <i class="fab fa-telegram-plane"></i>
            </div>
            <div>
                <div class="account-name">Telegram</div>
                <div class="account-status">
                    <i class="fas ${user.telegram_id ? 'fa-check-circle' : 'fa-times-circle'}"></i>
                    ${user.telegram_id ? 'Подключен' : 'Не подключен'}
                </div>
            </div>
        </div>
        ${!user.telegram_id ? '<button class="btn btn-outline" style="padding: 8px 15px;" onclick="alert(\'Функция подключения Telegram будет доступна в ближайшее время\')">Подключить</button>' : ''}
    `;
    container.appendChild(telegramItem);
}

async function loadMyRecipesForProfile() {
    try {
        const recipes = await apiRequest('/user-recipes');
        const container = document.getElementById('my-recipes-container');

        if (!container) return;

        if (recipes.length === 0) {
            container.innerHTML = `
                <div style="text-align: center; padding: 30px; color: var(--text-light);">
                    <i class="fas fa-utensils" style="font-size: 3rem; margin-bottom: 15px;"></i>
                    <p>У вас пока нет своих рецептов</p>
                </div>
            `;
            return;
        }

        container.innerHTML = '';

        recipes.slice(0, 5).forEach(recipe => {
            const item = document.createElement('div');
            item.className = 'my-recipe-item';
            item.innerHTML = `
                <img src="${recipe.image}" alt="${recipe.title}" class="my-recipe-img" onerror="this.src='https://images.unsplash.com/photo-1546069901-ba9599a7e63c'">
                <div class="my-recipe-info">
                    <div class="my-recipe-title">${recipe.title}</div>
                    <div class="my-recipe-meta">
                        <span><i class="far fa-clock"></i> ${recipe.time}</span>
                        <span><i class="fas fa-fire"></i> ${recipe.calories}</span>
                    </div>
                </div>
                <div class="my-recipe-actions">
                    <button class="my-recipe-btn edit" onclick="window.editRecipe(${recipe.id})">
                        <i class="fas fa-edit"></i>
                    </button>
                    <button class="my-recipe-btn delete" onclick="window.deleteRecipeHandler(${recipe.id})">
                        <i class="fas fa-trash"></i>
                    </button>
                </div>
            `;
            container.appendChild(item);
        });

        if (recipes.length > 5) {
            const showMore = document.createElement('div');
            showMore.style.textAlign = 'center';
            showMore.style.marginTop = '15px';
            showMore.innerHTML = '<button class="btn btn-outline" onclick="window.location.href=\'/#my-recipes\'">Показать все</button>';
            container.appendChild(showMore);
        }

    } catch (error) {
        console.error('❌ Ошибка загрузки моих рецептов:', error);
    }
}

async function saveProfileChanges(e) {
    e.preventDefault();

    const saveBtn = document.getElementById('save-profile-btn');
    if (!saveBtn) return;

    const originalText = saveBtn.innerHTML;
    saveBtn.innerHTML = '<div class="loading" style="width: 20px; height: 20px; margin: 0;"></div>';
    saveBtn.disabled = true;

    try {
        const username = document.getElementById('edit-username')?.value.trim();
        const avatar = document.getElementById('edit-avatar')?.value.trim();

        const updateData = {};
        if (username) updateData.username = username;
        if (avatar) updateData.avatar = avatar;

        const result = await apiRequest('/profile', 'PUT', updateData);

        if (result.success) {
            showNotification('Профиль обновлен', 'check-circle');
            await checkAuth(true);
            if (window.location.pathname === '/profile') {
                await loadProfile();
            }
        }
    } catch (error) {
        console.error('❌ Ошибка обновления профиля:', error);
        showNotification('Ошибка обновления профиля', 'exclamation-triangle');
    } finally {
        saveBtn.innerHTML = originalText;
        saveBtn.disabled = false;
    }
}

// ========== ФУНКЦИИ ДЛЯ НАВИГАЦИИ ==========

function switchTab(tabId) {
    console.log(`🔄 Переключение на вкладку: ${tabId}`);

    const navTabs = document.querySelectorAll('.nav-tab');
    navTabs.forEach(tab => {
        tab.classList.remove('active');
    });

    const targetTab = document.querySelector(`.nav-tab[data-tab="${tabId}"]`);
    if (targetTab) targetTab.classList.add('active');

    const tabContents = document.querySelectorAll('.tab-content');
    tabContents.forEach(tab => {
        tab.classList.remove('active');
    });

    const targetContent = document.getElementById(tabId);
    if (targetContent) targetContent.classList.add('active');

    if (tabId === 'recipes') {
        renderAllRecipes();
    } else if (tabId === 'favorites') {
        renderFavorites();
    } else if (tabId === 'my-recipes') {
        renderMyRecipes();
    } else if (tabId === 'photo-search') {
        resetPhotoSearch();
    }
}

// ========== ФУНКЦИИ ДЛЯ КАРТОЧЕК ==========

function attachRecipeCardHandlers(containerId = null) {
    const cards = containerId
        ? document.querySelectorAll(`#${containerId} .recipe-card`)
        : document.querySelectorAll('.recipe-card');

    cards.forEach(card => {
        card.onclick = null;

        card.onclick = async function(e) {
            if (e.target.closest('.favorite-btn') ||
                e.target.closest('.match-badge') ||
                e.target.closest('.user-recipe-badge') ||
                e.target.closest('.like-btn')) {
                return;
            }

            const now = Date.now();
            if (now - lastCardClickTime < 600) {
                return;
            }
            lastCardClickTime = now;

            e.preventDefault();
            e.stopPropagation();

            try {
                const recipeDataStr = this.dataset.recipeData;
                if (recipeDataStr) {
                    const recipe = JSON.parse(recipeDataStr);
                    await openRecipeModal(recipe);
                }
            } catch (error) {
                console.error('❌ Error opening recipe modal:', error);
            }
        };

        const favoriteBtn = card.querySelector('.favorite-btn');
        if (favoriteBtn) {
            favoriteBtn.onclick = null;

            favoriteBtn.onclick = async function(e) {
                e.preventDefault();
                e.stopPropagation();

                const recipeId = parseInt(this.dataset.recipeId);
                if (recipeId) {
                    await toggleFavorite(recipeId);
                }
            };
        }
    });
}

// ========== ФУНКЦИИ ДЛЯ УВЕДОМЛЕНИЙ ==========

function showNotification(message, icon = 'check-circle') {
    const existingNotifications = document.querySelectorAll('.notification');
    existingNotifications.forEach(n => n.remove());

    const notification = document.createElement('div');
    notification.className = 'notification';
    notification.innerHTML = `
        <i class="fas fa-${icon}"></i>
        <span>${message}</span>
    `;

    document.body.appendChild(notification);

    setTimeout(() => {
        notification.style.animation = 'slideUp 0.5s ease';
        setTimeout(() => {
            if (notification.parentNode) {
                notification.remove();
            }
        }, 500);
    }, 3500);
}

// ========== ФУНКЦИИ ДЛЯ КАМЕРЫ ==========

let cameraStream = null;
let isCameraOpen = false;

async function initCamera() {
    const cameraContainer = document.getElementById('camera-container');
    const video = document.getElementById('camera-video');
    const openCameraBtn = document.getElementById('open-camera-btn');
    const closeCameraBtn = document.getElementById('close-camera-btn');
    const captureBtn = document.getElementById('capture-btn');
    const canvas = document.getElementById('photo-canvas');
    const uploadArea = document.getElementById('upload-area');
    const uploadProgress = document.getElementById('upload-progress');
    const progressBar = document.getElementById('upload-progress-bar');

    if (!video || !cameraContainer) return;

    if (openCameraBtn) {
        openCameraBtn.onclick = async function() {
            try {
                uploadArea.style.display = 'none';
                cameraContainer.style.display = 'block';

                cameraStream = await navigator.mediaDevices.getUserMedia({
                    video: {
                        facingMode: 'environment',
                        width: { ideal: 1280 },
                        height: { ideal: 720 }
                    },
                    audio: false
                });

                video.srcObject = cameraStream;
                isCameraOpen = true;

                console.log('✅ Камера открыта');
            } catch (error) {
                console.error('❌ Ошибка доступа к камере:', error);
                showNotification('Не удалось получить доступ к камере', 'exclamation-triangle');
                uploadArea.style.display = 'block';
                cameraContainer.style.display = 'none';
            }
        };
    }

    if (closeCameraBtn) {
        closeCameraBtn.onclick = function() {
            if (cameraStream) {
                cameraStream.getTracks().forEach(track => track.stop());
                cameraStream = null;
            }
            video.srcObject = null;
            cameraContainer.style.display = 'none';
            uploadArea.style.display = 'block';
            isCameraOpen = false;
        };
    }

    if (captureBtn) {
        captureBtn.onclick = function() {
            if (!video.videoWidth) return;

            canvas.width = video.videoWidth;
            canvas.height = video.videoHeight;

            const ctx = canvas.getContext('2d');
            ctx.translate(canvas.width, 0);
            ctx.scale(-1, 1);
            ctx.drawImage(video, 0, 0, canvas.width, canvas.height);
            ctx.setTransform(1, 0, 0, 1, 0, 0);

            canvas.toBlob(async (blob) => {
                const file = new File([blob], 'camera_photo.jpg', { type: 'image/jpeg' });

                if (cameraStream) {
                    cameraStream.getTracks().forEach(track => track.stop());
                    cameraStream = null;
                }
                video.srcObject = null;
                cameraContainer.style.display = 'none';
                uploadArea.style.display = 'block';
                isCameraOpen = false;

                await realPhotoSearch(file);
            }, 'image/jpeg', 0.9);
        };
    }
}

// ========== ФУНКЦИИ ДЛЯ ФОРМЫ СОЗДАНИЯ РЕЦЕПТА ==========

function initRecipeForm() {
    const recipeForm = document.getElementById('recipe-form');
    if (!recipeForm) return;

    const newForm = recipeForm.cloneNode(false);
    recipeForm.parentNode.replaceChild(newForm, recipeForm);

    newForm.innerHTML = recipeForm.innerHTML;

    newForm.onsubmit = async function(e) {
        e.preventDefault();

        const saveBtn = this.querySelector('.save-btn');
        if (!saveBtn) return;

        const originalText = saveBtn.innerHTML;
        saveBtn.innerHTML = '<div class="loading" style="width: 20px; height: 20px; margin: 0;"></div>';
        saveBtn.disabled = true;

        try {
            const title = document.getElementById('recipe-title')?.value.trim();
            const image = document.getElementById('recipe-image')?.value.trim() || 'https://images.unsplash.com/photo-1546069901-ba9599a7e63c';
            const time = document.getElementById('recipe-time')?.value.trim();
            const difficulty = document.getElementById('recipe-difficulty')?.value;
            const calories = document.getElementById('recipe-calories')?.value.trim();
            const servings = document.getElementById('recipe-servings')?.value.trim();

            if (!title || !time || !difficulty || !calories || !servings) {
                showNotification('Заполните все обязательные поля', 'exclamation-triangle');
                return;
            }

            const ingredients = [];
            const ingredientPromises = [];

            document.querySelectorAll('.ingredient-row').forEach(row => {
                const select = row.querySelector('.ingredient-select');
                const input = row.querySelector('.ingredient-name-input');
                const amount = row.querySelector('.ingredient-amount-input')?.value.trim();

                let name = '';
                if (select && select.style.display !== 'none') {
                    name = select.value.trim();
                } else if (input) {
                    name = input.value.trim();
                }

                if (name && amount) {
                    ingredients.push({ name, amount });
                    if (input && input.style.display !== 'none') {
                        ingredientPromises.push(saveUserIngredient(name));
                    }
                }
            });

            await Promise.all(ingredientPromises);

            if (ingredients.length === 0) {
                showNotification('Добавьте хотя бы один ингредиент', 'exclamation-triangle');
                return;
            }

            const instructions = [];
            document.querySelectorAll('.step-row').forEach(row => {
                const step = row.querySelector('.step-input')?.value.trim();
                if (step) {
                    instructions.push(step);
                }
            });

            if (instructions.length === 0) {
                showNotification('Добавьте хотя бы один шаг приготовления', 'exclamation-triangle');
                return;
            }

            const recipeData = {
                title,
                image,
                time,
                difficulty,
                calories,
                servings,
                ingredients,
                instructions
            };

            const editId = this.dataset.editId;
            if (editId) {
                recipeData.id = parseInt(editId);
            }

            const result = await saveUserRecipe(recipeData);

            if (result && result.success) {
                await renderAllRecipes();
                await renderMyRecipes();
                switchTab('my-recipes');
                cancelCreate();
            }
        } catch (error) {
            console.error('❌ Error saving recipe:', error);
            showNotification('Ошибка при сохранении рецепта', 'exclamation-triangle');
        } finally {
            saveBtn.innerHTML = originalText;
            saveBtn.disabled = false;
        }
    };
}

function initPhotoSearch() {
    const uploadArea = document.getElementById('upload-area');
    const fileInput = document.getElementById('file-input');

    if (!uploadArea || !fileInput) return;

    const newUploadArea = uploadArea.cloneNode(false);
    uploadArea.parentNode.replaceChild(newUploadArea, uploadArea);

    const newFileInput = fileInput.cloneNode(false);
    fileInput.parentNode.replaceChild(newFileInput, fileInput);

    newUploadArea.innerHTML = `
        <i class="fas fa-camera upload-icon"></i>
        <div class="upload-text">Загрузите фото продуктов</div>
        <div class="upload-subtext">Перетащите сюда фото или нажмите для выбора файла</div>
    `;

    newUploadArea.onclick = () => {
        newFileInput.click();
    };

    newFileInput.onchange = function(e) {
        if (e.target.files.length > 0) {
            const file = e.target.files[0];

            if (file.size > 10 * 1024 * 1024) {
                showNotification('Файл слишком большой (макс 10MB)', 'exclamation-triangle');
                return;
            }

            if (!file.type.match('image.*')) {
                showNotification('Пожалуйста, выберите изображение', 'exclamation-triangle');
                return;
            }

            realPhotoSearch(file);
        }
    };

    newUploadArea.ondragover = function(e) {
        e.preventDefault();
        this.style.borderColor = 'var(--accent-teal)';
    };

    newUploadArea.ondragleave = function(e) {
        e.preventDefault();
        this.style.borderColor = 'var(--primary-green)';
    };

    newUploadArea.ondrop = function(e) {
        e.preventDefault();
        this.style.borderColor = 'var(--primary-green)';

        if (e.dataTransfer.files.length > 0) {
            const file = e.dataTransfer.files[0];

            if (file.size > 10 * 1024 * 1024) {
                showNotification('Файл слишком большой (макс 10MB)', 'exclamation-triangle');
                return;
            }

            if (!file.type.match('image.*')) {
                showNotification('Пожалуйста, перетащите изображение', 'exclamation-triangle');
                return;
            }

            const dataTransfer = new DataTransfer();
            dataTransfer.items.add(file);
            newFileInput.files = dataTransfer.files;

            realPhotoSearch(file);
        }
    };
}

async function checkModelStatus() {
    try {
        const response = await apiRequest('/model-status');
        return response;
    } catch (error) {
        return { loaded: false };
    }
}

async function checkDbStatus() {
    try {
        const response = await apiRequest('/db-status');
        return response;
    } catch (error) {
        return { connected: false };
    }
}

// ========== ФИКСЫ ДЛЯ КНОПОК ==========

function fixButtons() {
    console.log('🔧 Применение фиксов для кнопок...');

    const logoutBtn = document.getElementById('logout-btn');
    if (logoutBtn) {
        const newLogoutBtn = logoutBtn.cloneNode(true);
        if (logoutBtn.parentNode) {
            logoutBtn.parentNode.replaceChild(newLogoutBtn, logoutBtn);
        }

        newLogoutBtn.onclick = function(e) {
            e.preventDefault();
            e.stopPropagation();
            console.log('🚪 Прямой выход');
            logout();
            return false;
        };

        newLogoutBtn.style.pointerEvents = 'auto';
        newLogoutBtn.style.cursor = 'pointer';
        newLogoutBtn.style.zIndex = '999999';
    }

    const profileLink = document.getElementById('profile-link');
    if (profileLink) {
        const newProfileLink = profileLink.cloneNode(true);
        if (profileLink.parentNode) {
            profileLink.parentNode.replaceChild(newProfileLink, profileLink);
        }

        newProfileLink.onclick = function(e) {
            e.preventDefault();
            e.stopPropagation();
            console.log('👤 Переход в профиль');
            window.location.href = '/profile';
            return false;
        };

        newProfileLink.style.pointerEvents = 'auto';
        newProfileLink.style.cursor = 'pointer';
        newProfileLink.style.zIndex = '999999';
    }

    const addRecipeBtn = document.getElementById('add-recipe-btn');
    if (addRecipeBtn) {
        const newAddBtn = addRecipeBtn.cloneNode(true);
        if (addRecipeBtn.parentNode) {
            addRecipeBtn.parentNode.replaceChild(newAddBtn, addRecipeBtn);
        }

        newAddBtn.onclick = function(e) {
            e.preventDefault();
            e.stopPropagation();
            console.log('📝 Создание рецепта');
            openCreateRecipeForm();
            return false;
        };
    }
}

// ========== ИНИЦИАЛИЗАЦИЯ ПРИЛОЖЕНИЯ ==========

async function initApp() {
    console.log('🚀 Инициализация приложения...');

    const currentPath = window.location.pathname;

    // Несколько попыток проверки авторизации
    let authData = null;
    for (let i = 0; i < 3; i++) {
        authData = await checkAuth(true);
        if (authData) break;
        await new Promise(resolve => setTimeout(resolve, 500));
    }

    if (authData) {
        updateAuthUI(authData);
    } else {
        const savedAuth = restoreAuthFromStorage();
        if (savedAuth.authenticated) {
            updateAuthUI(savedAuth);
            setTimeout(async () => {
                const freshAuth = await checkAuth(true);
                if (freshAuth) {
                    updateAuthUI(freshAuth);
                }
            }, 1000);
        }
    }

    if ((currentPath === '/login' || currentPath === '/register')) {
        if (authData && authData.authenticated) {
            console.log('👤 Пользователь уже авторизован, перенаправление на главную');
            window.location.href = '/';
            return;
        }
    }

    if (currentPath === '/profile') {
        console.log('📄 Загрузка страницы профиля');
        if (!authData || !authData.authenticated) {
            window.location.href = '/login';
            return;
        }
        loadProfile();

        const profileForm = document.getElementById('profile-form');
        if (profileForm) {
            profileForm.onsubmit = saveProfileChanges;
        }
        return;
    }

    if (document.getElementById('recipes-list')) {
        console.log('📚 Загрузка рецептов...');

        await renderAllRecipes();
        await renderFavorites();
        await renderMyRecipes();

        attachRecipeCardHandlers();

        if (document.getElementById('ingredients-container')) {
            addIngredient();
            addStep();
        }

        initPhotoSearch();
        initCamera();
        initRecipeForm();

        setTimeout(fixButtons, 500);
        setTimeout(fixButtons, 1000);
        setTimeout(fixButtons, 2000);
    }


    setInterval(async () => {
        const authData = await checkAuth(true);
        if (authData) {
            updateAuthUI(authData);
        }
    }, 5000);

    console.log('✅ Инициализация завершена');
}

if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initApp);
} else {
    initApp();
}

// ========== ЭКСПОРТ В ГЛОБАЛЬНУЮ ОБЛАСТЬ ВИДИМОСТИ ==========

window.checkAuth = checkAuth;
window.updateAuthUI = updateAuthUI;
window.logout = logout;
window.addIngredient = addIngredient;
window.removeIngredient = removeIngredient;
window.toggleIngredientMode = toggleIngredientMode;
window.addStep = addStep;
window.removeStep = removeStep;
window.cancelCreate = cancelCreate;
window.openCreateRecipeForm = openCreateRecipeForm;
window.editRecipe = editRecipe;
window.deleteRecipeHandler = deleteRecipeHandler;
window.closeRecipeModal = closeRecipeModal;
window.switchTab = switchTab;
window.resetPhotoSearch = resetPhotoSearch;
window.realPhotoSearch = realPhotoSearch;
window.renderAllRecipes = renderAllRecipes;
window.renderFavorites = renderFavorites;
window.renderMyRecipes = renderMyRecipes;
window.loadProfile = loadProfile;
window.saveProfileChanges = saveProfileChanges;
window.showNotification = showNotification;
window.apiRequest = apiRequest;
window.toggleFavorite = toggleFavorite;
window.attachRecipeCardHandlers = attachRecipeCardHandlers;

console.log('✅ Все функции экспортированы в глобальную область видимости');