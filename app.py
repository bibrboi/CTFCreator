"""
CTFCreator — Flask Backend
Phase 2: Dynamic rank system replacing hardcoded tier column.
"""

from flask import Flask, render_template, request, jsonify, session, redirect, url_for, send_from_directory
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from datetime import datetime, timezone
import os, random, string, json
from groq import Groq
from dotenv import load_dotenv
load_dotenv()

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", os.urandom(24))
import pathlib
BASE_DIR = pathlib.Path(os.environ.get("PERSISTENT_DIR", pathlib.Path(__file__).parent))
(BASE_DIR / "db").mkdir(parents=True, exist_ok=True)
(BASE_DIR / "uploads" / "challenges").mkdir(parents=True, exist_ok=True)
app.config["SQLALCHEMY_DATABASE_URI"] = f"sqlite:///{BASE_DIR}/db/ctfcreator.db"

# ── File upload config ──────────────────────────────────────────────
UPLOAD_ROOT = BASE_DIR / "uploads" / "challenges"
UPLOAD_ROOT.mkdir(parents=True, exist_ok=True)
MAX_FILE_BYTES = 20 * 1024 * 1024          # 20 MB per file
ALLOWED_EXTENSIONS = {
    "py", "c", "cpp", "h", "js", "ts", "php", "rb", "go", "java",
    "elf", "bin", "exe", "out",
    "pcap", "pcapng",
    "zip", "tar", "gz", "7z", "rar",
    "txt", "md", "pdf",
    "png", "jpg", "jpeg", "gif",
    "pem", "key", "crt", "der",
    "sql", "db", "sqlite",
    "dockerfile", "sh", "bash",
    "json", "xml", "yaml", "yml",
}

def allowed_file(filename: str) -> bool:
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    return ext in ALLOWED_EXTENSIONS or filename.lower() == "dockerfile"

def challenge_upload_dir(challenge_id: int) -> pathlib.Path:
    p = UPLOAD_ROOT / str(challenge_id)
    p.mkdir(parents=True, exist_ok=True)
    return p

db = SQLAlchemy(app)


# ─────────────────────────────────────────────
#  RANK HELPER  (defined before models so User.rank_label can call it)
# ─────────────────────────────────────────────

RANK_TIERS = [
    (801,  "The Ghost"),
    (601,  "Exploiter"),
    (401,  "Hacker"),
    (201,  "CTF Player"),
    (0,    "Script Kiddie"),
]

def get_rank(points: int) -> str:
    """Return the rank label for a given point total."""
    for threshold, label in RANK_TIERS:
        if points >= threshold:
            return label
    return "Script Kiddie"

def get_rank_progress(points: int) -> dict:
    """
    Return current rank, next rank, and percentage progress toward the next tier.
    Useful for progress bars on the profile page (Phase 6).
    """
    thresholds = list(reversed(RANK_TIERS))   # ascending order: [(0,…),(201,…),…]
    current_label = get_rank(points)
    for i, (threshold, label) in enumerate(thresholds):
        if label == current_label:
            if i + 1 < len(thresholds):
                next_threshold, next_label = thresholds[i + 1]
                span     = next_threshold - threshold
                progress = points - threshold
                pct      = min(int((progress / span) * 100), 99)
                return {
                    "current":        current_label,
                    "next":           next_label,
                    "next_at":        next_threshold,
                    "points_needed":  next_threshold - points,
                    "progress_pct":   pct,
                }
            else:
                # Already at top tier
                return {
                    "current":       current_label,
                    "next":          None,
                    "next_at":       None,
                    "points_needed": 0,
                    "progress_pct":  100,
                }
    return {"current": "Script Kiddie", "next": "CTF Player", "next_at": 201,
            "points_needed": 201 - points, "progress_pct": 0}


# ─────────────────────────────────────────────
#  MODELS
# ─────────────────────────────────────────────

class User(db.Model):
    id            = db.Column(db.Integer, primary_key=True)
    username      = db.Column(db.String(50),  unique=True, nullable=False)
    password_hash = db.Column(db.String(256), nullable=False)
    first_name    = db.Column(db.String(50),  default="")
    last_name     = db.Column(db.String(50),  default="")
    email         = db.Column(db.String(120), unique=True, nullable=True)
    role          = db.Column(db.String(20),  default="player")
    points        = db.Column(db.Integer,     default=0)
    global_rank   = db.Column(db.Integer,     default=0)
    # NOTE: 'tier' column removed — rank is now computed from points via get_rank()
    last_login    = db.Column(db.DateTime,    default=lambda: datetime.now(timezone.utc))
    created_at    = db.Column(db.DateTime,    default=lambda: datetime.now(timezone.utc))

    solves        = db.relationship("Solve",     back_populates="user", lazy="dynamic")
    activities    = db.relationship("Activity",  back_populates="user", lazy="dynamic")
    badges        = db.relationship("UserBadge", back_populates="user", lazy="dynamic")

    def set_password(self, pw):   self.password_hash = generate_password_hash(pw)
    def check_password(self, pw): return check_password_hash(self.password_hash, pw)

    @property
    def rank_label(self):
        """Always computed live from current points — never stale."""
        return get_rank(self.points)


class Challenge(db.Model):
    id          = db.Column(db.Integer, primary_key=True)
    title       = db.Column(db.String(120), nullable=False)
    category    = db.Column(db.String(50),  nullable=False)
    difficulty  = db.Column(db.String(20),  nullable=False)
    points      = db.Column(db.Integer,     nullable=False)
    description = db.Column(db.Text,        nullable=False)
    flag        = db.Column(db.String(200),  nullable=False)
    files       = db.Column(db.String(300),  default="")   # comma-separated filenames
    author_id   = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True)
    created_at  = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    solves      = db.relationship("Solve", back_populates="challenge", lazy="dynamic")


class Solve(db.Model):
    id           = db.Column(db.Integer, primary_key=True)
    user_id      = db.Column(db.Integer, db.ForeignKey("user.id"),      nullable=False)
    challenge_id = db.Column(db.Integer, db.ForeignKey("challenge.id"), nullable=False)
    solved_at    = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    user         = db.relationship("User",      back_populates="solves")
    challenge    = db.relationship("Challenge", back_populates="solves")


class Activity(db.Model):
    id         = db.Column(db.Integer, primary_key=True)
    user_id    = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    kind       = db.Column(db.String(30),  nullable=False)   # solved|created|analyzed|attempted
    title      = db.Column(db.String(120), nullable=False)
    category   = db.Column(db.String(50),  default="")
    difficulty = db.Column(db.String(20),  default="")
    delta      = db.Column(db.Integer,     default=0)        # points change (0 = no change)
    label      = db.Column(db.String(30),  default="")       # "analyzed", "created", "failed"
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    user       = db.relationship("User", back_populates="activities")


