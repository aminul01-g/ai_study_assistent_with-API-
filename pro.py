import tkinter as tk
from tkinter import ttk, messagebox, simpledialog, scrolledtext, filedialog
import sqlite3
import hashlib
import json
import datetime
import time 
import asyncio 
import threading 
import os 
import shutil 

# --- Configuration ---
DATABASE_NAME = "ai_study_assistant.db"
GEMINI_API_KEY = "" # For all Gemini features (Quiz, Helper, Chat)
APP_VERSION = "1.3.4" # Updated app version for schema fix

# --- Database Manager ---
class DatabaseManager:
    def __init__(self, db_name):
        self.db_name = db_name
        self.conn = None
        self.cursor = None

    def connect(self):
        self.conn = sqlite3.connect(self.db_name, timeout=10) 
        self.cursor = self.conn.cursor()
        self.cursor.execute("PRAGMA foreign_keys = ON;") 

    def close(self):
        if self.conn:
            self.conn.close()
            self.conn = None 
            self.cursor = None 

    def execute_query(self, query, params=()):
        try:
            self.connect()
            self.cursor.execute(query, params)
            self.conn.commit()
            return self.cursor 
        except sqlite3.Error as e:
            print(f"Database execution error: {e} with query: {query} and params: {params}")
            return None
        finally:
            self.close()

    def fetch_one(self, query, params=()):
        try:
            self.connect()
            self.cursor.execute(query, params)
            return self.cursor.fetchone()
        except sqlite3.Error as e:
            print(f"Database fetch_one error: {e} with query: {query} and params: {params}")
            return None
        finally:
            self.close()

    def fetch_all(self, query, params=()):
        try:
            self.connect()
            self.cursor.execute(query, params)
            return self.cursor.fetchall()
        except sqlite3.Error as e:
            print(f"Database fetch_all error: {e} with query: {query} and params: {params}")
            return None
        finally:
            self.close()

    def _table_exists(self, cursor, table_name):
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name=?", (table_name,))
        return cursor.fetchone() is not None

    def _column_exists(self, cursor, table_name, column_name):
        if not self._table_exists(cursor, table_name):
            return False
        cursor.execute(f"PRAGMA table_info({table_name})")
        columns = [info[1] for info in cursor.fetchall()]
        return column_name in columns

    def _try_add_column(self, cursor, table_name, column_definition_sql, column_name_for_check):
        """Helper to attempt adding a column, using the full ADD COLUMN SQL."""
        if self._table_exists(cursor, table_name) and not self._column_exists(cursor, table_name, column_name_for_check):
            try:
                print(f"Migrating {table_name} table: Attempting to add column '{column_name_for_check}' with definition: {column_definition_sql}")
                cursor.execute(f"ALTER TABLE {table_name} ADD COLUMN {column_definition_sql}")
                print(f"Successfully executed ALTER TABLE for {column_name_for_check} on {table_name}.")
                return True 
            except sqlite3.OperationalError as e:
                if "duplicate column name" in str(e).lower():
                    print(f"'{column_name_for_check}' column already exists in '{table_name}' (ignored alter error).")
                    return False 
                else:
                    print(f"SQLite OperationalError during '{column_name_for_check}' column migration for {table_name}: {e}")
                    raise 
            except sqlite3.Error as e:
                print(f"General SQLite Error during '{column_name_for_check}' column migration for {table_name}: {e}")
                raise 
        elif self._column_exists(cursor, table_name, column_name_for_check):
            # This case means the column already exists, so no action needed for adding.
            # print(f"Column '{column_name_for_check}' already present in '{table_name}'.")
            pass
        return False

    def init_db(self):
        conn = sqlite3.connect(self.db_name)
        cursor = conn.cursor()
        cursor.execute("PRAGMA foreign_keys = ON;")
        
        made_schema_changes = False
        try:
            if self._try_add_column(cursor, "tasks", "category TEXT DEFAULT 'General'", "category"):
                made_schema_changes = True
            # Corrected ALTER TABLE for created_at: SQLite doesn't support CURRENT_TIMESTAMP as DEFAULT in ALTER ADD.
            # The INSERT statement will handle CURRENT_TIMESTAMP.
            if self._try_add_column(cursor, "tasks", "created_at TEXT", "created_at"):
                made_schema_changes = True
            if self._try_add_column(cursor, "quiz_attempts", "questions_data TEXT", "questions_data"):
                made_schema_changes = True
            
            if made_schema_changes:
                conn.commit()
                print("Schema migration changes (ALTER TABLE) committed.")
        except sqlite3.Error as e:
            print(f"Error during schema migration (ALTER TABLE): {e}")
        
        queries = [
            """
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL
            );
            """,
            """
            CREATE TABLE IF NOT EXISTS task_categories (
                category_id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                name TEXT NOT NULL,
                UNIQUE(user_id, name), 
                FOREIGN KEY (user_id) REFERENCES users (user_id) ON DELETE CASCADE
            );
            """,
            """
            CREATE TABLE IF NOT EXISTS tasks (
                task_id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                description TEXT NOT NULL,
                category TEXT DEFAULT 'General', 
                due_date TEXT, 
                completed INTEGER DEFAULT 0, 
                created_at TEXT DEFAULT CURRENT_TIMESTAMP, 
                FOREIGN KEY (user_id) REFERENCES users (user_id) ON DELETE CASCADE
            );
            """,
            """
            CREATE TABLE IF NOT EXISTS study_logs (
                log_id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                subject TEXT NOT NULL,
                start_time TEXT NOT NULL, 
                duration_minutes INTEGER NOT NULL,
                notes TEXT,
                FOREIGN KEY (user_id) REFERENCES users (user_id) ON DELETE CASCADE
            );
            """,
            """
            CREATE TABLE IF NOT EXISTS quiz_attempts (
                attempt_id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                topic TEXT NOT NULL,
                quiz_date TEXT NOT NULL, 
                score INTEGER NOT NULL,
                total_questions INTEGER NOT NULL,
                questions_data TEXT, 
                FOREIGN KEY (user_id) REFERENCES users (user_id) ON DELETE CASCADE
            );
            """,
            """
            CREATE TABLE IF NOT EXISTS config (
                key TEXT PRIMARY KEY,
                value TEXT 
            );
            """,
            """
            CREATE TABLE IF NOT EXISTS ai_generated_content (
                content_id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                type TEXT NOT NULL, 
                title TEXT, 
                input_text TEXT, 
                output_text TEXT NOT NULL,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users (user_id) ON DELETE CASCADE
            );
            """,
            """
            CREATE TABLE IF NOT EXISTS ai_chat_history (
                message_id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                role TEXT NOT NULL, 
                content TEXT NOT NULL,
                timestamp TEXT DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users (user_id) ON DELETE CASCADE
            );
            """
        ]
        try:
            for query in queries:
                cursor.execute(query)
            conn.commit()
            print("Database initialized/updated with CREATE IF NOT EXISTS statements.")
        except sqlite3.Error as e:
            print(f"Error initializing database with CREATE IF NOT EXISTS: {e}")
        finally:
            conn.close()

    # --- User Functions ---
    def add_user(self, username, password):
        password_hash = hashlib.sha256(password.encode()).hexdigest()
        res = self.execute_query("INSERT INTO users (username, password_hash) VALUES (?, ?)", (username, password_hash))
        if res and res.lastrowid: 
            user_id = res.lastrowid
            default_categories = ["General", "Academic", "Personal", "Project", "Urgent"]
            for cat_name in default_categories:
                self.add_task_category(user_id, cat_name)
        return res

    def check_user(self, username, password):
        password_hash = hashlib.sha256(password.encode()).hexdigest()
        return self.fetch_one("SELECT user_id, username FROM users WHERE username = ? AND password_hash = ?", (username, password_hash))

    # --- Task Category Functions ---
    def add_task_category(self, user_id, category_name):
        return self.execute_query("INSERT OR IGNORE INTO task_categories (user_id, name) VALUES (?, ?)", (user_id, category_name))

    def get_task_categories(self, user_id):
        categories = self.fetch_all("SELECT name FROM task_categories WHERE user_id = ? ORDER BY name", (user_id,))
        cat_list = [cat[0] for cat in categories] if categories else []
        if "General" not in cat_list:
            cat_list.insert(0, "General") 
        elif "General" in cat_list and cat_list.index("General") != 0: 
            cat_list.pop(cat_list.index("General"))
            cat_list.insert(0, "General")
        return cat_list


    def delete_task_category(self, user_id, category_name):
        if category_name.lower() == 'general': 
            return False 
        self.execute_query("UPDATE tasks SET category = 'General' WHERE user_id = ? AND category = ?", (user_id, category_name))
        return self.execute_query("DELETE FROM task_categories WHERE user_id = ? AND name = ?", (user_id, category_name))


    # --- Task Functions ---
    def add_task(self, user_id, description, category='General', due_date=None):
        if user_id is None:
            print("Error: user_id is None in DatabaseManager.add_task. Cannot add task.") 
            return None
        print(f"DBManager.add_task called with user_id: {user_id}, desc: {description}, cat: {category}, due: {due_date}") 
        return self.execute_query("INSERT INTO tasks (user_id, description, category, due_date, created_at) VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)",
                                  (user_id, description, category, due_date))

    def get_tasks(self, user_id, show_completed=False, category_filter=None, due_filter=None, limit=None): 
        params = [user_id]
        query = "SELECT task_id, description, category, due_date, completed, created_at FROM tasks WHERE user_id = ?"
        if not show_completed:
            query += " AND completed = 0"
        if category_filter and category_filter != "All Categories":
            query += " AND category = ?"
            params.append(category_filter)
        
        today_str = datetime.date.today().strftime('%Y-%m-%d')
        if due_filter == "today":
            query += " AND due_date = ?"
            params.append(today_str)
        elif due_filter == "upcoming": 
            next_week_str = (datetime.date.today() + datetime.timedelta(days=7)).strftime('%Y-%m-%d')
            query += " AND due_date > ? AND due_date <= ?"
            params.extend([today_str, next_week_str])
        elif due_filter == "overdue":
            query += " AND due_date < ? AND completed = 0" 
            params.append(today_str)

        query += " ORDER BY CASE WHEN due_date IS NULL OR due_date = '' THEN 1 ELSE 0 END, due_date ASC, created_at DESC"
        if limit:
            query += f" LIMIT {int(limit)}"
        return self.fetch_all(query, tuple(params))


    def update_task_status(self, task_id, completed):
        return self.execute_query("UPDATE tasks SET completed = ? WHERE task_id = ?", (1 if completed else 0, task_id))

    def delete_task(self, task_id):
        return self.execute_query("DELETE FROM tasks WHERE task_id = ?", (task_id,))

    # --- Study Log Functions ---
    def add_study_log(self, user_id, subject, start_time, duration_minutes, notes):
        return self.execute_query(
            "INSERT INTO study_logs (user_id, subject, start_time, duration_minutes, notes) VALUES (?, ?, ?, ?, ?)",
            (user_id, subject, start_time, duration_minutes, notes)
        )

    def get_study_logs(self, user_id, limit=None): 
        query = "SELECT log_id, subject, start_time, duration_minutes, notes FROM study_logs WHERE user_id = ? ORDER BY start_time DESC" 
        if limit:
            query += f" LIMIT {int(limit)}"
        return self.fetch_all(query, (user_id,))
    
    def get_study_days_count(self, user_id, days_period):
        date_threshold = (datetime.date.today() - datetime.timedelta(days=days_period)).strftime("%Y-%m-%d %H:%M:%S")
        query = "SELECT COUNT(DISTINCT DATE(start_time)) FROM study_logs WHERE user_id = ? AND start_time >= ?"
        result = self.fetch_one(query, (user_id, date_threshold))
        return result[0] if result else 0

    # --- Quiz Attempt Functions ---
    def add_quiz_attempt(self, user_id, topic, quiz_date, score, total_questions, questions_data_json): 
        return self.execute_query(
            "INSERT INTO quiz_attempts (user_id, topic, quiz_date, score, total_questions, questions_data) VALUES (?, ?, ?, ?, ?, ?)",
            (user_id, topic, quiz_date, score, total_questions, questions_data_json)
        )

    def get_quiz_attempts(self, user_id): 
        return self.fetch_all(
            "SELECT attempt_id, topic, quiz_date, score, total_questions FROM quiz_attempts WHERE user_id = ? ORDER BY quiz_date DESC",
            (user_id,) 
        )
    
    def get_quiz_attempt_details(self, attempt_id): 
        return self.fetch_one(
            "SELECT topic, questions_data FROM quiz_attempts WHERE attempt_id = ?", (attempt_id,)
        )
    
    # --- AI Generated Content Functions ---
    def add_ai_content(self, user_id, content_type, title, output_text, input_text=None):
        return self.execute_query(
            "INSERT INTO ai_generated_content (user_id, type, title, input_text, output_text, created_at) VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP)",
            (user_id, content_type, title, input_text, output_text)
        )

    def get_ai_content(self, user_id, content_type=None):
        query = "SELECT content_id, type, title, created_at FROM ai_generated_content WHERE user_id = ?"
        params = [user_id]
        if content_type:
            query += " AND type = ?"
            params.append(content_type)
        query += " ORDER BY created_at DESC"
        return self.fetch_all(query, tuple(params))

    def get_ai_content_detail(self, content_id):
        return self.fetch_one("SELECT title, type, input_text, output_text, created_at FROM ai_generated_content WHERE content_id = ?", (content_id,))

    def delete_ai_content(self, content_id):
        return self.execute_query("DELETE FROM ai_generated_content WHERE content_id = ?", (content_id,))

    # --- AI Chat History Functions (New) ---
    def add_chat_message(self, user_id, role, content):
        return self.execute_query(
            "INSERT INTO ai_chat_history (user_id, role, content, timestamp) VALUES (?, ?, ?, CURRENT_TIMESTAMP)",
            (user_id, role, content)
        )

    def get_chat_history(self, user_id, limit=50): # Load last N messages
        query = "SELECT role, content, timestamp FROM ai_chat_history WHERE user_id = ? ORDER BY timestamp DESC LIMIT ?"
        history = self.fetch_all(query, (user_id, limit))
        return list(reversed(history)) if history else [] # Reverse to show oldest first

    # --- Config Functions ---
    def get_config_value(self, key):
        row = self.fetch_one("SELECT value FROM config WHERE key = ?", (key,))
        return row[0] if row else None

    def set_config_value(self, key, value):
        return self.execute_query("INSERT OR REPLACE INTO config (key, value) VALUES (?, ?)", (key, value))


