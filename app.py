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

@app.route('/historie', methods=['GET'])
def get_historie():
    rezepte = GekochteRezept.query.order_by(GekochteRezept.gekocht_am.desc()).limit(20).all()
    return jsonify([{
        'id': r.id,
        'titel': r.titel,
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
    total = tage * mahlzeiten_pro_tag

    items = InventarItem.query.all()
    if not items:
        return jsonify({'error': 'Kein Inventar vorhanden'}), 400

    urgency_order = {'soon': 0, 'week': 1, 'later': 2}
    virtual_inventory = sorted(
        [{'name': i.name, 'menge': i.menge, 'urgency': i.urgency} for i in items],
        key=lambda x: urgency_order[x['urgency']]
    )

    # Dringende Zutaten identifizieren
    soon_items = [x for x in virtual_inventory if x['urgency'] == 'soon']
    soon_names = [x['name'] for x in soon_items]

    client = OpenAI(api_key=openai_key)
    plan = []

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

        inv_parts = []
        if soon: inv_parts.append('DRINGEND (MUSS in Tag 1-2 verwendet werden): ' + ', '.join(f"{x['menge']} {x['name']}" for x in soon))
        if week: inv_parts.append('Diese Woche: ' + ', '.join(f"{x['menge']} {x['name']}" for x in week))
        if later: inv_parts.append('Laenger haltbar: ' + ', '.join(f"{x['menge']} {x['name']}" for x in later))

        if not inv_parts:
            break

        already_planned = ', '.join([m['titel'] for m in plan]) if plan else 'keine'

        # Strenge Anweisung fuer fruehe Tage
        urgency_instruction = ''
        if tag <= 2 and soon:
            urgency_instruction = f'\nWICHTIG: Es ist Tag {tag}. Du MUSST mindestens eine DRINGENDE Zutat verwenden: {", ".join(soon_names)}. Diese verfallen sonst!'

        try:
            response = client.chat.completions.create(
                model='gpt-4o', max_tokens=800,
                messages=[
                    {"role": "system", "content": """Du planst Mahlzeiten fuer eine einzelne Person.
Generiere GENAU 1 Rezept als JSON Objekt.
REGELN:
- Verwende NUR Zutaten aus dem Inventar plus Wasser/Salz/Pfeffer/Oel
- Dringende Zutaten MUESSEN in den ersten 1-2 Tagen verwendet werden
- Nicht dasselbe Rezept wiederholen
- Antworte NUR mit validem JSON ohne Text
Format: {"titel":"Name","zeit":"20 Min","beschreibung":"Kurze appetitliche Beschreibung","zutaten":[{"name":"Spinat","menge":"ganze Tuete","urgency":"soon"}],"zubereitung":"Schritt 1: ... Schritt 2: ... Schritt 3: ..."}"""},
                    {"role": "user", "content": f"Inventar:\n{chr(10).join(inv_parts)}\n\nBereits geplant (nicht wiederholen): {already_planned}\nTag {tag} von {tage}, {mahlzeit_label}{urgency_instruction}"}
                ]
            )
            text = response.choices[0].message.content.replace('```json', '').replace('```', '').strip()
            rezept = json.loads(text)
            rezept['tag'] = tag
            rezept['mahlzeit'] = mahlzeit_label
            plan.append(rezept)

            for zutat in rezept.get('zutaten', []):
                zn = zutat['name'].lower()
                zm = zutat.get('menge', '').lower()
                for inv_item in list(virtual_inventory):
                    if inv_item['name'].lower() == zn:
                        if any(w in zm for w in ['ganz', 'alles', 'alle', 'komplett']):
                            virtual_inventory.remove(inv_item)
                            if inv_item['name'] in soon_names:
                                soon_names.remove(inv_item['name'])
                        elif any(w in zm for w in ['haelfte', 'halb']):
                            inv_item['menge'] = 'Haelfte noch'
                            inv_item['urgency'] = 'soon'
                        else:
                            inv_item['menge'] = 'wenig uebrig'
                            inv_item['urgency'] = 'soon'
                        break
        except Exception as e:
            plan.append({'tag': tag, 'mahlzeit': mahlzeit_label, 'titel': 'Fehler', 'beschreibung': str(e), 'zutaten': [], 'zubereitung': ''})

    # Einkaufsliste & Extra-Zutaten
    all_items_text = ', '.join([f"{i.menge} {i.name}" for i in items])
    plan_zutaten_text = '\n'.join([f"- {m['titel']}: {', '.join([z['name'] for z in m.get('zutaten',[])])}" for m in plan])
    budget_text = f"Budget fuer Einkauf: {budget:.2f} EUR" if budget > 0 else "Kein Budget festgelegt"

    einkaufsliste = {}
    extra_zutaten = []
    budget_verwendet = 0

    try:
        response = client.chat.completions.create(
            model='gpt-4o', max_tokens=1500,
            messages=[
                {"role": "system", "content": """Du bist ein Einkaufsplaner fuer Deutschland (REWE).
Antworte NUR mit validem JSON ohne Text davor/danach.

STRENGE REGELN:
- In "einkaufsliste" NUR Zutaten die entweder:
  a) typ "fehlend": im Meal Plan benoetigt aber NICHT im aktuellen Inventar
  b) typ "extra": explizit in extra_zutaten vorgeschlagen UND vom Nutzer hinzugefuegt
- KEINE anderen Zutaten erfinden
- extra_zutaten sind VORSCHLAEGE - sie kommen NICHT automatisch auf die Einkaufsliste
- Schaetze realistische deutsche REWE-Supermarktpreise

Format:
{
  "extra_zutaten": [
    {"name": "Zitrone", "menge": "2 Stueck", "preis_ca": 0.80, "grund": "Wuerde Rezept X deutlich aufwerten", "kategorie": "Obst & Gemuese"}
  ],
  "einkaufsliste": {
    "Obst & Gemuese": [{"name": "Tomate", "menge": "3 Stueck", "preis_ca": 1.29, "typ": "fehlend"}],
    "Kuehlregal": [],
    "Tiefkuehl": [],
    "Brot & Backwaren": [],
    "Trockenwaren & Konserven": [],
    "Getraenke": [],
    "Sonstiges": []
  },
  "budget_verwendet": 3.50,
  "budget_gesamt": 20.00
}"""},
                {"role": "user", "content": f"""Aktuelles Inventar (bereits vorhanden, NICHT auf Einkaufsliste):
{all_items_text}

Geplante Mahlzeiten und deren Zutaten:
{plan_zutaten_text}

Fehlende Zutaten (bereits auf Einkaufsliste, NICHT als Extra vorschlagen):
{', '.join(set([z['name'] for m in plan for z in m.get('zutaten', []) if z['name'].lower() not in [i.name.lower() for i in items]]))}

{budget_text}

Aufgaben:
1. Finde Zutaten die im Plan vorkommen aber NICHT im Inventar sind (typ: fehlend)
2. Schlage 2-3 optionale Extra-Zutaten vor die Rezepte verbessern wuerden - NUR Zutaten die WEDER im Inventar NOCH bereits auf der Einkaufsliste sind
3. Einkaufsliste enthaelt NUR fehlende Zutaten (typ: fehlend)
4. Halte dich ans Budget, fehlende Zutaten haben Prioritaet
5. Schaetze realistische deutsche REWE-Supermarktpreise"""}            ]
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
        'plan': grouped,
        'tage': tage,
        'mahlzeiten': mahlzeiten_pro_tag,
        'einkaufsliste': einkaufsliste,
        'extra_zutaten': extra_zutaten,
        'budget': budget,
        'budget_verwendet': budget_verwendet
    })

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(port=port, host='0.0.0.0', debug=False)