class UserBadge(db.Model):
    id         = db.Column(db.Integer, primary_key=True)
    user_id    = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    emoji      = db.Column(db.String(10), nullable=False)
    label      = db.Column(db.String(40), nullable=False)
    color      = db.Column(db.String(20), default="#63b3ed")

    user       = db.relationship("User", back_populates="badges")


class Achievement(db.Model):
    """Tracks which achievements a user has unlocked and when."""
    id          = db.Column(db.Integer, primary_key=True)
    user_id     = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    key         = db.Column(db.String(40),  nullable=False)   # e.g. "first_blood"
    name        = db.Column(db.String(60),  nullable=False)
    description = db.Column(db.String(120), nullable=False)
    emoji       = db.Column(db.String(10),  nullable=False)
    unlocked_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    user        = db.relationship("User")


# ─────────────────────────────────────────────
#  SEED DATA
# ─────────────────────────────────────────────

def seed_database():
    if User.query.count() > 0:
        return  # already seeded

    # Competitor accounts — no hardcoded tier, rank_label is computed
    competitors = [
        ("n0cturn4l",   24880, 1),
        ("p4yl0adX",    21330, 2),
        ("r3vXpert",    18750, 3),
        ("b1n4ryGh0st", 15420, 4),
        ("xOr_H4ck3r",    700, 5),   # demo user — sits in "Exploiter" tier
    ]
    users = {}
    for username, pts, rank in competitors:
        u = User(username=username, points=pts, global_rank=rank)
        u.set_password("password123")
        db.session.add(u)
        users[username] = u

    db.session.flush()  # get IDs

    # Badges
    badge_data = {
        "n0cturn4l":   [("🏅","Gold","#ffd700"),("🌐","Web","#63b3ed"),("🔐","Crypto","#a78bfa")],
        "p4yl0adX":    [("🏅","Gold","#ffd700"),("🔥","Fire","#f87171")],
        "r3vXpert":    [("🔐","Crypto","#a78bfa"),("⚡","Speed","#4ade80")],
        "b1n4ryGh0st": [("🌐","Web","#63b3ed")],
        "xOr_H4ck3r":  [("🌐","Web","#63b3ed"),("⚡","Speed","#4ade80")],
    }
    for uname, badges in badge_data.items():
        u = users[uname]
        for emoji, label, color in badges:
            db.session.add(UserBadge(user_id=u.id, emoji=emoji, label=label, color=color))

    # Challenges
    challenges = [
        ("SQL Injection Maze", "Web Exploitation", "Intermediate", 300,
         "A vulnerable login portal is running at the target endpoint. The database contains a hidden admin table with the flag. Exploit the unsanitized input to bypass auth and extract the flag from the <code>admin_secrets</code> table.",
         "CTF{sql_1nj3ct10n_m4st3r}", "chall.py,Dockerfile,README.md"),

        ("RSA Weak Key Recovery", "Cryptography", "Advanced", 500,
         "Two RSA public keys share a common prime factor. Given both public keys and ciphertexts, recover the private keys using the GCD attack and decrypt the hidden flag.",
         "CTF{gcd_4tt4ck_ftw}", "encrypt.py,public_keys.pem,ciphertext.bin"),

        ("Hidden in Plain Sight", "Digital Forensics", "Basic", 150,
         "A suspicious PNG was recovered from a compromised server. Metadata analysis suggests a secondary payload is embedded using LSB steganography. Extract the hidden message.",
         "CTF{l5b_5t3g_ezpz}", "suspect.png,README.md"),

        ("Anti-Debug Bypass", "Reverse Engineering", "Advanced", 450,
         "A binary employs anti-debugging (PTRACE checks, timing attacks). Bypass these protections and analyse the decryption routine to recover the hardcoded flag.",
         "CTF{ptrace_byp4ss_pr0}", "crackme.elf,hints.txt"),

        ("Format String Hell", "Binary Pwn", "Intermediate", 350,
         "A server-side application uses printf with user-controlled format strings. Leak stack addresses, bypass ASLR, and overwrite the return address to spawn a shell.",
         "CTF{f0rm4t_str1ng_3xpl01t}", "vuln,vuln.c,Dockerfile"),

        ("Cookie Monster", "Web Exploitation", "Intermediate", 300,
         "A session management vulnerability lurks in this e-commerce platform. The admin panel at /admin/dashboard checks only a cookie value. Forge the right cookie and claim the flag.",
         "CTF{c00k13_f0rg3ry_m4st3r}", "source.py,Dockerfile"),

        ("JWT Forgery Lab", "Web Exploitation", "Basic", 200,
         "A web app issues JWTs signed with the HS256 algorithm but the secret is weak. Crack the secret, forge an admin token, and access the flag endpoint.",
         "CTF{jwt_4lg_n0n3_byp4ss}", "app.js,README.md"),

        ("Heap Overflow v2", "Binary Pwn", "Advanced", 500,
         "A custom heap allocator contains an off-by-one vulnerability. Corrupt heap metadata, achieve arbitrary write, and redirect code execution to the flag-printing function.",
         "CTF{h34p_c0rrupt10n_n1nj4}", "vuln,vuln.c,Dockerfile"),
    ]
    chall_objects = []
    for title, cat, diff, pts, desc, flag, files in challenges:
        c = Challenge(title=title, category=cat, difficulty=diff, points=pts,
                      description=desc, flag=flag, files=files)
        db.session.add(c)
        chall_objects.append(c)

    db.session.flush()

    # Give the demo user (xOr) some existing solves
    xor = users["xOr_H4ck3r"]
    for c in [chall_objects[2], chall_objects[4], chall_objects[6]]:   # stego, format str, jwt
        db.session.add(Solve(user_id=xor.id, challenge_id=c.id))

    # Recent activity for xOr
    acts = [
        ("solved",   "Format String Hell",  "Binary Pwn",       "Intermediate", 350, ""),
        ("created",  "JWT Forgery Lab",      "Web Exploitation", "Basic",          0, "created"),
        ("analyzed", "RSA-512 Decrypt",      "Cryptography",     "AI Solver",      0, "analyzed"),
        ("solved",   "Steganography 101",    "Digital Forensics","Basic",        150, ""),
        ("attempted","Heap Overflow v2",     "Binary Pwn",       "Advanced",       0, "failed"),
    ]
    for kind, title, cat, diff, delta, label in acts:
        db.session.add(Activity(user_id=xor.id, kind=kind, title=title,
                                category=cat, difficulty=diff, delta=delta, label=label))

    db.session.commit()
    print("✅ Database seeded.")


