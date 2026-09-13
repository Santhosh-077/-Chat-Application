# Task 5: Real-Time Chat Application

**Internship:** Oasis Infobyte SIP (OIBSIP)  
**Domain:** Python Development  
**Task:** Task 5 – Chat Application (Beginner & Advanced Tiers)

---

## 🎯 Overview

The **Real-Time Chat Application** is a multi-threaded Python networking tool that enables instantaneous bidirectional communication between multiple clients. 

Built using Python's core `socket`, `threading`, `sqlite3`, and `tkinter` modules, this project requires **zero external third-party dependencies** while offering both an interactive **Command-Line Interface (CLI)** and a modern **Graphical User Interface (GUI)** with room management, persistent history, and user authentication.

---

## 🏗️ Architecture & How It Works

```
                     +---------------------------------------+
                     |           Chat Server                 |
                     |  (Multi-Threaded TCP Socket Listener) |
                     +-------------------+-------------------+
                                         |
                       +-----------------+-----------------+
                       |                                   |
                       v                                   v
             [SQLite Database]                   [In-Memory Room Broker]
             - users (salt + hash)               - #general
             - messages (room, history)          - #tech, #random, custom
                       ^                                   ^
                       |                                   |
        +--------------+---------------+   +---------------+---------------+
        |                              |   |                               |
+-------+-------+              +-------+---+---+                   +-------+-------+
|  Client A     |              |  Client B     |                   |  Client C     |
| (Tkinter GUI) |              | (Tkinter GUI) |                   |  (CLI Mode)   |
+---------------+              +---------------+                   +---------------+
```

1. **Server (`ChatServer`)**: Binds to `127.0.0.1:5000` and spawns a daemon thread for each accepted socket connection.
2. **Protocol Framing**: Communication utilizes newline-delimited (`\n`) JSON payloads, eliminating TCP stream fragmentation issues.
3. **Database Layer (`Database`)**: SQLite manages persistent user profiles and chat history across all rooms.
4. **Broadcast Engine**: Messages are routed only to clients currently subscribed to the specific target room.

---

## 🔒 Security & Transparency (End-to-End Awareness)

In compliance with the project's security transparency guidelines:

- **Password Storage:** User passwords are never saved in plaintext. When a user registers, a unique 16-byte cryptographic salt is generated using `secrets.token_hex(16)`, combined with the password, and hashed using **SHA-256**.
- **Message Storage:** Message history (room, sender, content, and timestamp) is stored in the local SQLite database file `chat_app.db`.
- **Wire Encryption Notice:** In this local development build, communication over TCP sockets is **unencrypted**. Packets traveling over open local networks could theoretically be inspected with packet capture tools (e.g., Wi-Fi sniffers).
- **Production Recommendation:** For production or public Internet deployment, socket connections should be wrapped with Python's standard **`ssl`** library (TLS 1.3 encryption with signed X.509 certificates) to prevent eavesdropping and Man-in-the-Middle (MITM) attacks.

---

## ✨ Features Checklist

### Beginner Tier
- [x] **Server Script:** Robust socket server listening for incoming client connections.
- [x] **Client Script:** Reliable socket client with auto-reconnect handling.
- [x] **Real-Time Bidirectional Communication:** Multi-client concurrent messaging via Python `threading`.
- [x] **Timestamp Prefixes:** Every message is stamped with `[HH:MM:SS]` formatted time.
- [x] **Graceful Disconnection:** Notifies rooms when a member leaves and releases socket resources cleanly.
- [x] **Localhost Execution:** Run server and multiple clients concurrently on `127.0.0.1`.

### Advanced Tier
- [x] **Modern Desktop GUI:** Built with Tkinter featuring a dark theme, custom cards, and styled message tags.
- [x] **User Authentication:** Registration and login system backed by SQLite and salted SHA-256.
- [x] **Multiple Chat Rooms:** Default rooms (`#general`, `#tech`, `#random`) plus the ability to create and join custom rooms on the fly.
- [x] **Message History:** Automatically retrieves and renders the past 40 messages when entering any room.
- [x] **Unread Notifications:** Window title update with unread message counter and system chime (`bell()`) when the window loses focus.
- [x] **Emoji Shortcode Engine:** Automatically converts shortcodes (e.g., `:smile:`, `:heart:`, `:fire:`, `:thumbsup:`, `:rocket:`) into Unicode emojis.
- [x] **Interactive Launcher:** Run `python main.py` to open an intuitive visual mode switcher (Server, GUI Client, or CLI Client).

---

## 🔠 Supported Emoji Shortcodes

| Shortcode | Rendered Emoji | Shortcode | Rendered Emoji |
| :--- | :---: | :--- | :---: |
| `:smile:` | 😊 | `:heart:` or `<3` | ❤️ |
| `:thumbsup:` or `:+1:` | 👍 | `:fire:` | 🔥 |
| `:rocket:` | 🚀 | `:star:` | ⭐ |
| `:party:` | 🎉 | `:clap:` | 👏 |
| `:sunglasses:` | 😎 | `:thinking:` | 🤔 |

---

## 🚀 How to Run

### 1. Open Terminal & Navigate
```bash
cd "python task-5 -Chat-Application"
```

### 2. Launch the Application

#### Option A: Interactive Visual Launcher
Simply run:
```bash
python main.py
```
A launcher dialog will appear allowing you to start the **Chat Server**, open a **GUI Client**, or run a **CLI Client**.

#### Option B: Direct Command Line Modes

1. **Start the Server in one terminal:**
   ```bash
   python main.py server
   ```

2. **Start a GUI Client in another terminal:**
   ```bash
   python main.py client
   ```

3. **Start a CLI Client (for terminal-only chat):**
   ```bash
   python main.py cli
   ```

*(You can open as many client instances as you want on the same machine to chat between different users).*
