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

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000, debug=True)