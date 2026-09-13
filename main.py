"""
TASK 5: Real-Time Chat Application
Internship: Oasis Infobyte SIP (OIBSIP)
Domain: Python Development
Author: Santhosh-077

A complete real-time messaging application supporting:
- Multi-client TCP Socket Server with Threading
- User Authentication (Registration & Login) stored in SQLite with salted SHA-256
- Multiple Chat Rooms with instant switching and custom room creation
- Persistent Message History loaded automatically upon joining rooms
- Formatted timestamps for all messages
- Graceful connection and disconnection handling
- Emoji shortcode translation (e.g. :smile:, :heart:, :fire:, :thumbsup:)
- Both modern Tkinter GUI mode and Command-Line Interface (CLI) mode
"""

import sys
import os
import socket
import threading
import json
import sqlite3
import hashlib
import secrets
from datetime import datetime

# Optional GUI imports
try:
    import tkinter as tk
    from tkinter import ttk, messagebox, scrolledtext
    TKINTER_AVAILABLE = True
except ImportError:
    TKINTER_AVAILABLE = False

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 5000
DB_FILE = "chat_app.db"

# Comprehensive Emoji Dictionary
EMOJI_MAP = {
    ":smile:": "😊",
    ":happy:": "😃",
    ":grin:": "😁",
    ":joy:": "😂",
    ":wink:": "😉",
    ":heart:": "❤️",
    "<3": "❤️",
    ":thumbsup:": "👍",
    ":+1:": "👍",
    ":thumbsdown:": "👎",
    ":-1:": "👎",
    ":fire:": "🔥",
    ":clap:": "👏",
    ":rocket:": "🚀",
    ":star:": "⭐",
    ":party:": "🎉",
    ":sunglasses:": "😎",
    ":thinking:": "🤔",
    ":sad:": "😢",
    ":crying:": "😭",
    ":check:": "✅",
    ":lock:": "🔒",
    ":wave:": "👋",
    ":eyes:": "👀",
}

def render_emojis(text: str) -> str:
    """Replaces emoji shortcodes with their respective Unicode representations."""
    for code, emoji in EMOJI_MAP.items():
        text = text.replace(code, emoji)
    return text

def hash_password(password: str, salt: str = None) -> tuple[str, str]:
    """Generates a secure salted SHA-256 password hash."""
    if salt is None:
        salt = secrets.token_hex(16)
    hashed = hashlib.sha256((password + salt).encode("utf-8")).hexdigest()
    return hashed, salt


