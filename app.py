from flask import Flask, render_template, request, redirect, url_for, session, flash
import random

app = Flask(__name__)
app.secret_key = "super_secret_key"

# ======= GLOBAL STATE =======
STATE = {
    "detection": 0,
    "max_detection": 5,
    "files": 0,          # total GB stolen by hackers (from successful hacks)
    "credits": 0,        # earned by selling intel on the Black Market
    # (Power Surge removed)
}

# Per-defense hack attempt logs
DEFENSE_LOGS = {
    "wires":   {"success": 0, "fail": 0},
    "keypad":  {"success": 0, "fail": 0},
    "firewall":{"success": 0, "fail": 0},
}

# Defender passwords per defense
DEFENDER_PASS = {
    "wires": "cut_all",
    "keypad": "1357908642",
    "firewall": "breach",
}

# Simple file catalogs (used when hackers succeed — cosmetic list)
FILE_CATALOG = {
    "wires": [
        ("relay_map.dat", 3), ("alarm_grid.bin", 4),
        ("maintenance.cfg", 2), ("schematics_w-17.pdf", 6)
    ],
    "keypad": [
        ("access_logs.log", 5), ("door_codes.enc", 7), ("audit_report.md", 4)
    ],
    "firewall": [
        ("threat_intel.db", 7), ("waf_rules.conf", 5), ("vpn_seeds.key", 3)
    ],
}

# Black market price (credits per GB) — changed to 1:1
MARKET_PRICE = 1

# ======= HELPERS (PUZZLES MATCH TRAINING RULES) =======
def gen_wires():
    """Generate a wires scenario + expected command per your training rules."""
    case = random.choice(["two_rb", "two_gy", "three_any", "one_red_other"])
    if case == "two_rb":
        return {"system": "wires", "desc": "Indicators: 2 lights | wires: red, blue", "expected": "connect red blue"}
    if case == "two_gy":
        return {"system": "wires", "desc": "Indicators: 2 lights | wires: green, yellow", "expected": "cut green"}
    if case == "three_any":
        a, b = random.sample(["red", "blue", "green", "yellow"], 2)
        return {"system": "wires", "desc": f"Indicators: 3 lights | wires: {a}, {b}", "expected": "disconnect all"}
    other = random.choice(["blue", "green", "yellow"])
    return {"system": "wires", "desc": f"Indicators: 1 light | wires: red, {other}", "expected": f"cut {other}"}

def gen_keypad():
    """Even → *2; Odd → +3; 9 → 999."""
    n = random.randint(1, 9)
    if n == 9: expected = "999"
    elif n % 2 == 0: expected = str(n * 2)
    else: expected = str(n + 3)
    return {"system": "keypad", "desc": f"Indicator number: {n}", "expected": expected}

def gen_firewall():
    """Pattern ABC starting with A/B/C/D → transform per training."""
    start = random.choice("ABCD")
    rest = "".join(random.choice("ABCDEF") for _ in range(2))
    pat = (start + rest).upper()
    if start == "A": expected = pat[::-1]
    elif start == "B": expected = pat * 2
    elif start == "C": expected = pat[0] + pat[2]  # drop the middle
    else: expected = pat  # as-is
    return {"system": "firewall", "desc": f"Firewall pattern: {pat}", "expected": expected}

def start_random_puzzle():
    maker = random.choice([gen_wires, gen_keypad, gen_firewall])
    p = maker()
    session["p_active"] = True
    session["p_system"] = p["system"]
    session["p_desc"] = p["desc"]
    session["p_expected"] = p["expected"]

def clear_puzzle():
    session.pop("p_active", None)
    session.pop("p_system", None)
    session.pop("p_desc", None)
    session.pop("p_expected", None)

def hacker_success(system):
    # Add some GB and show a small random file list
    files = FILE_CATALOG.get(system, [])
    selection = random.sample(files, k=min(2, len(files))) if files else []
    size = sum(sz for _, sz in selection)
    if size == 0:
        size = random.randint(10, 40)  # fallback GB amount
    STATE["files"] += size
    return selection, size

# ======= ROUTES (unchanged pages not included) =======
@app.route("/")
def index():
    return render_template("index.html", state=STATE)

@app.route("/training")
def training():
    # Block viewing Training while a hack is active (cancel is how to exit)
    if session.get("p_active"):
        flash("Finish or cancel your current hack before viewing Training.", "warn")
        return redirect(url_for("hack"))
    return render_template("training.html")

