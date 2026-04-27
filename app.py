"""
spark. — Python Chat Application
Run with: python app.py
Then open: http://localhost:5000
"""

from flask import Flask, render_template, request, session, redirect, url_for, jsonify
import json, os, time, re
from datetime import datetime
from functools import wraps

app = Flask(__name__)
app.secret_key = "spark-secret-key-change-in-production"


#  DATA STORAGE  (JSON flat-file database)


DATA_DIR      = "data"
USERS_FILE    = os.path.join(DATA_DIR, "users.json")
MESSAGES_FILE = os.path.join(DATA_DIR, "messages.json")

os.makedirs(DATA_DIR, exist_ok=True)


def load_json(path, default):
    try:
        with open(path) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return default


def save_json(path, data):
    with open(path, "w") as f:
        json.dump(data, f, indent=2)


def get_users():    return load_json(USERS_FILE,    {})
def get_messages(): return load_json(MESSAGES_FILE, {})

def save_users(u):    save_json(USERS_FILE,    u)
def save_messages(m): save_json(MESSAGES_FILE, m)


def convo_key(a, b):
    return "::".join(sorted([a, b]))



#   SEED DEFAULT USERS


def seed_data():
    users = get_users()
    if not users:
        defaults = [
            {"username": "alex_vibes",  "name": "Alex Carter", "avatar": "🦊", "password": "1234"},
            {"username": "luna_dev",    "name": "Luna Park",   "avatar": "🌙", "password": "1234"},
            {"username": "cosmic_jay",  "name": "Jay Rivers",  "avatar": "🚀", "password": "1234"},
            {"username": "neon_rose",   "name": "Rose Kim",    "avatar": "🌸", "password": "1234"},
        ]
        for u in defaults:
            users[u["username"]] = u
        save_users(users)

    messages = get_messages()
    if not messages:
        key = convo_key("alex_vibes", "luna_dev")
        messages[key] = [
            {"from": "alex_vibes", "to": "luna_dev",   "text": "hey! welcome to spark 🎉",                       "time": time.time() - 3600},
            {"from": "luna_dev",   "to": "alex_vibes", "text": "omg this is so cool!",                          "time": time.time() - 3500},
            {"from": "alex_vibes", "to": "luna_dev",   "text": "right? search for anyone and just start chatting","time": time.time() - 3400},
        ]
        save_messages(messages)


seed_data()


#  AUTH DECORATOR

def login_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if "username" not in session:
            return redirect(url_for("index"))
        return f(*args, **kwargs)
    return wrapper


#  ROUTES — AUTh

@app.route("/")
def index():
    if "username" in session:
        return redirect(url_for("chat"))
    return render_template("auth.html")


@app.route("/signup", methods=["POST"])
def signup():
    data     = request.get_json()
    name     = data.get("name", "").strip()
    username = data.get("username", "").strip().lower()
    password = data.get("password", "")
    avatar   = data.get("avatar", "🦊")

    if not name or not username or not password:
        return jsonify({"error": "All fields are required."}), 400
    if len(username) < 3:
        return jsonify({"error": "Username must be at least 3 characters."}), 400
    if len(password) < 4:
        return jsonify({"error": "Password must be at least 4 characters."}), 400
    if not re.match(r"^[a-z0-9_]+$", username):
        return jsonify({"error": "Username: only letters, numbers, underscores."}), 400

    users = get_users()
    if username in users:
        return jsonify({"error": "That username is already taken."}), 400

    users[username] = {"username": username, "name": name, "avatar": avatar, "password": password}
    save_users(users)
    session["username"] = username
    return jsonify({"ok": True, "redirect": "/chat"})


@app.route("/login", methods=["POST"])
def login():
    data     = request.get_json()
    username = data.get("username", "").strip().lower()
    password = data.get("password", "")

    users = get_users()
    user  = users.get(username)

    if not user:
        return jsonify({"error": "Username not found."}), 401
    if user["password"] != password:
        return jsonify({"error": "Wrong password."}), 401

    session["username"] = username
    return jsonify({"ok": True, "redirect": "/chat"})


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("index"))


#  ROUTES — MAIN APP