# --- Main Application ---
class AIStudyAssistant(tk.Tk):
    def __init__(self, db_manager):
        super().__init__()
        self.db_manager = db_manager
        self.title(f"AI Study Assistant - v{APP_VERSION}") 
        self.geometry("1050x800") 
        self.configure(bg="#e0e0e0") 

        self.current_user_id = None
        self.current_username = None
        self.pomodoro_work_duration = tk.IntVar(value=25) 
        self.pomodoro_break_duration = tk.IntVar(value=5)  

        style = ttk.Style(self)
        style.theme_use("clam") 
        self.main_bg_color = "#f4f6f8" 
        accent_color = "#4a69bd"; header_color = "#3c40c6"
        style.configure("TFrame", background=self.main_bg_color); style.configure("TLabel", background=self.main_bg_color, font=("Arial", 10))
        style.configure("TButton", font=("Arial", 10, "bold"), padding=7, borderwidth=1, relief="raised")
        style.map("TButton",foreground=[('pressed', 'white'), ('active', 'white')], background=[('pressed', '!disabled', accent_color), ('active', header_color)])
        style.configure("Header.TLabel", font=("Arial", 20, "bold"), foreground=header_color, background=self.main_bg_color) 
        style.configure("SubHeader.TLabel", font=("Arial", 13, "bold"), foreground=accent_color, background=self.main_bg_color) 
        style.configure("Treeview.Heading", font=('Arial', 10,'bold'), background="#dcdde1", relief="flat")
        style.map("Treeview.Heading", relief=[('active','groove'),('pressed','sunken')])
        style.configure("Danger.TButton", foreground="white", background="#c0392b", font=("Arial", 10, "bold")) 
        style.map("Danger.TButton", background=[('active', '#e74c3c')]) 
        style.configure("Placeholder.TLabel", font=("Arial", 10, "italic"), foreground="#7f8c8d", background=self.main_bg_color) 
        style.configure("Success.TLabel", font=("Arial", 10, "italic"), foreground="#27ae60", background=self.main_bg_color) 
        style.configure("Error.TLabel", font=("Arial", 10, "italic"), foreground="#c0392b", background=self.main_bg_color) 
        style.configure("TRadiobutton", background=self.main_bg_color, font=("Arial", 10)) 
        style.configure("TCheckbutton", background=self.main_bg_color, font=("Arial", 10))
        style.configure("Status.TLabel", background=accent_color, foreground="white", font=("Arial", 9), padding=4) 
        style.configure("Link.TLabel", foreground="blue", font=("Arial", 10, "underline"), background=self.main_bg_color)
        style.configure("UserChat.TLabel", background="#d1e7dd", foreground="black", padding=5, relief="solid", borderwidth=1, font=("Arial",10)) 
        style.configure("AssistantChat.TLabel", background="#f8f9fa", foreground="black", padding=5, relief="solid", borderwidth=1, font=("Arial",10)) 


        self.container = ttk.Frame(self, padding=15); self.container.pack(fill=tk.BOTH, expand=True)
        self.status_bar = ttk.Label(self, text="Welcome!", style="Status.TLabel", anchor=tk.W)
        self.status_bar.pack(side=tk.BOTTOM, fill=tk.X)
        self.frames = {}
        # Removed DailyPlanFrame from this list
        for F in (LoginPage, RegisterPage, MainPage, TaskManagerFrame, StudyTrackerFrame, 
                    QuizFrame, AnalyticsFrame, AIHelperFrame, SettingsFrame, 
                    ReviewHubFrame, GeminiChatFrame): 
            page_name = F.__name__; frame = F(parent=self.container, controller=self)
            self.frames[page_name] = frame; frame.grid(row=0, column=0, sticky="nsew")
        self.show_frame("LoginPage") 

    def show_frame(self, page_name, status_message=None): 
        if self.current_user_id is None and page_name not in ["LoginPage", "RegisterPage"]:
            messagebox.showinfo("Login Required", "Please log in."); self.show_frame("LoginPage"); return
        frame = self.frames.get(page_name)
        if frame:
            frame.tkraise(); 
            if hasattr(frame, 'refresh_data'): frame.refresh_data()
            if status_message: self.update_status(status_message)
        else: print(f"Error: Frame '{page_name}' not found."); self.update_status(f"Error loading page.", 5000)

    def login_user(self, user_id, username): 
        self.current_user_id = user_id; self.current_username = username
        self.show_frame("MainPage", status_message=f"Logged in as {username}")
        if "MainPage" in self.frames and hasattr(self.frames["MainPage"], 'update_welcome_message'):
             self.frames["MainPage"].update_welcome_message(); self.frames["MainPage"].fetch_motivational_quote() 

    def logout_user(self): 
        self.current_user_id = None; self.current_username = None
        self.show_frame("LoginPage", status_message="Successfully logged out.")

    def update_status(self, message, duration=5000): 
        self.status_bar.config(text=message)
        if duration > 0 and hasattr(self.status_bar, '_after_id') and self.status_bar._after_id:
            self.status_bar.after_cancel(self.status_bar._after_id)
        if duration > 0: self.status_bar._after_id = self.status_bar.after(duration, lambda: self.status_bar.config(text="")) 
        else: self.status_bar._after_id = None


# --- Frames (UI Pages) ---
class LoginPage(ttk.Frame): 
    def __init__(self, parent, controller):
        super().__init__(parent); self.controller = controller; center_frame = ttk.Frame(self); center_frame.pack(expand=True) 
        ttk.Label(center_frame, text="Login", style="Header.TLabel").pack(pady=20)
        ttk.Label(center_frame, text="Username:").pack(pady=(10,0))
        self.username_entry = ttk.Entry(center_frame, width=30, font=("Arial", 11)); self.username_entry.pack(ipady=4, pady=2) 
        ttk.Label(center_frame, text="Password:").pack(pady=(10,0))
        self.password_entry = ttk.Entry(center_frame, show="*", width=30, font=("Arial", 11)); self.password_entry.pack(ipady=4, pady=2)
        self.password_entry.bind("<Return>", lambda event: self.login()) 
        ttk.Button(center_frame, text="Login", command=self.login).pack(pady=20, ipadx=10, ipady=4)
        ttk.Button(center_frame, text="Register", command=lambda: controller.show_frame("RegisterPage")).pack(ipadx=5, ipady=4)
    def login(self):
        username = self.username_entry.get().strip(); password = self.password_entry.get() 
        if not username or not password: messagebox.showerror("Error", "Username/password empty."); self.controller.update_status("Login failed: fields empty.", 3000); return
        user = self.controller.db_manager.check_user(username, password)
        if user: self.controller.login_user(user[0], user[1]); self.username_entry.delete(0, tk.END); self.password_entry.delete(0, tk.END)
        else: messagebox.showerror("Login Failed", "Invalid credentials."); self.controller.update_status("Login failed: invalid credentials.", 3000)
    def refresh_data(self): self.controller.update_status("Please log in or register.")

class RegisterPage(ttk.Frame): 
    def __init__(self, parent, controller):
        super().__init__(parent); self.controller = controller; center_frame = ttk.Frame(self); center_frame.pack(expand=True)
        ttk.Label(center_frame, text="Register New Account", style="Header.TLabel").pack(pady=20)
        ttk.Label(center_frame, text="Username:").pack(pady=(10,0))
        self.username_entry = ttk.Entry(center_frame, width=30, font=("Arial", 11)); self.username_entry.pack(ipady=4, pady=2)
        ttk.Label(center_frame, text="Password (min 6 chars):").pack(pady=(10,0)) 
        self.password_entry = ttk.Entry(center_frame, show="*", width=30, font=("Arial", 11)); self.password_entry.pack(ipady=4, pady=2)
        ttk.Label(center_frame, text="Confirm Password:").pack(pady=(10,0))
        self.confirm_password_entry = ttk.Entry(center_frame, show="*", width=30, font=("Arial", 11)); self.confirm_password_entry.pack(ipady=4, pady=2)
        self.confirm_password_entry.bind("<Return>", lambda event: self.register()) 
        ttk.Button(center_frame, text="Register", command=self.register).pack(pady=20, ipadx=10, ipady=4)
        ttk.Button(center_frame, text="Back to Login", command=lambda: controller.show_frame("LoginPage")).pack(ipadx=5, ipady=4)
    def register(self):
        username = self.username_entry.get().strip(); password = self.password_entry.get(); confirm_password = self.confirm_password_entry.get() 
        if not username or not password or not confirm_password: messagebox.showerror("Error", "All fields required."); return
        if len(password) < 6: messagebox.showerror("Error", "Password min 6 chars."); return
        if password != confirm_password: messagebox.showerror("Error", "Passwords do not match."); return
        if self.controller.db_manager.fetch_one("SELECT user_id FROM users WHERE username = ?", (username,)): messagebox.showerror("Error", "Username exists."); return
        if self.controller.db_manager.add_user(username, password): 
            self.controller.update_status(f"User '{username}' registered. Please log in.", 5000)
            self.username_entry.delete(0, tk.END); self.password_entry.delete(0, tk.END); self.confirm_password_entry.delete(0, tk.END)
            self.controller.show_frame("LoginPage") 
        else: messagebox.showerror("DB Error", "Registration failed."); self.controller.update_status("Registration failed.", 3000)
    def refresh_data(self): self.controller.update_status("Create a new account.")


