import asyncio
import time
import logging
from aiogram import Bot, Dispatcher, types, Router
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext
from aiogram.filters import Command
import sqlite3

# Настройки
BOT_TOKEN = "5561216377:AAFdSv6VCHOQ_noIhLN4rJPZMh2G_sBwlI8"

bot = Bot(token=BOT_TOKEN)
router = Router()
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# Подключение к базе данных
def setup_database():
    conn = sqlite3.connect("tasks.db")
    cursor = conn.cursor()
    cursor.execute(
        """
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        telegram_id INTEGER UNIQUE,
        name TEXT,
        department TEXT,
        role TEXT
    )
    """
    )
    cursor.execute(
        """
    CREATE TABLE IF NOT EXISTS tasks (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        department TEXT,
        title TEXT,
        description TEXT,
        created_at TIMESTAMP,
        completed_at TIMESTAMP,
        status TEXT,
        created_by INTEGER
    )
    """
    )
    cursor.execute(
        """
    CREATE TABLE IF NOT EXISTS unauth_users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        telegram_id INTEGER UNIQUE,
        name TEXT,
        username TEXT
    )
    """
    )
    conn.commit()
    conn.close()


setup_database()


# Состояния FSM
class AddUserState(StatesGroup):
    waiting_for_user_id_or_username = State() # Новое состояние для ввода ID или username
    waiting_for_department = State()
    waiting_for_role = State()

class AddTaskState(StatesGroup):
    waiting_for_title = State()
    waiting_for_description = State()

class UpdateTaskState(StatesGroup):
    waiting_for_task_id = State()
    waiting_for_new_description = State()

@router.message(lambda message: message.text == "Обновить задачу")
async def handle_update_task(message: types.Message, state: FSMContext):
    await message.answer("Введите ID задачи, которую хотите обновить:")
    await state.set_state(UpdateTaskState.waiting_for_task_id)

@router.message(UpdateTaskState.waiting_for_task_id)
async def process_update_task_id(message: types.Message, state: FSMContext):
    task_id = message.text
    conn = sqlite3.connect("tasks.db")
    cursor = conn.cursor()
    cursor.execute("SELECT id FROM tasks WHERE id = ?", (task_id,))
    if cursor.fetchone() is None:
        await message.answer("Задача с таким ID не найдена.")
        conn.close()
        return

    await state.update_data(task_id=task_id)
    await message.answer("Введите новое описание задачи:")
    await state.set_state(UpdateTaskState.waiting_for_new_description)
    conn.close()

@router.message(UpdateTaskState.waiting_for_new_description)
async def process_new_description(message: types.Message, state: FSMContext):
    conn = sqlite3.connect("tasks.db")
    cursor = conn.cursor()
    data = await state.get_data()
    task_id = data["task_id"]
    new_description = message.text

    cursor.execute(
        "UPDATE tasks SET description = ? WHERE id = ?", (new_description, task_id)
    )
    conn.commit()
    cursor.close()
    conn.close()

    await state.clear()
    await message.answer("Описание задачи успешно обновлено!")

class DeleteTaskState(StatesGroup):
    waiting_for_task_id = State()

# Удаление задачи (общая команда)
@router.message(Command("delete_task"))
@router.message(lambda message: message.text == "Удалить задачу")
async def delete_task(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    conn = sqlite3.connect("tasks.db")
    cursor = conn.cursor()
    cursor.execute("SELECT role, department FROM users WHERE telegram_id = ?", (user_id,))
    user_data = cursor.fetchone()

    if not user_data:
        await message.answer("Вы не зарегистрированы в системе.")
        conn.close()
        return

    role, department = user_data
    if role == "admin":
        await message.answer("Введите ID задачи, которую хотите удалить:")
    else:
        await message.answer("Введите ID задачи, которую хотите удалить:")

    await state.set_state(DeleteTaskState.waiting_for_task_id)

@router.message(DeleteTaskState.waiting_for_task_id)
async def process_delete_task(message: types.Message, state: FSMContext):
    task_id = message.text.strip()
    user_id = message.from_user.id

    conn = sqlite3.connect("tasks.db")
    cursor = conn.cursor()
    cursor.execute("SELECT role, department FROM users WHERE telegram_id = ?", (user_id,))
    user_data = cursor.fetchone()

    if not user_data:
        await message.answer("Вы не зарегистрированы в системе.")
        conn.close()
        return

    role, department = user_data

    # Проверка для администратора
    if role == "admin":
        cursor.execute("DELETE FROM tasks WHERE id = ?", (task_id,))
        conn.commit()
        if cursor.rowcount > 0:
            await message.answer("Задача успешно удалена.")
        else:
            await message.answer("Задача с таким ID не найдена.")
    else:
        # Проверка для менеджера: только своего отдела и только задачи в процессе выполнения
        cursor.execute(
            "DELETE FROM tasks WHERE id = ? AND department = ? AND status = 'pending'",
            (task_id, department),
        )
        conn.commit()
        if cursor.rowcount > 0:
            await message.answer("Задача успешно удалена.")
        else:
            await message.answer("Задача с таким ID не найдена или вы не можете её удалить.")

    cursor.close()
    conn.close()
    await state.clear()

class CompleteTaskState(StatesGroup):
    waiting_for_task_id = State()


def manager_keyboard():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="Добавить задачу")],
            [KeyboardButton(text="Просмотреть задачи")],
            [KeyboardButton(text="Обновить задачу")],
            [KeyboardButton(text="Удалить задачу")],
        ],
        resize_keyboard=True,
        one_time_keyboard=False,
    )

