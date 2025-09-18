from flask import Flask, render_template, request, redirect, url_for, session, flash
import random
import secrets
import time

app = Flask(__name__)
app.secret_key = "super_secret_key"

# ======= GLOBAL STATE =======
STATE = {
    "detection": 0,
    "max_detection": 5,
    "files": 0,
    "credits": 0,
    # Start with NO defense use available (you requested this)
    "defense_boost_available": 0,
    "defense_boost_hacks_left": 0,
}

DEFENSE_REDUCTION_MULTIPLIER = 0.5

# Per-defense hack attempt logs
DEFENSE_LOGS = {
    "wires":   {"success": 0, "fail": 0},
    "keypad":  {"success": 0, "fail": 0},
    "firewall":{"success": 0, "fail": 0},
}

FILE_POOL = [
    ("waf_rules.conf", 5),
    ("threat_intel.db", 7),
    ("packet_capture.pcap", 4),
    ("exfil.tar", 6),
    ("creds.csv", 3),
    ("ops_notes.md", 2),
]

# Black market: 3 GB -> 1 credit
GB_PER_CREDIT = 3

# Defender passwords
PASS_WIRES = "-"
PASS_KEYPAD = "124578"
PASS_FIREWALL = "upgrade"

# Server-side puzzle store (token -> {"expected":..., "system":...})
PUZZLES = {}

# Cooldown after finish/cancel (seconds)
COOLDOWN_SECONDS = 10

def start_cooldown():
    session["hack_cooldown_until"] = time.time() + COOLDOWN_SECONDS

def cooldown_remaining():
    until = session.get("hack_cooldown_until", 0)
    return max(0, int(round(until - time.time())))


# ======= HELPERS (PUZZLES MATCH TRAINING RULES) =======
def gen_wires():
    case = random.choice(["two_rb", "two_gy", "three_any", "one_red_other"])
    if case == "two_rb":
        return {"system": "wires", "desc": "Indicators: 2 lights | wires: red, blue", "expected": "connect red blue"}
    elif case == "two_gy":
        return {"system": "wires", "desc": "Indicators: 2 lights | wires: green, yellow", "expected": "cut green"}
    elif case == "three_any":
        # show two random wires for flavor but expected remains 'disconnect all'
        colors = ["red", "green", "blue", "yellow"]
        shown = random.sample(colors, 2)
        desc = f"Indicators: 3 lights | wires: {shown[0]}, {shown[1]}"
        return {"system": "wires", "desc": desc, "expected": "disconnect all"}
    else:
        other = random.choice(["blue", "green", "yellow"])
        return {"system": "wires", "desc": f"Indicators: 1 light | wires: red, {other}", "expected": f"cut {other}"}

def gen_keypad():
    n = random.randint(1, 9)
    if n == 9:
        expected = "999"
    elif n % 2 == 0:
        expected = str(n * 2)
    else:
        expected = str(n + 3)
    return {"system": "keypad", "desc": f"Indicator number: {n}", "expected": expected}

def gen_firewall():
    start = random.choice("ABCD")
    rest = "".join(random.choice("ABCDEF") for _ in range(2))
    pat = (start + rest).upper()
    if start == "A":
        expected = pat[::-1]
    elif start == "B":
        expected = pat + pat
    elif start == "C":
        mid = len(pat) // 2
        expected = pat[:mid] + pat[mid+1:]
    else:
        expected = pat
    return {"system": "firewall", "desc": f"Firewall pattern: {pat}", "expected": expected}

def start_puzzle():
    """Start a random puzzle; store expected server-side and token in session only."""
    p = random.choice([gen_wires(), gen_keypad(), gen_firewall()])
    # display fields (safe) in session
    session["p_system"] = p["system"]
    session["p_desc"] = p["desc"]
    # server-side expected via token
    token = secrets.token_urlsafe(16)
    session["p_token"] = token
    PUZZLES[token] = {"expected": p["expected"], "system": p["system"]}

def clear_puzzle():
    """Remove server-side token and any session puzzle keys."""
    token = session.pop("p_token", None)
    if token:
        PUZZLES.pop(token, None)
    session.pop("p_system", None)
    session.pop("p_desc", None)

def hacker_success(system):
    selection = random.sample(FILE_POOL, k=2)
    size = sum(sz for _, sz in selection)
    if size == 0:
        size = random.randint(10, 40)

    # Apply defense boost if active (reduce intel gain)
    if STATE["defense_boost_hacks_left"] > 0:
        reduced = max(1, int(round(size * DEFENSE_REDUCTION_MULTIPLIER)))
        size = reduced

    STATE["files"] += size
    return selection, size


