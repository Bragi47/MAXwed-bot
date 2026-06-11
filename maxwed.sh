#!/usr/bin/env bash
# MAXwed Bot Manager — интерактивное меню для управления ботом

set -euo pipefail

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

log_info()  { echo -e "${GREEN}[INFO]${NC} $1"; }
log_warn()  { echo -e "${YELLOW}[WARN]${NC} $1"; }
log_error() { echo -e "${RED}[ERR]${NC} $1"; }

get_python() {
    for cmd in python3 python; do
        if command -v "$cmd" &>/dev/null; then
            echo "$cmd"
            return 0
        fi
    done
    log_error "Python не найден. Установи: apt install python3"
    exit 1
}

check_deps() {
    local missing=0

    for cmd in git docker; do
        if ! command -v "$cmd" &>/dev/null; then
            log_error "$cmd не найден."
            missing=1
        fi
    done
    if ! docker compose version &>/dev/null; then
        log_error "docker compose не найден. Установи Docker."
        missing=1
    fi
    get_python &>/dev/null || missing=1
    return $missing
}

is_setup_done() {
    test -f key.bin
}

banner() {
    clear
    echo -e "${CYAN}"
    echo "+----------------------------------------+"
    echo "|        MAXwed Bot Manager              |"
    echo "+----------------------------------------+"
    echo -e "${NC}"
}

menu() {
    echo " 1)  Полная установка (первичная настройка)"
    echo " 2)  Запустить бота"
    echo " 3)  Остановить бота"
    echo " 4)  Перезапустить бота"
    echo " 5)  Показать логи (Ctrl+C для выхода)"
    echo " 6)  Статус"
    echo " 7)  Обновить (git pull + rebuild)"
    echo " 8)  Сменить токен"
    echo " 9)  Настроить администраторов"
    echo " 10) Полностью удалить"
    echo " 11) Выход"
    echo ""
}

action_install() {
    log_info "Запуск мастера настройки..."
    PYTHONIOENCODING=utf-8 $(get_python) setup_encrypt.py
    log_info "Сборка и запуск контейнера..."
    docker compose up -d --build
    log_info "Готово! Бот запущен."
}

action_start() {
    touch .env
    docker compose up -d
    log_info "Бот запущен."
}

action_stop() {
    docker compose down
    log_info "Бот остановлен."
}

action_restart() {
    docker compose restart
    log_info "Бот перезапущен."
}

action_logs() {
    docker compose logs -f
}

action_status() {
    docker compose ps
}

action_update() {
    log_info "Загружаю обновления из GitHub..."
    git pull
    log_info "Пересобираю и запускаю..."
    docker compose up -d --build
    log_info "Бот обновлён и запущен."
}

action_reset_token() {
    log_info "Перезапись токена..."
    PYTHONIOENCODING=utf-8 $(get_python) setup_encrypt.py
    log_info "Перезапускаю бота..."
    docker compose restart
    log_info "Токен обновлён."
}

action_setup_admin() {
    log_info "Запуск мастера настройки администраторов..."
    PYTHONIOENCODING=utf-8 $(get_python) setup_encrypt.py --admin
    log_info "Готово. Перезапусти бота, если он запущен."
}

action_uninstall() {
    echo ""
    log_warn "Это полностью удалит бота и все данные!"
    read -p "Уверен? Напиши 'yes': " confirm
    if [ "$confirm" != "yes" ]; then
        log_info "Отменено."
        return
    fi
    log_info "Останавливаю контейнер..."
    docker compose down -v
    log_info "Удаляю проект..."
    cd ..
    rm -rf MAXwed-bot
    log_info "Готово! Проект полностью удалён."
    exit 0
}

main() {
    if ! check_deps; then
        exit 1
    fi

    if ! is_setup_done; then
        echo -e "${CYAN}"
        echo "+----------------------------------------+"
        echo "|        MAXwed Bot — первичная          |"
        echo "|        настройка                       |"
        echo "+----------------------------------------+"
        echo -e "${NC}"
        action_install
        echo ""
        log_info "Готово! Бот запущен и работает."
        exit 0
    fi

    while true; do
        banner
        menu
        read -p "Выбери действие (1-10): " choice
        echo ""
        case "$choice" in
            1)  action_install ;;
            2)  action_start ;;
            3)  action_stop ;;
            4)  action_restart ;;
            5)  action_logs ;;
            6)  action_status ;;
            7)  action_update ;;
            8)  action_reset_token ;;
            9)  action_setup_admin ;;
            10) action_uninstall ;;
            11) log_info "Пока!"; exit 0 ;;
            *)  log_error "Неверный пункт. Выбери 1-11." ;;
        esac
        echo ""
        read -p "Нажми Enter, чтобы продолжить..."
    done
}

main "$@"