def admin_keyboard():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="/add_user")],  # Добавить пользователя
            [KeyboardButton(text="/delete_user")],  # Удалить пользователя
            [KeyboardButton(text="/add_task")],  # Добавить задачу
            [KeyboardButton(text="/view_tasks")],  # Просмотреть задачи
            [KeyboardButton(text="/view_completed_tasks")],  # Просмотреть выполненные задачи
            [KeyboardButton(text="/complete_task")],  # Завершить задачу
            [KeyboardButton(text="/delete_task")],  # Удалить задачу
        ],
        resize_keyboard=True,
        one_time_keyboard=False,
    )


# Команда /start с проверкой пользователя
@router.message(Command("start"))
async def start_command(message: types.Message):
    user_id = message.from_user.id
    conn = sqlite3.connect("tasks.db")
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT role FROM users WHERE telegram_id = ?", (user_id,))
        user_data = cursor.fetchone()

        if user_data:
            role = user_data[0]
            if role == "admin":
                await message.answer("Добро пожаловать, администратор! Вы можете управлять задачами.", reply_markup=admin_keyboard())
            else:
                await message.answer("Добро пожаловать! Вы можете просматривать и создавать задачи в вашем отделе.", reply_markup=manager_keyboard()), 
        else:
            # Если пользователь не зарегистрирован
            await message.answer(
                "Вы не зарегистрированы в системе. Обратитесь к системному администратору."
            )
            # Добавление в таблицу неавторизованных, если еще не добавлен
            cursor.execute("SELECT telegram_id FROM unauth_users WHERE telegram_id = ?", (user_id,))
            if cursor.fetchone() is None:
                username = message.from_user.username or "Unknown"
                full_name = message.from_user.full_name or "Unknown"
                cursor.execute(
                    "INSERT INTO unauth_users (telegram_id, name, username) VALUES (?, ?, ?)",
                    (user_id, full_name, username)
                )
                conn.commit()
                logger.info(f"Неавторизованный пользователь {full_name} добавлен в базу данных.")
    except Exception as e:
        logger.error(f"Ошибка обработки команды /start: {e}")
    finally:
        cursor.close()
        conn.close()


# Команда для добавления пользователя
@router.message(Command("add_user"))
async def add_user_start(message: types.Message, state: FSMContext):
    conn = sqlite3.connect("tasks.db")
    cursor = conn.cursor()
    user_id = message.from_user.id
    cursor.execute("SELECT role FROM users WHERE telegram_id = ?", (user_id,))
    user_data = cursor.fetchone()

    if user_data[0] != "admin":
        await message.answer("Недоступная команда!")
        return

    # Начало процесса добавления пользователя
    await message.answer(
        "Введите Telegram ID или имя пользователя (username) для добавления:"
    )
    await state.set_state(AddUserState.waiting_for_user_id_or_username)


@router.message(AddUserState.waiting_for_user_id_or_username)
async def add_user_id_or_username(message: types.Message, state: FSMContext):
    input_value = message.text.strip()

    try:
        if input_value.isdigit():
            user_id = int(input_value)
        else:
            if  input_value.startswith("@"):  # Проверка на корректность username
                conn = sqlite3.connect("tasks.db")
                cursor = conn.cursor()
                cursor.execute("SELECT telegram_id FROM unauth_users WHERE username = ?", (input_value.lstrip("@"),))
                user_data = cursor.fetchone()
                conn.close()

                if user_data:
                    user_id = user_data[0]
                else:
                    await message.answer("Пользователь с таким username не найден в базе неавторизованных пользователей.")
                    return  # Если username, то оставляем ID пустым

    except ValueError:
        await message.answer("Введите корректный Telegram ID или username.")
        
    # Обновляем данные в FSM
    await state.update_data(user_id=user_id, username=input_value)
    await message.answer("Введите название отдела пользователя:")
    await state.set_state(AddUserState.waiting_for_department)


@router.message(AddUserState.waiting_for_department)
async def add_user_department(message: types.Message, state: FSMContext):
    await state.update_data(department=message.text)
    await message.answer("Введите роль пользователя (admin/manager):")
    await state.set_state(AddUserState.waiting_for_role)


