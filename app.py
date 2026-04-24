from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
from flask_sqlalchemy import SQLAlchemy
from openai import OpenAI
import json
import os
from datetime import datetime

app = Flask(__name__)
CORS(app, origins="*", allow_headers=["Content-Type"], methods=["POST", "OPTIONS", "GET", "DELETE"])

database_url = os.environ.get('DATABASE_URL', 'sqlite:///kuehlschrank.db')
if database_url.startswith('postgres://'):
    database_url = database_url.replace('postgres://', 'postgresql://', 1)

app.config['SQLALCHEMY_DATABASE_URI'] = database_url
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

class InventarItem(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    menge = db.Column(db.String(100), nullable=False)
    urgency = db.Column(db.String(20), nullable=False)
    erstellt_am = db.Column(db.DateTime, default=datetime.utcnow)

class GekochteRezept(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    titel = db.Column(db.String(200), nullable=False)
    zutaten_json = db.Column(db.Text, nullable=False)
    gekocht_am = db.Column(db.DateTime, default=datetime.utcnow)

class GespeichertesRezept(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    titel = db.Column(db.String(200), nullable=False)
    beschreibung = db.Column(db.Text, nullable=True)
    zutaten_json = db.Column(db.Text, nullable=False)
    zubereitung = db.Column(db.Text, nullable=True)
    quelle = db.Column(db.String(50), default='manuell')
    gespeichert_am = db.Column(db.DateTime, default=datetime.utcnow)

with app.app_context():
    db.create_all()

@app.after_request
def after_request(response):
    response.headers.add('Access-Control-Allow-Origin', '*')
    response.headers.add('Access-Control-Allow-Headers', 'Content-Type')
    response.headers.add('Access-Control-Allow-Methods', 'POST, OPTIONS, GET, DELETE')
    return response

@app.route('/')
def index():
    return send_from_directory(os.path.dirname(os.path.abspath(__file__)), 'index.html')

# --- Inventar ---
@app.route('/inventar', methods=['GET'])
def get_inventar():
    items = InventarItem.query.order_by(InventarItem.urgency).all()
    return jsonify([{'id': i.id, 'name': i.name, 'menge': i.menge, 'urgency': i.urgency} for i in items])

@app.route('/inventar', methods=['POST'])
def add_inventar():
    data = request.json
    item = InventarItem(name=data['name'], menge=data['menge'], urgency=data['urgency'])
    db.session.add(item)
    db.session.commit()
    return jsonify({'id': item.id, 'name': item.name, 'menge': item.menge, 'urgency': item.urgency})

@app.route('/inventar/<int:item_id>', methods=['DELETE'])
def delete_inventar(item_id):
    item = InventarItem.query.get_or_404(item_id)
    db.session.delete(item)
    db.session.commit()
    return jsonify({'ok': True})

@app.route('/inventar/<int:item_id>', methods=['POST'])
def update_inventar(item_id):
    item = InventarItem.query.get_or_404(item_id)
    data = request.json
    if 'menge' in data: item.menge = data['menge']
    if 'urgency' in data: item.urgency = data['urgency']
    db.session.commit()
    return jsonify({'ok': True})

# --- Historie ---
@app.route('/historie', methods=['GET'])
def get_historie():
    rezepte = GekochteRezept.query.order_by(GekochteRezept.gekocht_am.desc()).limit(20).all()
    return jsonify([{
        'id': r.id, 'titel': r.titel,
        'zutaten': json.loads(r.zutaten_json),
        'gekocht_am': r.gekocht_am.strftime('%d.%m.%Y')
    } for r in rezepte])

@app.route('/historie', methods=['POST'])
def add_historie():
    data = request.json
    r = GekochteRezept(titel=data['titel'], zutaten_json=json.dumps(data['zutaten']))
    db.session.add(r)
    db.session.commit()
    return jsonify({'ok': True})

# --- Gespeicherte Rezepte ---
@app.route('/meine-rezepte', methods=['GET'])
def get_meine_rezepte():
    rezepte = GespeichertesRezept.query.order_by(GespeichertesRezept.gespeichert_am.desc()).all()
    return jsonify([{
        'id': r.id, 'titel': r.titel, 'beschreibung': r.beschreibung,
        'zutaten': json.loads(r.zutaten_json),
        'zubereitung': r.zubereitung, 'quelle': r.quelle,
        'gespeichert_am': r.gespeichert_am.strftime('%d.%m.%Y')
    } for r in rezepte])

@app.route('/meine-rezepte', methods=['POST'])
def add_mein_rezept():
    data = request.json
    r = GespeichertesRezept(
        titel=data['titel'],
        beschreibung=data.get('beschreibung', ''),
        zutaten_json=json.dumps(data.get('zutaten', [])),
        zubereitung=data.get('zubereitung', ''),
        quelle=data.get('quelle', 'manuell')
    )
    db.session.add(r)
    db.session.commit()
    return jsonify({'id': r.id, 'ok': True})

@app.route('/meine-rezepte/<int:rezept_id>', methods=['DELETE'])
def delete_mein_rezept(rezept_id):
    r = GespeichertesRezept.query.get_or_404(rezept_id)
    db.session.delete(r)
    db.session.commit()
    return jsonify({'ok': True})

# --- Screenshot Rezept Parser ---
@app.route('/parse-rezept', methods=['POST', 'OPTIONS'])
def parse_rezept():
    if request.method == 'OPTIONS':
        return jsonify({'ok': True}), 200
    openai_key = os.environ.get('OPENAI_API_KEY')
    if not openai_key:
        return jsonify({'error': 'Kein API Key gespeichert'}), 400
    data = request.json
    image_base64 = data.get('image')
    if not image_base64:
        return jsonify({'error': 'image erforderlich'}), 400
    client = OpenAI(api_key=openai_key)
    try:
        response = client.chat.completions.create(
            model="gpt-4o", max_tokens=1200,
            messages=[{
                "role": "user",
                "content": [
                    {"type": "text", "text": """Das ist ein Screenshot eines Rezepts oder einer Social Media Caption mit Rezept.
Extrahiere das Rezept vollstaendig.
Antworte NUR mit validem JSON ohne Text davor oder danach.
Format: {
  "titel": "Rezeptname",
  "beschreibung": "Kurze Beschreibung in 1-2 Saetzen",
  "zutaten": [{"name": "Zutat", "menge": "Menge"}],
  "zubereitung": "Zubereitungsschritte"
}
Falls kein Rezept erkennbar: {"fehler": "Kein Rezept gefunden"}"""},
                    {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{image_base64}"}}
                ]
            }]
        )
        text = response.choices[0].message.content.replace('```json', '').replace('```', '').strip()
        result = json.loads(text)
        return jsonify(result)
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# --- Rezepte generieren ---
@app.route('/rezepte', methods=['POST', 'OPTIONS'])
def rezepte():
    if request.method == 'OPTIONS':
        return jsonify({'ok': True}), 200
    openai_key = os.environ.get('OPENAI_API_KEY')
    if not openai_key:
        return jsonify({'error': 'Kein API Key gespeichert'}), 400
    data = request.json
    inventory_text = data.get('inventory_text')
    if not inventory_text:
        return jsonify({'error': 'inventory_text erforderlich'}), 400
    client = OpenAI(api_key=openai_key)
    system_prompt = """Du bist ein Kuechenchef der fuer eine einzelne Person kocht.
Generiere genau 3 leckere Rezeptvorschlaege basierend auf dem Inventar.
STRENGE REGELN:
- Verwende AUSSCHLIESSLICH Zutaten die im Inventar stehen
- Erlaubt zusaetzlich: Wasser, Salz, Pfeffer, Oel
- Priorisiere Zutaten die bald weg muessen
- Mengen in natuerlichen Einheiten: "die Haelfte der Tuete Spinat", "2 von den 6 Eiern"
- Antworte NUR mit validem JSON Array, kein Text davor oder danach
Format: [{"titel":"Name","zeit":"20 Min","beschreibung":"Kurze Beschreibung","verwendet_dringend":true,"zutaten":[{"name":"Spinat","menge":"die ganze Tuete"}],"zubereitung":"Schritte in 2-3 Saetzen"}]"""
    try:
        response = client.chat.completions.create(
            model="gpt-4o", max_tokens=1500,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": f"Inventar:\n{inventory_text}\n\nGeneriere 3 Rezepte."}
            ]
        )
        text = response.choices[0].message.content.replace('```json', '').replace('```', '').strip()
        return jsonify({'recipes': json.loads(text)})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# --- Kassenbon Scanner ---
@app.route('/scan', methods=['POST', 'OPTIONS'])
def scan():
    if request.method == 'OPTIONS':
        return jsonify({'ok': True}), 200
    openai_key = os.environ.get('OPENAI_API_KEY')
    if not openai_key:
        return jsonify({'error': 'Kein API Key gespeichert'}), 400
    data = request.json
    image_base64 = data.get('image')
    if not image_base64:
        return jsonify({'error': 'image erforderlich'}), 400
    client = OpenAI(api_key=openai_key)
    try:
        response = client.chat.completions.create(
            model="gpt-4o", max_tokens=1000,
            messages=[{
                "role": "user",
                "content": [
                    {"type": "text", "text": """Kassenbon. Extrahiere alle Lebensmittel.
Ignoriere: Pfand, Tueten, Non-Food, Rabatte, Summen.
Antworte NUR mit validem JSON Array.
Format: [{"name":"Spinat","menge":"1 Tuete","haltbarkeit":"soon|week|later"}]
Haltbarkeit: soon=Obst/Gemuese/Fleisch/Fisch, week=Milch/Joghurt/Kaese/Brot, later=Konserven/Tiefkuehl/Nudeln/Reis"""},
                    {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{image_base64}"}}
                ]
            }]
        )
        text = response.choices[0].message.content.replace('```json', '').replace('```', '').strip()
        items = json.loads(text)
        for item in items:
            db.session.add(InventarItem(name=item['name'], menge=item['menge'], urgency=item['haltbarkeit']))
        db.session.commit()
        return jsonify({'items': items})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# --- Meal Plan ---
@app.route('/mealplan', methods=['POST', 'OPTIONS'])
def mealplan():
    if request.method == 'OPTIONS':
        return jsonify({'ok': True}), 200
    openai_key = os.environ.get('OPENAI_API_KEY')
    if not openai_key:
        return jsonify({'error': 'Kein API Key gespeichert'}), 400

    data = request.json
    tage = int(data.get('tage', 3))
    mahlzeiten_pro_tag = int(data.get('mahlzeiten', 2))
    budget = float(data.get('budget', 0))
    gespeicherte_ids = data.get('gespeicherte_rezepte', [])
    total = tage * mahlzeiten_pro_tag

    items = InventarItem.query.all()
    if not items:
        return jsonify({'error': 'Kein Inventar vorhanden'}), 400

    urgency_order = {'soon': 0, 'week': 1, 'later': 2}
    virtual_inventory = sorted(
        [{'name': i.name, 'menge': i.menge, 'urgency': i.urgency} for i in items],
        key=lambda x: urgency_order[x['urgency']]
    )
    soon_names = [x['name'] for x in virtual_inventory if x['urgency'] == 'soon']

    # Gespeicherte Rezepte laden und nach Dringlichkeit sortieren
    gespeicherte = []
    if gespeicherte_ids:
        alle_gespeicherten = GespeichertesRezept.query.filter(GespeichertesRezept.id.in_(gespeicherte_ids)).all()
        inv_names = [i.name.lower() for i in items]
        soon_inv = [i.name.lower() for i in items if i.urgency == 'soon']

        def rezept_score(r):
            zutaten = json.loads(r.zutaten_json)
            z_names = [z['name'].lower() for z in zutaten]
            soon_matches = sum(1 for z in z_names if z in soon_inv)
            inv_matches = sum(1 for z in z_names if z in inv_names)
            return (-soon_matches, -inv_matches)

        gespeicherte = sorted(alle_gespeicherten, key=rezept_score)

    client = OpenAI(api_key=openai_key)
    plan = []
    gespeicherte_idx = 0

    for i in range(total):
        tag = i // mahlzeiten_pro_tag + 1
        mahlzeit_nr = i % mahlzeiten_pro_tag + 1

        if mahlzeiten_pro_tag == 1:
            mahlzeit_label = 'Abendessen'
        elif mahlzeiten_pro_tag == 2:
            mahlzeit_label = ['Mittagessen', 'Abendessen'][mahlzeit_nr - 1]
        elif mahlzeiten_pro_tag == 3:
            mahlzeit_label = ['Fruehstueck', 'Mittagessen', 'Abendessen'][mahlzeit_nr - 1]
        else:
            mahlzeit_label = f'Mahlzeit {mahlzeit_nr}'

        soon = [x for x in virtual_inventory if x['urgency'] == 'soon']
        week = [x for x in virtual_inventory if x['urgency'] == 'week']
        later = [x for x in virtual_inventory if x['urgency'] == 'later']

        if not soon and not week and not later:
            break

        # Gespeichertes Rezept einplanen falls vorhanden
        if gespeicherte_idx < len(gespeicherte):
            gr = gespeicherte[gespeicherte_idx]
            gespeicherte_idx += 1
            zutaten = json.loads(gr.zutaten_json)
            rezept = {
                'titel': gr.titel,
                'beschreibung': gr.beschreibung or '',
                'zutaten': zutaten,
                'zubereitung': gr.zubereitung or '',
                'zeit': '–',
                'tag': tag,
                'mahlzeit': mahlzeit_label,
                'quelle': 'gespeichert'
            }
            plan.append(rezept)
            for zutat in zutaten:
                zn = zutat['name'].lower()
                for inv_item in list(virtual_inventory):
                    if inv_item['name'].lower() == zn:
                        virtual_inventory.remove(inv_item)
                        break
            continue

        inv_parts = []
        if soon: inv_parts.append('DRINGEND: ' + ', '.join(f"{x['menge']} {x['name']}" for x in soon))
        if week: inv_parts.append('Diese Woche: ' + ', '.join(f"{x['menge']} {x['name']}" for x in week))
        if later: inv_parts.append('Laenger haltbar: ' + ', '.join(f"{x['menge']} {x['name']}" for x in later))

        already_planned = ', '.join([m['titel'] for m in plan]) if plan else 'keine'
        urgency_instruction = ''
        if tag <= 2 and soon:
            urgency_instruction = f'\nWICHTIG: Tag {tag}. MUSS dringende Zutat verwenden: {", ".join(soon_names)}'

        try:
            response = client.chat.completions.create(
                model='gpt-4o', max_tokens=800,
                messages=[
                    {"role": "system", "content": "Du planst Mahlzeiten fuer eine Person. Generiere GENAU 1 Rezept als JSON. Verwende NUR Zutaten aus dem Inventar plus Wasser/Salz/Pfeffer/Oel. Dringende Zutaten MUESSEN in Tag 1-2. Nicht wiederholen. NUR JSON. Format: {\"titel\":\"Name\",\"zeit\":\"20 Min\",\"beschreibung\":\"Kurz\",\"zutaten\":[{\"name\":\"Spinat\",\"menge\":\"ganze Tuete\",\"urgency\":\"soon\"}],\"zubereitung\":\"Schritt 1: ...\"}"},
                    {"role": "user", "content": f"Inventar:\n{chr(10).join(inv_parts)}\n\nBereits geplant: {already_planned}\nTag {tag} von {tage}, {mahlzeit_label}{urgency_instruction}"}
                ]
            )
            text = response.choices[0].message.content.replace('```json', '').replace('```', '').strip()
            rezept = json.loads(text)
            rezept['tag'] = tag
            rezept['mahlzeit'] = mahlzeit_label
            rezept['quelle'] = 'ki'
            plan.append(rezept)

            for zutat in rezept.get('zutaten', []):
                zn = zutat['name'].lower()
                zm = zutat.get('menge', '').lower()
                for inv_item in list(virtual_inventory):
                    if inv_item['name'].lower() == zn:
                        if any(w in zm for w in ['ganz', 'alles', 'alle', 'komplett', 'gesamt']):
                            virtual_inventory.remove(inv_item)
                            if inv_item['name'] in soon_names:
                                soon_names.remove(inv_item['name'])
                        elif any(w in zm for w in ['hälfte', 'halb', 'haelfte']):
                            inv_item['menge'] = 'ca. Hälfte noch'
                            inv_item['urgency'] = 'soon'
                        else:
                            # Standardmäßig: Zutat als größtenteils verbraucht markieren
                            inv_item['menge'] = 'wenig übrig'
                            inv_item['urgency'] = 'soon'
                        break
        except Exception as e:
            plan.append({'tag': tag, 'mahlzeit': mahlzeit_label, 'titel': 'Fehler', 'beschreibung': str(e), 'zutaten': [], 'zubereitung': '', 'quelle': 'ki'})

    # Einkaufsliste & Extra-Zutaten
    all_items_text = ', '.join([f"{i.menge} {i.name}" for i in items])
    plan_zutaten_text = '\n'.join([f"- {m['titel']} (Tag {m['tag']}, {m['mahlzeit']}): {', '.join([z['name'] + ' (' + z.get('menge','') + ')' for z in m.get('zutaten',[])])}" for m in plan])
    fehlende_namen = ', '.join(set([z['name'] for m in plan for z in m.get('zutaten', []) if z['name'].lower() not in [i.name.lower() for i in items]]))
    budget_text = f"Budget für Einkauf: {budget:.2f} EUR" if budget > 0 else "Kein Budget festgelegt"

    einkaufsliste = {}
    extra_zutaten = []
    budget_verwendet = 0

    try:
        response = client.chat.completions.create(
            model='gpt-4o', max_tokens=1500,
            messages=[
                {"role": "system", "content": """Du bist Einkaufsplaner für Deutschland (REWE). Antworte NUR mit validem JSON.
REGELN:
- einkaufsliste: NUR Zutaten die im Plan benötigt aber NICHT im Inventar sind (typ: fehlend)
- extra_zutaten: optionale Zutaten die ein KONKRETES geplantes Rezept deutlich aufwerten würden - NIEMALS allgemeine Vorschläge
- Jede extra_zutat MUSS einen "rezept" Feldwert haben der den exakten Rezepttitel nennt den sie aufwertet
- extra_zutaten kommen NICHT automatisch auf die Einkaufsliste
- Grundzutaten wie Wasser, Salz, Pfeffer, Öl, Zucker NIEMALS vorschlagen
- Verwende korrekte deutsche Umlaute (ä, ö, ü)
- Realistische REWE-Preise
Format: {"extra_zutaten":[{"name":"Parmesan","menge":"1 Stück","preis_ca":2.49,"grund":"Macht die Pasta cremiger","rezept":"Pasta mit Tomaten","kategorie":"Kühlregal"}],"einkaufsliste":{"Obst & Gemüse":[{"name":"X","menge":"Y","preis_ca":1.20,"typ":"fehlend"}],"Kühlregal":[],"Tiefkühl":[],"Brot & Backwaren":[],"Trockenwaren & Konserven":[],"Getränke":[],"Sonstiges":[]},"budget_verwendet":5.00,"budget_gesamt":20.00}"""},
                {"role": "user", "content": f"""Inventar (vorhanden, NICHT auf Liste): {all_items_text}

Geplante Mahlzeiten mit Zutaten und Mengen:
{plan_zutaten_text}

Fehlende Zutaten (bereits auf Liste, NICHT als Extra): {fehlende_namen}
{budget_text}

Aufgaben:
1. Einkaufsliste: NUR Zutaten die im Plan benötigt aber NICHT im Inventar sind (kein Wasser/Salz/Pfeffer/Öl)
2. Extra-Vorschläge: 2-3 Zutaten die ein KONKRETES geplantes Rezept aufwerten - mit exaktem Rezeptnamen im Feld "rezept"
3. Budget beachten, fehlende Zutaten haben Priorität
4. Realistische REWE-Preise, korrekte Umlaute"""}
            ]
        )
        text = response.choices[0].message.content.replace('```json', '').replace('```', '').strip()
        einkauf_data = json.loads(text)
        einkaufsliste = einkauf_data.get('einkaufsliste', {})
        extra_zutaten = einkauf_data.get('extra_zutaten', [])
        budget_verwendet = einkauf_data.get('budget_verwendet', 0)
    except Exception as e:
        pass

    grouped = {}
    for m in plan:
        t = m['tag']
        if t not in grouped:
            grouped[t] = []
        grouped[t].append(m)

    return jsonify({
        'plan': grouped, 'tage': tage, 'mahlzeiten': mahlzeiten_pro_tag,
        'einkaufsliste': einkaufsliste, 'extra_zutaten': extra_zutaten,
        'budget': budget, 'budget_verwendet': budget_verwendet
    })

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(port=port, host='0.0.0.0', debug=False)