# ─────────────────────────────────────────────
#  HELPERS
# ─────────────────────────────────────────────

def current_user():
    uid = session.get("user_id")
    return User.query.get(uid) if uid else None


def login_required(f):
    from functools import wraps
    @wraps(f)
    def decorated(*args, **kwargs):
        if not current_user():
            return jsonify({"error": "Not authenticated"}), 401
        return f(*args, **kwargs)
    return decorated


def admin_required(f):
    """Decorator: user must be logged in AND have role 'challenge_creator'."""
    from functools import wraps
    @wraps(f)
    def decorated(*args, **kwargs):
        user = current_user()
        if not user:
            return jsonify({"error": "Not authenticated"}), 401
        if user.role != "challenge_creator":
            return jsonify({"error": "Admin access required"}), 403
        return f(*args, **kwargs)
    return decorated


def _time_ago(dt):
    """Human-readable relative time."""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    now = datetime.now(timezone.utc)
    diff = int((now - dt).total_seconds())
    if diff < 60:     return "just now"
    if diff < 3600:   return f"{diff//60} minutes ago"
    if diff < 86400:  return f"{diff//3600} hours ago"
    if diff < 172800: return "yesterday"
    return f"{diff//86400} days ago"


def _recalculate_ranks():
    """Re-number global_rank for all users by points (descending)."""
    users = User.query.order_by(User.points.desc()).all()
    for i, u in enumerate(users, 1):
        u.global_rank = i
    db.session.commit()


# ─────────────────────────────────────────────
#  ACHIEVEMENT ENGINE
# ─────────────────────────────────────────────

# Full achievement definitions — key, name, description, emoji
ACHIEVEMENTS = [
    {
        "key":         "first_blood",
        "name":        "First Blood",
        "description": "Solved your very first challenge.",
        "emoji":       "🩸",
    },
    {
        "key":         "ctf_addict",
        "name":        "CTF Addict",
        "description": "Solved 5 challenges.",
        "emoji":       "💉",
    },
    {
        "key":         "flag_hunter",
        "name":        "Flag Hunter",
        "description": "Solved 10 challenges.",
        "emoji":       "🚩",
    },
    {
        "key":         "unstoppable",
        "name":        "Unstoppable",
        "description": "Solved 25 challenges.",
        "emoji":       "⚡",
    },
    {
        "key":         "web_master",
        "name":        "Web Master",
        "description": "Solved all Web Exploitation challenges.",
        "emoji":       "🌐",
    },
    {
        "key":         "crypto_master",
        "name":        "Crypto Master",
        "description": "Solved all Cryptography challenges.",
        "emoji":       "🔐",
    },
    {
        "key":         "forensics_master",
        "name":        "Forensics Master",
        "description": "Solved all Digital Forensics challenges.",
        "emoji":       "🔍",
    },
    {
        "key":         "rev_master",
        "name":        "Reverse Engineer",
        "description": "Solved all Reverse Engineering challenges.",
        "emoji":       "⚙️",
    },
    {
        "key":         "pwn_master",
        "name":        "Pwn Master",
        "description": "Solved all Binary Pwn challenges.",
        "emoji":       "💥",
    },
    {
        "key":         "point_century",
        "name":        "Century",
        "description": "Reached 100 points.",
        "emoji":       "💯",
    },
    {
        "key":         "point_millionaire",
        "name":        "Point Millionaire",
        "description": "Reached 1,000 points.",
        "emoji":       "💰",
    },
    {
        "key":         "high_roller",
        "name":        "High Roller",
        "description": "Reached 5,000 points.",
        "emoji":       "🎰",
    },
    {
        "key":         "speedrunner",
        "name":        "Speedrunner",
        "description": "Solved a challenge within 10 minutes of account creation.",
        "emoji":       "⏱️",
    },
    {
        "key":         "ai_pioneer",
        "name":        "AI Pioneer",
        "description": "Used the AI Challenge Generator for the first time.",
        "emoji":       "🤖",
    },
]

ACHIEVEMENT_MAP = {a["key"]: a for a in ACHIEVEMENTS}


def _has_achievement(user_id: int, key: str) -> bool:
    return Achievement.query.filter_by(user_id=user_id, key=key).first() is not None


def _award(user_id: int, key: str) -> dict | None:
    """Award an achievement if not already earned. Returns the achievement dict or None."""
    if _has_achievement(user_id, key):
        return None
    a = ACHIEVEMENT_MAP.get(key)
    if not a:
        return None
    db.session.add(Achievement(
        user_id=user_id, key=key,
        name=a["name"], description=a["description"], emoji=a["emoji"],
    ))
    db.session.flush()
    return a


def check_and_award_achievements(user: "User", challenge: "Challenge" = None) -> list[dict]:
    """
    Run all achievement checks for a user after a solve (or other action).
    Returns list of newly awarded achievements so the API can notify the frontend.
    """
    newly_awarded = []
    uid           = user.id
    solve_count   = user.solves.count()

    def award(key):
        result = _award(uid, key)
        if result:
            newly_awarded.append(result)

    # ── Solve-count milestones ──────────────────────────────────────
    if solve_count >= 1:  award("first_blood")
    if solve_count >= 5:  award("ctf_addict")
    if solve_count >= 10: award("flag_hunter")
    if solve_count >= 25: award("unstoppable")

    # ── Points milestones ───────────────────────────────────────────
    if user.points >= 100:   award("point_century")
    if user.points >= 1000:  award("point_millionaire")
    if user.points >= 5000:  award("high_roller")

    # ── Category mastery ───────────────────────────────────────────
    cat_map = {
        "Web Exploitation":   "web_master",
        "Cryptography":       "crypto_master",
        "Digital Forensics":  "forensics_master",
        "Reverse Engineering":"rev_master",
        "Binary Pwn":         "pwn_master",
    }
    if challenge and challenge.category in cat_map:
        cat          = challenge.category
        total_in_cat = Challenge.query.filter_by(category=cat).count()
        solved_in_cat = (
            db.session.query(Solve)
            .join(Challenge)
            .filter(Solve.user_id == uid, Challenge.category == cat)
            .count()
        )
        if total_in_cat > 0 and solved_in_cat >= total_in_cat:
            award(cat_map[cat])

    # ── Speedrunner — solved within 10 min of account creation ─────
    if challenge and user.created_at:
        solve_time = datetime.now(timezone.utc)
        created    = user.created_at
        # Make both timezone-aware for comparison
        if created.tzinfo is None:
            created = created.replace(tzinfo=timezone.utc)
        if (solve_time - created).total_seconds() <= 600:
            award("speedrunner")

    db.session.commit()
    return newly_awarded