class MainPage(ttk.Frame):
    def __init__(self, parent, controller):
        super().__init__(parent)
        self.controller = controller

        self.welcome_label = ttk.Label(self, text="Welcome!", style="Header.TLabel")
        self.welcome_label.pack(pady=(15,5)) 

        self.quote_label = ttk.Label(self, text="Fetching inspiration...", style="Placeholder.TLabel", wraplength=750, justify=tk.CENTER)
        self.quote_label.pack(pady=(0, 15), padx=20)

        # Quick Entry Frame REMOVED

        button_frame = ttk.Frame(self) 
        button_frame.pack(pady=10, expand=True, fill=tk.X, padx=100) 
        buttons_config = [  
            # ("Daily Plan", "DailyPlanFrame"), # REMOVED Daily Plan Button
            ("Task Manager", "TaskManagerFrame"), 
            ("Study Tracker", "StudyTrackerFrame"),
            ("AI Helper (Gemini)", "AIHelperFrame"), 
            ("AI Chat (Gemini)", "GeminiChatFrame"), 
            ("AI Quizzes (Gemini)", "QuizFrame"), 
            ("Analytics", "AnalyticsFrame"), 
            ("Review Hub", "ReviewHubFrame"), 
            ("Settings", "SettingsFrame")
        ]
        for text, frame_name in buttons_config:
            btn = ttk.Button(button_frame, text=text, command=lambda fn=frame_name: controller.show_frame(fn))
            btn.pack(pady=6, fill=tk.X, ipady=4) 
        
        self.check_reminders_button = ttk.Button(self, text="Check Reminders", command=self.check_reminders) 
        self.check_reminders_button.pack(pady=(5,10))

        ttk.Button(self, text="Logout", command=controller.logout_user, style="Danger.TButton").pack(pady=15, ipady=3)

    # quick_add_task method REMOVED

    def check_reminders(self): 
        if not self.controller.current_user_id: return
        today = datetime.date.today().strftime("%Y-%m-%d")
        due_today = self.controller.db_manager.get_tasks(self.controller.current_user_id, False, due_filter="today")
        overdue = self.controller.db_manager.get_tasks(self.controller.current_user_id, False, due_filter="overdue")
        msg = ""
        if due_today: msg += "Tasks due TODAY:\n"; [msg := msg + f"- {t[1]} ({t[2]})\n" for t in due_today[:3]]; 
        if len(due_today) > 3: msg += f"...and {len(due_today)-3} more.\n"
        if overdue: msg += "\nOVERDUE Tasks:\n"; [msg := msg + f"- {t[1]} (Due: {t[3]})\n" for t in overdue[:3]]; 
        if len(overdue) > 3: msg += f"...and {len(overdue)-3} more.\n"
        if not msg: messagebox.showinfo("Reminders", "No urgent tasks."); self.controller.update_status("No urgent reminders.", 3000)
        else: ReminderPopup(self.controller, "Study Reminders", msg); self.controller.update_status("Reminders checked.", 3000)

    def update_welcome_message(self): 
        if self.controller.current_username: self.welcome_label.config(text=f"Welcome, {self.controller.current_username}!")
        else: self.welcome_label.config(text="Welcome!") 
    
    def fetch_motivational_quote(self): 
        self.quote_label.config(text="Fetching inspiration...", style="Placeholder.TLabel")
        threading.Thread(target=self._get_ai_quote, daemon=True).start()

    def _get_ai_quote(self): 
        api_key = GEMINI_API_KEY or self.controller.db_manager.get_config_value('GEMINI_API_KEY') or ""
        if not api_key: self.controller.after(0, lambda: self.quote_label.config(text="API key missing.", style="Error.TLabel")); return
        prompt = "A short, unique, inspiring motivational quote for a student. Concise."
        payload = {"contents": [{"role": "user", "parts": [{"text": prompt}]}]}
        url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={api_key}"
        try:
            import requests; r=requests.post(url, headers={'Content-Type':'application/json'},json=payload,timeout=20); r.raise_for_status(); res=r.json()
            if res.get("candidates") and res["candidates"][0].get("content",{}).get("parts"):
                quote = res["candidates"][0]["content"]["parts"][0].get("text", "Keep learning!").strip()
                self.controller.after(0, lambda: self.quote_label.config(text=f"\"{quote}\"", style="Success.TLabel"))
            else: self.controller.after(0, lambda: self.quote_label.config(text="Stay focused!", style="Success.TLabel"))
        except Exception as e: print(f"Quote error: {e}"); self.controller.after(0, lambda: self.quote_label.config(text="Keep going!", style="Success.TLabel"))

    def refresh_data(self): 
        self.update_welcome_message(); self.fetch_motivational_quote() 
        self.controller.update_status(f"Welcome back, {self.controller.current_username}!")


# --- Reminder Popup (New Toplevel window) ---
class ReminderPopup(tk.Toplevel): 
    def __init__(self, controller, title, message):
        super().__init__(controller); self.title(title); self.geometry("400x300")
        bg = getattr(controller, 'main_bg_color', "#f4f6f8"); self.configure(bg=bg); self.transient(controller); self.grab_set() 
        style = ttk.Style(self); style.configure("Reminder.TLabel", background=bg, font=("Arial", 10)); style.configure("ReminderHeader.TLabel", background=bg, font=("Arial", 12, "bold"))
        ttk.Label(self, text=title, style="ReminderHeader.TLabel").pack(pady=10)
        txt_area = scrolledtext.ScrolledText(self, wrap=tk.WORD, height=10, width=45, font=("Arial", 10), bg=bg); txt_area.insert(tk.END, message)
        txt_area.config(state=tk.DISABLED); txt_area.pack(pady=10, padx=10, fill=tk.BOTH, expand=True)
        ttk.Button(self, text="OK", command=self.destroy, style="TButton").pack(pady=10)
        self.update_idletasks(); x=controller.winfo_x()+(controller.winfo_width()//2)-(self.winfo_width()//2); y=controller.winfo_y()+(controller.winfo_height()//2)-(self.winfo_height()//2)
        self.geometry(f"+{x}+{y}"); self.focus_set()


# --- Daily Plan Frame (REMOVED) ---
# class DailyPlanFrame(ttk.Frame):
#    ... (Content of DailyPlanFrame was here)


# --- Review Hub Frame (New) ---
class ReviewHubFrame(ttk.Frame): 
    def __init__(self, parent, controller):
        super().__init__(parent); self.controller = controller
        ttk.Label(self, text="Review Hub", style="Header.TLabel").pack(pady=10)
        nb = ttk.Notebook(self); nb.pack(pady=10, padx=20, fill=tk.BOTH, expand=True)
        self.ai_tab = ttk.Frame(nb); self.logs_tab = ttk.Frame(nb)
        nb.add(self.ai_tab, text='Saved AI Content'); nb.add(self.logs_tab, text='Study Logs Review')
        self._setup_saved_ai_tab(); self._setup_study_logs_tab()
        ttk.Button(self, text="Back to Main Menu", command=lambda: controller.show_frame("MainPage")).pack(pady=10, side=tk.BOTTOM)
    def _setup_saved_ai_tab(self): 
        ttk.Label(self.ai_tab, text="Saved AI Explanations, Summaries & Questions", style="SubHeader.TLabel").pack(pady=10)
        lf = ttk.Frame(self.ai_tab); lf.pack(fill=tk.X, pady=5)
        cols = ("Title", "Type", "Created"); self.ai_tree = ttk.Treeview(lf, columns=cols, show="headings", height=8)
        self.ai_tree.heading("Title", text="Title/Topic"); self.ai_tree.column("Title", width=250, anchor=tk.W)
        self.ai_tree.heading("Type", text="Type"); self.ai_tree.column("Type", width=100, anchor=tk.CENTER)
        self.ai_tree.heading("Created", text="Saved On"); self.ai_tree.column("Created", width=150, anchor=tk.CENTER)
        self.ai_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        sb = ttk.Scrollbar(lf, orient=tk.VERTICAL, command=self.ai_tree.yview); self.ai_tree.configure(yscroll=sb.set); sb.pack(side=tk.RIGHT, fill=tk.Y)
        self.ai_tree.bind("<<TreeviewSelect>>", self.display_selected_ai_content)
        btns = ttk.Frame(self.ai_tab); btns.pack(pady=5)
        ttk.Button(btns, text="Delete Selected", command=self.delete_selected_ai_content, style="Danger.TButton").pack(side=tk.LEFT, padx=5)
        self.ai_disp = scrolledtext.ScrolledText(self.ai_tab, height=10, wrap=tk.WORD, state=tk.DISABLED, font=("Arial", 10))
        self.ai_disp.pack(pady=10, fill=tk.BOTH, expand=True)
    def _setup_study_logs_tab(self): 
        ttk.Label(self.logs_tab, text="Review Your Past Study Sessions", style="SubHeader.TLabel").pack(pady=10)
        cols_l = ("Subject", "Date", "Duration", "Notes"); self.rev_logs_tree = ttk.Treeview(self.logs_tab, columns=cols_l, show="headings", height=15)
        for c in cols_l: self.rev_logs_tree.heading(c, text=c)
        self.rev_logs_tree.column("Subject", width=200); self.rev_logs_tree.column("Date", width=120, anchor=tk.CENTER)
        self.rev_logs_tree.column("Duration", width=100, anchor=tk.CENTER); self.rev_logs_tree.column("Notes", width=300)
        self.rev_logs_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, pady=5)
        sb_l = ttk.Scrollbar(self.logs_tab, orient=tk.VERTICAL, command=self.rev_logs_tree.yview)
        self.rev_logs_tree.configure(yscroll=sb_l.set); sb_l.pack(side=tk.RIGHT, fill=tk.Y)
    def refresh_data(self): 
        if not self.controller.current_user_id: self.controller.show_frame("LoginPage"); return
        self._load_saved_ai_content(); self._load_study_logs_for_review(); self.controller.update_status("Review Hub loaded.")
    def _load_saved_ai_content(self): 
        for i in self.ai_tree.get_children(): self.ai_tree.delete(i)
        self.ai_disp.config(state=tk.NORMAL); self.ai_disp.delete("1.0",tk.END); self.ai_disp.config(state=tk.DISABLED)
        items = self.controller.db_manager.get_ai_content(self.controller.current_user_id)
        if items:
            for item in items: 
                cr_s = item[3]
                try: cr_dt_obj = datetime.datetime.strptime(cr_s, "%Y-%m-%d %H:%M:%S.%f") if '.' in cr_s else datetime.datetime.strptime(cr_s, "%Y-%m-%d %H:%M:%S"); cr_d = cr_dt_obj.strftime("%Y-%m-%d %H:%M")
                except ValueError: cr_d = cr_s
                self.ai_tree.insert("",tk.END,values=(item[2],item[1],cr_d),iid=str(item[0]))
    def display_selected_ai_content(self, event=None): 
        sel_id = self.ai_tree.focus(); 
        if not sel_id: return
        det = self.controller.db_manager.get_ai_content_detail(int(sel_id))
        if det: 
            txt = f"Type: {det[1]}\nTitle: {det[0]}\nSaved: {det[4]}\n\n"
            if det[2]: txt += f"--- Input ---\n{det[2]}\n\n"
            txt += f"--- AI Response ---\n{det[3]}"
            self.ai_disp.config(state=tk.NORMAL); self.ai_disp.delete("1.0",tk.END)
            self.ai_disp.insert(tk.END,txt); self.ai_disp.config(state=tk.DISABLED)
    def delete_selected_ai_content(self): 
        sel_id = self.ai_tree.focus(); 
        if not sel_id: messagebox.showwarning("Sel Error","Select item to delete."); return
        if messagebox.askyesno("Confirm","Delete saved AI content?"):
            if self.controller.db_manager.delete_ai_content(int(sel_id)):
                self._load_saved_ai_content(); self.controller.update_status("AI content deleted.",3000)
            else: messagebox.showerror("Error","Delete failed."); self.controller.update_status("Delete failed.",3000)
    def _load_study_logs_for_review(self): 
        for i in self.rev_logs_tree.get_children(): self.rev_logs_tree.delete(i)
        logs = self.controller.db_manager.get_study_logs(self.controller.current_user_id) 
        if logs:
            for log in logs: 
                lid,s,st,dur,n=log
                try: dt_o=datetime.datetime.strptime(st,"%Y-%m-%d %H:%M:%S"); d_d=dt_o.strftime("%Y-%m-%d %H:%M")
                except ValueError: d_d=st 
                dur_d=f"{dur} min"; self.rev_logs_tree.insert("","end",values=(s,d_d,dur_d,n),iid=str(lid))


# --- Other Frames (TaskManagerFrame, StudyTrackerFrame, QuizFrame, QuizReviewer, AIHelperFrame, SettingsFrame, AnalyticsFrame) ---