@app.route("/chat")
@login_required
def chat():
    users    = get_users()
    me       = users[session["username"]]
    messages = get_messages()

    # Build conversation list for sidebar
    convos = []
    for key, msgs in messages.items():
        parts = key.split("::")
        if session["username"] not in parts:
            continue
        other_username = [p for p in parts if p != session["username"]][0]
        other = users.get(other_username)
        if not other:
            continue
        last_msg = msgs[-1] if msgs else None
        unread   = sum(1 for m in msgs if m["from"] != session["username"] and not m.get("read"))
        convos.append({
            "key":        key,
            "other":      other,
            "last_msg":   last_msg,
            "unread":     unread,
        })

    convos.sort(key=lambda c: c["last_msg"]["time"] if c["last_msg"] else 0, reverse=True)
    return render_template("chat.html", me=me, convos=convos)


#  API — MESSAGES

@app.route("/api/messages/<other_username>")
@login_required
def get_convo(other_username):
    key      = convo_key(session["username"], other_username)
    messages = get_messages()
    msgs     = messages.get(key, [])

    # Mark all incoming as read
    changed = False
    for m in msgs:
        if m["from"] != session["username"] and not m.get("read"):
            m["read"] = True
            changed = True
    if changed:
        save_messages(messages)

    users = get_users()
    other = users.get(other_username)
    if not other:
        return jsonify({"error": "User not found"}), 404

    return jsonify({"messages": msgs, "other": other})


@app.route("/api/messages/<other_username>", methods=["POST"])
@login_required
def send_message(other_username):
    data = request.get_json()
    text = data.get("text", "").strip()
    if not text:
        return jsonify({"error": "Empty message"}), 400

    users = get_users()
    if other_username not in users:
        return jsonify({"error": "User not found"}), 404

    key      = convo_key(session["username"], other_username)
    messages = get_messages()
    if key not in messages:
        messages[key] = []

    msg = {
        "from": session["username"],
        "to":   other_username,
        "text": text,
        "time": time.time(),
        "read": False,
    }
    messages[key].append(msg)
    save_messages(messages)
    return jsonify({"ok": True, "message": msg})


@app.route("/api/react", methods=["POST"])
@login_required
def react():
    data           = request.get_json()
    other_username = data.get("other")
    idx            = data.get("idx")
    emoji          = data.get("emoji")

    key      = convo_key(session["username"], other_username)
    messages = get_messages()
    msgs     = messages.get(key, [])

    if idx is None or idx >= len(msgs):
        return jsonify({"error": "Invalid message index"}), 400

    msgs[idx]["reaction"] = emoji
    save_messages(messages)
    return jsonify({"ok": True})


#  API — USERS / SEARCH

@app.route("/api/search")
@login_required
def search_users():
    q     = request.args.get("q", "").lower().strip()
    users = get_users()
    if not q:
        return jsonify([])

    results = [
        {"username": u["username"], "name": u["name"], "avatar": u["avatar"]}
        for u in users.values()
        if u["username"] != session["username"]
        and (q in u["username"] or q in u["name"].lower())
    ]
    return jsonify(results)


@app.route("/api/me")
@login_required
def get_me():
    users = get_users()
    me    = users[session["username"]]
    return jsonify({"username": me["username"], "name": me["name"], "avatar": me["avatar"]})


@app.route("/api/poll/<other_username>")
@login_required
def poll_messages(other_username):
    """Long-poll endpoint — returns new messages since a given timestamp."""
    since    = float(request.args.get("since", 0))
    key      = convo_key(session["username"], other_username)
    messages = get_messages()
    msgs     = messages.get(key, [])
    new_msgs = [m for m in msgs if m["time"] > since]

    # Mark as read
    changed = False
    for m in msgs:
        if m["from"] != session["username"] and not m.get("read") and m["time"] > since:
            m["read"] = True
            changed = True
    if changed:
        save_messages(messages)

    return jsonify({"messages": new_msgs})


#  RUN

if __name__ == "__main__":
    print("\n  spark. chat app")
    print("  ─────────────────────────────")
    print("  Running at: http://localhost:5000")
    print("  Press Ctrl+C to stop\n")
    app.run(debug=True, port=5000)