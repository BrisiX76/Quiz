from flask import Flask, render_template, request, redirect, session, jsonify
import json, random, os, copy, sqlite3
from datetime import datetime

app = Flask(__name__)
app.secret_key = "test123"

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

with open(os.path.join(BASE_DIR, "domande.json"), "r", encoding="utf-8") as f:
    domande_db = json.load(f)

# ── DATABASE CLASSIFICA ──
def init_db():
    conn = sqlite3.connect(os.path.join(BASE_DIR, "classifica.db"))
    conn.execute("""
        CREATE TABLE IF NOT EXISTS punteggi (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nome TEXT NOT NULL,
            livello TEXT NOT NULL,
            punteggio INTEGER NOT NULL,
            totale INTEGER NOT NULL,
            percentuale INTEGER NOT NULL,
            data TEXT NOT NULL
        )
    """)
    conn.commit()
    conn.close()

init_db()

def salva_punteggio(nome, livello, punteggio, totale, percentuale):
    conn = sqlite3.connect(os.path.join(BASE_DIR, "classifica.db"))
    conn.execute(
        "INSERT INTO punteggi (nome, livello, punteggio, totale, percentuale, data) VALUES (?,?,?,?,?,?)",
        (nome, livello, punteggio, totale, percentuale, datetime.now().strftime("%d/%m/%Y %H:%M"))
    )
    conn.commit()
    conn.close()

def get_classifica():
    conn = sqlite3.connect(os.path.join(BASE_DIR, "classifica.db"))
    rows = conn.execute("""
        SELECT nome, livello, MAX(percentuale) as best, COUNT(*) as partite,
               ROUND(AVG(percentuale)) as media, MAX(data) as ultima
        FROM punteggi
        GROUP BY nome, livello
        ORDER BY best DESC, media DESC
    """).fetchall()
    conn.close()
    return [{"nome": r[0], "livello": r[1], "best": r[2],
             "partite": r[3], "media": r[4], "ultima": r[5]} for r in rows]

def get_storico():
    conn = sqlite3.connect(os.path.join(BASE_DIR, "classifica.db"))
    rows = conn.execute("""
        SELECT nome, livello, punteggio, totale, percentuale, data
        FROM punteggi ORDER BY id DESC LIMIT 30
    """).fetchall()
    conn.close()
    return [{"nome": r[0], "livello": r[1], "punteggio": r[2],
             "totale": r[3], "percentuale": r[4], "data": r[5]} for r in rows]

# ── GENERA DOMANDE ──
def genera_domande(materia, livello, n=10, viste=None):
    pool = domande_db.get(materia, {}).get(livello, [])
    # Assegna un ID univoco a ogni domanda basato sul testo
    def domanda_id(d):
        return d["domanda"][:40]
    # Escludi domande già viste
    if viste:
        pool_non_viste = [d for d in pool if domanda_id(d) not in viste]
        # Se rimangono meno di n domande, resetta e usa tutto il pool
        if len(pool_non_viste) < n:
            pool_non_viste = pool
    else:
        pool_non_viste = pool
    campione = random.sample(pool_non_viste, min(n, len(pool_non_viste)))
    result = []
    for d in campione:
        nd = copy.deepcopy(d)
        nd["_id"] = domanda_id(nd)  # aggiungi ID per tracking
        random.shuffle(nd["opzioni"])
        result.append(nd)
    return result

# ── HOME MEDICINA ──
@app.route("/")
def index():
    return render_template("index.html")

# ── HOME GRUPPO ──
@app.route("/medicina")
def medicina():
    return render_template("medicina.html")

@app.route("/gruppo")
def gruppo():
    return render_template("gruppo.html")

# ── START MEDICINA ──
@app.route("/start", methods=["POST"])
def start():
    materia = request.form.get("materia", "biologia")
    livello = request.form.get("livello", "medio")
    n_domande = int(request.form.get("n_domande", 10))
    viste_raw = request.form.get("viste", "")
    viste = set(v for v in viste_raw.split("||") if v) if viste_raw else set()
    session["domande"]   = genera_domande(materia, livello, n=n_domande, viste=viste)
    session["indice"]    = 0
    session["punteggio"] = 0
    session["feedback"]  = None
    session["materia"]   = materia
    session["livello"]   = livello
    session["modalita"]  = "medicina"
    session["nome"]      = None
    return redirect("/quiz")