class TaskManagerFrame(ttk.Frame): 
    def __init__(self, parent, controller): 
        super().__init__(parent); self.controller = controller; self.user_task_categories = []
        ttk.Label(self, text="Task Manager", style="Header.TLabel").pack(pady=10) 
        filter_add_frame = ttk.Frame(self); filter_add_frame.pack(pady=5, fill=tk.X, padx=20)
        ttk.Label(filter_add_frame, text="Filter:").pack(side=tk.LEFT, padx=(0,5))
        self.category_filter_combobox = ttk.Combobox(filter_add_frame, state="readonly", width=15, font=("Arial", 10))
        self.category_filter_combobox.pack(side=tk.LEFT, padx=5)
        self.category_filter_combobox.bind("<<ComboboxSelected>>", lambda e: self.refresh_data())
        # Export .ics button REMOVED
        # ttk.Button(filter_add_frame, text="Export .ics", command=self.export_tasks_to_ics).pack(side=tk.RIGHT, padx=5)
        input_frame = ttk.Frame(self); input_frame.pack(pady=10, fill=tk.X, padx=20)
        ttk.Label(input_frame, text="New Task:").pack(side=tk.LEFT, padx=(0,5))
        self.task_entry = ttk.Entry(input_frame, width=30, font=("Arial", 10)); self.task_entry.pack(side=tk.LEFT, expand=True, fill=tk.X, padx=5, ipady=2)
        self.task_entry.bind("<Return>", lambda event: self.add_task()) 
        ttk.Label(input_frame, text="Category:").pack(side=tk.LEFT, padx=(10,5))
        self.category_combobox = ttk.Combobox(input_frame, state="readonly", width=12, font=("Arial", 10)); self.category_combobox.pack(side=tk.LEFT, padx=5)
        ttk.Label(input_frame, text="Due:").pack(side=tk.LEFT, padx=(10,5)); self.due_date_entry = ttk.Entry(input_frame, width=12, font=("Arial", 10)) 
        self.due_date_entry.pack(side=tk.LEFT, padx=5, ipady=2); self.due_date_entry.insert(0, datetime.date.today().strftime('%Y-%m-%d')) 
        ttk.Button(input_frame, text="Add", command=self.add_task).pack(side=tk.LEFT, padx=5) 
        list_frame = ttk.Frame(self); list_frame.pack(pady=10, fill=tk.BOTH, expand=True, padx=20)
        cols = ("Description", "Category", "Due Date", "Status", "Created"); self.task_tree = ttk.Treeview(list_frame, columns=cols, show="headings", style="Treeview")
        for col in cols: self.task_tree.heading(col, text=col)
        self.task_tree.column("Description", width=280); self.task_tree.column("Category", width=100, anchor=tk.CENTER)
        self.task_tree.column("Due Date", width=100, anchor=tk.CENTER); self.task_tree.column("Status", width=80, anchor=tk.CENTER)
        self.task_tree.column("Created", width=120, anchor=tk.CENTER); self.task_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar = ttk.Scrollbar(list_frame, orient=tk.VERTICAL, command=self.task_tree.yview)
        self.task_tree.configure(yscroll=scrollbar.set); scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        action_frame = ttk.Frame(self); action_frame.pack(pady=10, padx=20, fill=tk.X)
        ttk.Button(action_frame, text="Toggle Status", command=self.toggle_task_status).pack(side=tk.LEFT, padx=5) 
        ttk.Button(action_frame, text="Delete Task", command=self.delete_task, style="Danger.TButton").pack(side=tk.LEFT, padx=5)
        self.show_completed_var = tk.BooleanVar(); ttk.Checkbutton(action_frame, text="Show Completed", variable=self.show_completed_var, command=self.refresh_data, style="TCheckbutton").pack(side=tk.LEFT, padx=10)
        ttk.Button(self, text="Back to Main Menu", command=lambda: self.controller.show_frame("MainPage")).pack(pady=10, side=tk.BOTTOM)
    
    def load_categories(self): 
        if self.controller.current_user_id:
            self.user_task_categories = self.controller.db_manager.get_task_categories(self.controller.current_user_id)
            self.category_combobox['values'] = self.user_task_categories
            self.category_combobox.set("General" if "General" in self.user_task_categories else (self.user_task_categories[0] if self.user_task_categories else ""))
            self.category_filter_combobox['values'] = ["All Categories"] + self.user_task_categories
            self.category_filter_combobox.set("All Categories")

    def add_task(self): 
        description = self.task_entry.get().strip(); cat = self.category_combobox.get(); due_str = self.due_date_entry.get().strip()
        if not description: messagebox.showerror("Error", "Task description empty."); return
        if not cat: messagebox.showerror("Error", "Select category."); return # Ensure category is selected
        try:
            if due_str: datetime.datetime.strptime(due_str, '%Y-%m-%d')
        except ValueError: messagebox.showerror("Error", "Invalid date (YYYY-MM-DD)."); return
        
        uid = self.controller.current_user_id
        if not uid: # Explicit check for user_id before DB call
            messagebox.showerror("Authentication Error", "No user logged in. Please log in again.")
            self.controller.show_frame("LoginPage")
            return

        print(f"TaskManagerFrame.add_task: User ID: {uid}, Desc: '{description}', Cat: '{cat}', Due: '{due_str}'") # Debug print
        
        if self.controller.db_manager.add_task(uid, description, cat, due_str if due_str else None):
            self.controller.update_status(f"Task '{description[:20]}...' added.", 3000)
            self.task_entry.delete(0, tk.END); self.due_date_entry.delete(0, tk.END); self.due_date_entry.insert(0, datetime.date.today().strftime('%Y-%m-%d'))
            self.refresh_data()
        else: 
            messagebox.showerror("DB Error", "Failed to add task. Check console for specific database errors.")
            self.controller.update_status("Add task failed. See console.", 3000)
            
    def refresh_data(self): # Same
        if not self.controller.current_user_id: self.controller.show_frame("LoginPage"); return 
        self.load_categories(); 
        for i in self.task_tree.get_children(): self.task_tree.delete(i)
        cat_filter = self.category_filter_combobox.get()
        tasks = self.controller.db_manager.get_tasks(self.controller.current_user_id, self.show_completed_var.get(), cat_filter)
        if tasks:
            for task in tasks:
                tid, d, c, due, comp, cr_at = task; stat = "Completed" if comp else "Pending"; due_d = due if due else "N/A" 
                try: cr_dt = datetime.datetime.strptime(cr_at, "%Y-%m-%d %H:%M:%S.%f") if '.' in cr_at else datetime.datetime.strptime(cr_at, "%Y-%m-%d %H:%M:%S"); cr_disp = cr_dt.strftime("%y-%m-%d %H:%M")
                except ValueError: cr_disp = cr_at 
                self.task_tree.insert("", tk.END, values=(d, c, due_d, stat, cr_disp), iid=str(tid))
        self.controller.update_status("Task list refreshed.")
    
    # export_tasks_to_ics method REMOVED
    # def export_tasks_to_ics(self): ...

    def get_selected_task_id(self): # Same
        sel = self.task_tree.focus(); 
        if not sel: messagebox.showwarning("No Sel", "Select task."); return None
        return int(sel) 
    def toggle_task_status(self): # Same
        tid = self.get_selected_task_id(); 
        if tid is None: return 
        t_details = self.controller.db_manager.fetch_one("SELECT completed, description FROM tasks WHERE task_id=? AND user_id=?", (tid, self.controller.current_user_id))
        if t_details:
            n_stat = not t_details[0]; t_desc = t_details[1][:20] 
            if self.controller.db_manager.update_task_status(tid, n_stat):
                self.refresh_data(); s_txt = "completed" if n_stat else "pending"
                self.controller.update_status(f"Task '{t_desc}...' {s_txt}.", 3000)
            else: messagebox.showerror("DB Error", "Update failed."); self.controller.update_status("Task update failed.", 3000)
        else: messagebox.showerror("Error", "Task not found/permission.")
    def delete_task(self): # Same
        tid = self.get_selected_task_id(); 
        if tid is None: return
        t_details = self.controller.db_manager.fetch_one("SELECT description FROM tasks WHERE task_id=? AND user_id=?", (tid, self.controller.current_user_id))
        if not t_details: messagebox.showerror("Error", "Task not found/permission."); return
        t_desc = t_details[0][:20]
        if messagebox.askyesno("Confirm", f"Delete '{t_desc}...'?"):
            if self.controller.db_manager.delete_task(tid): 
                self.refresh_data(); self.controller.update_status(f"Task '{t_desc}...' deleted.", 3000)
            else: messagebox.showerror("DB Error", "Delete failed."); self.controller.update_status("Task delete failed.", 3000)


class StudyTrackerFrame(ttk.Frame): # Updated with Pomodoro
    def __init__(self, parent, controller):
        super().__init__(parent)
        self.controller = controller
        self.timer_running = False; self.start_time = None; self.timer_id = None
        self.pomodoro_mode = tk.BooleanVar(value=False)
        self.pomodoro_state = "work" 
        self.pomodoro_cycles_done = 0
        
        ttk.Label(self, text="Study Session Logger & Pomodoro", style="Header.TLabel").pack(pady=10) # Removed emoji
        
        timer_control_frame = ttk.Frame(self); timer_control_frame.pack(fill=tk.X, padx=20, pady=(5,0))
        self.timer_label = ttk.Label(timer_control_frame, text="Timer: 00:00:00", font=("Arial", 16, "bold"))
        self.timer_label.pack(side=tk.LEFT, padx=(0,10))
        self.start_timer_button = ttk.Button(timer_control_frame, text="Start Timer", command=self.toggle_timer, width=12)
        self.start_timer_button.pack(side=tk.LEFT, padx=5)
        self.reset_timer_button = ttk.Button(timer_control_frame, text="Reset Timer", command=self.reset_timer, width=12)
        self.reset_timer_button.pack(side=tk.LEFT, padx=5)

        pomodoro_frame = ttk.Frame(self, padding=(0,5)); pomodoro_frame.pack(fill=tk.X, padx=20)
        ttk.Checkbutton(pomodoro_frame, text="Pomodoro Mode", variable=self.pomodoro_mode, command=self.toggle_pomodoro_mode_ui, style="TCheckbutton").pack(side=tk.LEFT, padx=(0,10))
        self.pomodoro_status_label = ttk.Label(pomodoro_frame, text="Mode: Standard Timer", font=("Arial", 10, "italic"))
        self.pomodoro_status_label.pack(side=tk.LEFT)
        self.pomodoro_cycle_label = ttk.Label(pomodoro_frame, text="", font=("Arial", 10))
        self.pomodoro_cycle_label.pack(side=tk.LEFT, padx=10)

        form_frame = ttk.Frame(self, padding=20); form_frame.pack(expand=False, fill=tk.X, pady=5) 
        ttk.Label(form_frame, text="Subject:").grid(row=0, column=0, padx=5, pady=5, sticky=tk.W)
        self.subject_entry = ttk.Entry(form_frame, width=40, font=("Arial", 10)); self.subject_entry.grid(row=0, column=1, padx=5, pady=5, sticky=tk.EW, ipady=2)
        ttk.Label(form_frame, text="Duration (min):").grid(row=1, column=0, padx=5, pady=5, sticky=tk.W)
        self.duration_entry = ttk.Entry(form_frame, width=10, font=("Arial", 10)); self.duration_entry.grid(row=1, column=1, padx=5, pady=5, sticky=tk.W, ipady=2)
        ttk.Label(form_frame, text="Notes:").grid(row=2, column=0, padx=5, pady=5, sticky=tk.NW)
        self.notes_text = scrolledtext.ScrolledText(form_frame, width=38, height=3, wrap=tk.WORD, font=("Arial", 10)); self.notes_text.grid(row=2, column=1, padx=5, pady=5, sticky=tk.EW)
        form_frame.columnconfigure(1, weight=1) 
        ttk.Button(form_frame, text="Log Session", command=self.log_session).grid(row=3, column=0, columnspan=2, pady=10)
        ttk.Label(self, text="Recent Study Logs:", style="SubHeader.TLabel").pack(pady=(5,5)) 
        log_display_frame = ttk.Frame(self); log_display_frame.pack(fill=tk.BOTH, expand=True, padx=20, pady=(0,5))
        cols = ("Subject", "Date", "Duration", "Notes"); self.log_tree = ttk.Treeview(log_display_frame, columns=cols, show="headings", style="Treeview", height=5)
        for col in cols: self.log_tree.heading(col, text=col)
        self.log_tree.column("Subject", width=200); self.log_tree.column("Date", width=120, anchor=tk.CENTER)
        self.log_tree.column("Duration", width=100, anchor=tk.CENTER); self.log_tree.column("Notes", width=300)
        self.log_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar = ttk.Scrollbar(log_display_frame, orient=tk.VERTICAL, command=self.log_tree.yview)
        self.log_tree.configure(yscroll=scrollbar.set); scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        ttk.Button(self, text="Back to Main Menu", command=lambda: self.controller.show_frame("MainPage")).pack(pady=10, side=tk.BOTTOM)

    def toggle_pomodoro_mode_ui(self): # Same
        if self.pomodoro_mode.get():
            self.pomodoro_status_label.config(text=f"Mode: Pomodoro ({self.controller.pomodoro_work_duration.get()}m work / {self.controller.pomodoro_break_duration.get()}m break)")
            self.reset_timer() 
        else:
            self.pomodoro_status_label.config(text="Mode: Standard Timer"); self.pomodoro_cycle_label.config(text=""); self.reset_timer() 

    def update_timer_display(self): # Same
        if self.timer_running and self.start_time:
            el_s = int(time.time() - self.start_time)
            if self.pomodoro_mode.get():
                curr_dur_s = (self.controller.pomodoro_work_duration.get() if self.pomodoro_state == "work" else self.controller.pomodoro_break_duration.get()) * 60
                rem_s = curr_dur_s - el_s
                if rem_s <= 0: 
                    if self.pomodoro_state == "work":
                        self.pomodoro_state = "break"; self.pomodoro_cycles_done +=1; self.pomodoro_cycle_label.config(text=f"Cycles: {self.pomodoro_cycles_done}")
                        self.controller.update_status("Pomodoro: Break time!", 0); messagebox.showinfo("Pomodoro Break", f"Work done! Break for {self.controller.pomodoro_break_duration.get()} min.")
                    else: 
                        self.pomodoro_state = "work"; self.controller.update_status("Pomodoro: Work time!", 0); messagebox.showinfo("Pomodoro Work", "Break over! Next session.")
                    self.start_time = time.time(); el_s = 0; rem_s = (self.controller.pomodoro_work_duration.get() if self.pomodoro_state == "work" else self.controller.pomodoro_break_duration.get()) * 60
                h,r=divmod(rem_s,3600);m,s=divmod(r,60); self.timer_label.config(text=f"{self.pomodoro_state.capitalize()}: {h:02}:{m:02}:{s:02}")
            else: h,r=divmod(el_s,3600);m,s=divmod(r,60); self.timer_label.config(text=f"Timer: {h:02}:{m:02}:{s:02}")
            self.timer_id = self.after(1000, self.update_timer_display)

    def toggle_timer(self): # Same
        if self.timer_running: 
            self.timer_running=False; 
            if self.timer_id: self.after_cancel(self.timer_id); self.timer_id=None
            self.start_timer_button.config(text="Start Timer")
            if self.start_time and not self.pomodoro_mode.get(): 
                el_min=int((time.time()-self.start_time)/60); self.duration_entry.delete(0,tk.END); self.duration_entry.insert(0,str(el_min if el_min>0 else 1)) 
            self.controller.update_status(f"Timer stopped.",3000)
        else: 
            self.timer_running=True; self.start_time=time.time(); self.start_timer_button.config(text="Stop Timer")
            if self.pomodoro_mode.get():
                self.pomodoro_state="work"; self.pomodoro_cycle_label.config(text=f"Cycles: {self.pomodoro_cycles_done}"); self.controller.update_status(f"Pomodoro work started!",3000)
            else: self.controller.update_status("Timer started!",3000)
            self.update_timer_display()

    def reset_timer(self): # Same
        if self.timer_running: self.toggle_timer() 
        self.start_time=None; self.pomodoro_cycles_done=0; self.pomodoro_state="work" 
        if self.pomodoro_mode.get(): self.timer_label.config(text=f"Work: {self.controller.pomodoro_work_duration.get():02}:00:00"); self.pomodoro_cycle_label.config(text="Cycles: 0")
        else: self.timer_label.config(text="Timer: 00:00:00"); self.pomodoro_cycle_label.config(text="")
        self.duration_entry.delete(0,tk.END); self.controller.update_status("Timer reset.",3000)

    def log_session(self): # Same
        subj=self.subject_entry.get().strip(); dur_str=self.duration_entry.get().strip(); notes=self.notes_text.get("1.0",tk.END).strip() 
        if not subj or not dur_str: messagebox.showerror("Error","Subject/duration required."); return
        try:
            dur_min=int(dur_str); 
            if dur_min<=0: raise ValueError("Duration positive.")
        except ValueError: messagebox.showerror("Error","Invalid duration."); return
        uid=self.controller.current_user_id
        if uid:
            start_s=datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S") 
            if self.controller.db_manager.add_study_log(uid,subj,start_s,dur_min,notes):
                self.controller.update_status(f"Session '{subj}' logged.",3000)
                self.subject_entry.delete(0,tk.END); self.duration_entry.delete(0,tk.END); self.notes_text.delete("1.0",tk.END); self.reset_timer(); self.refresh_data() 
            else: messagebox.showerror("DB Error","Log failed."); self.controller.update_status("Log failed.",3000)
        else: messagebox.showerror("Auth Error","No user."); self.controller.show_frame("LoginPage")

    def refresh_data(self): # Same
        if not self.controller.current_user_id: self.controller.show_frame("LoginPage"); return
        for i in self.log_tree.get_children(): self.log_tree.delete(i)
        logs=self.controller.db_manager.get_study_logs(self.controller.current_user_id,limit=100) 
        if logs:
            for log in logs: 
                _,s,st,dur,n=log; 
                try: dt=datetime.datetime.strptime(st,"%Y-%m-%d %H:%M:%S"); date_d=dt.strftime("%Y-%m-%d %H:%M")
                except ValueError: date_d=st 
                dur_d=f"{dur} min"; self.log_tree.insert("","end",values=(s,date_d,dur_d,n))
        self.toggle_pomodoro_mode_ui(); 
        if not self.timer_running: self.controller.update_status("Study Tracker ready.")


