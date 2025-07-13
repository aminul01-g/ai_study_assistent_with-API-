# AI Study Assistant

![version](https://img.shields.io/badge/version-1.3.4-blue.svg)
![python](https://img.shields.io/badge/python-3.x-brightgreen.svg)
![license](https://img.shields.io/badge/license-MIT-lightgrey.svg)

An all-in-one desktop application built with Python and Tkinter, designed to help students organize their tasks, track study sessions, and leverage the power of AI for a more effective learning experience. This application uses a local SQLite database to store all user data and integrates with the Google Gemini API for its intelligent features.

---

## ✨ Key Features

* **User Authentication**: Secure login and registration system with hashed password storage.
* **Task Manager**: Create, manage, and track tasks. Organize them by customizable categories and set due dates.
* **Study Tracker**: Log study sessions with a subject, duration, and notes. Includes an integrated **Pomodoro Timer** to help maintain focus.
* **AI Helper (Gemini)**: Get clear explanations of complex topics, summarize long texts, or generate practice questions on any subject.
* **AI Quiz Generator (Gemini)**: Instantly create multiple-choice quizzes on any topic to test your knowledge. Review your answers with detailed explanations.
* **AI Chat (Gemini)**: A conversational chatbot to assist with quick questions, brainstorming, and study support.
* **Performance Analytics**: Visualize your progress with statistics on task completion, total study time, and quiz performance. Includes gamification elements like a study streak and learning points.
* **Review Hub**: A centralized place to revisit all your saved AI-generated content (summaries, explanations) and review past study logs.
* **Settings & Data Management**:
    * Securely save your Google Gemini API key.
    * Manage custom task categories.
    * Configure Pomodoro timer durations.
    * Backup and restore your entire application database.

---

## 📸 Screenshots

*(You can add screenshots of your application here to give users a visual preview.)*

| Main Menu                               | Task Manager                            | AI Chat                                 |
| --------------------------------------- | --------------------------------------- | --------------------------------------- |
| `[Your Screenshot of the Main Menu]`    | `[Your Screenshot of the Task Manager]` | `[Your Screenshot of the AI Chat]`      |
| **Analytics** | **AI Quiz** | **Study Tracker** |
| `[Your Screenshot of the Analytics Page]` | `[Your Screenshot of the AI Quiz]`      | `[Your Screenshot of the Study Tracker]`|

---

## 🛠️ Technology Stack

* **Frontend (GUI)**: Python's `Tkinter` library with `ttk` for modern widgets.
* **Backend Logic**: Python 3
* **Database**: `SQLite 3` for local, file-based data storage.
* **AI Integration**: `Google Gemini API`
* **External Libraries**: `requests` for handling API calls.

---

## 🚀 Setup and Installation

Follow these steps to get the application running on your local machine.

### Prerequisites

* Python 3.6 or newer.
* A Google Gemini API Key. You can get one from [Google AI Studio](https://aistudio.google.com/app/apikey).

### Installation Steps

1.  **Clone the repository:**
    ```sh
    git clone [https://github.com/your-username/ai-study-assistant.git](https://github.com/your-username/ai-study-assistant.git)
    cd ai-study-assistant
    ```

2.  **Install the required Python package:**
    The application primarily uses standard Python libraries, but requires the `requests` library for API calls.
    ```sh
    pip install requests
    ```

3.  **Run the application:**
    ```sh
    python main.py
    ```
    *(Assuming you save the code as `main.py`)*

---

## ⚙️ Configuration

To use the AI-powered features (Helper, Quiz, Chat, Quotes), you must configure your Google Gemini API key.

1.  Launch the application and register/log in.
2.  Navigate to the **Settings** page from the main menu.
3.  Enter your Gemini API Key in the designated field and click **"Save Gemini Key"**.
4.  The key will be securely stored in the local database for future sessions. A restart may be required for all features to pick up the new key.

---

## 📖 How to Use

1.  **Register/Login**: Start the app and create a new user account.
2.  **Explore**: Use the main menu to navigate between the different modules.
3.  **Manage Tasks**: Go to the **Task Manager** to add your to-do items. Create custom categories in **Settings**.
4.  **Track Study Time**: Use the **Study Tracker** to log your sessions or start the Pomodoro timer.
5.  **Get AI Help**: Go to the **AI Helper**, **AI Quizzes**, or **AI Chat** to enhance your study process. Remember to set your API key first!
6.  **Review Progress**: Visit the **Analytics** page to see your stats and the **Review Hub** to look over saved AI content.

---

## 📄 License

This project is licensed under the MIT License. See the `LICENSE` file for details.