# ---------- HACK ----------
@app.route("/hack", methods=["GET", "POST"])
def hack():
    """
    Credit features (Power Surge removed):
      - Reroll Hack (3 cr)
      - One-Time Hint (5 cr)
      - Cool Down (8 cr)
    Cancel Hack now costs 2GB intel to use.
    """
    result = None
    files = []
    total = 0
    hint_text = None

    if request.method == "POST":
        action = request.form.get("action")

        # Start / Submit / Cancel
        if action == "new":
            start_random_puzzle()

        elif action == "submit":
            if not session.get("p_active"):
                flash("Start a hack first.", "warn")
            else:
                sysname = session.get("p_system")
                expected = (session.get("p_expected") or "").strip()
                answer = (request.form.get("answer") or "").strip()

                ok = False
                if sysname == "wires":
                    ok = (answer.lower() == expected.lower())
                elif sysname == "keypad":
                    ok = (answer == expected)
                else:  # firewall
                    ok = (answer.upper() == expected.upper())

                if ok:
                    DEFENSE_LOGS[sysname]["success"] += 1
                    sel, size = hacker_success(sysname)
                    files, total = sel, size
                    result = {"ok": True, "msg": f"Hack success on {sysname.upper()} — downloaded {size}GB."}
                else:
                    DEFENSE_LOGS[sysname]["fail"] += 1
                    if STATE["detection"] >= STATE["max_detection"]:
                        STATE["files"] = max(0, STATE["files"] - 15)
                        result = {"ok": False, "msg": f"Hack failed on {sysname.upper()} — hackers traced, −15GB."}
                    else:
                        STATE["detection"] = min(STATE["max_detection"], STATE["detection"] + 1)
                        result = {"ok": False, "msg": f"Hack failed on {sysname.upper()} — detection raised."}

                clear_puzzle()

        elif action == "cancel":
            if not session.get("p_active"):
                flash("No active hack to cancel.", "warn")
            else:
                # Require 2GB to cancel
                if STATE["files"] < 2:
                    flash("Not enough intel to cancel (requires 2GB).", "warn")
                else:
                    clear_puzzle()
                    STATE["files"] -= 2
                    result = {"ok": True, "msg": "Hack cancelled."}

        # ===== Credits actions =====
        elif action == "reroll":
            if not session.get("p_active"):
                flash("Start a hack first.", "warn")
            elif STATE["credits"] < 3:
                flash("Not enough credits for Reroll (3).", "warn")
            else:
                STATE["credits"] -= 3
                start_random_puzzle()
                result = {"ok": True, "msg": "Reroll used. New hack generated."}

        elif action == "hint":
            if not session.get("p_active"):
                flash("Start a hack first.", "warn")
            elif STATE["credits"] < 5:
                flash("Not enough credits for Hint (5).", "warn")
            else:
                STATE["credits"] -= 5
                sysname = session.get("p_system")
                if sysname == "wires":
                    hint_text = "Wires: 2 lights → red+blue, 3 lights → disconnect all, 1 light w/ red → cut the other."
                elif sysname == "keypad":
                    hint_text = "Keypad: even ×2, odd +3, nine → 999."
                elif sysname == "firewall":
                    hint_text = "Firewall: A=reverse, B=double, C=drop middle, D=as-is."
                else:
                    hint_text = "No hint available."

        elif action == "cooldown":
            if STATE["credits"] < 8:
                flash("Not enough credits for Cool Down (8).", "warn")
            elif STATE["detection"] <= 0:
                flash("Detection is already at minimum.", "warn")
            else:
                STATE["credits"] -= 8
                STATE["detection"] = max(0, STATE["detection"] - 1)
                result = {"ok": True, "msg": "System cooled. Detection decreased by 1."}

    # Expose current puzzle (label + prompt) WITHOUT auto-start on GET
    puzzle = None
    if session.get("p_active"):
        puzzle = {"system": session.get("p_system"), "desc": session.get("p_desc")}

    return render_template(
        "hack.html",
        state=STATE,
        puzzle=puzzle,
        result=result,
        files=files,
        total=total,
        hint_text=hint_text
    )

# ---------- LOGIN (DEFENDER MENU WITH PASSWORD PER DEFENSE) ----------
@app.route("/login", methods=["GET", "POST"])
def login():
    admin_scope = session.get("admin_scope")  # None or "wires"/"keypad"/"firewall"
    result = None
    stats = None

    if request.method == "POST":
        action = request.form.get("action")

        # Step 1: choose & authenticate for a defense
        if action == "choose":
            chosen = (request.form.get("defense") or "").strip()
            pw = (request.form.get("def_pass") or "").strip()
            if chosen not in DEFENDER_PASS:
                flash("Pick a defense to manage.", "warn")
            elif pw != DEFENDER_PASS[chosen]:
                flash("Wrong password for that defense.", "warn")
            else:
                session["admin_scope"] = chosen
                admin_scope = chosen

        # Actions once a defense is chosen
        elif admin_scope:
            if action == "logs":
                s = DEFENSE_LOGS[admin_scope]
                stats = {"success": s["success"], "fail": s["fail"]}

            elif action == "download":
                result = {"ok": True, "msg": f"Secure backup executed for {admin_scope.upper()} (no intel exposed)."}

            elif action == "logout":
                session.pop("admin_scope", None)
                admin_scope = None

            elif action == "cancel_detection":
                if STATE["detection"] >= STATE["max_detection"]:
                    STATE["files"] = max(0, STATE["files"] - 100)  # penalty to hackers
                    STATE["detection"] = 0
                    result = {"ok": True, "msg": "Detection cancelled. −100GB penalty applied to hackers."}
                else:
                    result = {"ok": False, "msg": "Detection is not full. Nothing to cancel."}

    return render_template(
        "login.html",
        state=STATE,
        admin_scope=admin_scope,
        stats=stats,
        result=result
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
    Sell stolen intel for credits at 1:1 rate.
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
            message = {"ok": False, "text": "Enter a valid amount."}
        elif qty > STATE["files"]:
            message = {"ok": False, "text": "Not enough intel to sell."}
        else:
            sold = qty
            gained = qty * MARKET_PRICE  # 1:1
            STATE["files"] -= sold
            STATE["credits"] += gained
            message = {"ok": True, "text": f"Sold {sold} for {gained} credits."}

    return render_template(
        "black_market.html",
        state=STATE,
        price=MARKET_PRICE,
        message=message,
        sold=sold,
        gained=gained
    )

if __name__ == "__main__":
    app.run(debug=True)