class QuizFrame(ttk.Frame): # Kept for context, largely same
    def __init__(self, parent, controller): 
        super().__init__(parent); self.controller = controller; self.quiz_questions_full_data = []; self.current_question_index = 0
        self.score = 0; self.quiz_topic = ""; self.num_questions_to_generate = 5 
        setup_frame = ttk.Frame(self, padding=10); setup_frame.pack(pady=10, fill=tk.X)
        ttk.Label(setup_frame, text="Quiz Topic:", font=("Arial", 12)).pack(side=tk.LEFT, padx=5)
        self.topic_entry = ttk.Entry(setup_frame, width=30, font=("Arial", 11)); self.topic_entry.pack(side=tk.LEFT, padx=5, expand=True, fill=tk.X, ipady=2)
        self.topic_entry.insert(0, "World Capitals") 
        ttk.Label(setup_frame, text="#Q:", font=("Arial", 12)).pack(side=tk.LEFT, padx=(10,0)) 
        self.num_questions_spinbox = ttk.Spinbox(setup_frame, from_=3, to=10, width=3, font=("Arial", 11), state="readonly", wrap=True)
        self.num_questions_spinbox.set(self.num_questions_to_generate); self.num_questions_spinbox.pack(side=tk.LEFT, padx=(0,5))
        self.generate_button = ttk.Button(setup_frame, text="Generate AI Quiz", command=self.start_quiz_generation_thread); self.generate_button.pack(side=tk.LEFT, padx=10)
        self.loading_label = ttk.Label(setup_frame, text="", style="Placeholder.TLabel"); self.loading_label.pack(side=tk.LEFT, padx=5)
        self.quiz_area = ttk.Frame(self, padding=10)
        self.question_label = ttk.Label(self.quiz_area, text="", wraplength=750, font=("Arial", 14, "bold"), anchor="center", justify=tk.CENTER); self.question_label.pack(pady=20, fill=tk.X)
        self.radio_var = tk.StringVar(); self.option_buttons_frame = ttk.Frame(self.quiz_area) 
        self.option_buttons_frame.pack(pady=10, fill=tk.X, padx=20); self.option_buttons = [] 
        for i in range(4): rb = ttk.Radiobutton(self.option_buttons_frame, text="", variable=self.radio_var, value="", style="TRadiobutton"); self.option_buttons.append(rb)
        self.submit_button = ttk.Button(self.quiz_area, text="Submit Answer", command=self.submit_answer, state=tk.DISABLED); self.submit_button.pack(pady=20)
        self.feedback_label = ttk.Label(self.quiz_area, text="", font=("Arial", 11), wraplength=750, justify=tk.CENTER); self.feedback_label.pack(pady=10)
        self.result_area = ttk.Frame(self, padding=10)
        self.result_label = ttk.Label(self.result_area, text="", font=("Arial", 16, "bold"), anchor="center", justify=tk.CENTER); self.result_label.pack(pady=20, fill=tk.X)
        self.post_quiz_button_frame = ttk.Frame(self.result_area); self.post_quiz_button_frame.pack(pady=10)
        self.review_quiz_button = ttk.Button(self.post_quiz_button_frame, text="Review Quiz", command=self.review_quiz, state=tk.DISABLED); self.review_quiz_button.pack(side=tk.LEFT, padx=5)
        ttk.Button(self.post_quiz_button_frame, text="Try Another Quiz", command=self.reset_for_new_quiz).pack(side=tk.LEFT, padx=5)
        ttk.Button(self, text="Back to Main Menu", command=self.go_back_to_main).pack(side=tk.BOTTOM, pady=20)
    def go_back_to_main(self): self.reset_quiz_ui(); self.controller.show_frame("MainPage")
    def start_quiz_generation_thread(self): # Same
        self.quiz_topic=self.topic_entry.get().strip(); self.num_questions_to_generate=int(self.num_questions_spinbox.get())
        if not self.quiz_topic: messagebox.showerror("Error","Topic empty."); return
        self.loading_label.config(text="Generating..."); self.generate_button.config(state=tk.DISABLED); self.reset_quiz_ui_elements() 
        threading.Thread(target=self.generate_ai_quiz,daemon=True).start()
    def generate_ai_quiz(self): # Same
        api_key=GEMINI_API_KEY or self.controller.db_manager.get_config_value('GEMINI_API_KEY') or ""
        if not api_key: self.controller.after(0,lambda:messagebox.showerror("API Key Error","Key missing.")); self.controller.after(0,self.generation_finished); return
        prompt = (f"Gen {self.num_questions_to_generate} MCQ on '{self.quiz_topic}'. Each: 'question_text', 'options' (4 strings), 'correct_option_index' (0-3 int), 'explanation'.")
        payload = {"contents": [{"role": "user", "parts": [{"text": prompt}]}],"generationConfig": {"responseMimeType": "application/json","responseSchema": {"type": "ARRAY", "items": { "type": "OBJECT", "properties": {"question_text": {"type": "STRING"}, "options": { "type": "ARRAY", "items": {"type": "STRING"}, "minItems": 4, "maxItems": 4},"correct_option_index": {"type": "INTEGER"}, "explanation": {"type": "STRING"}},"required": ["question_text", "options", "correct_option_index", "explanation"]}}}}
        url=f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={api_key}"
        try:
            import requests; r=requests.post(url,headers={'Content-Type':'application/json'},json=payload,timeout=90); r.raise_for_status(); res=r.json()
            if res.get("candidates") and res["candidates"][0].get("content",{}).get("parts"):
                txt=res["candidates"][0]["content"]["parts"][0].get("text")
                if txt:
                    data=json.loads(txt); v_q=[]
                    if isinstance(data,list):
                        for q in data:
                            if isinstance(q,dict) and all(k in q for k in ["question_text","options","correct_option_index","explanation"]) and isinstance(q.get("options",[]),list) and len(q["options"])==4 and all(isinstance(o,str) for o in q["options"]) and isinstance(q.get("correct_option_index",-1),int) and 0<=q["correct_option_index"]<=3:
                                q_c=q.copy(); q_c['user_answer_index']=None; v_q.append(q_c)
                        self.quiz_questions_full_data=v_q
                    if self.quiz_questions_full_data: self.controller.after(0,self.display_quiz_start); self.controller.after(0,lambda:self.controller.update_status(f"Quiz '{self.quiz_topic}' ready!",3000))
                    else: self.controller.after(0,lambda:messagebox.showwarning("Quiz Gen","AI gave no valid Qs.")); self.controller.after(0,lambda:self.controller.update_status("Quiz gen failed.",3000))
                else: self.controller.after(0,lambda:messagebox.showerror("API Error","AI response no content."))
            else: 
                err="API response unexpected."; fb=res.get("promptFeedback",{}); br=fb.get("blockReason"); 
                if br: err+=f" Blocked: {br}"
                elif res.get("error"): err+=f" API Error: {res['error'].get('message','Unknown')}"
                self.controller.after(0,lambda:messagebox.showerror("API Error",err))
        except Exception as e: print(f"Quiz gen err: {e}"); self.controller.after(0,lambda:messagebox.showerror("Error",f"Quiz error: {e}"))
        finally: self.controller.after(0,self.generation_finished)
    def generation_finished(self): self.loading_label.config(text=""); self.generate_button.config(state=tk.NORMAL)
    def display_quiz_start(self): # Same
        if not self.quiz_questions_full_data: messagebox.showwarning("Quiz Not Ready","No Qs."); self.reset_quiz_ui(); return
        self.current_question_index=0; self.score=0; self.quiz_area.pack(fill=tk.BOTH,expand=True)
        self.result_area.pack_forget(); self.review_quiz_button.config(state=tk.DISABLED); self.display_question()
    def display_question(self): # Same
        self.submit_button.config(state=tk.NORMAL)
        if self.current_question_index < len(self.quiz_questions_full_data):
            q=self.quiz_questions_full_data[self.current_question_index]
            self.question_label.config(text=f"Q{self.current_question_index+1}: {q['question_text']}")
            self.radio_var.set(None); self.feedback_label.config(text="",style="TLabel")
            for w in self.option_buttons_frame.winfo_children(): w.pack_forget()
            for i,opt in enumerate(q['options']):
                self.option_buttons[i].config(text=opt,value=opt,state=tk.NORMAL)
                self.option_buttons[i].pack(anchor=tk.W,padx=30,pady=5,fill=tk.X)
            self.submit_button.config(text="Submit Answer",command=self.submit_answer)
        else: self.show_results()
    def submit_answer(self): # Same
        sel_ans=self.radio_var.get()
        if not sel_ans: messagebox.showwarning("No Answer","Select option."); return
        q=self.quiz_questions_full_data[self.current_question_index]
        try: sel_idx=q['options'].index(sel_ans)
        except ValueError: messagebox.showerror("Error","Selected ans not in opts."); return
        q['user_answer_index']=sel_idx
        corr_idx=q['correct_option_index']; corr_txt=q['options'][corr_idx]
        is_c=(sel_idx==corr_idx)
        if is_c: self.score+=1; self.feedback_label.config(text=f"Correct! {q.get('explanation','')}",style="Success.TLabel")
        else: self.feedback_label.config(text=f"Incorrect. Correct: \"{corr_txt}\".\nExp: {q.get('explanation','')}",style="Error.TLabel")
        for rb in self.option_buttons: rb.config(state=tk.DISABLED)
        self.submit_button.config(text="Next Question",command=self.next_question)
    def next_question(self): # Same
        self.current_question_index+=1
        if self.current_question_index < len(self.quiz_questions_full_data): self.display_question()
        else: self.show_results()
    def show_results(self): # Same
        self.quiz_area.pack_forget(); self.result_area.pack(fill=tk.BOTH,expand=True); self.review_quiz_button.config(state=tk.NORMAL)
        num_q=len(self.quiz_questions_full_data)
        self.result_label.config(text=f"Quiz Finished!\nTopic: {self.quiz_topic}\nScore: {self.score}/{num_q}")
        self.controller.update_status(f"Quiz '{self.quiz_topic}' done. Score: {self.score}/{num_q}",5000)
        if self.controller.current_user_id and num_q>0:
            q_date=datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            q_data_store=[{'question_text':q["question_text"],'options':q["options"],'correct_option_index':q["correct_option_index"],'explanation':q["explanation"],'user_answer_index':q["user_answer_index"]} for q in self.quiz_questions_full_data] 
            q_json=json.dumps(q_data_store)
            self.controller.db_manager.add_quiz_attempt(self.controller.current_user_id,self.quiz_topic,q_date,self.score,num_q,q_json)
    def review_quiz(self): # Same
        if not self.quiz_questions_full_data: messagebox.showinfo("No Quiz Data","No quiz to review."); return
        rev=tk.Toplevel(self.controller); rev.title(f"Review: {self.quiz_topic}"); rev.geometry("700x550"); rev.configure(bg="#e8eaf6")
        QuizReviewer(rev,self.quiz_questions_full_data,self.controller); self.controller.update_status(f"Reviewing quiz: {self.quiz_topic}")
    def reset_for_new_quiz(self): # Same
        self.result_area.pack_forget(); self.quiz_area.pack_forget(); self.topic_entry.delete(0,tk.END); self.topic_entry.insert(0,"World History")
        self.num_questions_spinbox.set(self.num_questions_to_generate); self.generate_button.config(state=tk.NORMAL)
        self.review_quiz_button.config(state=tk.DISABLED); self.quiz_questions_full_data=[]; self.reset_quiz_ui_elements()
    def reset_quiz_ui(self): # Same
        self.quiz_area.pack_forget(); self.result_area.pack_forget(); self.reset_quiz_ui_elements()
        self.quiz_questions_full_data=[]; self.current_question_index=0; self.score=0; self.quiz_topic=""
        self.generate_button.config(state=tk.NORMAL); self.review_quiz_button.config(state=tk.DISABLED)
    def reset_quiz_ui_elements(self): # Same
        self.question_label.config(text=""); self.feedback_label.config(text="",style="TLabel"); self.radio_var.set(None)
        for rb in self.option_buttons: rb.pack_forget()
        self.submit_button.config(text="Submit Answer",state=tk.DISABLED); self.loading_label.config(text="")
    def refresh_data(self): self.reset_quiz_ui(); self.controller.update_status("Ready for new quiz.")