# ─────────────────────────────────────────────
#  AUTH ROUTES
# ─────────────────────────────────────────────

@app.route("/api/auth/login", methods=["POST"])
def api_login():
    data = request.get_json(force=True)
    user = User.query.filter_by(username=data.get("username")).first()
    if not user or not user.check_password(data.get("password", "")):
        return jsonify({"error": "Invalid credentials"}), 401
    user.last_login = datetime.now(timezone.utc)
    db.session.commit()
    session["user_id"] = user.id
    return jsonify({"ok": True, "username": user.username, "role": user.role})


@app.route("/api/auth/logout", methods=["POST"])
def api_logout():
    session.clear()
    return jsonify({"ok": True})


@app.route("/api/auth/register", methods=["POST"])
def api_register():
    data       = request.get_json(force=True)
    username   = data.get("username",   "").strip()
    password   = data.get("password",   "")
    confirm    = data.get("confirm",    "")
    email      = data.get("email",      "").strip()
    first_name = data.get("first_name", "").strip()
    last_name  = data.get("last_name",  "").strip()
    role       = data.get("role",       "player")
    terms      = data.get("terms",      False)

    # Normalise role value from frontend ("creator" → "challenge_creator")
    if role == "creator":
        role = "challenge_creator"
    if role not in ("player", "challenge_creator"):
        role = "player"

    if not username or not password:
        return jsonify({"error": "Username and password are required"}), 400
    if password != confirm:
        return jsonify({"error": "Passwords do not match"}), 400
    if len(password) < 8:
        return jsonify({"error": "Password must be at least 8 characters"}), 400
    if not terms:
        return jsonify({"error": "You must accept the Terms of Service"}), 400
    if User.query.filter_by(username=username).first():
        return jsonify({"error": "Username already taken"}), 409
    if email and User.query.filter_by(email=email).first():
        return jsonify({"error": "Email already registered"}), 409

    u = User(
        username=username, email=email or None,
        first_name=first_name, last_name=last_name, role=role
    )
    u.set_password(password)
    db.session.add(u)
    db.session.commit()
    _recalculate_ranks()
    session["user_id"] = u.id
    return jsonify({
        "ok":         True,
        "username":   u.username,
        "rank_label": u.rank_label,   # "Script Kiddie" for a brand-new user
    }), 201


# ─────────────────────────────────────────────
#  RANK API  (standalone endpoint)
# ─────────────────────────────────────────────

@app.route("/api/ranks", methods=["GET"])
def api_ranks():
    """
    Returns the full tier table so the frontend can render a legend
    or a progress bar without hardcoding the thresholds in JS.
    """
    return jsonify([
        {"label": label, "min_points": threshold}
        for threshold, label in reversed(RANK_TIERS)   # ascending order
    ])


# ─────────────────────────────────────────────
#  DASHBOARD DATA
# ─────────────────────────────────────────────

@app.route("/api/dashboard", methods=["GET"])
@login_required
def api_dashboard():
    user         = current_user()
    solved_count = user.solves.count()
    active_count = Challenge.query.count() - solved_count
    progress     = get_rank_progress(user.points)

    return jsonify({
        "username":      user.username,
        "points":        user.points,
        "global_rank":   user.global_rank,
        "rank_label":    user.rank_label,
        "rank_progress": progress,
        "solved_count":  solved_count,
        "active_count":  max(active_count, 0),
        "last_login":    _time_ago(user.last_login) if user.last_login else "Never",
        "initials":      user.username[:2].upper(),
        "role":          user.role,
    })


# ─────────────────────────────────────────────
#  LEADERBOARD
# ─────────────────────────────────────────────

@app.route("/api/leaderboard", methods=["GET"])
def api_leaderboard():
    top   = User.query.order_by(User.points.desc()).limit(15).all()
    me_id = session.get("user_id")
    rows  = []
    for i, u in enumerate(top, 1):
        rows.append({
            "rank":       i,
            "username":   u.username,
            "points":     u.points,
            "rank_label": u.rank_label,            # computed, never stale
            "initials":   u.username[:2].upper(),
            "is_me":      u.id == me_id,
            "badges":     [{"emoji": b.emoji, "label": b.label, "color": b.color}
                           for b in u.badges],
        })
    return jsonify(rows)


# ─────────────────────────────────────────────
#  RECENT ACTIVITY
# ─────────────────────────────────────────────

@app.route("/api/activity", methods=["GET"])
@login_required
def api_activity():
    user = current_user()
    acts = (Activity.query
            .filter_by(user_id=user.id)
            .order_by(Activity.created_at.desc())
            .limit(10).all())
    result = []
    for a in acts:
        result.append({
            "kind":       a.kind,
            "title":      a.title,
            "category":   a.category,
            "difficulty": a.difficulty,
            "delta":      a.delta,
            "label":      a.label,
            "time_ago":   _time_ago(a.created_at),
        })
    return jsonify(result)


# ─────────────────────────────────────────────
#  CHALLENGES
# ─────────────────────────────────────────────

@app.route("/api/challenges", methods=["GET"])
def api_challenges():
    cat   = request.args.get("category")
    diff  = request.args.get("difficulty")
    q     = Challenge.query
    if cat:  q = q.filter_by(category=cat)
    if diff: q = q.filter_by(difficulty=diff)
    challs = q.all()
    me_id  = session.get("user_id")
    solved_ids = set()
    if me_id:
        solved_ids = {s.challenge_id for s in Solve.query.filter_by(user_id=me_id).all()}

    return jsonify([{
        "id":          c.id,
        "title":       c.title,
        "category":    c.category,
        "difficulty":  c.difficulty,
        "points":      c.points,
        "description": c.description,
        "files":       c.files.split(",") if c.files else [],
        "solved":      c.id in solved_ids,
        "solve_count": c.solves.count(),
    } for c in challs])


@app.route("/api/challenges/<int:cid>", methods=["GET"])
def api_challenge_detail(cid):
    c = Challenge.query.get_or_404(cid)
    return jsonify({
        "id":          c.id,
        "title":       c.title,
        "category":    c.category,
        "difficulty":  c.difficulty,
        "points":      c.points,
        "description": c.description,
        "files":       c.files.split(",") if c.files else [],
        "solve_count": c.solves.count(),
    })