@router.message(AddUserState.waiting_for_role)
async def add_user_role(message: types.Message, state: FSMContext):
    role = message.text.lower()
    if role not in ["admin", "manager"]:
        await message.answer("Недопустимая роль. Используйте 'admin' или 'manager'.")
        return

    # Получаем данные из состояния
    data = await state.get_data()
    user_id = data.get("user_id")
    username = data.get("username")
    department = data.get("department")

    conn = sqlite3.connect("tasks.db")
    cursor = conn.cursor()

    try:
        # Пытаемся добавить пользователя в базу данных
        cursor.execute(
            "INSERT INTO users (telegram_id, name, department, role) VALUES (?, ?, ?, ?)",
            (user_id, username, department, role),
        )
        conn.commit()
        await message.answer(
            f"Пользователь {username} (ID: {user_id or 'не указан'}) добавлен в систему как {role} отдела {department}."
        )
    except sqlite3.IntegrityError:
        await message.answer("Пользователь уже существует в системе.")
    finally:
        conn.close()

    # Завершаем состояние
    await state.clear()

# Уведомление администраторам о новых задачах
async def notify_admins(task_title, task_description, department):
    conn = sqlite3.connect("tasks.db")
    cursor = conn.cursor()
    cursor.execute("SELECT telegram_id FROM users WHERE role = 'admin'")
    admins = cursor.fetchall()
    conn.close()

    for admin in admins:
        admin_id = admin[0]
        try:
            await bot.send_message(
                admin_id,
                f"🔔 Новая задача добавлена!\n"
                f"📌 Название: {task_title}\n"
                f"📝 Описание: {task_description}\n"
                f"🏢 Отдел: {department}"
            )
        except Exception as e:
            logger.error(f"Не удалось отправить уведомление администратору {admin_id}: {e}")

# Добавление задачи (общая команда)
@router.message(Command("add_task"))
@router.message(lambda message: message.text == "Добавить задачу")
async def add_task(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    conn = sqlite3.connect("tasks.db")
    cursor = conn.cursor()
    cursor.execute("SELECT role, department FROM users WHERE telegram_id = ?", (user_id,))
    user_data = cursor.fetchone()

    if not user_data:
        await message.answer("Вы не зарегистрированы в системе.")
        conn.close()
        return

    role, department = user_data
    if role in ["admin", "manager"]:
        await message.answer("Введите название задачи:")
        await state.set_state(AddTaskState.waiting_for_title)
        await state.update_data(department=department, created_by=user_id)
    else:
        await message.answer("У вас нет прав для добавления задач.")
    cursor.close()
    conn.close()

@router.message(AddTaskState.waiting_for_title)
async def process_task_title(message: types.Message, state: FSMContext):
    await state.update_data(title=message.text)
    await message.answer("Введите описание задачи:")
    await state.set_state(AddTaskState.waiting_for_description)

@router.message(AddTaskState.waiting_for_description)
async def process_task_description(message: types.Message, state: FSMContext):
    data = await state.get_data()
    department = data.get("department")
    title = data.get("title")
    description = message.text
    created_by = data.get("created_by")
    created_at = time.strftime("%Y-%m-%d %H:%M:%S")

    conn = sqlite3.connect("tasks.db")
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO tasks (department, title, description, created_at, status, created_by) VALUES (?, ?, ?, ?, ?, ?)",
        (department, title, description, created_at, "pending", created_by)
    )
    conn.commit()
    cursor.close()
    conn.close()

    await notify_admins(title, description, department)
    await state.clear()
    await message.answer("Задача успешно добавлена и уведомление отправлено администраторам!")



# Команда для завершения задачи
@router.message(Command("complete_task"))
async def complete_task_start(message: types.Message, state: FSMContext):
    await message.answer("Введите ID задачи, которую хотите завершить:")
    await state.set_state(CompleteTaskState.waiting_for_task_id)


@router.message(CompleteTaskState.waiting_for_task_id)
async def complete_task_process(message: types.Message, state: FSMContext):
    task_id = message.text

    conn = sqlite3.connect("tasks.db")
    cursor = conn.cursor()
    user_id = message.from_user.id
    cursor.execute("SELECT role, department FROM users WHERE telegram_id = ?", (user_id,))
    user_data = cursor.fetchone()
    
    if not user_data:
        await message.answer("Вы не зарегистрированы в системе.")
        return
        
    cursor = conn.cursor()
    cursor.execute(
        "SELECT * FROM tasks WHERE id = ? AND status = 'pending'", (task_id,)
    )
    task = cursor.fetchone()
    
    if not task:
        await message.answer("Задача с таким ID не найдена или уже завершена.")
        return

    completed_at = time.strftime("%Y-%m-%d %H:%M:%S")
    cursor.execute(
        "UPDATE tasks SET status = 'completed', completed_at = ? WHERE id = ?",
        (completed_at, task_id),
    )
    conn.commit()
    conn.close()

    await message.answer("Задача успешно завершена!")
    await state.clear()