class QuizReviewer(ttk.Frame): # Kept for context, logic same
    def __init__(self, parent_window, quiz_data, controller): 
        super().__init__(parent_window, padding=15); self.parent_window = parent_window; self.quiz_data = quiz_data
        self.controller = controller; self.current_review_index = 0; self.pack(fill=tk.BOTH, expand=True)
        self.question_text_label = ttk.Label(self, text="", style="SubHeader.TLabel", wraplength=650, justify=tk.LEFT); self.question_text_label.pack(pady=(0,10), anchor="w")
        self.options_frame = ttk.Frame(self); self.options_frame.pack(pady=5, fill=tk.X, anchor="w")
        self.user_answer_label = ttk.Label(self, text="", font=("Arial", 10), wraplength=650, justify=tk.LEFT); self.user_answer_label.pack(pady=2, anchor="w")
        self.correct_answer_label = ttk.Label(self, text="", font=("Arial", 10, "bold"), wraplength=650, justify=tk.LEFT); self.correct_answer_label.pack(pady=2, anchor="w")
        self.explanation_label = ttk.Label(self, text="", font=("Arial", 10, "italic"), wraplength=650, justify=tk.LEFT); self.explanation_label.pack(pady=(5,10), anchor="w")
        nav_frame = ttk.Frame(self); nav_frame.pack(pady=10, fill=tk.X)
        self.prev_button = ttk.Button(nav_frame, text="⬅ Previous", command=self.prev_question_review); self.prev_button.pack(side=tk.LEFT, padx=5)
        self.next_button = ttk.Button(nav_frame, text="Next ➡", command=self.next_question_review); self.next_button.pack(side=tk.LEFT, padx=5)
        self.q_counter_label = ttk.Label(nav_frame, text=""); self.q_counter_label.pack(side=tk.LEFT, padx=10)
        ttk.Button(self, text="Close Review", command=self.parent_window.destroy).pack(pady=10); self.display_review_question()
    def display_review_question(self): # Same
        if not (0 <= self.current_review_index < len(self.quiz_data)): return
        q_item = self.quiz_data[self.current_review_index]
        self.question_text_label.config(text=f"Q{self.current_review_index + 1}: {q_item['question_text']}")
        for w in self.options_frame.winfo_children(): w.destroy()
        for i, opt_txt in enumerate(q_item['options']):
            opt_lbl_txt = f"  {chr(65+i)}. {opt_txt}"; style = "TLabel"; prefix = "  "
            if i == q_item['correct_option_index']: prefix = "✔ "; style = "Success.TLabel"
            if i == q_item.get('user_answer_index'): 
                if i == q_item['correct_option_index']: prefix = "✔ "
                else: prefix = "❌ "; style = "Error.TLabel" if style != "Success.TLabel" else style
            ttk.Label(self.options_frame, text=f"{prefix}{opt_lbl_txt.strip()}", style=style).pack(anchor="w")
        usr_ans_idx = q_item.get('user_answer_index')
        usr_ans_txt = q_item['options'][usr_ans_idx] if usr_ans_idx is not None and 0 <= usr_ans_idx < len(q_item['options']) else "Not answered"
        self.user_answer_label.config(text=f"Your Answer: {usr_ans_txt}")
        corr_ans_txt = q_item['options'][q_item['correct_option_index']]
        self.correct_answer_label.config(text=f"Correct Answer: {corr_ans_txt}", style="Success.TLabel")
        self.explanation_label.config(text=f"Explanation: {q_item['explanation']}")
        self.q_counter_label.config(text=f"Q {self.current_review_index + 1}/{len(self.quiz_data)}")
        self.prev_button.config(state=tk.NORMAL if self.current_review_index > 0 else tk.DISABLED)
        self.next_button.config(state=tk.NORMAL if self.current_review_index < len(self.quiz_data) - 1 else tk.DISABLED)
    def prev_question_review(self): # Same
        if self.current_review_index > 0: self.current_review_index -= 1; self.display_review_question()
    def next_question_review(self): # Same
        if self.current_review_index < len(self.quiz_data) - 1: self.current_review_index += 1; self.display_review_question()

class AIHelperFrame(ttk.Frame): # Kept for context, logic largely same
    def __init__(self, parent, controller):
        super().__init__(parent); self.controller = controller
        ttk.Label(self, text="AI Study Helper (Gemini)", style="Header.TLabel").pack(pady=10) # Clarified Gemini
        input_area = ttk.Frame(self, padding=10); input_area.pack(fill=tk.X, padx=20)
        ttk.Label(input_area, text="Topic, Concept, or Text to Summarize:").pack(anchor="w")
        self.ai_input_text = scrolledtext.ScrolledText(input_area, height=5, width=70, wrap=tk.WORD, font=("Arial", 10)); self.ai_input_text.pack(fill=tk.X, expand=True, pady=(0,5))
        title_frame = ttk.Frame(input_area); title_frame.pack(fill=tk.X, pady=(0,5))
        ttk.Label(title_frame, text="Title for Saving (Optional):").pack(side=tk.LEFT)
        self.save_title_entry = ttk.Entry(title_frame, width=40, font=("Arial", 10)); self.save_title_entry.pack(side=tk.LEFT, padx=5, expand=True, fill=tk.X)
        action_frame = ttk.Frame(input_area); action_frame.pack(fill=tk.X)
        self.explain_button = ttk.Button(action_frame, text="Explain", command=lambda: self.get_ai_help("explain")); self.explain_button.pack(side=tk.LEFT, padx=2)
        self.summarize_button = ttk.Button(action_frame, text="Summarize", command=lambda: self.get_ai_help("summarize")); self.summarize_button.pack(side=tk.LEFT, padx=2)
        self.practice_q_button = ttk.Button(action_frame, text="Practice Qs", command=lambda: self.get_ai_help("practice_questions")); self.practice_q_button.pack(side=tk.LEFT, padx=2)
        self.ai_helper_loading_label = ttk.Label(action_frame, text="", style="Placeholder.TLabel"); self.ai_helper_loading_label.pack(side=tk.LEFT, padx=5)
        ttk.Label(self, text="AI Response:", style="SubHeader.TLabel").pack(pady=(5,5), padx=20, anchor="w")
        self.ai_output_text = scrolledtext.ScrolledText(self, height=12, width=70, wrap=tk.WORD, state=tk.DISABLED, font=("Arial", 10)); self.ai_output_text.pack(fill=tk.BOTH, expand=True, padx=20, pady=(0,5))
        save_button_frame = ttk.Frame(self); save_button_frame.pack(pady=5, padx=20, fill=tk.X)
        self.save_ai_response_button = ttk.Button(save_button_frame, text="Save AI Response", command=self.save_ai_response, state=tk.DISABLED) # Removed emoji
        self.save_ai_response_button.pack(anchor="e") 
        ttk.Button(self, text="Back to Main Menu", command=lambda: controller.show_frame("MainPage")).pack(pady=10, side=tk.BOTTOM)
        self.current_ai_mode = None 
    def get_ai_help(self, mode): # Same
        user_input = self.ai_input_text.get("1.0", tk.END).strip()
        if not user_input: messagebox.showwarning("Input Required", "Enter text or topic."); return
        self.current_ai_mode = mode; self.ai_helper_loading_label.config(text="AI thinking...", style="Placeholder.TLabel")
        self.explain_button.config(state=tk.DISABLED); self.summarize_button.config(state=tk.DISABLED); self.practice_q_button.config(state=tk.DISABLED)
        self.save_ai_response_button.config(state=tk.DISABLED)
        self.ai_output_text.config(state=tk.NORMAL); self.ai_output_text.delete("1.0", tk.END); self.ai_output_text.config(state=tk.DISABLED)
        threading.Thread(target=self._call_ai_for_help, args=(user_input, mode), daemon=True).start()
    def _call_ai_for_help(self, text_input, mode): # Same
        api_key = GEMINI_API_KEY or self.controller.db_manager.get_config_value('GEMINI_API_KEY') or ""
        if not api_key: self.controller.after(0,lambda:self._update_ai_output("Gemini API Key missing.",is_error=True)); self.controller.after(0,self._ai_help_finished); return
        prompt = ""
        if mode == "explain": prompt = f"Explain '{text_input}' clearly for a student."
        elif mode == "summarize": prompt = f"Summarize for a student:\n\n{text_input}"
        elif mode == "practice_questions": prompt = f"Generate 3-4 open-ended/short factual recall practice questions on '{text_input}' for a student. No answers."
        else: self.controller.after(0,lambda:self._update_ai_output("Invalid mode.",is_error=True)); self.controller.after(0,self._ai_help_finished); return
        payload = {"contents": [{"role": "user", "parts": [{"text": prompt}]}]}
        url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={api_key}"
        try:
            import requests; r=requests.post(url,headers={'Content-Type':'application/json'},json=payload,timeout=45); r.raise_for_status(); res=r.json()
            if res.get("candidates") and res["candidates"][0].get("content",{}).get("parts"):
                ai_txt = res["candidates"][0]["content"]["parts"][0].get("text","No response.").strip()
                self.controller.after(0,lambda:self._update_ai_output(ai_txt))
            else: self.controller.after(0,lambda:self._update_ai_output("AI response empty/malformed.",is_error=True))
        except Exception as e: print(f"AI Helper err: {e}"); self.controller.after(0,lambda:self._update_ai_output(f"Error: {e}",is_error=True))
        finally: self.controller.after(0,self._ai_help_finished)
    def _update_ai_output(self, text, is_error=False): # Same
        self.ai_output_text.config(state=tk.NORMAL); self.ai_output_text.delete("1.0", tk.END)
        self.ai_output_text.insert(tk.END, text); self.ai_output_text.config(state=tk.DISABLED)
        if is_error: self.controller.update_status("AI Helper error.", 3000); self.save_ai_response_button.config(state=tk.DISABLED)
        else: self.controller.update_status("AI response received.", 3000); self.save_ai_response_button.config(state=tk.NORMAL)
    def _ai_help_finished(self): # Same
        self.ai_helper_loading_label.config(text="")
        self.explain_button.config(state=tk.NORMAL); self.summarize_button.config(state=tk.NORMAL); self.practice_q_button.config(state=tk.NORMAL)
    def save_ai_response(self): # Same
        if not self.controller.current_user_id: return
        output_text = self.ai_output_text.get("1.0", tk.END).strip()
        if not output_text or output_text == "No response from AI." or "Error contacting AI" in output_text: messagebox.showwarning("Cannot Save", "No valid AI response."); return
        title = self.save_title_entry.get().strip()
        if not title: 
            input_preview = self.ai_input_text.get("1.0", "1.50").strip() 
            if input_preview: title = f"{self.current_ai_mode.capitalize()}: {input_preview}..."
            else: title = f"{self.current_ai_mode.capitalize()} - {datetime.datetime.now().strftime('%Y-%m-%d %H:%M')}"
        input_text_for_db = self.ai_input_text.get("1.0", tk.END).strip() 
        if self.controller.db_manager.add_ai_content(self.controller.current_user_id, self.current_ai_mode, title, output_text, input_text_for_db):
            messagebox.showinfo("Saved", f"AI response '{title}' saved!"); self.controller.update_status("AI response saved.", 3000); self.save_title_entry.delete(0, tk.END)
        else: messagebox.showerror("Error", "Failed to save AI response."); self.controller.update_status("Failed to save AI response.", 3000)
    def refresh_data(self): # Same
        self.ai_input_text.delete("1.0", tk.END); self.save_title_entry.delete(0, tk.END)
        self.ai_output_text.config(state=tk.NORMAL); self.ai_output_text.delete("1.0", tk.END); self.ai_output_text.config(state=tk.DISABLED)
        self.save_ai_response_button.config(state=tk.DISABLED); self.controller.update_status("AI Helper ready.")