# ── START GRUPPO ──
@app.route("/start-gruppo", methods=["POST"])
def start_gruppo():
    livello    = request.form.get("livello", "medio")
    nome       = request.form.get("nome", "Anonimo").strip() or "Anonimo"
    n_domande  = int(request.form.get("n_domande", 10))
    viste_raw  = request.form.get("viste", "")
    viste      = set(v for v in viste_raw.split("||") if v) if viste_raw else set()
    session["domande"]   = genera_domande("gruppo", livello, n=n_domande, viste=viste)
    session["indice"]    = 0
    session["punteggio"] = 0
    session["feedback"]  = None
    session["materia"]   = "gruppo"
    session["livello"]   = livello
    session["modalita"]  = "gruppo"
    session["nome"]      = nome
    return redirect("/quiz")

# ── QUIZ ──
@app.route("/quiz", methods=["GET", "POST"])
def quiz_page():
    if "indice" not in session or "domande" not in session:
        return redirect("/")

    if request.method == "POST":
        action = request.form.get("action")

        if action == "risposta":
            scelta   = int(request.form["scelta"])
            domanda  = session["domande"][session["indice"]]
            corretta = domanda["corretta"]

            if scelta == -1:
                esatta = False
                spiegazione = "⏱ Tempo scaduto! " + domanda.get("spiegazione", "")
            else:
                esatta = domanda["opzioni"][scelta] == corretta
                spiegazione = domanda.get("spiegazione", "")

            if esatta:
                session["punteggio"] += 1

            session["feedback"] = {
                "scelta":          scelta,
                "corretta":        esatta,
                "risposta_giusta": corretta,
                "spiegazione":     spiegazione
            }
            session.modified = True
            return redirect("/quiz")

        elif action == "avanti":
            session["indice"]  += 1
            session["feedback"] = None
            session.modified = True
            return redirect("/quiz")

    if session["indice"] >= len(session["domande"]):
        return redirect("/risultato")

    domanda  = session["domande"][session["indice"]]
    feedback = session.get("feedback")
    totale   = len(session["domande"])
    modalita = session.get("modalita", "medicina")

    return render_template(
        "quiz.html",
        domanda  = domanda,
        indice   = session["indice"] + 1,
        totale   = totale,
        feedback = feedback,
        lettere  = ["A", "B", "C", "D"],
        modalita = modalita
    )

# ── START SAME ──
@app.route("/start-same")
def start_same():
    materia  = session.get("materia", "biologia")
    livello  = session.get("livello", "medio")
    modalita = session.get("modalita", "medicina")
    nome     = session.get("nome")
    session["domande"]   = genera_domande(materia, livello)
    session["indice"]    = 0
    session["punteggio"] = 0
    session["feedback"]  = None
    session["modalita"]  = modalita
    session["nome"]      = nome
    session.modified = True
    return redirect("/quiz")

# ── RISULTATO ──
@app.route("/risultato")
def risultato():
    if "domande" not in session:
        return redirect("/")
    totale      = len(session.get("domande", []))
    punteggio   = session.get("punteggio", 0)
    percentuale = round((punteggio / totale) * 100) if totale else 0
    materia     = session.get("materia", "")
    livello     = session.get("livello", "")
    modalita    = session.get("modalita", "medicina")
    nome        = session.get("nome")

    # Salva in DB solo per modalità gruppo
    if modalita == "gruppo" and nome:
        salva_punteggio(nome, livello, punteggio, totale, percentuale)

    # Raccoglie gli ID delle domande viste in questa sessione
    domande_viste = [d.get("_id", d["domanda"][:40])
                     for d in session.get("domande", [])]
    # Calcola quante domande ci sono in totale per questa combinazione
    pool = domande_db.get(materia, {}).get(livello, [])
    max_domande = len(pool)

    return render_template(
        "risultato.html",
        punteggio     = punteggio,
        totale        = totale,
        percentuale   = percentuale,
        materia       = materia,
        livello       = livello,
        modalita      = modalita,
        nome          = nome,
        domande_viste = domande_viste,
        max_domande   = max_domande
    )