# Просмотр задач
@router.message(Command("view_tasks"))
@router.message(lambda message: message.text == "Просмотреть задачи")
async def view_tasks(message: types.Message):
    conn = sqlite3.connect("tasks.db")
    cursor = conn.cursor()
    user_id = message.from_user.id
    cursor.execute(
        "SELECT role, department FROM users WHERE telegram_id = ?", (user_id,)
    )
    user_data = cursor.fetchone()

    if not user_data:
        await message.answer("Вы не зарегистрированы в системе.")
        return

    role, department = user_data
    print(role, user_data)
    if role == "admin":
        # Администратор видит все задачи
        cursor.execute(
            "SELECT id, department, title, description FROM tasks WHERE status = 'pending'"
        )
        tasks = cursor.fetchall()
        if not tasks:
            await message.answer("Нет текущих задач.")
        else:
            response = "\n".join(
                [f"{task[0]}. [{task[1]}] {task[2]} - {task[3]}" for task in tasks]
            )
            await message.answer(f"Все текущие задачи:\n{response}")
    else:
        # Пользователь видит задачи своего отдела
        cursor.execute(
            "SELECT id, title, description FROM tasks WHERE department = ? AND status = 'pending'",
            (department,),
        )
        tasks = cursor.fetchall()
        if not tasks:
            await message.answer("У вас нет текущих задач.")
        else:
            response = "\n".join(
                [f"{task[0]}. {task[1]} - {task[2]}" for task in tasks]
            )
            await message.answer(f"Текущие задачи:\n{response}")
    conn.close()


# Просмотр выполненных задач для администратора
@router.message(Command("view_completed_tasks"))
async def view_completed_tasks(message: types.Message):
    conn = sqlite3.connect("tasks.db")
    cursor = conn.cursor()
    user_id = message.from_user.id
    cursor.execute(
        "SELECT role FROM users WHERE telegram_id = ?", (user_id,)
    )
    user_data = cursor.fetchone()

    if not user_data or user_data[0] != "admin":
        await message.answer("Эта команда доступна только администраторам.")
        return

    cursor.execute(
        "SELECT id, department, title, description, completed_at FROM tasks WHERE status = 'completed'"
    )
    tasks = cursor.fetchall()

    if not tasks:
        await message.answer("Нет выполненных задач.")
    else:
        response = "\n".join(
            [
                f"ID: {task[0]}, Отдел: {task[1]}, Название: {task[2]}, Описание: {task[3]}, Завершена: {task[4]}"
                for task in tasks
            ]
        )
        await message.answer(f"Выполненные задачи:\n{response}")

    cursor.close()
    conn.close()


# Удаление пользователя с расширенными возможностями
@router.message(Command("delete_user"))
async def delete_user(message: types.Message):
    user_id = message.from_user.id
    conn = sqlite3.connect("tasks.db")
    cursor = conn.cursor()
    cursor.execute("SELECT role FROM users WHERE telegram_id = ?", (user_id,))
    user_data = cursor.fetchone()

    if not user_data or user_data[0] != "admin":
        await message.answer("Эта команда доступна только администраторам.")
        return

    await message.answer("Введите Telegram ID или username пользователя, которого нужно удалить:")

    @router.message()
    async def process_user_deletion(delete_message: types.Message):
        target_input = delete_message.text.strip()
        try:
            if target_input.isdigit():
                target_id = int(target_input)
                cursor.execute("DELETE FROM users WHERE telegram_id = ?", (target_id,))
                cursor.execute("DELETE FROM unauth_users WHERE telegram_id = ?", (target_id,))
            else:
                cursor.execute("DELETE FROM users WHERE name = ?", (target_input,))
                cursor.execute("DELETE FROM unauth_users WHERE username = ?", (target_input,))

            if cursor.rowcount == 0:
                await delete_message.answer("Пользователь с таким ID или username не найден.")
            else:
                conn.commit()
                await delete_message.answer("Пользователь успешно удалён.")
        except Exception as e:
            logger.error(f"Ошибка удаления пользователя: {e}")
            await delete_message.answer("Произошла ошибка при удалении пользователя.")
        finally:
            conn.close()


# Запуск бота
async def main():
    dp = Dispatcher()
    dp.include_router(router)
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
# import sqlite3
# conn = sqlite3.connect("tasks.db")
# cursor = conn.cursor()
# cursor.execute("SELECT id FROM users LIMIT 1")
# first_row = cursor.fetchone()
# cursor.execute("UPDATE users SET role = ? WHERE id = ?", ("admin", first_row[0]))
# conn.commit()