@app.route("/api/challenges/ai-generate", methods=["POST"])
@login_required
def api_ai_generate():
    """
    Use Gemini to generate a brand-new CTF challenge from scratch.
    Saves the challenge + generated file to DB and disk immediately (Option B).
    """
    data = request.get_json(force=True)
    cat  = data.get("category",  "Web Exploitation")
    diff = data.get("difficulty", "Basic")

    # Validate inputs
    if cat not in VALID_CATEGORIES:
        return jsonify({"error": "Invalid category"}), 400
    if diff not in VALID_DIFFICULTIES:
        return jsonify({"error": "Invalid difficulty"}), 400

    # ── Points mapping ──────────────────────────────────────────────
    points_map = {
        ("Basic",        "Web Exploitation"):   150,
        ("Basic",        "Cryptography"):       150,
        ("Basic",        "Digital Forensics"):  100,
        ("Basic",        "Reverse Engineering"):200,
        ("Basic",        "Binary Pwn"):         200,
        ("Intermediate", "Web Exploitation"):   300,
        ("Intermediate", "Cryptography"):       350,
        ("Intermediate", "Digital Forensics"):  250,
        ("Intermediate", "Reverse Engineering"):350,
        ("Intermediate", "Binary Pwn"):         350,
        ("Advanced",     "Web Exploitation"):   450,
        ("Advanced",     "Cryptography"):       500,
        ("Advanced",     "Digital Forensics"):  400,
        ("Advanced",     "Reverse Engineering"):450,
        ("Advanced",     "Binary Pwn"):         500,
    }
    points = points_map.get((diff, cat), 300)

    # ── File type guidance per category ────────────────────────────
    file_guidance = {
        "Web Exploitation":   "a vulnerable Python Flask app (app.py) that contains the vulnerability described",
        "Cryptography":       "a Python encryption script (encrypt.py) that was used to encrypt the flag, plus output the ciphertext as a variable inside the same file",
        "Digital Forensics":  "a Python script (generate.py) that creates a file with hidden data (simulate it with comments and print statements showing what the tool would do)",
        "Reverse Engineering":"a C source file (chall.c) with the flag hidden/obfuscated inside using XOR or string reversal, that needs to be analyzed to extract it",
        "Binary Pwn":         "a vulnerable C source file (vuln.c) that contains the memory vulnerability described (buffer overflow, format string, etc.)",
    }
    file_hint = file_guidance.get(cat, "a Python helper script (helper.py) related to the challenge")

    # ── Build the prompt ────────────────────────────────────────────
    prompt = f"""You are a CTF (Capture The Flag) challenge designer. Generate a complete, original CTF challenge.

Category: {cat}
Difficulty: {diff}
Points: {points}

Requirements:
- The challenge must be realistic and solvable
- The flag MUST be in the exact format: CTF{{some_meaningful_text_here}}
- The flag text should relate to the exploit/technique used
- The description should give enough context without giving away the solution
- Include hints through the narrative but not the direct answer
- Also generate {file_hint}

Respond ONLY with a valid JSON object in this exact structure, no markdown, no explanation:
{{
  "title": "Challenge title (max 60 chars, creative and specific)",
  "description": "Full challenge description with scenario context. Can include <code>tags</code> for inline code. 3-5 sentences.",
  "flag": "CTF{{meaningful_flag_text}}",
  "file_name": "filename.ext",
  "file_content": "Complete file content as a string. Must be real, working code relevant to the challenge. Minimum 20 lines."
}}"""

    # ── Call Groq API ───────────────────────────────────────────────
    try:
        client = Groq(api_key=os.environ.get("GROQ_API_KEY"))
        chat   = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.9,
            max_tokens=2048,
        )
        raw = chat.choices[0].message.content.strip()

        # Strip markdown fences if model wraps in ```json
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
            raw = raw.strip()

        # First attempt: standard parse
        try:
            generated = json.loads(raw)
        except json.JSONDecodeError:
            # Llama sometimes emits literal newlines/tabs inside string values.
            # Extract file_content separately, then parse the rest safely.
            import re

            # Pull out file_content block first (everything between the key and the last closing brace area)
            fc_match = re.search(r'"file_content"\s*:\s*"(.*?)"(?=\s*\})', raw, re.DOTALL)
            file_content_raw = fc_match.group(1) if fc_match else ""

            # Remove the file_content key+value from raw so the rest is clean JSON
            raw_stripped = re.sub(r',?\s*"file_content"\s*:\s*".*?"(?=\s*\})', '', raw, flags=re.DOTALL)

            # Parse the stripped JSON
            generated = json.loads(raw_stripped)

            # Decode the file_content string (unescape \\n → \n etc.)
            try:
                file_content_decoded = bytes(file_content_raw, "utf-8").decode("unicode_escape")
            except Exception:
                file_content_decoded = file_content_raw.replace("\\n", "\n").replace("\\t", "\t")

            generated["file_content"] = file_content_decoded

    except json.JSONDecodeError as e:
        return jsonify({"error": f"AI returned invalid JSON: {str(e)}"}), 500
    except Exception as e:
        return jsonify({"error": f"Generation failed: {str(e)}"}), 500

    # ── Validate required fields ────────────────────────────────────
    required = ["title", "description", "flag", "file_name", "file_content"]
    for field in required:
        if not generated.get(field):
            return jsonify({"error": f"AI response missing field: {field}"}), 500

    flag = generated["flag"].strip()
    if not flag.startswith("CTF{") or not flag.endswith("}"):
        return jsonify({"error": "AI generated an invalid flag format"}), 500

    # ── Save challenge to DB ────────────────────────────────────────
    safe_filename_str = secure_filename(generated["file_name"])
    if not safe_filename_str:
        safe_filename_str = "challenge_file.py"

    c = Challenge(
        title=generated["title"][:120],
        category=cat,
        difficulty=diff,
        points=points,
        description=generated["description"],
        flag=flag,
        files=safe_filename_str,
        author_id=None,   # AI-generated — no human author
    )
    db.session.add(c)
    db.session.flush()  # get c.id before writing file

    # ── Save generated file to disk ─────────────────────────────────
    upload_dir = challenge_upload_dir(c.id)
    file_path  = upload_dir / safe_filename_str
    file_path.write_text(generated["file_content"], encoding="utf-8")

    # ── Log activity for the requesting user ────────────────────────
    user = current_user()
    db.session.add(Activity(
        user_id=user.id, kind="created", title=c.title,
        category=cat, difficulty=diff, delta=0, label="ai-generated"
    ))
    db.session.commit()

    # Award AI Pioneer on first use of the generator
    ai_pioneer = _award(user.id, "ai_pioneer")
    if ai_pioneer:
        db.session.commit()

    return jsonify({
        "id":          c.id,
        "title":       c.title,
        "category":    c.category,
        "difficulty":  c.difficulty,
        "points":      c.points,
        "description": c.description,
        "flag":        c.flag,
        "files":       [safe_filename_str],
        "ai_generated": True,
    }), 201