# ======= ROUTES =======
@app.route("/")
def index():
    return render_template("index.html", state=STATE)

@app.route("/training")
def training():
    # If a hack is active (token exists server-side), redirect back to Hack
    token = session.get("p_token")
    if token and token in PUZZLES:
        flash("Finish or cancel your current hack first.", "warn")
        return redirect(url_for("hack"))
    return render_template("training.html")

@app.route("/hack", methods=["GET", "POST"])
def hack():
    """
    No auto-start. Puzzle is active only if session['p_token'] exists AND token in PUZZLES.
    Submit requires answer server-side only.
    Cancel: +1 detection, but if at max detection, traced penalty (-12GB).
    After submit or cancel, a 10s cooldown starts.
    """
    result = None
    files = []
    total = 0

    # Cleanup: if a token is in session but not present server-side, clear it.
    token = session.get("p_token")
    if token and token not in PUZZLES:
        clear_puzzle()

    if request.method == "POST":
        action = request.form.get("action")

        if action == "new":
            # If already active, warn
            if session.get("p_token") and session["p_token"] in PUZZLES:
                flash("A hack is already in progress.", "warn")
            else:
                # Enforce 10s cooldown
                rem = cooldown_remaining()
                if rem > 0:
                    result = {"neutral": True, "msg": f"Cooldown active — try again in {rem}s."}
                else:
                    start_puzzle()

        elif action == "submit":
            token = session.get("p_token")
            if not token or token not in PUZZLES:
                flash("Start a hack first.", "warn")
            else:
                answer = (request.form.get("answer") or "").strip().lower()
                expected = (PUZZLES.get(token, {}).get("expected") or "").strip().lower()
                sysname = PUZZLES.get(token, {}).get("system")

                if answer == "":
                    result = {"neutral": True, "msg": "You must enter an answer to submit."}
                else:
                    if expected != "" and answer == expected:
                        files, total = hacker_success(sysname)
                        DEFENSE_LOGS[sysname]["success"] += 1
                        result = {"ok": True, "msg": f"Hack success on {sysname.upper()} — +{total}GB intel."}
                    else:
                        DEFENSE_LOGS[sysname]["fail"] += 1
                        STATE["detection"] = min(STATE["max_detection"], STATE["detection"] + 1)

                        # At max detection, apply -12GB penalty
                        if STATE["detection"] >= STATE["max_detection"]:
                            penalty = min(12, STATE["files"])
                            STATE["files"] -= penalty
                            result = {
                                "ok": False,
                                "msg": f"Hack failed on {sysname.upper()} — detection raised. ",
                                "bad": f"Been traced — -{penalty}GB penalty."
                            }
                        else:
                            result = {"ok": False, "msg": f"Hack failed on {sysname.upper()} — detection raised."}

                    # count down defense boost attempts if active
                    if STATE["defense_boost_hacks_left"] > 0:
                        STATE["defense_boost_hacks_left"] -= 1

                    # start cooldown and cleanup
                    start_cooldown()
                    clear_puzzle()

        elif action == "cancel":
            token = session.get("p_token")
            if not token or token not in PUZZLES:
                flash("No active hack to cancel.", "warn")
            else:
                # If at max detection, traced penalty instead of +1 detection
                if STATE["detection"] >= STATE["max_detection"]:
                    penalty = min(12, STATE["files"])
                    STATE["files"] -= penalty
                    # you chose ok=True for this case
                    result = {"ok": True, "msg": "Hack cancelled. ", "bad": f"Been traced — -{penalty}GB penalty."}
                else:
                    STATE["detection"] = min(STATE["max_detection"], STATE["detection"] + 1)
                    result = {"ok": True, "msg": "Hack cancelled. ", "bad": "Detection +1."}

                if STATE["defense_boost_hacks_left"] > 0:
                    STATE["defense_boost_hacks_left"] -= 1

                # start cooldown and cleanup
                start_cooldown()
                clear_puzzle()

        elif action == "reroll":
            token = session.get("p_token")
            if not token or token not in PUZZLES:
                flash("Start a hack first.", "warn")
            else:
                if STATE["credits"] < 1:
                    result = {"neutral": True, "msg": "Not enough credits for Reroll (cost 1)."}
                else:
                    STATE["credits"] -= 1
                    # regenerate puzzle (replace existing token)
                    clear_puzzle()
                    start_puzzle()
                    result = {"ok": True, "msg": "Puzzle rerolled."}

        elif action == "cooldown":
            if STATE["credits"] < 5:
                result = {"neutral": True, "msg": "Not enough credits for Cool Down (cost 5)."}
            else:
                STATE["credits"] -= 5
                STATE["detection"] = max(0, STATE["detection"] - 1)
                result = {"ok": True, "msg": "System cooled. Detection decreased by 1."}

    # Puzzle visible only if token exists server-side
    puzzle = None
    token = session.get("p_token")
    if token and token in PUZZLES:
        puzzle = {"system": session.get("p_system"), "desc": session.get("p_desc")}

    return render_template(
        "hack.html",
        state=STATE,
        puzzle=puzzle,
        result=result,
        files=files,
        total=total,
    )