class SettingsFrame(ttk.Frame): # Updated to remove OpenAI API Key field
    def __init__(self, parent, controller):
        super().__init__(parent); self.controller = controller
        ttk.Label(self, text="Application Settings", style="Header.TLabel").pack(pady=10) 
        
        api_keys_frame = ttk.LabelFrame(self, text="API Key Management", padding=10)
        api_keys_frame.pack(pady=10, padx=20, fill=tk.X)
        ttk.Label(api_keys_frame, text="Gemini API Key (for all AI features):").grid(row=0, column=0, padx=5, pady=5, sticky="w")
        self.gemini_api_key_entry = ttk.Entry(api_keys_frame, width=40, show="*")
        self.gemini_api_key_entry.grid(row=0, column=1, padx=5, pady=5, sticky="ew")
        ttk.Button(api_keys_frame, text="Save Gemini Key", command=lambda: self.save_api_key('GEMINI_API_KEY', self.gemini_api_key_entry.get())).grid(row=0, column=2, padx=5)
        api_keys_frame.columnconfigure(1, weight=1)

        cat_frame = ttk.LabelFrame(self, text="Manage Task Categories", padding=10); cat_frame.pack(pady=10, padx=20, fill=tk.X)
        self.category_listbox = tk.Listbox(cat_frame, height=5, font=("Arial", 10)); self.category_listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0,10))
        cat_btn_frame = ttk.Frame(cat_frame); cat_btn_frame.pack(side=tk.LEFT, fill=tk.Y)
        ttk.Label(cat_btn_frame, text="New Category:").pack(anchor="w")
        self.new_category_entry = ttk.Entry(cat_btn_frame, width=20, font=("Arial", 10)); self.new_category_entry.pack(pady=(0,5), ipady=2)
        ttk.Button(cat_btn_frame, text="Add Category", command=self.add_category).pack(fill=tk.X, pady=2)
        ttk.Button(cat_btn_frame, text="Delete Selected", command=self.delete_category, style="Danger.TButton").pack(fill=tk.X, pady=2)
        
        pomo_settings_frame = ttk.LabelFrame(self, text="Pomodoro Timer Settings (minutes)", padding=10); pomo_settings_frame.pack(pady=10, padx=20, fill=tk.X)
        ttk.Label(pomo_settings_frame, text="Work Duration:").grid(row=0, column=0, padx=5, pady=5, sticky="w")
        self.pomo_work_spinbox = ttk.Spinbox(pomo_settings_frame, from_=5, to=60, increment=5, width=5, textvariable=controller.pomodoro_work_duration, font=("Arial", 10)); self.pomo_work_spinbox.grid(row=0, column=1, padx=5, pady=5)
        ttk.Label(pomo_settings_frame, text="Break Duration:").grid(row=1, column=0, padx=5, pady=5, sticky="w")
        self.pomo_break_spinbox = ttk.Spinbox(pomo_settings_frame, from_=1, to=30, increment=1, width=5, textvariable=controller.pomodoro_break_duration, font=("Arial", 10)); self.pomo_break_spinbox.grid(row=1, column=1, padx=5, pady=5)
        
        db_frame = ttk.LabelFrame(self, text="Database Management", padding=10); db_frame.pack(pady=10, padx=20, fill=tk.X)
        ttk.Button(db_frame, text="Backup Database", command=self.backup_database).pack(side=tk.LEFT, padx=10, ipady=3)
        ttk.Button(db_frame, text="Restore Database", command=self.restore_database).pack(side=tk.LEFT, padx=10, ipady=3)
        ttk.Button(self, text="Back to Main Menu", command=lambda: controller.show_frame("MainPage")).pack(pady=20, side=tk.BOTTOM)

    def save_api_key(self, key_name, key_value):
        if not key_value: messagebox.showwarning("API Key", f"{key_name.replace('_', ' ')} cannot be empty."); return
        self.controller.db_manager.set_config_value(key_name, key_value)
        messagebox.showinfo("API Key Saved", f"{key_name.replace('_', ' ')} saved. Restart might be needed.")
        self.controller.update_status(f"{key_name.replace('_', ' ')} saved.", 3000)
        if key_name == 'GEMINI_API_KEY': global GEMINI_API_KEY; GEMINI_API_KEY = key_value; self.gemini_api_key_entry.delete(0, tk.END)

    def load_api_keys(self):
        gemini_key = self.controller.db_manager.get_config_value('GEMINI_API_KEY')
        self.gemini_api_key_entry.delete(0, tk.END)
        if gemini_key: self.gemini_api_key_entry.insert(0, gemini_key) 

    def load_user_categories(self): # Same
        self.category_listbox.delete(0,tk.END)
        if self.controller.current_user_id:
            cats=self.controller.db_manager.get_task_categories(self.controller.current_user_id)
            for c in cats: self.category_listbox.insert(tk.END,c)
    def add_category(self): # Same
        name=self.new_category_entry.get().strip()
        if not name: messagebox.showwarning("Input Error","Category name empty."); return
        if not self.controller.current_user_id: return
        if self.controller.db_manager.add_task_category(self.controller.current_user_id,name):
            self.load_user_categories(); self.new_category_entry.delete(0,tk.END)
            self.controller.update_status(f"Category '{name}' added.",3000)
        else: messagebox.showerror("Error",f"Failed to add '{name}'. Exists?"); self.controller.update_status("Add category failed.",3000)
    def delete_category(self): # Same
        sel=self.category_listbox.curselection()
        if not sel: messagebox.showwarning("Selection Error","Select category."); return
        name_del=self.category_listbox.get(sel[0])
        if name_del.lower()=='general': messagebox.showerror("Error","'General' cannot be deleted."); return
        if not self.controller.current_user_id: return
        if messagebox.askyesno("Confirm",f"Delete '{name_del}'? Tasks moved to 'General'."):
            if self.controller.db_manager.delete_task_category(self.controller.current_user_id,name_del):
                self.load_user_categories(); self.controller.update_status(f"Category '{name_del}' deleted.",3000)
            else: messagebox.showerror("Error",f"Failed to delete '{name_del}'."); self.controller.update_status("Delete category failed.",3000)
    def backup_database(self): # Same
        db_p=self.controller.db_manager.db_name; bak_fname=f"aistudy_bak_{datetime.datetime.now().strftime('%y%m%d_%H%M%S')}.db"
        save_p=filedialog.asksaveasfilename(initialfile=bak_fname,defaultextension=".db",filetypes=[("DB","*.db")],title="Save DB Backup")
        if not save_p: return
        try: shutil.copy2(db_p,save_p); messagebox.showinfo("Backup OK",f"DB backed up to:\n{save_p}"); self.controller.update_status("DB backup OK.",3000)
        except Exception as e: messagebox.showerror("Backup Fail",f"Backup error: {e}"); self.controller.update_status("DB backup fail.",3000)
    def restore_database(self): # Same
        if not messagebox.askokcancel("Confirm","Restore DB will OVERWRITE current data.\nBackup current DB first.\nProceed?"): return
        bak_p=filedialog.askopenfilename(defaultextension=".db",filetypes=[("DB","*.db")],title="Select DB Backup")
        if not bak_p: return
        curr_db_p=self.controller.db_manager.db_name
        try:
            shutil.copy2(bak_p,curr_db_p); messagebox.showinfo("Restore OK",f"DB restored from:\n{bak_p}\n\nRestart app recommended.")
            self.controller.update_status("DB restore OK. Restart app.",0); self.controller.logout_user()
        except Exception as e: messagebox.showerror("Restore Fail",f"Restore error: {e}"); self.controller.update_status("DB restore fail.",3000)
    def refresh_data(self): 
        self.load_user_categories()
        self.load_api_keys() 
        self.controller.update_status("Settings loaded.")

