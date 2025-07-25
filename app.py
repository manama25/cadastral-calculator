import streamlit as st
import pandas as pd
import bcrypt
import datetime
import io
import os

# --- Настройки ---
DATA_PATH = "data/land_data.csv"
USERS_PATH = "users.csv"
LOG_PATH = "requests_log.csv"
PENDING_PATH = "pending_requests.csv"  # Заявки на доступ

# --- Загрузка данных ---
@st.cache_data
def load_data():
    try:
        df = pd.read_csv(DATA_PATH, sep=";", on_bad_lines="skip", dtype={"Код КЛАДР": str, "Кадастровый квартал": str})
        return df
    except Exception as e:
        st.error(f"Ошибка загрузки данных: {e}")
        st.stop()

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

def log_pending_request(username, email, phone):
    entry = {
        "timestamp": datetime.datetime.now().isoformat(),
        "username": username,
        "email": email,
        "phone": phone,
        "status": "ожидает"
    }
    df = pd.DataFrame([entry])
    header = not os.path.exists(PENDING_PATH)
    df.to_csv(PENDING_PATH, mode="a", header=header, index=False)

# --- Авторизация ---
def login():
    st.title("🔐 Вход в калькулятор кадастровой стоимости")

    username = st.text_input("Логин")
    password = st.text_input("Пароль", type="password")

    col1, col2 = st.columns([1, 2])
    if col1.button("Войти"):
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
            if st.button("Отправить запрос"):
                if new_user and email:
                    log_pending_request(new_user, email, phone)
                    st.success("Запрос отправлен администратору.")
                else:
                    st.error("Заполните логин и email.")

# --- Основное приложение ---
def main_app():
    df = load_data()
    st.title("📐 Калькулятор кадастровой стоимости")

    # --- Фильтры ---
    col1, col2 = st.columns(2)

    with col1:
        category = st.selectbox(
            "Категория земель",
            ["Все"] + sorted(df["Категория земель"].dropna().unique().tolist())
        )
        water = st.checkbox("Центральное водоснабжение", value=None, key="water")
        gas = st.checkbox("Центральное газоснабжение", value=None, key="gas")
        sewer = st.checkbox("Центральная канализация", value=None, key="sewer")

    with col2:
        heat = st.checkbox("Центральное теплоснабжение", value=None, key="heat")
        electricity = st.checkbox("Центральное электроснабжение", value=None, key="electricity")

    # --- Выбор территории ---
    territory_mode = st.radio("Выбор территории", ["По кадастровому кварталу", "По адресу"])

    filter_kq = filter_addr = None

    if territory_mode == "По кадастровому кварталу":
        filter_kq = st.text_input("Кадастровый квартал (например, 78:12:0305002)")
    else:
        addresses = sorted(df["Адрес по КЛАДР"].dropna().astype(str).tolist())
        search = st.text_input("Введите часть адреса для поиска...")

        if search:
            matches = [addr for addr in addresses if search.lower() in addr.lower()]
            if len(matches) == 0:
                st.warning("Адрес не найден.")
            elif len(matches) > 50:
                st.info("Найдено более 50 совпадений. Уточните запрос.")
            else:
                filter_addr = st.radio("Выберите адрес:", matches)

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

        # --- Кнопка экспорта в Excel ---
        if st.button("📥 Скачать результаты в Excel"):
            buffer = io.BytesIO()
            with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
                filtered.to_excel(writer, index=False, sheet_name="Результаты")
            buffer.seek(0)
            filename = f"кадастр_{st.session_state['username']}_{datetime.datetime.now().strftime('%Y%m%d_%H%M')}.xlsx"
            st.download_button(
                label="✅ Нажмите, чтобы скачать файл",
                data=buffer,
                file_name=filename,
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )

        if st.checkbox("Показать найденные участки"):
            st.dataframe(
                filtered[[
                    "Номер", "Кадастровый квартал", "Адрес по КЛАДР",
                    "Вид использования участка по документу", col_name
                ]],
                use_container_width=True
            )

        # Логируем запрос
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
        if os.path.exists(PENDING_PATH):
            pending_df = pd.read_csv(PENDING_PATH)
            st.dataframe(pending_df, use_container_width=True)
        else:
            st.info("Пока нет заявок на доступ.")

        # Лог запросов
        st.markdown("### 📋 История запросов")
        if st.button("Обновить логи"):
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
    if st.sidebar.button("Выйти"):
        st.session_state.clear()
        st.rerun()
    main_app()