# ---------- LOGIN (DEFENDER MENU WITH PASSWORD PER DEFENSE) ----------
@app.route("/login", methods=["GET", "POST"])
def login():
    admin_scope = session.get("admin_scope")
    result = None
    stats = None

    if request.method == "POST":
        action = request.form.get("action")

        if action == "choose":
            defense = request.form.get("defense", "")
            pwd = request.form.get("def_pass", "")
            ok = False
            if defense == "wires" and pwd == PASS_WIRES:
                ok = True
            elif defense == "keypad" and pwd == PASS_KEYPAD:
                ok = True
            elif defense == "firewall" and pwd == PASS_FIREWALL:
                ok = True

            if ok:
                session["admin_scope"] = defense
                return redirect(url_for("login"))
            else:
                result = {"ok": False, "msg": "Invalid defense or password."}

        elif action == "logs" and admin_scope:
            s = DEFENSE_LOGS.get(admin_scope, {"success": 0, "fail": 0})
            stats = {"success": s["success"], "fail": s["fail"]}

        elif action == "download" and admin_scope:
            if STATE["defense_boost_available"] <= 0:
                result = {"ok": False, "msg": "Increase Defense already used this detection."}
            else:
                STATE["defense_boost_available"] = 0
                STATE["defense_boost_hacks_left"] = 8
                result = {"ok": True, "msg": "Defense increased: next 8 hacks yield reduced intel."}

        elif action == "logout":
            session.pop("admin_scope", None)
            return redirect(url_for("login"))

        elif action == "cancel_detection":
            if STATE["detection"] >= STATE["max_detection"]:
                STATE["files"] = max(0, STATE["files"] - 100)
                STATE["detection"] = 0
                # recharge the one use for the NEW detection cycle
                STATE["defense_boost_available"] = 1
                result = {"ok": True, "msg": "Detection cancelled. −100GB penalty applied to hackers."}
            else:
                result = {"ok": False, "msg": "Detection is not full. Nothing to cancel."}

    return render_template(
        "login.html",
        state=STATE,
        admin_scope=session.get("admin_scope"),
        stats=stats,
        result=result,
        can_increase_defense=(STATE["defense_boost_available"] > 0)
    )

@app.route("/system")
def system_panel():
    return render_template("system.html", state=STATE, logs=DEFENSE_LOGS)

@app.route("/logout")
def logout():
    session.pop("admin_scope", None)
    return redirect(url_for("index"))

# ---------- BLACK MARKET ----------
@app.route("/black-market", methods=["GET", "POST"])
def black_market():
    """
    Sell stolen intel for credits.
    Ratio: 3 GB -> 1 credit (full groups only).
    """
    message = None
    sold = 0
    gained = 0

    if request.method == "POST":
        try:
            qty = int(request.form.get("gb", "0"))
        except ValueError:
            qty = 0

        if qty <= 0:
            message = {"neutral": True, "ok": False, "text": "Enter a valid amount."}
        elif qty > STATE["files"]:
            message = {"neutral": True, "ok": False, "text": "Not enough intel to sell."}
        else:
            credits = qty // GB_PER_CREDIT
            if credits <= 0:
                message = {"neutral": True, "ok": False, "text": f"You need at least {GB_PER_CREDIT} GB to get 1 credit."}
            else:
                sold = credits * GB_PER_CREDIT
                gained = credits
                STATE["files"] -= sold
                STATE["credits"] += gained
                message = {"neutral": False, "ok": True, "text": f"Sold {sold} GB → +{gained} credits."}

    return render_template(
        "black_market.html",
        state=STATE,
        gb_per_credit=GB_PER_CREDIT,
        price=GB_PER_CREDIT,   # back-compat if old template referenced 'price'
        message=message,
        sold=sold,
        gained=gained
    )


if __name__ == "__main__":
    app.run(debug=True)