# ─────────────────────────────────────────────
#  FLAG SUBMISSION
# ─────────────────────────────────────────────

@app.route("/api/challenges/<int:cid>/submit", methods=["POST"])
@login_required
def api_submit_flag(cid):
    user = current_user()
    c    = Challenge.query.get_or_404(cid)
    data = request.get_json(force=True)
    flag = data.get("flag", "").strip()

    # Already solved?
    if Solve.query.filter_by(user_id=user.id, challenge_id=cid).first():
        return jsonify({"result": "already_solved", "message": "You already solved this challenge."})

    if flag == c.flag:
        old_rank_label = user.rank_label
        db.session.add(Solve(user_id=user.id, challenge_id=cid))
        user.points += c.points
        db.session.add(Activity(
            user_id=user.id, kind="solved", title=c.title,
            category=c.category, difficulty=c.difficulty, delta=c.points
        ))
        db.session.commit()
        _recalculate_ranks()

        # Check and award achievements
        new_achievements = check_and_award_achievements(user, challenge=c)

        new_rank_label = user.rank_label
        rank_up        = new_rank_label != old_rank_label

        return jsonify({
            "result":           "correct",
            "message":          f"FLAG ACCEPTED — +{c.points} pts! {'🎉 Rank up: ' + new_rank_label + '!' if rank_up else 'Rank updated.'}",
            "points":           user.points,
            "global_rank":      user.global_rank,
            "rank_label":       new_rank_label,
            "rank_progress":    get_rank_progress(user.points),
            "rank_up":          rank_up,
            "rank_up_label":    new_rank_label if rank_up else None,
            "new_achievements": new_achievements,
        })
    else:
        db.session.add(Activity(
            user_id=user.id, kind="attempted", title=c.title,
            category=c.category, difficulty=c.difficulty, delta=0, label="failed"
        ))
        db.session.commit()
        return jsonify({"result": "incorrect", "message": "INCORRECT FLAG — Check your exploit and try again."})


# ─────────────────────────────────────────────
#  SESSION CHECK (for welcome page)
# ─────────────────────────────────────────────

@app.route("/api/me", methods=["GET"])
def api_me():
    """Check if user is logged in and return basic info."""
    user = current_user()
    if user:
        return jsonify({
            "authenticated": True,
            "username": user.username,
            "points": user.points,
            "rank_label": user.rank_label,
            "role": user.role,
        })
    return jsonify({"authenticated": False})


@app.route("/api/user/<username>/profile", methods=["GET"])
def api_user_profile(username):
    """Public profile data for any user."""
    me_id = session.get("user_id")
    u = User.query.filter_by(username=username).first_or_404()

    solves = u.solves.all()
    cat_breakdown = {}
    for s in solves:
        cat = s.challenge.category if s.challenge else "Unknown"
        cat_breakdown[cat] = cat_breakdown.get(cat, 0) + 1

    # Achievements — earned ones only for public profile
    earned = Achievement.query.filter_by(user_id=u.id).order_by(Achievement.unlocked_at).all()
    achievements = [{
        "key":         a.key,
        "name":        a.name,
        "description": a.description,
        "emoji":       a.emoji,
        "unlocked_at": a.unlocked_at.strftime("%Y-%m-%d") if a.unlocked_at else None,
    } for a in earned]

    acts = (Activity.query
            .filter_by(user_id=u.id)
            .order_by(Activity.created_at.desc())
            .limit(10).all())
    activity = [{
        "kind":       a.kind,
        "title":      a.title,
        "category":   a.category,
        "difficulty": a.difficulty,
        "delta":      a.delta,
        "label":      a.label,
        "time_ago":   _time_ago(a.created_at),
    } for a in acts]

    return jsonify({
        "username":      u.username,
        "initials":      u.username[:2].upper(),
        "points":        u.points,
        "global_rank":   u.global_rank,
        "rank_label":    u.rank_label,
        "rank_progress": get_rank_progress(u.points),
        "solve_count":   len(solves),
        "achievements":  achievements,
        "cat_breakdown": cat_breakdown,
        "activity":      activity,
        "member_since":  u.created_at.strftime("%b %Y") if u.created_at else "—",
        "last_seen":     _time_ago(u.last_login) if u.last_login else "Never",
        "is_me":         u.id == me_id,
    })


@app.route("/admin")
def admin_page():
    user = current_user()
    if not user:
        return redirect("/login")
    if user.role != "challenge_creator":
        return redirect("/dashboard")
    return render_template("admin.html")


# ─────────────────────────────────────────────
#  ADMIN — CHALLENGE CRUD  (Phase 2 & 3)
# ─────────────────────────────────────────────

VALID_CATEGORIES  = {"Web Exploitation", "Cryptography", "Digital Forensics",
                     "Reverse Engineering", "Binary Pwn"}
VALID_DIFFICULTIES = {"Basic", "Intermediate", "Advanced"}


@app.route("/api/admin/challenges", methods=["GET"])
@admin_required
def api_admin_list_challenges():
    """List all challenges with author info and solve counts."""
    challs = Challenge.query.order_by(Challenge.created_at.desc()).all()
    return jsonify([{
        "id":          c.id,
        "title":       c.title,
        "category":    c.category,
        "difficulty":  c.difficulty,
        "points":      c.points,
        "flag":        c.flag,
        "description": c.description,
        "files":       c.files or "",
        "solve_count": c.solves.count(),
        "created_at":  c.created_at.strftime("%Y-%m-%d") if c.created_at else "—",
        "author_id":   c.author_id,
    } for c in challs])


