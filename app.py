# app.py

from flask import Flask, render_template, request, redirect, url_for, session, flash
import random

app = Flask(__name__)
app.secret_key = "super_secret_key"

STATE = {
    "detection": 0,
    "max_detection": 5,
    "files": 0,
    "credits": 0,
    "defense_boost_available": 1,
    "defense_boost_hacks_left": 0,
}

DEFENSE_REDUCTION_MULTIPLIER = 0.5

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

# ===== Black market ratio: 3 GB -> 1 credit =====
GB_PER_CREDIT = 3

PASS_WIRES = "-"
PASS_KEYPAD = "124578"
PASS_FIREWALL = "upgrade"

# ---------- helpers (unchanged) ----------
def gen_wires():
    case = random.choice(["two_rb", "two_gy", "three_any", "one_red_other"])
    if case == "two_rb":
        return {"system": "wires", "desc": "Indicators: 2 lights | wires: red, blue", "expected": "connect red blue"}
    elif case == "two_gy":
        return {"system": "wires", "desc": "Indicators: 2 lights | wires: green, yellow", "expected": "cut green"}
    elif case == "three_any":
        return {"system": "wires", "desc": "Indicators: 3 lights | any pair shown", "expected": "disconnect all"}
    else:
        other = random.choice(["blue", "green", "yellow"])
        return {"system": "wires", "desc": f"Indicators: 1 light | wires: red, {other}", "expected": f"cut {other}"}

def gen_keypad():
    n = random.randint(1, 9)
    if n == 9: expected = "999"
    elif n % 2 == 0: expected = str(n * 2)
    else: expected = str(n + 3)
    return {"system": "keypad", "desc": f"Indicator number: {n}", "expected": expected}

def gen_firewall():
    start = random.choice("ABCD")
    rest = "".join(random.choice("ABCDEF") for _ in range(2))
    pat = (start + rest).upper()
    if start == "A": expected = pat[::-1]
    elif start == "B": expected = pat + pat
    elif start == "C":
        mid = len(pat) // 2
        expected = pat[:mid] + pat[mid+1:]
    else: expected = pat
    return {"system": "firewall", "desc": f"Firewall pattern: {pat}", "expected": expected}

def start_puzzle():
    p = random.choice([gen_wires(), gen_keypad(), gen_firewall()])
    session["p_active"] = True
    session["p_system"] = p["system"]
    session["p_desc"] = p["desc"]
    session["p_expected"] = p["expected"]
    session["p_explicit"] = True

def clear_puzzle():
    for k in ("p_active", "p_system", "p_desc", "p_expected", "p_explicit"):
        session.pop(k, None)

def hacker_success(system):
    selection = random.sample(FILE_POOL, k=2)
    size = sum(sz for _, sz in selection) or random.randint(10, 40)
    if STATE["defense_boost_hacks_left"] > 0:
        size = max(1, int(round(size * DEFENSE_REDUCTION_MULTIPLIER)))
    STATE["files"] += size
    return selection, size

# ---------- routes ----------
@app.route("/")
def index():
    return render_template("index.html", state=STATE)

@app.route("/training")
def training():
    return render_template("training.html")

