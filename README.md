# SINANA Sales

Самостоятельное приложение для руководителя и торговых представителей SINANA. Проект не использует код, базу данных, пользователей или настройки WMS.

## Локальный запуск

1. Создайте виртуальное окружение и установите `requirements.txt`.
2. Установите переменные `SINANA_SECRET_KEY`, `SINANA_ADMIN_LOGIN`, `SINANA_ADMIN_PASSWORD`.
3. Выполните `flask --app run.py init-admin`.
4. Запустите `flask --app run.py run`.

Для сервера база задаётся отдельной переменной `SINANA_DATABASE_URL`; рекомендуется отдельная PostgreSQL-база и отдельный домен.