# ── CLASSIFICA ──
@app.route("/classifica")
def classifica():
    return render_template(
        "classifica.html",
        classifica = get_classifica(),
        storico    = get_storico()
    )

@app.route("/reset-classifica", methods=["POST"])
def reset_classifica():
    conn = sqlite3.connect(os.path.join(BASE_DIR, "classifica.db"))
    conn.execute("DELETE FROM punteggi")
    conn.commit()
    conn.close()
    return redirect("/classifica")

# ── STATISTICHE MEDICINA ──
@app.route("/api/classifica-live")
def api_classifica_live():
    return jsonify(get_classifica())

@app.route("/statistiche")
def statistiche():
    return render_template("statistiche.html")
# ══════════════════════════════════════════
# QUIZ CDR — aggiungere in app_web.py
# ══════════════════════════════════════════

# Credenziali operatori — modifica qui per aggiungere utenti
CDR_UTENTI = {
    "operatore1": "password1",
    "operatore2": "password2",
    "admin":      "1212",
}

# Utenti con diritto di reset classifica
CDR_ADMIN = {"admin"}

def get_classifica_cdr():
    conn = sqlite3.connect(os.path.join(BASE_DIR, "classifica.db"))
    rows = conn.execute("""
        SELECT nome, livello, MAX(percentuale) as best, COUNT(*) as partite,
               ROUND(AVG(percentuale)) as media, MAX(data) as ultima
        FROM punteggi_cdr
        GROUP BY nome, livello
        ORDER BY best DESC, media DESC
    """).fetchall()
    conn.close()
    return [{"nome": r[0], "livello": r[1], "best": r[2],
             "partite": r[3], "media": r[4], "ultima": r[5]} for r in rows]

def get_storico_cdr():
    conn = sqlite3.connect(os.path.join(BASE_DIR, "classifica.db"))
    rows = conn.execute("""
        SELECT nome, livello, punteggio, totale, percentuale, data
        FROM punteggi_cdr ORDER BY id DESC LIMIT 30
    """).fetchall()
    conn.close()
    return [{"nome": r[0], "livello": r[1], "punteggio": r[2],
             "totale": r[3], "percentuale": r[4], "data": r[5]} for r in rows]

def salva_punteggio_cdr(nome, livello, punteggio, totale, percentuale):
    conn = sqlite3.connect(os.path.join(BASE_DIR, "classifica.db"))
    conn.execute("""
        CREATE TABLE IF NOT EXISTS punteggi_cdr (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nome TEXT NOT NULL,
            livello TEXT NOT NULL,
            punteggio INTEGER NOT NULL,
            totale INTEGER NOT NULL,
            percentuale INTEGER NOT NULL,
            data TEXT NOT NULL
        )
    """)
    conn.execute(
        "INSERT INTO punteggi_cdr (nome, livello, punteggio, totale, percentuale, data) VALUES (?,?,?,?,?,?)",
        (nome, livello, punteggio, totale, percentuale, datetime.now().strftime("%d/%m/%Y %H:%M"))
    )
    conn.commit()
    conn.close()

# ── LOGIN ──
@app.route("/cdr-login", methods=["GET", "POST"])
def cdr_login():
    errore = None
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        if username in CDR_UTENTI and CDR_UTENTI[username] == password:
            session["cdr_ok"] = True
            session["cdr_username"] = username
            session["cdr_admin"] = username in CDR_ADMIN
            return redirect("/cdr")
        else:
            errore = "Credenziali non valide. Riprova."
    return render_template("cdr_login.html", errore=errore)

@app.route("/cdr-logout")
def cdr_logout():
    session.pop("cdr_ok", None)
    session.pop("cdr_username", None)
    session.pop("cdr_admin", None)
    return redirect("/")

# ── HOME CdR ──
@app.route("/cdr")
def cdr():
    if not session.get("cdr_ok"):
        return redirect("/cdr-login")
    return render_template("cdr.html", username=session.get("cdr_username", "Operatore"))

