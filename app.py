# app.py — Калькулятор кадастровой стоимости
# Загружает данные с Яндекс.Диска: https://disk.yandex.ru/d/DB_EoNBlaIoLMg
# Исправлена ошибка KeyError: 'Категория земель' → теперь работает с 'Категория земли'

import streamlit as st
import pandas as pd
import bcrypt
import datetime
import io
import requests
from io import StringIO
import os

# --- Настройки ---
YANDEX_PUBLIC_KEY = "DB_EoNBlaIoLMg"  # ← ваш ID из ссылки
USERS_PATH = "users.csv"
LOG_PATH = "requests_log.csv"

# --- Загрузка данных с Яндекс.Диска ---
@st.cache_data(ttl=3600)  # Кэш на 1 час
def load_data():
    try:
        # Получаем прямую ссылку на скачивание
        download_url = f"https://cloud-api.yandex.net/v1/disk/public/resources/download?public_key=https://disk.yandex.ru/d/{YANDEX_PUBLIC_KEY}"
        response = requests.get(download_url)
        response.raise_for_status()
        direct_link = response.json()["href"]

        # Скачиваем CSV
        csv_response = requests.get(direct_link)
        csv_response.raise_for_status()

        # Читаем в DataFrame
        df = pd.read_csv(
            StringIO(csv_response.text),
            sep=";",  # Разделитель — точка с запятой
            on_bad_lines="skip",
            dtype={"Код КЛАДР": str, "Кадастровый квартал": str}
        )

        # 🔽 Очищаем имена столбцов (удаляем пробелы, переносы)
        df.columns = df.columns.str.strip().str.replace("\n", "", regex=False).str.replace("\r", "", regex=False)

        # 🔽 Принудительное переименование — ключевое исправление
        column_mapping = {
            'Категория земли': 'Категория земель',  # ← Правильное исправление!
            'Категория земель ': 'Категория земель',
            'категория земель': 'Категория земель',
            'Категория_земель': 'Категория земель',
            'Категория Земель': 'Категория земель',
            '  Категория земель  ': 'Категория земель',
            'Наличие центрального водоснабжения ': 'Наличие центрального водоснабжения',
            'Наличие центрального газоснабжения ': 'Наличие центрального газоснабжения',
            'Наличие центральной канализации ': 'Наличие центральной канализации',
            'Наличие центрального теплоснабжения ': 'Наличие центрального теплоснабжения',
            'Наличие центрального электроснабжения ': 'Наличие центрального электроснабжения',
            'Удельный показатель кадастровой стоимости ': 'Удельный показатель кадастровой стоимости',
            'Адрес по КЛАДР ': 'Адрес по КЛАДР',
            'Кадастровый квартал ': 'Кадастровый квартал',
        }
        df = df.rename(columns=column_mapping)

        return df

    except Exception as e:
        st.error(f"❌ Не удалось загрузить данные: {e}")
        st.stop()

# --- Загрузка пользователей ---
@st.cache_data
def load_users():
    if not os.path.exists(USERS_PATH):
        st.error("Файл пользователей не найден: users.csv")
        st.stop()
    return pd.read_csv(USERS_PATH)

def log_request(username, filters, count):
    log_entry = {
        "timestamp": datetime.datetime.now().isoformat(),
        "username": username,
        "filters": str(filters),
        "result_count": count,
        "ip": st.context.request.remote_addr if st.context.request else "unknown"
    }
    log_df = pd.DataFrame([log_entry])
    header = not os.path.exists(LOG_PATH)
    log_df.to_csv(LOG_PATH, mode="a", header=header, index=False)

# --- Авторизация ---
def login():
    st.title("🔐 Вход в калькулятор кадастровой стоимости")

    username = st.text_input("Логин")
    password = st.text_input("Пароль", type="password")

    col1, col2 = st.columns([1, 2])
    
    if col1.button("Войти", key="login_btn", help="Нажмите один раз"):
        with st.spinner("Вход..."):
            users = load_users()
            user = users[users["username"] == username]
            if len(user) == 1:
                try:
                    hashed = user["hashed_password"].iloc[0].encode('utf-8')
                    if bcrypt.checkpw(password.encode('utf-8'), hashed):
                        st.session_state["logged_in"] = True
                        st.session_state["username"] = username
                        st.session_state["is_admin"] = user["is_admin"].iloc[0]
                        st.rerun()
                    else:
                        st.error("Неверный пароль")
                except Exception:
                    st.error("Ошибка проверки пароля")
            else:
                st.error("Пользователь не найден")

    with col2:
        st.markdown("### 🔔 Запрос доступа")
        with st.expander("Отправить запрос на доступ"):
            new_user = st.text_input("Желаемый логин")
            email = st.text_input("Email")
            phone = st.text_input("Телефон")
            if st.button("Отправить запрос", key="req_btn"):
                if new_user and email:
                    log_pending_request(new_user, email, phone)
                    st.success("Запрос отправлен администратору.")
                else:
                    st.error("Заполните логин и email.")

def log_pending_request(username, email, phone):
    entry = {
        "timestamp": datetime.datetime.now().isoformat(),
        "username": username,
        "email": email,
        "phone": phone,
        "status": "ожидает"
    }
    df = pd.DataFrame([entry])
    header = not os.path.exists("pending_requests.csv")
    df.to_csv("pending_requests.csv", mode="a", header=header, index=False)