@app.route("/api/admin/challenges", methods=["POST"])
@admin_required
def api_admin_create_challenge():
    """Create a new challenge."""
    user = current_user()
    data = request.get_json(force=True)

    title       = (data.get("title",       "") or "").strip()
    category    = (data.get("category",    "") or "").strip()
    difficulty  = (data.get("difficulty",  "") or "").strip()
    description = (data.get("description", "") or "").strip()
    flag        = (data.get("flag",        "") or "").strip()

    try:
        points = int(data.get("points", 0))
    except (ValueError, TypeError):
        return jsonify({"error": "Points must be a number"}), 400

    # Validation
    if not title:
        return jsonify({"error": "Title is required"}), 400
    if category not in VALID_CATEGORIES:
        return jsonify({"error": f"Invalid category. Choose from: {', '.join(sorted(VALID_CATEGORIES))}"}), 400
    if difficulty not in VALID_DIFFICULTIES:
        return jsonify({"error": "Difficulty must be Basic, Intermediate, or Advanced"}), 400
    if points < 1 or points > 1000:
        return jsonify({"error": "Points must be between 1 and 1000"}), 400
    if not description:
        return jsonify({"error": "Description is required"}), 400
    if not flag:
        return jsonify({"error": "Flag is required"}), 400
    if not flag.startswith("CTF{") or not flag.endswith("}"):
        return jsonify({"error": "Flag must be in CTF{...} format"}), 400

    c = Challenge(
        title=title, category=category, difficulty=difficulty,
        points=points, description=description, flag=flag,
        files="", author_id=user.id,
    )
    db.session.add(c)
    db.session.add(Activity(
        user_id=user.id, kind="created", title=title,
        category=category, difficulty=difficulty, delta=0, label="created"
    ))
    db.session.commit()

    return jsonify({"ok": True, "id": c.id, "title": c.title}), 201


@app.route("/api/admin/challenges/<int:cid>", methods=["PUT"])
@admin_required
def api_admin_update_challenge(cid):
    """Update an existing challenge."""
    c    = Challenge.query.get_or_404(cid)
    data = request.get_json(force=True)

    title       = (data.get("title",       c.title)       or "").strip()
    category    = (data.get("category",    c.category)    or "").strip()
    difficulty  = (data.get("difficulty",  c.difficulty)  or "").strip()
    description = (data.get("description", c.description) or "").strip()
    flag        = (data.get("flag",        c.flag)        or "").strip()

    try:
        points = int(data.get("points", c.points))
    except (ValueError, TypeError):
        return jsonify({"error": "Points must be a number"}), 400

    if not title:
        return jsonify({"error": "Title is required"}), 400
    if category not in VALID_CATEGORIES:
        return jsonify({"error": f"Invalid category"}), 400
    if difficulty not in VALID_DIFFICULTIES:
        return jsonify({"error": "Invalid difficulty"}), 400
    if points < 1 or points > 1000:
        return jsonify({"error": "Points must be between 1 and 1000"}), 400
    if not description:
        return jsonify({"error": "Description is required"}), 400
    if not flag:
        return jsonify({"error": "Flag is required"}), 400
    if not flag.startswith("CTF{") or not flag.endswith("}"):
        return jsonify({"error": "Flag must be in CTF{...} format"}), 400

    c.title       = title
    c.category    = category
    c.difficulty  = difficulty
    c.points      = points
    c.description = description
    c.flag        = flag
    # NOTE: c.files is NOT touched here — managed exclusively by upload/delete endpoints
    db.session.commit()

    return jsonify({"ok": True, "id": c.id})


@app.route("/api/admin/challenges/<int:cid>", methods=["DELETE"])
@admin_required
def api_admin_delete_challenge(cid):
    """Delete a challenge and all its solves."""
    c = Challenge.query.get_or_404(cid)
    # Delete all uploaded files from disk
    upload_dir = UPLOAD_ROOT / str(cid)
    if upload_dir.exists():
        import shutil
        shutil.rmtree(str(upload_dir))
    # Cascade delete solves manually (SQLite doesn't enforce FK cascades by default)
    Solve.query.filter_by(challenge_id=cid).delete()
    db.session.delete(c)
    db.session.commit()
    return jsonify({"ok": True})


@app.route("/api/admin/stats", methods=["GET"])
@admin_required
def api_admin_stats():
    """Quick stats for the admin dashboard header."""
    return jsonify({
        "total_challenges": Challenge.query.count(),
        "total_players":    User.query.filter_by(role="player").count(),
        "total_solves":     Solve.query.count(),
        "total_admins":     User.query.filter_by(role="challenge_creator").count(),
    })


# ─────────────────────────────────────────────
#  SERVE FRONTEND
# ─────────────────────────────────────────────

@app.route("/")
def index():
    return render_template("welcome.html")  # Landing page

@app.route("/login")
def login_page():
    return render_template("login.html")

@app.route("/signup")
def signup_page():
    return render_template("signup.html")

@app.route("/challenges")
def challenges_page():
    if not current_user():
        return redirect("/login")
    return render_template("challenges.html")

@app.route("/dashboard")
def dashboard_page():
    if not current_user():
        return redirect("/login")
    return render_template("dashboard.html")

@app.route("/leaderboard")
def leaderboard_page():
    if not current_user():
        return redirect("/login")
    return render_template("leaderboard.html")

@app.route("/profile/<username>")
def profile_page(username):
    if not current_user():
        return redirect("/login")
    # This renders your profile.html layout. 
    # Your frontend JS will then use the 'username' from the URL to fetch from /api/user/<username>/profile
    return render_template("profile.html")


@app.route("/api/user/achievements", methods=["GET"])
@login_required
def api_user_achievements():
    """Return all achievements — unlocked ones with date, locked ones greyed out."""
    user   = current_user()
    earned = {a.key: a.unlocked_at for a in Achievement.query.filter_by(user_id=user.id).all()}
    result = []
    for a in ACHIEVEMENTS:
        unlocked_at = earned.get(a["key"])
        result.append({
            "key":         a["key"],
            "name":        a["name"],
            "description": a["description"],
            "emoji":       a["emoji"],
            "unlocked":    a["key"] in earned,
            "unlocked_at": unlocked_at.strftime("%Y-%m-%d") if unlocked_at else None,
        })
    return jsonify({
        "achievements": result,
        "total":        len(ACHIEVEMENTS),
        "earned":       len(earned),
    })


@app.route("/settings")
def settings_page():
    if not current_user():
        return redirect("/login")
    return render_template("settings.html")


@app.route("/api/user/settings", methods=["GET"])
@login_required
def api_get_settings():
    user = current_user()
    return jsonify({
        "username":   user.username,
        "email":      user.email or "",
        "first_name": user.first_name or "",
        "last_name":  user.last_name or "",
        "role":       user.role,
    })