# ── START CdR ──
@app.route("/cdr-start", methods=["POST"])
def cdr_start():
    if not session.get("cdr_ok"):
        return redirect("/cdr-login")
    livello   = request.form.get("livello", "medio")
    n_domande = int(request.form.get("n_domande", 10))
    viste_raw = request.form.get("viste", "")
    viste     = set(v for v in viste_raw.split("||") if v) if viste_raw else set()
    session["domande"]   = genera_domande("cdr", livello, n=n_domande, viste=viste)
    session["indice"]    = 0
    session["punteggio"] = 0
    session["feedback"]  = None
    session["materia"]   = "cdr"
    session["livello"]   = livello
    session["modalita"]  = "cdr"
    session["nome"]      = session.get("cdr_username", "Operatore")
    return redirect("/cdr-quiz")

# ── START SAME CdR ──
@app.route("/cdr-start-same")
def cdr_start_same():
    if not session.get("cdr_ok"):
        return redirect("/cdr-login")
    livello = session.get("livello", "medio")
    nome    = session.get("nome", "Operatore")
    session["domande"]   = genera_domande("cdr", livello)
    session["indice"]    = 0
    session["punteggio"] = 0
    session["feedback"]  = None
    session["modalita"]  = "cdr"
    session["nome"]      = nome
    session.modified = True
    return redirect("/cdr-quiz")

# ── QUIZ CdR ──
@app.route("/cdr-quiz", methods=["GET", "POST"])
def cdr_quiz():
    if not session.get("cdr_ok"):
        return redirect("/cdr-login")
    if "indice" not in session or "domande" not in session:
        return redirect("/cdr")

    if request.method == "POST":
        action = request.form.get("action")
        if action == "risposta":
            scelta   = int(request.form["scelta"])
            domanda  = session["domande"][session["indice"]]
            corretta = domanda["corretta"]
            if scelta == -1:
                esatta = False
                spiegazione = "⏱ Tempo scaduto! " + domanda.get("spiegazione", "")
            else:
                esatta = domanda["opzioni"][scelta] == corretta
                spiegazione = domanda.get("spiegazione", "")
            if esatta:
                session["punteggio"] += 1
            session["feedback"] = {
                "scelta": scelta, "corretta": esatta,
                "risposta_giusta": corretta, "spiegazione": spiegazione
            }
            session.modified = True
            return redirect("/cdr-quiz")
        elif action == "avanti":
            session["indice"]  += 1
            session["feedback"] = None
            session.modified = True
            return redirect("/cdr-quiz")

    if session["indice"] >= len(session["domande"]):
        return redirect("/cdr-risultato")

    return render_template(
        "quiz_cdr.html",
        domanda  = session["domande"][session["indice"]],
        indice   = session["indice"] + 1,
        totale   = len(session["domande"]),
        feedback = session.get("feedback"),
        lettere  = ["A", "B", "C", "D"]
    )

# ── RISULTATO CdR ──
@app.route("/cdr-risultato")
def cdr_risultato():
    if not session.get("cdr_ok"):
        return redirect("/cdr-login")
    if "domande" not in session:
        return redirect("/cdr")
    totale      = len(session.get("domande", []))
    punteggio   = session.get("punteggio", 0)
    percentuale = round((punteggio / totale) * 100) if totale else 0
    livello     = session.get("livello", "medio")
    nome        = session.get("nome", "Operatore")
    salva_punteggio_cdr(nome, livello, punteggio, totale, percentuale)
    domande_viste = [d.get("_id", d["domanda"][:40]) for d in session.get("domande", [])]
    pool = domande_db.get("cdr", {}).get(livello, [])
    return render_template(
        "cdr_risultato.html",
        punteggio     = punteggio,
        totale        = totale,
        percentuale   = percentuale,
        livello       = livello,
        nome          = nome,
        domande_viste = domande_viste,
        max_domande   = len(pool)
    )

# ── CLASSIFICA CdR ──
@app.route("/cdr-classifica")
def cdr_classifica():
    if not session.get("cdr_ok"):
        return redirect("/cdr-login")
    return render_template(
        "cdr_classifica.html",
        classifica = get_classifica_cdr(),
        storico    = get_storico_cdr()
    )

@app.route("/cdr-reset-classifica", methods=["POST"])
def cdr_reset_classifica():
    if not session.get("cdr_admin"):
        return redirect("/cdr-classifica")
    conn = sqlite3.connect(os.path.join(BASE_DIR, "classifica.db"))
    conn.execute("DELETE FROM punteggi_cdr")
    conn.commit()
    conn.close()
    return redirect("/cdr-classifica")

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000, debug=True)
    