# --- Основное приложение ---
def main_app():
    df = load_data()
    st.title("📐 Калькулятор кадастровой стоимости")

    # --- Фильтры ---
    col1, col2 = st.columns(2)

    with col1:
        category = st.selectbox(
            "Категория земель",
            ["Все"] + sorted(df["Категория земель"].dropna().unique().tolist()),
            key="category"
        )
        water = st.checkbox("Центральное водоснабжение", value=None, key="water")
        gas = st.checkbox("Центральное газоснабжение", value=None, key="gas")
        sewer = st.checkbox("Центральная канализация", value=None, key="sewer")

    with col2:
        heat = st.checkbox("Центральное теплоснабжение", value=None, key="heat")
        electricity = st.checkbox("Центральное электроснабжение", value=None, key="electricity")

    # --- Выбор территории ---
    territory_mode = st.radio("Выбор территории", ["По кадастровому кварталу", "По адресу"], key="territory_mode")

    filter_kq = filter_addr = None

    if territory_mode == "По кадастровому кварталу":
        filter_kq = st.text_input("Кадастровый квартал (например, 78:12:0305002)", key="kq_input")
    else:
        addresses = sorted(df["Адрес по КЛАДР"].dropna().astype(str).tolist())
        search = st.text_input("Введите часть адреса для поиска...", key="addr_search")

        if search:
            matches = [addr for addr in addresses if search.lower() in addr.lower()]
            if len(matches) == 0:
                st.warning("Адрес не найден.")
            elif len(matches) > 50:
                st.info("Найдено более 50 совпадений. Уточните запрос.")
            else:
                filter_addr = st.selectbox("Выберите адрес:", [""] + matches, key="addr_select")

    # --- Фильтрация ---
    filtered = df.copy()

    if category != "Все":
        filtered = filtered[filtered["Категория земель"] == category]

    for col, value in [
        ("Наличие центрального водоснабжения", water),
        ("Наличие центрального газоснабжения", gas),
        ("Наличие центральной канализации", sewer),
        ("Наличие центрального теплоснабжения", heat),
        ("Наличие центрального электроснабжения", electricity),
    ]:
        if value is not None:
            filtered = filtered[filtered[col] == value]

    if filter_kq:
        filtered = filtered[filtered["Кадастровый квартал"].str.contains(filter_kq, na=False, case=True)]
    if filter_addr:
        filtered = filtered[filtered["Адрес по КЛАДР"] == filter_addr]

    # --- Результат ---
    if len(filtered) == 0:
        st.warning("❌ По вашим параметрам участки не найдены.")
    else:
        col_name = "Удельный показатель кадастровой стоимости"
        mean_val = filtered[col_name].mean()
        min_val = filtered[col_name].min()
        max_val = filtered[col_name].max()

        st.success(f"📊 **Среднее значение:** {mean_val:,.2f}")
        st.info(f"📉 **Минимум:** {min_val:,.2f} | **Максимум:** {max_val:,.2f}")

        # --- Экспорт в Excel ---
        if st.button("📥 Скачать результаты в Excel", key="export_btn"):
            with st.spinner("Формируем Excel..."):
                buffer = io.BytesIO()
                with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
                    filtered.to_excel(writer, index=False, sheet_name="Результаты")
                buffer.seek(0)
                filename = f"кадастр_{st.session_state['username']}_{datetime.datetime.now().strftime('%Y%m%d_%H%M')}.xlsx"
                st.download_button(
                    label="✅ Нажмите, чтобы скачать",
                    data=buffer,
                    file_name=filename,
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    key="dl_btn"
                )

        if st.checkbox("Показать найденные участки", key="show_data"):
            st.dataframe(
                filtered[[
                    "Номер", "Кадастровый квартал", "Адрес по КЛАДР",
                    "Вид использования участка по документу", col_name
                ]],
                use_container_width=True
            )

        log_request(st.session_state["username"], {
            "category": category,
            "water": water,
            "gas": gas,
            "sewer": sewer,
            "heat": heat,
            "electricity": electricity,
            "kq": filter_kq,
            "address": filter_addr
        }, len(filtered))

    # --- Админ-панель ---
    if st.session_state.get("is_admin"):
        st.divider()
        st.subheader("🛠️ Админ-панель")

        # Заявки на доступ
        st.markdown("### 📥 Заявки на доступ")
        if os.path.exists("pending_requests.csv"):
            pending_df = pd.read_csv("pending_requests.csv")
            st.dataframe(pending_df, use_container_width=True)
        else:
            st.info("Пока нет заявок на доступ.")

        # Лог запросов
        st.markdown("### 📋 История запросов")
        if st.button("Обновить логи", key="refresh_logs"):
            if os.path.exists(LOG_PATH):
                log_df = pd.read_csv(LOG_PATH)
                st.dataframe(log_df, use_container_width=True)
            else:
                st.info("Логи пока пусты.")

# --- Главный цикл ---
if "logged_in" not in st.session_state:
    st.sidebar.title("🔐 Авторизация")
    login()
else:
    st.sidebar.success(f"Привет, {st.session_state['username']}!")
    if st.sidebar.button("Выйти", key="logout_btn"):
        st.session_state.clear()
        st.rerun()
    main_app()