@app.route("/hack", methods=["GET", "POST"])
def hack():
    result, files, total = None, [], 0
    if request.method == "GET" and session.get("p_active") and not session.get("p_explicit"):
        clear_puzzle()

    if request.method == "POST":
        action = request.form.get("action")
        if action == "new":
            if session.get("p_active"): flash("A hack is already in progress.", "warn")
            else: start_puzzle()

        elif action == "submit":
            if not session.get("p_active"):
                flash("Start a hack first.", "warn")
            else:
                answer = (request.form.get("answer") or "").strip().lower()
                if answer == "":
                    result = {"neutral": True, "msg": "You must enter an answer to submit."}
                else:
                    expected = (session.get("p_expected") or "").strip().lower()
                    sysname = session.get("p_system")
                    if answer == expected:
                        files, total = hacker_success(sysname)
                        DEFENSE_LOGS[sysname]["success"] += 1
                        result = {"ok": True, "msg": f"Hack success on {sysname.upper()} — +{total}GB intel."}
                    else:
                        DEFENSE_LOGS[sysname]["fail"] += 1
                        STATE["detection"] = min(STATE["max_detection"], STATE["detection"] + 1)
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
                    if STATE["defense_boost_hacks_left"] > 0:
                        STATE["defense_boost_hacks_left"] -= 1
                    clear_puzzle()

        elif action == "cancel":
            if not session.get("p_active"):
                flash("No active hack to cancel.", "warn")
            else:
                STATE["detection"] = min(STATE["max_detection"], STATE["detection"] + 1)
                result = {"ok": True, "msg": "Hack cancelled. ", "bad": "Detection +1."}
                if STATE["defense_boost_hacks_left"] > 0:
                    STATE["defense_boost_hacks_left"] -= 1
                clear_puzzle()

        elif action == "reroll":
            if not session.get("p_active"):
                flash("Start a hack first.", "warn")
            else:
                if STATE["credits"] < 1:
                    result = {"neutral": True, "msg": "Not enough credits for Reroll (cost 1)."}
                else:
                    STATE["credits"] -= 1
                    start_puzzle()
                    result = {"ok": True, "msg": "Puzzle rerolled."}

        elif action == "cooldown":
            if STATE["credits"] < 5:
                result = {"neutral": True, "msg": "Not enough credits for Cool Down (cost 5)."}
            else:
                STATE["credits"] -= 5
                STATE["detection"] = max(0, STATE["detection"] - 1)
                result = {"ok": True, "msg": "System cooled. Detection decreased by 1."}

    puzzle = {"system": session.get("p_system"), "desc": session.get("p_desc")} if session.get("p_active") else None
    return render_template("hack.html", state=STATE, puzzle=puzzle, result=result, files=files, total=total)

@app.route("/login", methods=["GET", "POST"])
def login():
    admin_scope = session.get("admin_scope")
    result, stats = None, None
    if request.method == "POST":
        action = request.form.get("action")
        if action == "choose":
            defense = request.form.get("defense", ""); pwd = request.form.get("def_pass", "")
            ok = (defense == "wires" and pwd == PASS_WIRES) or \
                 (defense == "keypad" and pwd == PASS_KEYPAD) or \
                 (defense == "firewall" and pwd == PASS_FIREWALL)
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
                STATE["defense_boost_available"] = 1
                result = {"ok": True, "msg": "Detection cancelled. −100GB penalty applied to hackers."}
            else:
                result = {"ok": False, "msg": "Detection is not full. Nothing to cancel."}

    return render_template("login.html",
        state=STATE,
        admin_scope=session.get("admin_scope"),
        stats=stats,
        result=result,
        can_increase_defense=(STATE["defense_boost_available"] > 0)
    )

@app.route("/system")
def system_panel():
    # unchanged: template expects state and logs
    return render_template("system.html", state=STATE, logs=DEFENSE_LOGS)

# ---------- Black Market (fixed for old/new templates) ----------
@app.route("/black-market", methods=["GET", "POST"])
def black_market():
    """
    Sell stolen intel for credits.
    New ratio: 3 GB -> 1 credit (full groups only).
    Back-compat: exposes both gb_per_credit AND price; message has ok/neutral fields.
    """
    message, sold, gained = None, 0, 0

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

    # Back-compat: pass both names
    return render_template(
        "black_market.html",
        state=STATE,
        gb_per_credit=GB_PER_CREDIT,
        price=GB_PER_CREDIT,           # OLD templates used {{ price }}
        message=message,
        sold=sold,
        gained=gained
    )

@app.route("/logout")
def logout():
    session.pop("admin_scope", None)
    return redirect(url_for("index"))

if __name__ == "__main__":
    app.run(debug=True)