class AnalyticsFrame(ttk.Frame): # Kept for context, logic largely same
    def __init__(self, parent, controller):
        super().__init__(parent); self.controller = controller
        ttk.Label(self, text="Performance Analytics", style="Header.TLabel").pack(pady=10) 
        self.stats_text = scrolledtext.ScrolledText(self, width=80, height=18, wrap=tk.WORD, state=tk.DISABLED, font=("Courier New", 9)) 
        self.stats_text.pack(pady=10, padx=20, fill=tk.BOTH, expand=True)
        gamify_frame = ttk.Frame(self, padding=10); gamify_frame.pack(pady=5, fill=tk.X)
        ttk.Label(gamify_frame, text="Achievements & Streaks:", font=("Arial", 12, "bold")).pack(anchor=tk.W)
        self.streak_label = ttk.Label(gamify_frame, text="Study Streak: ...", font=("Arial", 10, "bold"), foreground="#e67e22") 
        self.streak_label.pack(anchor=tk.W, padx=20, pady=2)
        self.consistency_label = ttk.Label(gamify_frame, text="Study Consistency: ...", font=("Arial", 10))
        self.consistency_label.pack(anchor="w", padx=20, pady=2)
        self.points_label = ttk.Label(gamify_frame, text="Learning Points: ...", font=("Arial", 10))
        self.points_label.pack(anchor=tk.W, padx=20, pady=2)
        btn_frame = ttk.Frame(self); btn_frame.pack(pady=10, side=tk.BOTTOM, fill=tk.X, padx=20)
        ttk.Button(btn_frame, text="Refresh", command=self.refresh_data).pack(side=tk.LEFT, expand=True, padx=5) 
        ttk.Button(btn_frame, text="Back", command=lambda: controller.show_frame("MainPage")).pack(side=tk.LEFT, expand=True, padx=5) 
    def calculate_study_streak(self, study_logs_data): # Corrected logic
        if not study_logs_data: return 0
        unique_study_dates = set()
        for log_item in study_logs_data: # log_id, subject, start_time, duration, notes
            try:
                date_obj = datetime.datetime.strptime(log_item[2].split(" ")[0], "%Y-%m-%d").date() # start_time is at index 2
                unique_study_dates.add(date_obj)
            except (ValueError, IndexError):
                print(f"Warning: Could not parse date from study_log start_time: {log_item[2] if len(log_item) > 2 else 'INVALID LOG ITEM'}")
                continue
        if not unique_study_dates: return 0
        today = datetime.date.today(); current_streak = 0
        # Check if studied today or yesterday to even consider a current streak
        if not (today in unique_study_dates or (today - datetime.timedelta(days=1)) in unique_study_dates):
            return 0
        check_date = today
        while check_date in unique_study_dates:
            current_streak += 1
            check_date -= datetime.timedelta(days=1)
        # If today was not a study day, but yesterday was, the loop above would result in streak = 0.
        # This additional check ensures that if the streak ended yesterday, it's counted as 1.
        if current_streak == 0 and (today - datetime.timedelta(days=1)) in unique_study_dates:
            current_streak = 1 # For yesterday
            check_date = today - datetime.timedelta(days=2) # Start checking from day before yesterday
            while check_date in unique_study_dates:
                current_streak +=1
                check_date -= datetime.timedelta(days=1)
        return current_streak

    def refresh_data(self): # Same
        if not self.controller.current_user_id:
            self.stats_text.config(state=tk.NORMAL); self.stats_text.delete("1.0",tk.END); self.stats_text.insert(tk.END,"Log in for analytics."); self.stats_text.config(state=tk.DISABLED)
            self.streak_label.config(text="Study Streak: N/A"); self.points_label.config(text="Learning Points: N/A"); self.consistency_label.config(text="Consistency: N/A")
            self.controller.show_frame("LoginPage"); return
        uid=self.controller.current_user_id; stats=f"Analytics for {self.controller.current_username}:\n{'-'*50}\n\n"
        tasks=self.controller.db_manager.get_tasks(uid,True); total_t=len(tasks) if tasks else 0
        comp_t=len([t for t in tasks if t[4]]) if tasks else 0; pend_t=total_t-comp_t
        comp_rate=(comp_t/total_t*100) if total_t>0 else 0
        stats+=f"{'[Task Management ]':<28}\n Total Tasks: {total_t}\n Completed: {comp_t}\n Pending: {pend_t}\n Rate: {comp_rate:.1f}%\n\n"
        s_logs=self.controller.db_manager.get_study_logs(uid); total_s_sess=len(s_logs) if s_logs else 0
        total_s_time_m=sum(log[3] for log in s_logs) if s_logs else 0 # duration_minutes is at index 3
        stats+=f"{'[Study Tracking ]':<28}\n Sessions: {total_s_sess}\n Total Time: {total_s_time_m//60}h {total_s_time_m%60}m\n"
        d_s_7=self.controller.db_manager.get_study_days_count(uid,7); d_s_30=self.controller.db_manager.get_study_days_count(uid,30)
        self.consistency_label.config(text=f"Consistency: {d_s_7}/7d (wk), {d_s_30}/30d (mth)")
        stats+=f" Days Studied (Last 7): {d_s_7}\n Days Studied (Last 30): {d_s_30}\n"
        if s_logs:
            subj_t={}; 
            for log in s_logs: subj_t[log[1]]=subj_t.get(log[1],0)+log[3] # subject at index 1, duration at index 3
            if subj_t: stats+=" Top Subjects (Time):\n"; 
            for s,t_v in sorted(subj_t.items(),key=lambda i:i[1],reverse=True)[:3]: stats+=f"  - {s[:20]:<22}: {t_v//60}h {t_v%60}m\n" 
        stats+="\n"
        q_atts=self.controller.db_manager.get_quiz_attempts(uid); total_q_taken=len(q_atts) if q_atts else 0
        avg_s_pc=0.0; total_corr_ans=0
        if q_atts:
            total_s_ach=sum(att[3] for att in q_atts); total_p_s=sum(att[4] for att in q_atts); total_corr_ans=total_s_ach
            if total_p_s>0: avg_s_pc=(total_s_ach/total_p_s)*100
        stats+=f"{'[Quiz Performance ]':<28}\n Quizzes Taken: {total_q_taken}\n Avg Score: {avg_s_pc:.2f}%\n"
        if q_atts: stats+=" Recent Quizzes (Top 3):\n"; 
        for att in q_atts[:3]:
            try: dt_o=datetime.datetime.strptime(att[2],"%Y-%m-%d %H:%M:%S"); d_disp=dt_o.strftime("%y-%m-%d")
            except ValueError: d_disp="N/A"
            stats+=f"  - {d_disp} | {att[1][:15]:<15} | {att[3]}/{att[4]}\n" 
        stats+="\n"; self.stats_text.config(state=tk.NORMAL); self.stats_text.delete("1.0",tk.END)
        self.stats_text.insert(tk.END,stats); self.stats_text.config(state=tk.DISABLED)
        current_streak_val = self.calculate_study_streak(s_logs if s_logs else []) # Use corrected method
        self.streak_label.config(text=f"Study Streak: {current_streak_val} day(s)") 
        pts=(comp_t*10)+(total_s_sess*5)+total_corr_ans; self.points_label.config(text=f"Learning Points: {pts}") 
        self.controller.update_status("Analytics refreshed.",3000)


# --- Gemini Chat Frame (Replaces OpenAIChatFrame) ---
class GeminiChatFrame(ttk.Frame):
    def __init__(self, parent, controller):
        super().__init__(parent)
        self.controller = controller
        self.chat_history_for_api = [] 
        self.gemini_api_key = None 

        ttk.Label(self, text="AI Chat Assistant (Gemini)", style="Header.TLabel").pack(pady=10)

        chat_area_frame = ttk.Frame(self)
        chat_area_frame.pack(pady=5, padx=20, fill=tk.BOTH, expand=True)
        self.chat_display = scrolledtext.ScrolledText(chat_area_frame, height=20, width=80, wrap=tk.WORD, state=tk.DISABLED, font=("Arial", 10))
        self.chat_display.pack(fill=tk.BOTH, expand=True)
        
        self.chat_display.tag_configure("user", justify="right", background="#DCF8C6", relief=tk.RAISED, borderwidth=1, spacing3=5, wrap=tk.WORD) 
        self.chat_display.tag_configure("model", justify="left", background="#FFFFFF", relief=tk.RAISED, borderwidth=1, spacing3=5, wrap=tk.WORD) 
        self.chat_display.tag_configure("error", foreground="red", font=("Arial", 10, "bold"))
        self.chat_display.tag_configure("timestamp_user", foreground="grey", font=("Arial", 8, "italic"), justify="right", spacing1=5)
        self.chat_display.tag_configure("timestamp_model", foreground="grey", font=("Arial", 8, "italic"), justify="left", spacing1=5)


        input_frame = ttk.Frame(self, padding=(20,10))
        input_frame.pack(fill=tk.X)
        self.chat_input_entry = ttk.Entry(input_frame, width=70, font=("Arial", 11))
        self.chat_input_entry.pack(side=tk.LEFT, expand=True, fill=tk.X, ipady=4)
        self.chat_input_entry.bind("<Return>", self.send_chat_message_event)
        self.send_button = ttk.Button(input_frame, text="Send", command=self.send_chat_message)
        self.send_button.pack(side=tk.LEFT, padx=5)
        self.chat_loading_label = ttk.Label(input_frame, text="", style="Placeholder.TLabel")
        self.chat_loading_label.pack(side=tk.LEFT, padx=5)

        ttk.Button(self, text="Back to Main Menu", command=lambda: controller.show_frame("MainPage")).pack(pady=10, side=tk.BOTTOM)

    def send_chat_message_event(self, event):
        self.send_chat_message()

    def send_chat_message(self):
        user_message_content = self.chat_input_entry.get().strip()
        if not user_message_content: return
        if not self.controller.current_user_id: messagebox.showerror("Error", "User not logged in."); return
        
        self.gemini_api_key = GEMINI_API_KEY or self.controller.db_manager.get_config_value('GEMINI_API_KEY')
        if not self.gemini_api_key:
            self._display_message_in_chat("Gemini API Key not set. Please set it in Settings.", "error")
            return

        self.chat_input_entry.delete(0, tk.END)
        self._add_message_to_display("user", user_message_content) 
        self.chat_history_for_api.append({"role": "user", "parts": [{"text": user_message_content}]})
        self.controller.db_manager.add_chat_message(self.controller.current_user_id, "user", user_message_content)
        
        self.chat_loading_label.config(text="AI is thinking...")
        self.send_button.config(state=tk.DISABLED)

        thread = threading.Thread(target=self._get_gemini_response, daemon=True)
        thread.start()

    def _get_gemini_response(self):
        context_messages_for_api = self.chat_history_for_api[-20:] 
        payload = {"contents": context_messages_for_api}
        api_url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={self.gemini_api_key}"

        try:
            import requests
            response = requests.post(api_url, headers={'Content-Type': 'application/json'}, json=payload, timeout=60)
            response.raise_for_status()
            result = response.json()
            
            ai_response_content = "Sorry, I couldn't get a response from Gemini."
            if result.get("candidates") and result["candidates"][0].get("content") and result["candidates"][0]["content"].get("parts"):
                ai_response_content = result["candidates"][0]["content"]["parts"][0].get("text", ai_response_content).strip()
            
            self.controller.after(0, lambda: self._add_message_to_display("model", ai_response_content)) 
            self.chat_history_for_api.append({"role": "model", "parts": [{"text": ai_response_content}]})
            self.controller.db_manager.add_chat_message(self.controller.current_user_id, "model", ai_response_content) 

        except requests.exceptions.HTTPError as http_err:
            err_detail = str(http_err)
            try: 
                err_json = http_err.response.json()
                if "error" in err_json and "message" in err_json["error"]: err_detail = err_json["error"]["message"]
            except: pass
            self.controller.after(0, lambda: self._display_message_in_chat(f"Gemini API Error: {err_detail}", "error"))
        except Exception as e:
            print(f"Gemini Chat error: {e}")
            self.controller.after(0, lambda: self._display_message_in_chat(f"Error communicating with Gemini: {e}", "error"))
        finally:
            self.controller.after(0, self._gemini_response_finished)

    def _gemini_response_finished(self):
        self.chat_loading_label.config(text="")
        self.send_button.config(state=tk.NORMAL)

    def _add_message_to_display(self, role, content): 
        self.chat_display.config(state=tk.NORMAL)
        timestamp_str = datetime.datetime.now().strftime("%H:%M:%S")
        
        display_role_tag = role 
        timestamp_tag = f"timestamp_{role}" 
        display_name = "You" if role == "user" else "Gemini AI"

        self.chat_display.insert(tk.END, f"{display_name} ({timestamp_str})\n", (timestamp_tag,))
        self.chat_display.insert(tk.END, content + "\n\n", (display_role_tag,))
        
        self.chat_display.config(state=tk.DISABLED)
        self.chat_display.see(tk.END)

    def _display_message_in_chat(self, message, tag=None): 
        self.chat_display.config(state=tk.NORMAL)
        if tag: self.chat_display.insert(tk.END, message + "\n\n", (tag,))
        else: self.chat_display.insert(tk.END, message + "\n\n")
        self.chat_display.config(state=tk.DISABLED)
        self.chat_display.see(tk.END)

    def refresh_data(self):
        self.gemini_api_key = GEMINI_API_KEY or self.controller.db_manager.get_config_value('GEMINI_API_KEY')
        
        self.chat_display.config(state=tk.NORMAL); self.chat_display.delete("1.0", tk.END); self.chat_display.config(state=tk.DISABLED)
        if not self.controller.current_user_id: self.controller.show_frame("LoginPage"); return
        
        if not self.gemini_api_key:
            self._display_message_in_chat("Gemini API Key not set. Configure in Settings.", "error")
            self.send_button.config(state=tk.DISABLED)
        else:
            self.send_button.config(state=tk.NORMAL)
            
        self.chat_history_for_api = [] 
        db_chat_history = self.controller.db_manager.get_chat_history(self.controller.current_user_id, limit=20) 
        
        if db_chat_history:
            for record in db_chat_history: 
                role, content, ts_str = record 
                self._add_message_to_display(role, content) 
                self.chat_history_for_api.append({"role": role, "parts": [{"text": content}]}) 
        self.controller.update_status("Gemini Chat ready. API key required.")


# --- Entry Point ---
if __name__ == "__main__":
    db_manager = DatabaseManager(DATABASE_NAME)
    db_manager.init_db() 
    if not GEMINI_API_KEY: 
        print(f"Warning: GEMINI_API_KEY not set (v{APP_VERSION}). Gemini AI features may be limited.")
    
    app = AIStudyAssistant(db_manager)
    app.mainloop() 