@app.route("/api/user/settings", methods=["POST"])
@login_required
def api_update_settings():
    user = current_user()
    data = request.get_json(force=True)

    first_name   = (data.get("first_name",   "") or "").strip()[:50]
    last_name    = (data.get("last_name",    "") or "").strip()[:50]
    email        = (data.get("email",        "") or "").strip()[:120]
    new_password = (data.get("new_password", "") or "").strip()
    cur_password = (data.get("cur_password", "") or "").strip()

    # Email uniqueness check
    if email and email != user.email:
        existing = User.query.filter_by(email=email).first()
        if existing and existing.id != user.id:
            return jsonify({"error": "Email already in use"}), 400

    user.first_name = first_name
    user.last_name  = last_name
    user.email      = email or None

    # Password change — requires current password
    if new_password:
        if not cur_password:
            return jsonify({"error": "Current password required to set a new one"}), 400
        if not user.check_password(cur_password):
            return jsonify({"error": "Current password is incorrect"}), 400
        if len(new_password) < 8:
            return jsonify({"error": "New password must be at least 8 characters"}), 400
        user.set_password(new_password)

    db.session.commit()
    return jsonify({"ok": True, "message": "Settings saved successfully"})
# ─────────────────────────────────────────────

@app.route("/api/admin/challenges/<int:cid>/files", methods=["POST"])
@admin_required
def api_admin_upload_file(cid):
    """Upload one or more files to a challenge. Multipart form data."""
    c = Challenge.query.get_or_404(cid)

    if "files" not in request.files:
        return jsonify({"error": "No files in request"}), 400

    uploaded   = []
    errors     = []
    upload_dir = challenge_upload_dir(cid)

    for f in request.files.getlist("files"):
        if not f or not f.filename:
            continue

        original_name = f.filename.strip()
        if not allowed_file(original_name):
            ext = original_name.rsplit(".", 1)[-1] if "." in original_name else "?"
            errors.append(f"{original_name}: .{ext} files are not allowed")
            continue

        safe_name = secure_filename(original_name)
        if not safe_name:
            errors.append(f"{original_name}: invalid filename")
            continue

        # Read and size-check before writing
        data = f.read()
        if len(data) > MAX_FILE_BYTES:
            errors.append(f"{safe_name}: exceeds 20 MB limit")
            continue

        dest = upload_dir / safe_name
        dest.write_bytes(data)

        # Add to Challenge.files (avoid duplicates)
        current = [x for x in (c.files or "").split(",") if x.strip()]
        if safe_name not in current:
            current.append(safe_name)
            c.files = ",".join(current)

        uploaded.append(safe_name)

    db.session.commit()

    return jsonify({
        "ok":       True,
        "uploaded": uploaded,
        "errors":   errors,
        "files":    [x for x in (c.files or "").split(",") if x.strip()],
    })


@app.route("/api/admin/challenges/<int:cid>/files/<filename>", methods=["DELETE"])
@admin_required
def api_admin_delete_file(cid, filename):
    """Remove a single file from a challenge."""
    c         = Challenge.query.get_or_404(cid)
    safe_name = secure_filename(filename)
    dest      = challenge_upload_dir(cid) / safe_name

    # Delete from disk (ignore if already gone)
    if dest.exists():
        dest.unlink()

    # Remove from DB column
    current = [x for x in (c.files or "").split(",") if x.strip() and x != safe_name]
    c.files = ",".join(current)
    db.session.commit()

    return jsonify({
        "ok":    True,
        "files": current,
    })


@app.route("/files/<int:cid>/<path:filename>")
@login_required
def serve_challenge_file(cid, filename):
    """Serve a challenge file to any authenticated player (triggers browser download)."""
    # Verify the challenge exists
    Challenge.query.get_or_404(cid)
    upload_dir = UPLOAD_ROOT / str(cid)
    safe_name  = secure_filename(filename)
    return send_from_directory(
        str(upload_dir),
        safe_name,
        as_attachment=True,
    )


# ─────────────────────────────────────────────
#  AI SOLVER BOT
# ─────────────────────────────────────────────

@app.route("/api/challenges/solve", methods=["POST"])
@login_required
def api_ai_solve():
    """
    Analyse a CTF challenge using Groq/Llama and return
    structured solving guidance (steps, hint, explanation, category).
    """
    data        = request.get_json(force=True)
    user_input  = (data.get("input", "") or "").strip()
    file_content = (data.get("file_content", "") or "").strip()

    if not user_input and not file_content:
        return jsonify({"error": "No challenge input provided"}), 400

    # Build combined context
    context = user_input
    if file_content:
        context += f"\n\n--- Attached File Content ---\n{file_content[:3000]}"

    prompt = f"""You are an expert CTF (Capture The Flag) security analyst and educator.
Analyze the following CTF challenge and provide structured solving guidance.
Do NOT reveal the exact flag — guide the player toward finding it themselves.

Challenge Input:
{context}

Respond ONLY with a valid JSON object in this exact structure, no markdown, no backticks:
{{
  "category": "One of: Web Exploitation, Cryptography, Digital Forensics, Reverse Engineering, Binary Pwn",
  "steps": [
    "Step 1 description",
    "Step 2 description",
    "Step 3 description",
    "Step 4 description"
  ],
  "tools": ["tool1", "tool2", "tool3"],
  "hint": "A useful hint that points toward the solution without giving it away directly",
  "explanation": "A paragraph explaining the vulnerability or technique involved and why it works"
}}"""

    try:
        client = Groq(api_key=os.environ.get("GROQ_API_KEY"))
        chat   = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.6,
            max_tokens=1024,
        )
        raw = chat.choices[0].message.content.strip()

        # Strip markdown fences
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
            raw = raw.strip()

        parsed = json.loads(raw)

    except json.JSONDecodeError as e:
        return jsonify({"error": f"AI returned invalid JSON: {str(e)}"}), 500
    except Exception as e:
        return jsonify({"error": f"Solver failed: {str(e)}"}), 500

    # Ensure required keys exist with fallbacks
    return jsonify({
        "category":    parsed.get("category", "Unknown"),
        "steps":       parsed.get("steps",    ["Analyze the challenge carefully."]),
        "tools":       parsed.get("tools",    []),
        "hint":        parsed.get("hint",     "Read the challenge description carefully."),
        "explanation": parsed.get("explanation", ""),
    })


# ─────────────────────────────────────────────
#  BOOT
# ─────────────────────────────────────────────

with app.app_context():
    db.create_all()
    seed_database()

if __name__ == "__main__":
    app.run(debug=False, port=5000)