# ============================================================================
# DATABASE LAYER
# ============================================================================
class Database:
    """Thread-safe SQLite database manager for chat history and user credentials."""
    def __init__(self, db_path=DB_FILE):
        self.db_path = db_path
        self._init_db()

    def get_connection(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            # Users Table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    username TEXT UNIQUE NOT NULL,
                    password_hash TEXT NOT NULL,
                    salt TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            # Messages Table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    room TEXT NOT NULL,
                    username TEXT NOT NULL,
                    message TEXT NOT NULL,
                    timestamp TEXT NOT NULL
                )
            """)
            conn.commit()

    def register_user(self, username, password) -> tuple[bool, str]:
        username = username.strip()
        if len(username) < 3:
            return False, "Username must be at least 3 characters."
        if len(password) < 4:
            return False, "Password must be at least 4 characters."

        pwd_hash, salt = hash_password(password)
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "INSERT INTO users (username, password_hash, salt) VALUES (?, ?, ?)",
                    (username, pwd_hash, salt)
                )
                conn.commit()
                return True, "Registration successful."
        except sqlite3.IntegrityError:
            return False, "Username already exists. Please pick another."

    def authenticate_user(self, username, password) -> tuple[bool, str]:
        username = username.strip()
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT password_hash, salt FROM users WHERE username = ?", (username,))
            row = cursor.fetchone()
            if not row:
                return False, "User not found."
            stored_hash = row["password_hash"]
            salt = row["salt"]
            calculated_hash, _ = hash_password(password, salt)
            if calculated_hash == stored_hash:
                return True, "Login successful."
            return False, "Incorrect password."

    def save_message(self, room, username, message, timestamp):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO messages (room, username, message, timestamp) VALUES (?, ?, ?, ?)",
                (room, username, message, timestamp)
            )
            conn.commit()

    def get_room_history(self, room, limit=40):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT room, username, message, timestamp FROM messages WHERE room = ? ORDER BY id DESC LIMIT ?",
                (room, limit)
            )
            rows = cursor.fetchall()
            # Return in chronological order
            return [dict(r) for r in reversed(rows)]


# ============================================================================
# SERVER IMPLEMENTATION
# ============================================================================
class ChatServer:
    """Multi-threaded TCP Socket Chat Server handling rooms, auth, and broadcasts."""
    def __init__(self, host=DEFAULT_HOST, port=DEFAULT_PORT):
        self.host = host
        self.port = port
        self.db = Database()
        self.server_socket = None
        self.is_running = False
        self.clients = {}  # socket: {"username": str, "room": str, "addr": tuple}
        self.lock = threading.Lock()

    def start(self):
        self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            self.server_socket.bind((self.host, self.port))
            self.server_socket.listen(20)
            self.is_running = True
            print(f"[*] Chat Server running on {self.host}:{self.port}")
            print("[*] Waiting for incoming client connections...")

            while self.is_running:
                try:
                    client_sock, addr = self.server_socket.accept()
                    with self.lock:
                        self.clients[client_sock] = {"username": None, "room": "general", "addr": addr}
                    threading.Thread(target=self._handle_client, args=(client_sock, addr), daemon=True).start()
                except OSError:
                    break
        except Exception as e:
            print(f"[!] Server error: {e}")
        finally:
            self.stop()

    def stop(self):
        self.is_running = False
        with self.lock:
            for sock in list(self.clients.keys()):
                try:
                    sock.close()
                except Exception:
                    pass
            self.clients.clear()
        if self.server_socket:
            try:
                self.server_socket.close()
            except Exception:
                pass
        print("[*] Server stopped cleanly.")

    def _send_payload(self, client_sock, payload: dict):
        try:
            msg_str = json.dumps(payload) + "\n"
            client_sock.sendall(msg_str.encode("utf-8"))
        except Exception:
            pass

    def _broadcast(self, room: str, payload: dict, exclude_sock=None):
        with self.lock:
            target_socks = [
                s for s, info in self.clients.items()
                if info.get("room") == room and s != exclude_sock and info.get("username")
            ]
        for s in target_socks:
            self._send_payload(s, payload)

    def _get_room_users(self, room: str):
        with self.lock:
            return [
                info["username"] for info in self.clients.values()
                if info.get("room") == room and info.get("username")
            ]

    def _broadcast_room_users(self, room: str):
        users = self._get_room_users(room)
        payload = {"type": "USERS_LIST", "room": room, "users": users}
        self._broadcast(room, payload)

    def _handle_client(self, client_sock, addr):
        buffer = ""
        try:
            while self.is_running:
                data = client_sock.recv(4096)
                if not data:
                    break
                buffer += data.decode("utf-8", errors="ignore")
                while "\n" in buffer:
                    line, buffer = buffer.split("\n", 1)
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        req = json.loads(line)
                        self._process_request(client_sock, req)
                    except json.JSONDecodeError:
                        continue
        except Exception:
            pass
        finally:
            self._disconnect_client(client_sock)

    def _disconnect_client(self, client_sock):
        with self.lock:
            info = self.clients.pop(client_sock, None)
        try:
            client_sock.close()
        except Exception:
            pass

        if info and info.get("username"):
            user = info["username"]
            room = info.get("room", "general")
            timestamp = datetime.now().strftime("%H:%M:%S")
            leave_msg = {
                "type": "SYSTEM",
                "room": room,
                "message": f"{user} has left the chat.",
                "timestamp": timestamp
            }
            self._broadcast(room, leave_msg)
            self._broadcast_room_users(room)
            print(f"[-] {user} disconnected from room #{room}")

    def _process_request(self, client_sock, req: dict):
        action = req.get("type")

        # --- REGISTRATION ---
        if action == "REGISTER":
            username = req.get("username", "").strip()
            password = req.get("password", "")
            success, msg = self.db.register_user(username, password)
            self._send_payload(client_sock, {"type": "AUTH_RES", "success": success, "message": msg})

        # --- LOGIN ---
        elif action == "LOGIN":
            username = req.get("username", "").strip()
            password = req.get("password", "")
            # Check if user already logged in from another session
            with self.lock:
                already_active = any(
                    info.get("username") == username for info in self.clients.values()
                )
            if already_active:
                self._send_payload(client_sock, {"type": "AUTH_RES", "success": False, "message": "User is already logged in elsewhere."})
                return

            success, msg = self.db.authenticate_user(username, password)
            if success:
                with self.lock:
                    self.clients[client_sock]["username"] = username
                    self.clients[client_sock]["room"] = "general"
                self._send_payload(client_sock, {"type": "AUTH_RES", "success": True, "message": msg, "username": username, "room": "general"})
                # Send history for general room
                history = self.db.get_room_history("general")
                self._send_payload(client_sock, {"type": "HISTORY", "room": "general", "messages": history})
                # Announce arrival
                timestamp = datetime.now().strftime("%H:%M:%S")
                self._broadcast("general", {
                    "type": "SYSTEM",
                    "room": "general",
                    "message": f"{username} has joined #general!",
                    "timestamp": timestamp
                }, exclude_sock=client_sock)
                self._broadcast_room_users("general")
                print(f"[+] User logged in: {username}")
            else:
                self._send_payload(client_sock, {"type": "AUTH_RES", "success": False, "message": msg})

        # --- JOIN / CHANGE ROOM ---
        elif action == "JOIN_ROOM":
            new_room = req.get("room", "general").strip().lower().replace("#", "")
            if not new_room:
                new_room = "general"
            with self.lock:
                info = self.clients.get(client_sock)
                if not info or not info.get("username"):
                    return
                old_room = info["room"]
                user = info["username"]
                info["room"] = new_room

            timestamp = datetime.now().strftime("%H:%M:%S")
            if old_room != new_room:
                # Notify old room
                self._broadcast(old_room, {
                    "type": "SYSTEM",
                    "room": old_room,
                    "message": f"{user} left for #{new_room}.",
                    "timestamp": timestamp
                })
                self._broadcast_room_users(old_room)

            # Acknowledge room change
            self._send_payload(client_sock, {"type": "ROOM_CHANGED", "room": new_room})
            # Send history for new room
            history = self.db.get_room_history(new_room)
            self._send_payload(client_sock, {"type": "HISTORY", "room": new_room, "messages": history})
            # Notify new room
            self._broadcast(new_room, {
                "type": "SYSTEM",
                "room": new_room,
                "message": f"{user} joined #{new_room}!",
                "timestamp": timestamp
            }, exclude_sock=client_sock)
            self._broadcast_room_users(new_room)

        # --- CHAT MESSAGE ---
        elif action == "MSG":
            with self.lock:
                info = self.clients.get(client_sock)
                if not info or not info.get("username"):
                    return
                user = info["username"]
                room = info["room"]

            raw_text = req.get("message", "").strip()
            if not raw_text:
                return

            text_with_emojis = render_emojis(raw_text)
            timestamp = datetime.now().strftime("%H:%M:%S")

            # Persist to database
            self.db.save_message(room, user, text_with_emojis, timestamp)

            payload = {
                "type": "MSG",
                "room": room,
                "username": user,
                "message": text_with_emojis,
                "timestamp": timestamp
            }
            # Broadcast to all users in this room (including sender for acknowledgment)
            self._broadcast(room, payload)


# ============================================================================
# ADVANCED GUI CLIENT (TKINTER)
# ============================================================================
class ChatGUIClient:
    """Modern Desktop Tkinter GUI with Auth, Rooms, Emoji picker, and notifications."""
    def __init__(self, root, host=DEFAULT_HOST, port=DEFAULT_PORT):
        self.root = root
        self.host = host
        self.port = port
        self.sock = None
        self.username = None
        self.current_room = "general"
        self.is_connected = False
        self.is_focused = True
        self.unread_count = 0

        self.root.title("OIBSIP · Real-Time Chat Application")
        self.root.geometry("880x640")
        self.root.minsize(700, 500)
        self.root.configure(bg="#0f172a")

        # Track window focus for notifications
        self.root.bind("<FocusIn>", self._on_focus_in)
        self.root.bind("<FocusOut>", self._on_focus_out)
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

        self.style = ttk.Style()
        try:
            self.style.theme_use("clam")
        except Exception:
            pass

        self._build_auth_screen()

    def _on_focus_in(self, event=None):
        self.is_focused = True
        self.unread_count = 0
        if self.username:
            self.root.title(f"OIBSIP Chat — #{self.current_room} ({self.username})")

    def _on_focus_out(self, event=None):
        self.is_focused = False

    def _build_auth_screen(self):
        for widget in self.root.winfo_children():
            widget.destroy()

        container = tk.Frame(self.root, bg="#0f172a")
        container.place(relx=0.5, rely=0.5, anchor="center")

        # Card Frame
        card = tk.Frame(container, bg="#1e293b", padx=35, pady=30, relief="flat", highlightthickness=1, highlightbackground="#334155")
        card.pack()

        title_lbl = tk.Label(card, text="💬 Real-Time Chat App", font=("Segoe UI", 18, "bold"), fg="#f8fafc", bg="#1e293b")
        title_lbl.pack(pady=(0, 5))
        sub_lbl = tk.Label(card, text="Oasis Infobyte SIP · Task 5", font=("Segoe UI", 10), fg="#94a3b8", bg="#1e293b")
        sub_lbl.pack(pady=(0, 20))

        # Host & Port row
        net_frame = tk.Frame(card, bg="#1e293b")
        net_frame.pack(fill="x", pady=(0, 10))

        tk.Label(net_frame, text="Server Host:", font=("Segoe UI", 9, "bold"), fg="#cbd5e1", bg="#1e293b").grid(row=0, column=0, sticky="w")
        self.host_entry = tk.Entry(net_frame, font=("Segoe UI", 10), bg="#0f172a", fg="#f8fafc", insertbackground="white", relief="flat", width=14)
        self.host_entry.insert(0, self.host)
        self.host_entry.grid(row=0, column=1, padx=(5, 15), pady=2)

        tk.Label(net_frame, text="Port:", font=("Segoe UI", 9, "bold"), fg="#cbd5e1", bg="#1e293b").grid(row=0, column=2, sticky="w")
        self.port_entry = tk.Entry(net_frame, font=("Segoe UI", 10), bg="#0f172a", fg="#f8fafc", insertbackground="white", relief="flat", width=6)
        self.port_entry.insert(0, str(self.port))
        self.port_entry.grid(row=0, column=3, padx=(5, 0), pady=2)

        # Username
        tk.Label(card, text="Username", font=("Segoe UI", 9, "bold"), fg="#cbd5e1", bg="#1e293b").pack(anchor="w", pady=(5, 2))
        self.user_entry = tk.Entry(card, font=("Segoe UI", 11), bg="#0f172a", fg="#f8fafc", insertbackground="white", relief="flat", width=28)
        self.user_entry.pack(pady=(0, 10), ipady=5)

        # Password
        tk.Label(card, text="Password", font=("Segoe UI", 9, "bold"), fg="#cbd5e1", bg="#1e293b").pack(anchor="w", pady=(5, 2))
        self.pwd_entry = tk.Entry(card, show="•", font=("Segoe UI", 11), bg="#0f172a", fg="#f8fafc", insertbackground="white", relief="flat", width=28)
        self.pwd_entry.pack(pady=(0, 15), ipady=5)

        # Buttons
        btn_frame = tk.Frame(card, bg="#1e293b")
        btn_frame.pack(fill="x", pady=(5, 0))

        login_btn = tk.Button(
            btn_frame, text="Login", font=("Segoe UI", 10, "bold"),
            bg="#2563eb", fg="white", activebackground="#1d4ed8", activeforeground="white",
            relief="flat", cursor="hand2", padx=15, pady=6, command=lambda: self._authenticate("LOGIN")
        )
        login_btn.pack(side="left", expand=True, fill="x", padx=(0, 5))

        reg_btn = tk.Button(
            btn_frame, text="Register", font=("Segoe UI", 10, "bold"),
            bg="#334155", fg="#e2e8f0", activebackground="#475569", activeforeground="white",
            relief="flat", cursor="hand2", padx=15, pady=6, command=lambda: self._authenticate("REGISTER")
        )
        reg_btn.pack(side="right", expand=True, fill="x", padx=(5, 0))

        # Status Label
        self.auth_status = tk.Label(card, text="", font=("Segoe UI", 9), fg="#ef4444", bg="#1e293b", wraplength=260)
        self.auth_status.pack(pady=(12, 0))

    def _authenticate(self, mode):
        host = self.host_entry.get().strip()
        port_str = self.port_entry.get().strip()
        username = self.user_entry.get().strip()
        password = self.pwd_entry.get()

        if not username or not password:
            self.auth_status.config(text="Please enter both username and password.", fg="#ef4444")
            return

        try:
            port = int(port_str)
        except ValueError:
            self.auth_status.config(text="Port must be an integer.", fg="#ef4444")
            return

        self.auth_status.config(text="Connecting to server...", fg="#38bdf8")
        self.root.update_idletasks()

        if not self.is_connected or not self.sock:
            try:
                self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                self.sock.connect((host, port))
                self.is_connected = True
                self.host = host
                self.port = port
                # Start listener thread
                threading.Thread(target=self._listen_server, daemon=True).start()
            except Exception as e:
                self.is_connected = False
                self.auth_status.config(text=f"Cannot connect: {e}", fg="#ef4444")
                return

        # Send authentication payload
        payload = {"type": mode, "username": username, "password": password}
        self._send_payload(payload)

    def _send_payload(self, payload: dict):
        if self.sock and self.is_connected:
            try:
                msg_str = json.dumps(payload) + "\n"
                self.sock.sendall(msg_str.encode("utf-8"))
            except Exception as e:
                print(f"[!] Send error: {e}")

    def _listen_server(self):
        buffer = ""
        while self.is_connected:
            try:
                data = self.sock.recv(4096)
                if not data:
                    break
                buffer += data.decode("utf-8", errors="ignore")
                while "\n" in buffer:
                    line, buffer = buffer.split("\n", 1)
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        res = json.loads(line)
                        self.root.after(0, self._handle_server_message, res)
                    except json.JSONDecodeError:
                        continue
            except Exception:
                break

        self.is_connected = False
        self.root.after(0, self._handle_disconnect)

    def _handle_disconnect(self):
        if self.username:
            messagebox.showwarning("Disconnected", "Lost connection to the chat server.")
            self.username = None
            self._build_auth_screen()

    def _handle_server_message(self, res: dict):
        msg_type = res.get("type")

        # Authentication Response
        if msg_type == "AUTH_RES":
            success = res.get("success", False)
            msg = res.get("message", "")
            if success:
                if "username" in res:  # Successful login
                    self.username = res["username"]
                    self.current_room = res.get("room", "general")
                    self._build_chat_screen()
                else:  # Successful registration
                    self.auth_status.config(text="Registered successfully! You can now log in.", fg="#4ade80")
            else:
                self.auth_status.config(text=msg, fg="#ef4444")

        # Chat Message
        elif msg_type == "MSG":
            room = res.get("room")
            if room == self.current_room:
                user = res.get("username")
                text = res.get("message")
                ts = res.get("timestamp")
                self._display_chat_message(user, text, ts)

                # In-app notification if window unfocused
                if not self.is_focused and user != self.username:
                    self.unread_count += 1
                    self.root.title(f"({self.unread_count}) New message from {user}! — OIBSIP Chat")
                    self.root.bell()

        # System Notice (Join/Leave)
        elif msg_type == "SYSTEM":
            room = res.get("room")
            if room == self.current_room:
                text = res.get("message")
                ts = res.get("timestamp")
                self._display_system_message(text, ts)

        # Room Changed
        elif msg_type == "ROOM_CHANGED":
            self.current_room = res.get("room", "general")
            self.room_title_lbl.config(text=f"#{self.current_room}")
            self.chat_display.config(state="normal")
            self.chat_display.delete("1.0", tk.END)
            self.chat_display.config(state="disabled")
            self._display_system_message(f"Switched to room #{self.current_room}.", datetime.now().strftime("%H:%M:%S"))
            self.root.title(f"OIBSIP Chat — #{self.current_room} ({self.username})")

        # Message History
        elif msg_type == "HISTORY":
            room = res.get("room")
            if room == self.current_room:
                messages = res.get("messages", [])
                if messages:
                    self._display_system_message("--- Loaded previous messages ---", "")
                    for m in messages:
                        self._display_chat_message(m["username"], m["message"], m["timestamp"])
                    self._display_system_message("-------------------------------", "")

        # Users List
        elif msg_type == "USERS_LIST":
            room = res.get("room")
            if room == self.current_room:
                users = res.get("users", [])
                self._update_users_list(users)

    def _build_chat_screen(self):
        for widget in self.root.winfo_children():
            widget.destroy()

        self.root.title(f"OIBSIP Chat — #{self.current_room} ({self.username})")

        # Top Navigation Bar
        nav_bar = tk.Frame(self.root, bg="#1e293b", height=50, padx=15, pady=8)
        nav_bar.pack(fill="x", side="top")

        self.room_title_lbl = tk.Label(nav_bar, text=f"#{self.current_room}", font=("Segoe UI", 14, "bold"), fg="#38bdf8", bg="#1e293b")
        self.room_title_lbl.pack(side="left")

        user_badge = tk.Label(nav_bar, text=f"👤 {self.username}", font=("Segoe UI", 10, "bold"), fg="#e2e8f0", bg="#334155", padx=10, pady=3)
        user_badge.pack(side="right", padx=(10, 0))

        disconnect_btn = tk.Button(
            nav_bar, text="Disconnect", font=("Segoe UI", 9, "bold"),
            bg="#ef4444", fg="white", activebackground="#dc2626", activeforeground="white",
            relief="flat", cursor="hand2", padx=10, pady=2, command=self._disconnect_user
        )
        disconnect_btn.pack(side="right")

        # Main Layout (Sidebar + Chat Area)
        main_pane = tk.Frame(self.root, bg="#0f172a")
        main_pane.pack(fill="both", expand=True)

        # --- LEFT SIDEBAR ---
        sidebar = tk.Frame(main_pane, bg="#1e293b", width=220, padx=12, pady=12)
        sidebar.pack(fill="y", side="left")
        sidebar.pack_propagate(False)

        # Rooms Header
        tk.Label(sidebar, text="CHAT ROOMS", font=("Segoe UI", 8, "bold"), fg="#94a3b8", bg="#1e293b").pack(anchor="w", pady=(0, 6))

        # Default Room Buttons
        self.room_btns_frame = tk.Frame(sidebar, bg="#1e293b")
        self.room_btns_frame.pack(fill="x", pady=(0, 10))

        for rm in ["general", "tech", "random"]:
            btn = tk.Button(
                self.room_btns_frame, text=f"# {rm}", font=("Segoe UI", 9),
                bg="#0f172a", fg="#cbd5e1", activebackground="#2563eb", activeforeground="white",
                anchor="w", relief="flat", padx=8, pady=4, cursor="hand2",
                command=lambda r=rm: self._join_room(r)
            )
            btn.pack(fill="x", pady=2)

        # Custom Room Join
        tk.Label(sidebar, text="JOIN / CREATE ROOM", font=("Segoe UI", 8, "bold"), fg="#94a3b8", bg="#1e293b").pack(anchor="w", pady=(10, 4))
        self.custom_room_entry = tk.Entry(sidebar, font=("Segoe UI", 9), bg="#0f172a", fg="#f8fafc", insertbackground="white", relief="flat")
        self.custom_room_entry.pack(fill="x", pady=(0, 4), ipady=3)
        self.custom_room_entry.bind("<Return>", lambda e: self._join_room(self.custom_room_entry.get()))

        join_room_btn = tk.Button(
            sidebar, text="Join Room", font=("Segoe UI", 8, "bold"),
            bg="#2563eb", fg="white", activebackground="#1d4ed8",
            relief="flat", cursor="hand2", pady=3,
            command=lambda: self._join_room(self.custom_room_entry.get())
        )
        join_room_btn.pack(fill="x", pady=(0, 15))

        # Active Users List
        tk.Label(sidebar, text="ACTIVE USERS IN ROOM", font=("Segoe UI", 8, "bold"), fg="#94a3b8", bg="#1e293b").pack(anchor="w", pady=(0, 4))
        self.users_listbox = tk.Listbox(
            sidebar, font=("Segoe UI", 9), bg="#0f172a", fg="#38bdf8",
            selectbackground="#334155", relief="flat", highlightthickness=0
        )
        self.users_listbox.pack(fill="both", expand=True)

        # --- CHAT DISPLAY & INPUT ---
        chat_frame = tk.Frame(main_pane, bg="#0f172a", padx=10, pady=10)
        chat_frame.pack(fill="both", expand=True, side="right")

        # Chat Transcript Area
        self.chat_display = scrolledtext.ScrolledText(
            chat_frame, wrap=tk.WORD, font=("Consolas", 10),
            bg="#0f172a", fg="#f8fafc", relief="flat",
            highlightthickness=1, highlightbackground="#334155", padx=10, pady=10
        )
        self.chat_display.pack(fill="both", expand=True, pady=(0, 8))
        self.chat_display.config(state="disabled")

        # Color Tags for Transcript
        self.chat_display.tag_config("timestamp", foreground="#64748b", font=("Consolas", 9))
        self.chat_display.tag_config("self_user", foreground="#38bdf8", font=("Segoe UI", 10, "bold"))
        self.chat_display.tag_config("other_user", foreground="#a78bfa", font=("Segoe UI", 10, "bold"))
        self.chat_display.tag_config("message_text", foreground="#f8fafc", font=("Segoe UI", 10))
        self.chat_display.tag_config("system_text", foreground="#eab308", font=("Segoe UI", 9, "italic"))

        # Emoji Shortcut Quick Bar
        emoji_bar = tk.Frame(chat_frame, bg="#0f172a")
        emoji_bar.pack(fill="x", pady=(0, 6))

        tk.Label(emoji_bar, text="Quick Emojis:", font=("Segoe UI", 8, "bold"), fg="#94a3b8", bg="#0f172a").pack(side="left", padx=(0, 5))
        quick_emojis = ["😊", "❤️", "👍", "🔥", "🎉", "🚀", "👏", "⭐"]
        for em in quick_emojis:
            btn = tk.Button(
                emoji_bar, text=em, font=("Segoe UI", 9),
                bg="#1e293b", fg="white", activebackground="#334155",
                relief="flat", cursor="hand2", padx=4, pady=0,
                command=lambda e=em: self._insert_emoji(e)
            )
            btn.pack(side="left", padx=2)

        # Input & Send Row
        input_row = tk.Frame(chat_frame, bg="#0f172a")
        input_row.pack(fill="x")

        self.msg_entry = tk.Entry(
            input_row, font=("Segoe UI", 11),
            bg="#1e293b", fg="#f8fafc", insertbackground="white",
            relief="flat", highlightthickness=1, highlightbackground="#334155"
        )
        self.msg_entry.pack(side="left", fill="x", expand=True, ipady=6, padx=(0, 8))
        self.msg_entry.bind("<Return>", lambda e: self._send_chat_message())
        self.msg_entry.focus_set()

        send_btn = tk.Button(
            input_row, text="Send ➔", font=("Segoe UI", 10, "bold"),
            bg="#2563eb", fg="white", activebackground="#1d4ed8", activeforeground="white",
            relief="flat", cursor="hand2", padx=18, pady=6, command=self._send_chat_message
        )
        send_btn.pack(side="right")

    def _insert_emoji(self, emoji_char):
        self.msg_entry.insert(tk.INSERT, emoji_char)
        self.msg_entry.focus_set()

    def _join_room(self, room_name):
        room_name = room_name.strip().lower().replace("#", "")
        if not room_name or room_name == self.current_room:
            return
        payload = {"type": "JOIN_ROOM", "room": room_name}
        self._send_payload(payload)

    def _send_chat_message(self):
        text = self.msg_entry.get().strip()
        if not text:
            return
        payload = {"type": "MSG", "message": text}
        self._send_payload(payload)
        self.msg_entry.delete(0, tk.END)

    def _display_chat_message(self, user, text, timestamp):
        self.chat_display.config(state="normal")
        ts_str = f"[{timestamp}] " if timestamp else ""
        self.chat_display.insert(tk.END, ts_str, "timestamp")

        if user == self.username:
            self.chat_display.insert(tk.END, f"{user}: ", "self_user")
        else:
            self.chat_display.insert(tk.END, f"{user}: ", "other_user")

        self.chat_display.insert(tk.END, f"{text}\n", "message_text")
        self.chat_display.see(tk.END)
        self.chat_display.config(state="disabled")

    def _display_system_message(self, text, timestamp):
        self.chat_display.config(state="normal")
        ts_str = f"[{timestamp}] " if timestamp else ""
        self.chat_display.insert(tk.END, f"{ts_str}ℹ️  {text}\n", "system_text")
        self.chat_display.see(tk.END)
        self.chat_display.config(state="disabled")

    def _update_users_list(self, users: list):
        self.users_listbox.delete(0, tk.END)
        for u in users:
            prefix = "★ " if u == self.username else "• "
            self.users_listbox.insert(tk.END, f"{prefix}{u}")

    def _disconnect_user(self):
        if self.sock:
            try:
                self.sock.close()
            except Exception:
                pass
        self.sock = None
        self.is_connected = False
        self.username = None
        self._build_auth_screen()

    def _on_close(self):
        self._disconnect_user()
        self.root.destroy()


# ============================================================================
# COMMAND LINE INTERFACE (CLI) CLIENT
# ============================================================================
def run_cli_client(host=DEFAULT_HOST, port=DEFAULT_PORT):
    """Interactive command-line client supporting authentication, rooms, and timestamps."""
    print("=" * 55)
    print("       OIBSIP CHAT APPLICATION (CLI MODE)")
    print("=" * 55)

    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.connect((host, port))
    except Exception as e:
        print(f"[!] Could not connect to {host}:{port} - {e}")
        return

    # Authentication Loop
    logged_in = False
    username = ""
    current_room = "general"

    while not logged_in:
        print("\n1. Login")
        print("2. Register")
        print("3. Exit")
        choice = input("Select option (1/2/3): ").strip()

        if choice == "3":
            sock.close()
            return
        elif choice not in ("1", "2"):
            print("[!] Invalid option.")
            continue

        username = input("Enter Username: ").strip()
        password = input("Enter Password: ").strip()

        mode = "LOGIN" if choice == "1" else "REGISTER"
        payload = {"type": mode, "username": username, "password": password}
        sock.sendall((json.dumps(payload) + "\n").encode("utf-8"))

        # Wait for response
        resp_line = sock.recv(4096).decode("utf-8").strip()
        if not resp_line:
            print("[!] Server disconnected.")
            return

        res = json.loads(resp_line.split("\n")[0])
        if res.get("success"):
            if mode == "LOGIN":
                logged_in = True
                print(f"[+] Login successful! Welcome, {username}.")
            else:
                print("[+] Registration successful! Please log in now.")
        else:
            print(f"[!] {res.get('message', 'Authentication failed')}")

    print(f"\n[+] Connected to #{current_room}. Type your messages below.")
    print("[+] Commands: '/join <room>' to switch room, '/exit' to quit.\n")

    # Background receiver
    def receive_loop():
        buffer = ""
        while True:
            try:
                data = sock.recv(4096)
                if not data:
                    print("\n[!] Disconnected from server.")
                    break
                buffer += data.decode("utf-8", errors="ignore")
                while "\n" in buffer:
                    line, buffer = buffer.split("\n", 1)
                    line = line.strip()
                    if not line:
                        continue
                    res = json.loads(line)
                    t = res.get("type")
                    if t == "MSG":
                        ts = res.get("timestamp")
                        u = res.get("username")
                        m = res.get("message")
                        if u != username:
                            print(f"\n[{ts}] {u}: {m}")
                    elif t == "SYSTEM":
                        ts = res.get("timestamp")
                        m = res.get("message")
                        print(f"\n[{ts}] ℹ️  {m}")
                    elif t == "ROOM_CHANGED":
                        r = res.get("room")
                        print(f"\n[+] Active room changed to #{r}")
            except Exception:
                break

    threading.Thread(target=receive_loop, daemon=True).start()

    while True:
        try:
            msg = input(f"[{username}]: ").strip()
            if not msg:
                continue
            if msg.lower() == "/exit":
                break
            elif msg.lower().startswith("/join "):
                new_room = msg.split(" ", 1)[1].strip()
                sock.sendall((json.dumps({"type": "JOIN_ROOM", "room": new_room}) + "\n").encode("utf-8"))
            else:
                sock.sendall((json.dumps({"type": "MSG", "message": msg}) + "\n").encode("utf-8"))
        except (KeyboardInterrupt, EOFError):
            break

    sock.close()
    print("\nGoodbye!")


# ============================================================================
# LAUNCHER / ENTRYPOINT
# ============================================================================
def launch_gui_mode(host=DEFAULT_HOST, port=DEFAULT_PORT):
    if not TKINTER_AVAILABLE:
        print("[!] Tkinter is not available in your Python environment.")
        print("[*] Launching CLI mode instead...")
        run_cli_client(host, port)
        return

    root = tk.Tk()
    ChatGUIClient(root, host, port)
    root.mainloop()

def launch_server_mode(host=DEFAULT_HOST, port=DEFAULT_PORT):
    server = ChatServer(host, port)
    try:
        server.start()
    except KeyboardInterrupt:
        print("\nStopping server...")
        server.stop()

def show_launcher():
    """Interactive mode launcher if run without specific command line arguments."""
    if not TKINTER_AVAILABLE:
        print("1. Start Chat Server")
        print("2. Launch Chat Client (CLI)")
        choice = input("Select option (1/2): ").strip()
        if choice == "1":
            launch_server_mode()
        else:
            run_cli_client()
        return

    root = tk.Tk()
    root.title("OIBSIP · Chat Application Launcher")
    root.geometry("450x380")
    root.configure(bg="#0f172a")

    card = tk.Frame(root, bg="#1e293b", padx=30, pady=25, highlightthickness=1, highlightbackground="#334155")
    card.place(relx=0.5, rely=0.5, anchor="center")

    tk.Label(card, text="💬 Chat Application", font=("Segoe UI", 16, "bold"), fg="#f8fafc", bg="#1e293b").pack(pady=(0, 4))
    tk.Label(card, text="Oasis Infobyte SIP · Task 5", font=("Segoe UI", 9), fg="#94a3b8", bg="#1e293b").pack(pady=(0, 20))

    def start_server_action():
        root.destroy()
        print("[*] Starting Chat Server...")
        launch_server_mode()

    def start_gui_client_action():
        root.destroy()
        launch_gui_mode()

    def start_cli_client_action():
        root.destroy()
        run_cli_client()

    btn_server = tk.Button(
        card, text="🚀 Start Chat Server", font=("Segoe UI", 10, "bold"),
        bg="#2563eb", fg="white", activebackground="#1d4ed8", activeforeground="white",
        relief="flat", cursor="hand2", padx=20, pady=8, width=22, command=start_server_action
    )
    btn_server.pack(pady=6)

    btn_client = tk.Button(
        card, text="💬 Launch Chat Client (GUI)", font=("Segoe UI", 10, "bold"),
        bg="#059669", fg="white", activebackground="#047857", activeforeground="white",
        relief="flat", cursor="hand2", padx=20, pady=8, width=22, command=start_gui_client_action
    )
    btn_client.pack(pady=6)

    btn_cli = tk.Button(
        card, text="📟 Launch Chat Client (CLI)", font=("Segoe UI", 9, "bold"),
        bg="#334155", fg="#e2e8f0", activebackground="#475569", activeforeground="white",
        relief="flat", cursor="hand2", padx=20, pady=6, width=22, command=start_cli_client_action
    )
    btn_cli.pack(pady=6)

    root.mainloop()


if __name__ == "__main__":
    if len(sys.argv) > 1:
        arg = sys.argv[1].lower().replace("-", "")
        h = sys.argv[2] if len(sys.argv) > 2 else DEFAULT_HOST
        p = int(sys.argv[3]) if len(sys.argv) > 3 else DEFAULT_PORT

        if arg in ("server", "s"):
            launch_server_mode(h, p)
        elif arg in ("client", "gui", "c"):
            launch_gui_mode(h, p)
        elif arg in ("cli", "terminal"):
            run_cli_client(h, p)
        else:
            print("Usage: python main.py [server | client | cli] [host] [port]")
    else:
        show_launcher()
