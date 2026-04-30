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
    kategorien = db.Column(db.Text, default='[]')
    gespeichert_am = db.Column(db.DateTime, default=datetime.utcnow)

class UserSettings(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    ernaehrung = db.Column(db.String(50), default='alles')
    cuisines = db.Column(db.Text, default='[]')
    schwierigkeit = db.Column(db.String(20), default='mittel')
    tools = db.Column(db.Text, default='[]')
    mag_nicht = db.Column(db.Text, default='')
    mag = db.Column(db.Text, default='')
    snacks_aktiv = db.Column(db.Boolean, default=False)
    snack_budget_typ = db.Column(db.String(20), default='im_budget')
    snack_budget = db.Column(db.Float, default=0.0)
    ziel_kalorien = db.Column(db.Integer, default=0)
    ziel_protein = db.Column(db.Integer, default=0)
    ziel_kohlenhydrate = db.Column(db.Integer, default=0)
    ziel_fett = db.Column(db.Integer, default=0)

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
    result = []
    for r in rezepte:
        try:
            nw = json.loads(r.naehrstoffe) if hasattr(r, 'naehrstoffe') and r.naehrstoffe else {}
        except:
            nw = {}
        result.append({
            'id': r.id, 'titel': r.titel, 'beschreibung': r.beschreibung,
            'zutaten': json.loads(r.zutaten_json),
            'zubereitung': r.zubereitung, 'quelle': r.quelle,
            'kategorien': json.loads(r.kategorien or '[]'),
            'naehrstoffe': nw,
            'gespeichert_am': r.gespeichert_am.strftime('%d.%m.%Y')
        })
    return jsonify(result)

@app.route('/meine-rezepte', methods=['POST'])
def add_mein_rezept():
    data = request.json
    r = GespeichertesRezept(
        titel=data['titel'],
        beschreibung=data.get('beschreibung', ''),
        zutaten_json=json.dumps(data.get('zutaten', [])),
        zubereitung=data.get('zubereitung', ''),
        quelle=data.get('quelle', 'manuell'),
        kategorien=json.dumps(data.get('kategorien', []))
    )
    db.session.add(r)
    db.session.commit()
    return jsonify({'id': r.id, 'ok': True})

@app.route('/meine-rezepte/<int:rezept_id>', methods=['PUT'])
def update_mein_rezept(rezept_id):
    r = GespeichertesRezept.query.get_or_404(rezept_id)
    data = request.json
    if 'titel' in data: r.titel = data['titel']
    if 'beschreibung' in data: r.beschreibung = data['beschreibung']
    if 'zutaten' in data: r.zutaten_json = json.dumps(data['zutaten'])
    if 'zubereitung' in data: r.zubereitung = data['zubereitung']
    if 'kategorien' in data: r.kategorien = json.dumps(data['kategorien'])
    db.session.commit()
    return jsonify({'ok': True})
    db.session.add(r)
    db.session.commit()
    return jsonify({'id': r.id, 'ok': True})

@app.route('/meine-rezepte/<int:rezept_id>', methods=['DELETE'])
def delete_mein_rezept(rezept_id):
    r = GespeichertesRezept.query.get_or_404(rezept_id)
    db.session.delete(r)
    db.session.commit()
    return jsonify({'ok': True})

@app.route('/meine-rezepte/<int:rezept_id>/kategorien', methods=['POST'])
def update_kategorien(rezept_id):
    r = GespeichertesRezept.query.get_or_404(rezept_id)
    r.kategorien = json.dumps(request.json.get('kategorien', []))
    db.session.commit()
    return jsonify({'ok': True})

# --- Historie löschen ---
@app.route('/historie/<int:rezept_id>', methods=['DELETE'])
def delete_historie(rezept_id):
    r = GekochteRezept.query.get_or_404(rezept_id)
    db.session.delete(r)
    db.session.commit()
    return jsonify({'ok': True})

# --- User Settings ---
@app.route('/user-settings', methods=['GET'])
def get_user_settings():
    s = UserSettings.query.first()
    if not s:
        return jsonify({
            'ernaehrung': 'alles', 'cuisines': [], 'schwierigkeit': 'mittel',
            'tools': [], 'mag_nicht': '', 'mag': '',
            'snacks_aktiv': False, 'snack_budget_typ': 'im_budget', 'snack_budget': 0.0,
            'ziel_kalorien': 0, 'ziel_protein': 0, 'ziel_kohlenhydrate': 0, 'ziel_fett': 0
        })
    return jsonify({
        'ernaehrung': s.ernaehrung,
        'cuisines': json.loads(s.cuisines or '[]'),
        'schwierigkeit': s.schwierigkeit,
        'tools': json.loads(s.tools or '[]'),
        'mag_nicht': s.mag_nicht or '',
        'mag': s.mag or '',
        'snacks_aktiv': s.snacks_aktiv,
        'snack_budget_typ': s.snack_budget_typ,
        'snack_budget': s.snack_budget,
        'ziel_kalorien': s.ziel_kalorien or 0,
        'ziel_protein': s.ziel_protein or 0,
        'ziel_kohlenhydrate': s.ziel_kohlenhydrate or 0,
        'ziel_fett': s.ziel_fett or 0
    })

@app.route('/user-settings', methods=['POST'])
def save_user_settings():
    data = request.json
    s = UserSettings.query.first()
    if not s:
        s = UserSettings()
        db.session.add(s)
    s.ernaehrung = data.get('ernaehrung', 'alles')
    s.cuisines = json.dumps(data.get('cuisines', []))
    s.schwierigkeit = data.get('schwierigkeit', 'mittel')
    s.tools = json.dumps(data.get('tools', []))
    s.mag_nicht = data.get('mag_nicht', '')
    s.mag = data.get('mag', '')
    s.snacks_aktiv = data.get('snacks_aktiv', False)
    s.snack_budget_typ = data.get('snack_budget_typ', 'im_budget')
    s.snack_budget = float(data.get('snack_budget', 0))
    s.ziel_kalorien = int(data.get('ziel_kalorien', 0))
    s.ziel_protein = int(data.get('ziel_protein', 0))
    s.ziel_kohlenhydrate = int(data.get('ziel_kohlenhydrate', 0))
    s.ziel_fett = int(data.get('ziel_fett', 0))
    db.session.commit()
    return jsonify({'ok': True})

# --- Meal als gekocht markieren ---
@app.route('/meal-gekocht', methods=['POST', 'OPTIONS'])
def meal_gekocht():
    if request.method == 'OPTIONS':
        return jsonify({'ok': True}), 200
    data = request.json
    zutaten = data.get('zutaten', [])
    portionen = float(data.get('portionen', 1))
    titel = data.get('titel', '')

    import re

    def parse_menge(menge_str):
        """Extrahiert Zahl und Einheit aus Mengenstring. Gibt (zahl, einheit) zurück oder (None, None)."""
        menge_str = menge_str.strip().lower()
        m = re.match(r'^([\d.,]+)\s*(g|kg|ml|l|stück|stk|el|tl|packung|pck|dose|glas|becher|bund|liter)?', menge_str)
        if m and m.group(1):
            try:
                zahl = float(m.group(1).replace(',', '.'))
                einheit = m.group(2) or ''
                return zahl, einheit
            except:
                pass
        return None, None

    def berechne_rest(inventar_menge, verbrauch_menge, portionen):
        """Berechnet Restmenge nach Verbrauch."""
        inv_zahl, inv_einheit = parse_menge(inventar_menge)
        verb_zahl, verb_einheit = parse_menge(verbrauch_menge)

        if inv_zahl is not None and verb_zahl is not None and inv_einheit == verb_einheit:
            # Beide haben gleiche Einheit -> direkte Subtraktion
            rest = inv_zahl - (verb_zahl * portionen)
            if rest <= 0:
                return None  # Komplett verbraucht
            # Schöne Ausgabe
            if inv_einheit in ['g', 'ml']:
                return f"{int(rest)}{inv_einheit}"
            elif inv_einheit in ['kg', 'l', 'liter']:
                return f"{rest:.2f} {inv_einheit}".rstrip('0').rstrip('.')
            elif inv_einheit in ['stück', 'stk', '']:
                return f"{int(rest)} Stück" if rest >= 1 else None
            else:
                return f"{int(rest)} {inv_einheit}"
        return None  # Kann nicht berechnet werden

    def beschreibung_zu_anteil(menge_str):
        """Konvertiert Beschreibung wie 'halbe Packung' zu Anteil (0.5)."""
        m = menge_str.lower()
        if any(w in m for w in ['ganz', 'alles', 'alle', 'komplett', 'gesamt']): return 1.0
        if any(w in m for w in ['dreiviertel', '3/4']): return 0.75
        if any(w in m for w in ['hälfte', 'halb', '1/2']): return 0.5
        if any(w in m for w in ['viertel', '1/4']): return 0.25
        if any(w in m for w in ['drittel', '1/3']): return 0.33
        return None

    def inventar_anteil_zu_text(anteil):
        """Konvertiert Anteil zu lesbarem Text."""
        if anteil <= 0: return None
        if anteil >= 0.9: return 'fast alles'
        if anteil >= 0.6: return 'ca. dreiviertel Packung'
        if anteil >= 0.4: return 'ca. halbe Packung'
        if anteil >= 0.2: return 'ca. viertel Packung'
        return 'wenig übrig'

    for zutat in zutaten:
        name = zutat.get('name', '').lower()
        rezept_menge = zutat.get('menge', '').lower()
        kaufen = zutat.get('kaufen', False)
        if kaufen:
            continue

        item = InventarItem.query.filter(
            db.func.lower(InventarItem.name) == name
        ).first()
        if not item:
            continue

        inv_menge = item.menge

        # Versuch 1: Direkte numerische Berechnung
        rest = berechne_rest(inv_menge, rezept_menge, portionen)
        if rest is not None:
            item.menge = rest
            item.urgency = 'soon'
            db.session.flush()
            continue
        elif rest is None and berechne_rest(inv_menge, rezept_menge, portionen) is None:
            # Prüfen ob berechnung 0 oder negativ war
            inv_zahl, inv_e = parse_menge(inv_menge)
            verb_zahl, verb_e = parse_menge(rezept_menge)
            if inv_zahl and verb_zahl and inv_e == verb_e:
                if inv_zahl - verb_zahl * portionen <= 0:
                    db.session.delete(item)
                    continue

        # Versuch 2: Anteil-basierte Berechnung (z.B. "halbe Packung")
        rezept_anteil = beschreibung_zu_anteil(rezept_menge)
        inv_anteil = beschreibung_zu_anteil(inv_menge)

        if rezept_anteil is not None:
            verbrauch_gesamt = rezept_anteil * portionen
            if inv_anteil is not None:
                rest_anteil = inv_anteil - verbrauch_gesamt
            else:
                # Inventar hat keine Anteilsangabe -> assume voll
                rest_anteil = 1.0 - verbrauch_gesamt

            if rest_anteil <= 0.05:
                db.session.delete(item)
            else:
                item.menge = inventar_anteil_zu_text(rest_anteil)
                item.urgency = 'soon'
            continue

        # Fallback: wenig übrig
        if any(w in rezept_menge for w in ['ganz', 'alles', 'alle', 'komplett']):
            db.session.delete(item)
        else:
            item.menge = 'wenig übrig'
            item.urgency = 'soon'

    r = GekochteRezept(titel=titel, zutaten_json=json.dumps(zutaten))
    db.session.add(r)
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
            model="gpt-4o", max_tokens=1500,
            messages=[{
                "role": "user",
                "content": [
                    {"type": "text", "text": """Das ist ein Screenshot eines Rezepts oder einer Social Media Caption.
Extrahiere das Rezept vollständig. Antworte NUR mit validem JSON.
Falls Nährwerte im Screenshot sichtbar sind, extrahiere sie. Falls nicht, schätze sie.
Format: {
  "titel": "Rezeptname",
  "beschreibung": "Kurze Beschreibung",
  "zutaten": [{"name": "Zutat", "menge": "Menge"}],
  "zubereitung": "Zubereitungsschritte",
  "naehrstoffe": {"kalorien": 500, "protein": 30, "kohlenhydrate": 50, "fett": 15}
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
@app.route('/preis-schaetzen', methods=['POST', 'OPTIONS'])
def preis_schaetzen():
    if request.method == 'OPTIONS':
        return jsonify({'ok': True}), 200
    openai_key = os.environ.get('OPENAI_API_KEY')
    if not openai_key:
        return jsonify({'preis': 0}), 200
    data = request.json
    name = data.get('name', '')
    if not name:
        return jsonify({'preis': 0}), 200
    client = OpenAI(api_key=openai_key)
    try:
        response = client.chat.completions.create(
            model='gpt-4o', max_tokens=50,
            messages=[{
                'role': 'user',
                'content': f'Was kostet "{name}" ungefähr im deutschen REWE Supermarkt? Antworte NUR mit der Zahl in Euro (z.B. 1.99). Kein Text, keine Einheit.'
            }]
        )
        text = response.choices[0].message.content.strip().replace(',', '.')
        import re
        m = re.search(r'[\d.]+', text)
        preis = float(m.group()) if m else 0
        return jsonify({'preis': round(preis, 2)})
    except:
        return jsonify({'preis': 0})

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
    meal_prep = data.get('meal_prep', False)
    start_mahlzeit = data.get('start_mahlzeit', 'Mittagessen')  # erste Mahlzeit des ersten Tags
    total = tage * mahlzeiten_pro_tag

    # Alle User Settings laden
    user_settings = UserSettings.query.first()
    ernaehrung = user_settings.ernaehrung if user_settings else 'alles'
    cuisines = json.loads(user_settings.cuisines or '[]') if user_settings else []
    schwierigkeit = user_settings.schwierigkeit if user_settings else 'mittel'
    tools = json.loads(user_settings.tools or '[]') if user_settings else []
    mag_nicht = user_settings.mag_nicht if user_settings else ''
    mag = user_settings.mag if user_settings else ''
    snacks_aktiv = user_settings.snacks_aktiv if user_settings else False
    snack_budget_typ = user_settings.snack_budget_typ if user_settings else 'im_budget'
    snack_budget_val = user_settings.snack_budget if user_settings else 0.0
    ziel_kalorien = (user_settings.ziel_kalorien or 0) if user_settings else 0
    ziel_protein = (user_settings.ziel_protein or 0) if user_settings else 0
    ziel_kohlenhydrate = (user_settings.ziel_kohlenhydrate or 0) if user_settings else 0
    ziel_fett = (user_settings.ziel_fett or 0) if user_settings else 0

    ernaehrung_map = {
        'alles': 'keine Einschränkungen',
        'vegetarisch': 'vegetarisch - kein Fleisch, kein Fisch',
        'vegan': 'vegan - keine tierischen Produkte',
        'pescetarisch': 'pescetarisch - kein Fleisch, aber Fisch erlaubt',
        'kein_schwein': 'kein Schweinefleisch',
        'kein_rohes_fleisch': 'kein rohes Fleisch zum Zubereiten (kein Hackfleisch, kein rohes Hähnchen/Rind/Schwein zum Kochen) - aber Aufschnitt, Bacon, Wurst, TK-vorgegartes Fleisch ist erlaubt'
    }
    ernaehrung_text = ernaehrung_map.get(ernaehrung, 'keine Einschränkungen')

    schwierigkeit_map = {
        'einfach': 'einfache Rezepte (max. 20 Min, wenige Zutaten, keine komplexen Techniken)',
        'mittel': 'mittelschwere Rezepte (20-40 Min, normale Kochtechniken)',
        'anspruchsvoll': 'anspruchsvolle Rezepte (auch aufwändigere Gerichte erlaubt)'
    }
    schwierigkeit_text = schwierigkeit_map.get(schwierigkeit, 'mittelschwere Rezepte')

    cuisines_list = ', '.join(cuisines) if cuisines else ''
    cuisines_text = f"Bevorzugte Küchen (WECHSLE zwischen diesen ab): {cuisines_list}" if cuisines_list else "Verschiedene Küchen abwechseln"
    tools_text = f"Verfügbare Küchengeräte (NUR diese verwenden): {', '.join(tools)}" if tools else ""
    tools_verboten = "VERBOTEN (nicht vorhanden): Muffinform, Eismaschine" if tools and 'muffinform' not in [t.lower() for t in tools] else ""
    if tools:
        nicht_vorhanden = []
        alle_tools = ['mixer','stabmixer','backofen','mikrowelle','dampfgarer','slow cooker','wok','grill','küchenmaschine','reiskocher','heißluftfritteuse','waffeleisen','muffinform']
        for t in alle_tools:
            if t not in [x.lower() for x in tools]:
                nicht_vorhanden.append(t)
        if nicht_vorhanden:
            tools_verboten = f"NICHT VERFÜGBAR - keine Rezepte die diese Geräte benötigen: {', '.join(nicht_vorhanden)}"
    mag_nicht_text = f"Mag NICHT - niemals verwenden: {mag_nicht}" if mag_nicht.strip() else ""
    mag_text = f"Mag besonders gerne - bevorzuge diese: {mag}" if mag.strip() else ""

    # Gespeicherte Rezepte als Stil-Referenz laden
    alle_gespeicherten_titel = []
    try:
        style_rezepte = GespeichertesRezept.query.order_by(GespeichertesRezept.gespeichert_am.desc()).limit(10).all()
        alle_gespeicherten_titel = [r.titel for r in style_rezepte]
    except:
        pass
    style_text = f"Rezepte die diese Person gerne isst (als Stil-Referenz): {', '.join(alle_gespeicherten_titel)}" if alle_gespeicherten_titel else ""

    # Macro-Ziele für Prompt
    macro_text = ""
    if ziel_kalorien or ziel_protein or ziel_kohlenhydrate or ziel_fett:
        macro_parts = []
        if ziel_kalorien: macro_parts.append(f"{ziel_kalorien} kcal")
        if ziel_protein: macro_parts.append(f"{ziel_protein}g Protein")
        if ziel_kohlenhydrate: macro_parts.append(f"{ziel_kohlenhydrate}g Kohlenhydrate")
        if ziel_fett: macro_parts.append(f"{ziel_fett}g Fett")
        mahlzeiten_faktor = mahlzeiten_pro_tag if mahlzeiten_pro_tag > 0 else 2
        macro_text = f"Macro-Ziele pro TAG: {', '.join(macro_parts)} - verteile dies auf {mahlzeiten_faktor} Mahlzeiten"

    # Fleisch-Einschränkung global berechnen
    fleisch_einschraenkung = ""
    if ernaehrung == 'kein_rohes_fleisch':
        fleisch_einschraenkung = "FLEISCH: Kein rohes Fleisch (kein Hackfleisch, keine rohe Haehnchenbrust). Erlaubt: Aufschnitt, Bacon, TK-Gefluegel (vorgegart)."
    elif ernaehrung == 'vegetarisch':
        fleisch_einschraenkung = "KEIN Fleisch, KEIN Fisch - STRIKT einhalten."
    elif ernaehrung == 'vegan':
        fleisch_einschraenkung = "KEINE tierischen Produkte - STRIKT einhalten."

    # Prompt-Variablen (als einfache Strings, keine f-triple-strings)
    phase1_system_prompt = (
        "Du bist ein Koch und planst eine Mahlzeit fuer eine Person.\n"
        "ERNAEHRUNG: " + ernaehrung_text + " - STRIKT einhalten.\n"
        + (fleisch_einschraenkung + "\n" if fleisch_einschraenkung else "")
        + "SCHWIERIGKEIT: " + schwierigkeit_text + "\n"
        + cuisines_text + "\n"
        + (mag_nicht_text + "\n" if mag_nicht_text else "")
        + (mag_text + "\n" if mag_text else "")
        + "VORGEHEN:\n"
        "1. Waehle ein leckeres, bekanntes Gericht das zu den Inventar-Zutaten passt\n"
        "2. Nutze Inventar-Zutaten NUR wenn sie zum Gericht passen\n"
        "3. NIEMALS unpassende Zutaten kombinieren (kein Parmesan in Pancakes, kein Kaese zu Beeren)\n"
        "4. Dringende Zutaten priorisieren wenn sie zum Gericht passen\n"
        "5. Abwechslungsreich - nicht dasselbe wie bereits geplant\n"
        'NUR JSON: {"titel":"Name","zeit":"20 Min","beschreibung":"Kurz","kueche":"deutsch",'
        '"zutaten":[{"name":"Spinat","menge":"ganze Tuete","kaufen":false}],'
        '"zubereitung":"Schritt 1...","naehrstoffe":{"kalorien":400,"protein":25,"kohlenhydrate":40,"fett":12}}'
    )

    phase2_system_prompt = (
        "Du bist ein Koch und planst eine Mahlzeit fuer eine Person in Deutschland.\n"
        "ERNAEHRUNG: " + ernaehrung_text + " - STRIKT einhalten.\n"
        + (fleisch_einschraenkung + "\n" if fleisch_einschraenkung else "")
        + "SCHWIERIGKEIT: " + schwierigkeit_text + "\n"
        + cuisines_text + "\n"
        + (mag_nicht_text + "\n" if mag_nicht_text else "")
        + (mag_text + "\n" if mag_text else "")
        + (style_text + "\n" if style_text else "")
        + (macro_text + "\n" if macro_text else "")
        + "VORGEHEN:\n"
        "1. Waehle ein konkretes, leckeres Gericht aus der gewuenschten Kueche\n"
        "2. Nutze Inventar-Zutaten nur wenn sie wirklich passen\n"
        "3. NIEMALS unpassende Zutaten kombinieren\n"
        "4. Realistische Mengen: 150-200g Protein, 80-100g Nudeln/Reis\n"
        "5. Handelsübliche Packungsgroessen bei Einkauf\n"
        "6. Budget einhalten\n"
        'NUR JSON: {"titel":"Name","zeit":"25 Min","beschreibung":"X","kueche":"italienisch",'
        '"zutaten":[{"name":"Hahnchen","menge":"1 Stueck (150g)","kaufen":true}],'
        '"zubereitung":"Schritt 1...","naehrstoffe":{"kalorien":550,"protein":35,"kohlenhydrate":60,"fett":15}}'
    )

    snack_system_prompt = (
        "Gesunder, einfacher Snack fuer 1 Person. "
        "ERNAEHRUNG: " + ernaehrung_text + ". "
        + (mag_nicht_text if mag_nicht_text else "") + "\n"
        "Nur bekannte, realistische Snacks.\n"
        "WICHTIG: Genaue Mengenangaben. kaufen:false wenn im Inventar.\n"
        'NUR JSON: {"titel":"Name","zeit":"2 Min","beschreibung":"Kurz",'
        '"zutaten":[{"name":"Apfel","menge":"1 Stueck (150g)","kaufen":false}],'
        '"naehrstoffe":{"kalorien":80,"protein":1,"kohlenhydrate":20,"fett":0}}'
    )
    budget_warnung = ""
    if budget > 0:
        budget_pro_tag = budget / tage
        if budget_pro_tag < 3:
            budget_warnung = f"BUDGET_WARNUNG: {budget:.2f}€ für {tage} Tage ist sehr knapp (ca. {budget_pro_tag:.2f}€/Tag)."
        elif budget_pro_tag < 5:
            budget_warnung = f"Budget ist moderat ({budget_pro_tag:.2f}€/Tag) - günstige Zutaten bevorzugen."

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
            mahlzeit_label = ['Frühstück', 'Mittagessen', 'Abendessen'][mahlzeit_nr - 1]
        else:
            mahlzeit_label = f'Mahlzeit {mahlzeit_nr}'

        # start_mahlzeit: Mahlzeiten vor der gewählten Startmahlzeit an Tag 1 überspringen
        if tag == 1 and start_mahlzeit:
            mahlzeit_reihenfolge = ['Frühstück', 'Fruehstueck', 'Mittagessen', 'Abendessen']
            start_idx = next((i for i, m in enumerate(mahlzeit_reihenfolge) if m == start_mahlzeit), 0)
            label_idx = next((i for i, m in enumerate(mahlzeit_reihenfolge) if m == mahlzeit_label), 0)
            if label_idx < start_idx:
                continue  # Diese Mahlzeit überspringen

        # Meal Prep: Mittagessen von Tag 2+ = Abendessen des Vortags
        if meal_prep and mahlzeit_label == 'Mittagessen' and tag > 1:
            prev_abendessen = next(
                (m for m in plan if m.get('tag') == tag - 1 and m.get('mahlzeit') == 'Abendessen'),
                None
            )
            if prev_abendessen:
                # Makros der Meal Prep Kopie = gleich wie Abendessen (beide bereits pro Portion)
                plan.append({
                    **prev_abendessen,
                    'tag': tag,
                    'mahlzeit': 'Mittagessen',
                    'quelle': 'meal_prep',
                    'meal_prep_von': prev_abendessen['titel']
                })
                continue

        soon = [x for x in virtual_inventory if x['urgency'] == 'soon']
        week = [x for x in virtual_inventory if x['urgency'] == 'week']
        later = [x for x in virtual_inventory if x['urgency'] == 'later']

        # Phase bestimmen: Phase 1 wenn dringende Zutaten ODER Budget=0 (kein Einkauf)
        phase1 = len(soon_names) > 0 or budget == 0
        phase2 = not phase1

        already_planned = ', '.join(set([m['titel'] for m in plan])) if plan else 'keine'
        todays_meals = [m for m in plan if m.get('tag') == tag]
        todays_titles = ', '.join([m['titel'] for m in todays_meals]) if todays_meals else 'keine'

        # Gespeichertes Rezept einplanen: passendes für diesen Slot suchen
        gespeichert_einplanen = None
        if gespeicherte_idx < len(gespeicherte):
            slot_map = {'Frühstück': 'fruehstueck', 'Fruehstueck': 'fruehstueck',
                        'Mittagessen': 'mittagessen', 'Abendessen': 'abendessen', 'Snack': 'snack'}
            slot_key = slot_map.get(mahlzeit_label, '')

            # Suche das erste noch nicht verwendete Rezept das zum Slot passt
            for gi in range(gespeicherte_idx, len(gespeicherte)):
                gr_check = gespeicherte[gi]
                kat_check = json.loads(gr_check.kategorien or '[]')
                # Passt wenn: keine Kategorie gesetzt ODER slot_key in Kategorien
                if not kat_check or not slot_key or slot_key in kat_check:
                    gespeichert_einplanen = gr_check
                    gespeicherte.pop(gi)  # aus Liste entfernen damit es nicht nochmal verwendet wird
                    break

        if gespeichert_einplanen:
            gr = gespeichert_einplanen
            zutaten = json.loads(gr.zutaten_json)

            # Ernährungseinschränkung prüfen
            fleisch_zutaten = ['hähnchen', 'hühnchen', 'huhn', 'rind', 'hackfleisch', 'schwein', 'lamm', 'kalb', 'turkey', 'truthahn']
            rohes_fleisch = any(any(f in z['name'].lower() for f in fleisch_zutaten) for z in zutaten)
            braucht_ersatz = (ernaehrung in ['vegetarisch', 'vegan'] and rohes_fleisch) or \
                             (ernaehrung == 'kein_rohes_fleisch' and rohes_fleisch)

            if braucht_ersatz:
                ersatz_map = {'vegetarisch': 'Tofu oder Tempeh', 'vegan': 'Tofu oder Tempeh', 'kein_rohes_fleisch': 'TK-Hähnchen (vorgegart) oder Tofu'}
                ersatz = ersatz_map.get(ernaehrung, 'pflanzliche Alternative')
                zutaten = [dict(z, name=ersatz) if any(f in z['name'].lower() for f in fleisch_zutaten) else z for z in zutaten]
                titel = gr.titel + f' (mit {ersatz})'
            else:
                titel = gr.titel
                braucht_ersatz = False

            rezept = {
                'titel': titel, 'beschreibung': gr.beschreibung or '',
                'zutaten': zutaten, 'zubereitung': gr.zubereitung or '',
                'zeit': '-', 'tag': tag, 'mahlzeit': mahlzeit_label,
                'quelle': 'gespeichert', 'naehrstoffe': {}, 'ersatz': braucht_ersatz
            }
            plan.append(rezept)
            for zutat in zutaten:
                zn = zutat['name'].lower()
                for inv_item in list(virtual_inventory):
                    if inv_item['name'].lower() == zn:
                        virtual_inventory.remove(inv_item)
                        if inv_item['name'] in soon_names:
                            soon_names.remove(inv_item['name'])
                        break
            continue

        try:
            if phase2:
                # Phase 2: Freie Planung - abwechslungsreich, ausgewogen, budget-bewusst
                budget_pro_mahlzeit = (budget / total) if budget > 0 else 0
                inv_rest = ', '.join([f"{x['menge']} {x['name']}" for x in virtual_inventory]) if virtual_inventory else 'nichts mehr'
                is_snack = mahlzeit_label == 'Snack'

                extra_constraints = '\n'.join(filter(None, [
                    mag_nicht_text,
                    mag_text,
                    tools_text,
                    tools_verboten
                ]))

                if is_snack:
                    snack_budget_info = ''
                    if snack_budget_typ == 'eigenes' and snack_budget_val > 0:
                        snack_budget_info = f'Snack-Budget pro Tag: ca. {snack_budget_val/tage:.2f} €'
                    elif snack_budget_typ == 'im_budget':
                        snack_budget_info = f'Snack-Budget: Teil des Gesamtbudgets ({budget_pro_mahlzeit:.2f} € pro Slot)'
                    else:
                        snack_budget_info = 'Kein Budget-Tracking für Snacks'

                    response = client.chat.completions.create(
                        model='gpt-4o', max_tokens=600,
                        messages=[
                            {"role": "system", "content": f"""Du planst einen gesunden Snack für eine Person in Deutschland.
ERNÄHRUNG: {ernaehrung_text}
{extra_constraints}
Generiere GENAU 1 Snack-Vorschlag als JSON.
- Gesund, sättigend, einfach zuzubereiten
- Wenn möglich Obst einbauen (Apfel, Banane, Beeren, etc.)
- Nur bekannte, alltagstaugliche Snacks - keine seltsamen Kombinationen
- Kein Kochen nödig oder max. 5 Min
- Korrekte deutsche Umlaute, NUR JSON
Format: {{"titel":"Name","zeit":"2 Min","beschreibung":"Kurz","zutaten":[{{"name":"Apfel","menge":"1 Stück","kaufen":true}}],"zubereitung":"Kurz","naehrstoffe":{{"kalorien":150,"protein":3,"kohlenhydrate":25,"fett":2}}}}"""},
                            {"role": "user", "content": f"""Inventar (kostenlos): {inv_rest}
{snack_budget_info}
Bereits heute geplant: {todays_titles}
Snack für Tag {tag}. Einfach, gesund, mit Obst wenn möglich."""}
                        ]
                    )
                else:
                    # Meal Prep Hinweis
                    meal_prep_hinweis = ""
                    if meal_prep and mahlzeit_label == 'Abendessen':
                        meal_prep_hinweis = "\nMEAL PREP: Dieses Abendessen wird auch morgen als Mittagessen gegessen. Zutaten für GENAU 2 Portionen angeben."

                    # Bereits verplante Zutaten aus dem Plan
                    verplante_zutaten = set()
                    for m in plan:
                        for z in m.get('zutaten', []):
                            if z.get('kaufen', False):
                                verplante_zutaten.add(z['name'].lower())

                    # Cuisines rotieren
                    used_cuisines = [m.get('kueche', '') for m in plan if m.get('kueche')]
                    next_cuisine = ''
                    if cuisines:
                        unused = [c for c in cuisines if c not in used_cuisines]
                        next_cuisine = unused[0] if unused else cuisines[i % len(cuisines)]

                    response = client.chat.completions.create(
                        model='gpt-4o', max_tokens=900,
                        messages=[
                            {"role": "system", "content": phase2_system_prompt},
                            {"role": "user", "content": (
                                f"Inventar (kostenlos nutzbar): {inv_rest}\n"
                                f"Budget pro Mahlzeit: {f'ca. {budget_pro_mahlzeit:.2f} EUR' if budget_pro_mahlzeit > 0 else 'guenstig kochen'}\n"
                                f"Heute geplant: {todays_titles}\n"
                                f"Alle bisher geplanten Gerichte (NICHT wiederholen): {already_planned}\n"
                                f"Kuechen bisher: {', '.join(used_cuisines) if used_cuisines else 'keine'}\n"
                                f"Mahlzeit: Tag {tag} von {tage}, {mahlzeit_label}{meal_prep_hinweis}\n"
                                f"{f'Bevorzugte Kueche: {next_cuisine}' if next_cuisine else ''}\n"
                                "Realistische Portionsgroesse. Nur Zutaten kombinieren die kulinarisch zusammenpassen."
                            )}
                        ]
                    )
            else:
                # Phase 1: Nur Inventar verwenden, dringendes zuerst
                # Originale Mengen aus DB verwenden, nicht "wenig übrig" aus virtualem Inventar
                orig_mengen = {i.name.lower(): i.menge for i in items}
                def clean_menge(item):
                    orig = orig_mengen.get(item['name'].lower(), item['menge'])
                    if orig.lower().startswith('wenig') or orig.lower().startswith('ca. hälfte'):
                        return item['menge']  # fallback
                    return orig

                inv_parts = []
                if soon: inv_parts.append('DRINGEND: ' + ', '.join(f"{clean_menge(x)} {x['name']}" for x in soon))
                if week: inv_parts.append('Diese Woche: ' + ', '.join(f"{clean_menge(x)} {x['name']}" for x in week))
                if later: inv_parts.append('Länger haltbar: ' + ', '.join(f"{clean_menge(x)} {x['name']}" for x in later))

                urgency_instruction = ''
                if soon and budget > 0:
                    urgency_instruction = f'\nWICHTIG: MUSS dringende Zutat verwenden: {", ".join(soon_names)}'
                elif soon:
                    urgency_instruction = f'\nBevorzuge dringende Zutaten: {", ".join(soon_names)}'

                kein_einkauf_hinweis = "\nKEIN EINKAUF: Verwende ausschließlich Zutaten aus dem Inventar. Keine neuen Zutaten kaufen." if budget == 0 else ""

                response = client.chat.completions.create(
                    model='gpt-4o', max_tokens=800,
                    messages=[
                        {"role": "system", "content": phase1_system_prompt},
                                                {"role": "user", "content": f"Verfügbares Inventar:\n{chr(10).join(inv_parts)}\n\nBereits geplant: {already_planned}\nTag {tag} von {tage}, {mahlzeit_label}{urgency_instruction}{kein_einkauf_hinweis}"}
                    ]
                )

            text = response.choices[0].message.content.strip()
            # Bereinigen: Markdown Backticks, führende/trailing Whitespace
            text = text.replace('```json', '').replace('```', '').strip()
            # Falls die KI Text vor dem JSON schreibt, JSON-Block extrahieren
            if not text.startswith('{'):
                import re as re2
                json_match = re2.search(r'\{.*\}', text, re2.DOTALL)
                if json_match:
                    text = json_match.group(0)
            try:
                rezept = json.loads(text)
            except json.JSONDecodeError as je:
                print(f"JSON Parse Error: {je}\nText: {text[:200]}")
                # Fallback: einfaches Rezept generieren
                rezept = {
                    'titel': 'Einfaches Gericht',
                    'beschreibung': 'Konnte nicht generiert werden',
                    'zutaten': [],
                    'zubereitung': '',
                    'naehrstoffe': {}
                }

            # Post-Processing: unrealistische Mengen korrigieren
            for z in rezept.get('zutaten', []):
                menge = z.get('menge', '')
                # Regex für Mengen > 500g Getreide/Reis/Nudeln für 1 Person
                import re
                m = re.search(r'(\d+)\s*(?:g|Gramm)', menge, re.IGNORECASE)
                if m:
                    gramm = int(m.group(1))
                    name_lower = z.get('name', '').lower()
                    if gramm > 300 and any(w in name_lower for w in ['reis', 'nudel', 'pasta', 'mehl', 'hafer', 'linsen', 'bohnen']):
                        z['menge'] = menge.replace(m.group(0), f'{min(gramm, 150)}g')
                    elif gramm > 400 and any(w in name_lower for w in ['gemüse', 'spinat', 'brokkoli', 'karott', 'zucchini']):
                        z['menge'] = menge.replace(m.group(0), f'{min(gramm, 200)}g')
                # kg -> g wenn > 0.5 kg für Einzelzutaten
                m_kg = re.search(r'(\d+(?:[.,]\d+)?)\s*kg', menge, re.IGNORECASE)
                if m_kg:
                    kg = float(m_kg.group(1).replace(',', '.'))
                    if kg > 0.3:
                        z['menge'] = menge.replace(m_kg.group(0), f'{int(kg * 1000 * 0.15)}g')
            rezept['tag'] = tag
            rezept['mahlzeit'] = mahlzeit_label
            rezept['quelle'] = 'ki'
            rezept['phase'] = 2 if phase2 else 1

            # Meal Prep: Makros auf "pro Portion" normieren (KI gibt 2 Portionen an)
            if meal_prep and mahlzeit_label == 'Abendessen':
                nw = rezept.get('naehrstoffe', {})
                if nw and any(nw.get(k) for k in ['kalorien', 'protein', 'kohlenhydrate', 'fett']):
                    rezept['naehrstoffe'] = {
                        'kalorien': round((nw.get('kalorien') or 0) / 2),
                        'protein': round((nw.get('protein') or 0) / 2),
                        'kohlenhydrate': round((nw.get('kohlenhydrate') or 0) / 2),
                        'fett': round((nw.get('fett') or 0) / 2),
                    }

            plan.append(rezept)

            for zutat in rezept.get('zutaten', []):
                zn = zutat['name'].lower()
                zm = zutat.get('menge', '').lower()
                if zutat.get('kaufen', False):
                    continue  # Neue Zutat - nicht im Inventar
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
                            inv_item['menge'] = 'wenig übrig'
                            inv_item['urgency'] = 'soon'
                            if inv_item['name'] in soon_names:
                                soon_names.remove(inv_item['name'])
                        break
        except Exception as e:
            plan.append({'tag': tag, 'mahlzeit': mahlzeit_label, 'titel': 'Fehler', 'beschreibung': str(e), 'zutaten': [], 'zubereitung': '', 'quelle': 'ki'})

    # Snacks generieren (separater Loop)
    if snacks_aktiv:
        already_snacks = []
        inv_names_lower = {i.name.lower() for i in items}
        for tag in range(1, tage + 1):
            inv_rest = ', '.join([f"{x['menge']} {x['name']}" for x in virtual_inventory]) if virtual_inventory else 'nichts'
            snack_budget_info = ''
            if snack_budget_typ == 'eigenes' and snack_budget_val > 0:
                snack_budget_info = f'Budget: ca. {snack_budget_val/tage:.2f} €'
            elif snack_budget_typ == 'im_budget' and budget > 0:
                snack_budget_info = f'Budget: ca. {budget/(tage*(mahlzeiten_pro_tag+1)):.2f} €'
            try:
                response = client.chat.completions.create(
                    model='gpt-4o', max_tokens=500,
                    messages=[
                        {"role": "system", "content": snack_system_prompt},
                        {"role": "user", "content": f"Inventar (kaufen:false): {inv_rest}\n{snack_budget_info}\nBisherige Snacks: {', '.join(already_snacks)}\nSnack fuer Tag {tag}."}
                    ]
                )
                text = response.choices[0].message.content.replace('```json','').replace('```','').strip()
                if not text.startswith('{'):
                    import re as re3
                    jm = re3.search(r'\{.*\}', text, re3.DOTALL)
                    if jm: text = jm.group(0)
                try:
                    snack = json.loads(text)
                except json.JSONDecodeError:
                    snack = {'titel': 'Snack', 'beschreibung': '', 'zutaten': [], 'zubereitung': '', 'naehrstoffe': {}}
                # kaufen-Flag nachkorrigieren basierend auf Inventar
                for z in snack.get('zutaten', []):
                    if z['name'].lower() in inv_names_lower:
                        z['kaufen'] = False
                snack['tag'] = tag
                snack['mahlzeit'] = 'Snack'
                snack['quelle'] = 'ki'
                snack['phase'] = 2
                plan.append(snack)
                already_snacks.append(snack.get('titel',''))
            except Exception as e:
                plan.append({'tag': tag, 'mahlzeit': 'Snack', 'titel': 'Snack', 'beschreibung': str(e), 'zutaten': [], 'zubereitung': '', 'quelle': 'ki', 'phase': 2})

    # Einkaufsliste: serverseitig berechnen, KI nur für Preise und Extras
    plan_ohne_meal_prep = [m for m in plan if m.get('quelle') != 'meal_prep']

    import re as re_m

    def parse_g(s):
        """Zahl aus Mengenstring extrahieren (in Gramm/Stück normiert)."""
        if not s: return None
        s = s.lower().strip()
        m = re_m.search(r'([\d.,]+)\s*kg', s)
        if m: return float(m.group(1).replace(',','.')) * 1000
        m = re_m.search(r'([\d.,]+)\s*g\b', s)
        if m: return float(m.group(1).replace(',','.'))
        m = re_m.search(r'([\d.,]+)\s*ml', s)
        if m: return float(m.group(1).replace(',','.'))
        m = re_m.search(r'([\d.,]+)\s*l\b', s)
        if m: return float(m.group(1).replace(',','.')) * 1000
        m = re_m.search(r'([\d.,]+)\s*st[üu]ck', s)
        if m: return float(m.group(1).replace(',','.'))
        m = re_m.search(r'^([\d.,]+)$', s.strip())
        if m: return float(m.group(1).replace(',','.'))
        return None

    # Bedarf pro Zutat summieren
    bedarf = {}  # name.lower -> {name, kaufen_immer, gramm_gesamt, mengen[]}
    for m in plan_ohne_meal_prep:
        for z in m.get('zutaten', []):
            zn = z['name'].lower()
            if zn not in bedarf:
                bedarf[zn] = {'name': z['name'], 'kaufen_immer': z.get('kaufen', False), 'gramm': 0, 'mengen': []}
            bedarf[zn]['mengen'].append(z.get('menge', ''))
            g = parse_g(z.get('menge', ''))
            if g: bedarf[zn]['gramm'] += g
            if z.get('kaufen', False): bedarf[zn]['kaufen_immer'] = True

    # Inventar-Map
    inv_map = {i.name.lower(): {'menge': i.menge, 'gramm': parse_g(i.menge)} for i in items}

    # Was muss wirklich gekauft werden?
    muss_kaufen = []  # [{name, menge_rezept, fehlend_gramm}]
    for zn, info in bedarf.items():
        if info['kaufen_immer']:
            muss_kaufen.append({'name': info['name'], 'mengen': info['mengen'], 'fehlend': info['gramm']})
            continue
        inv = inv_map.get(zn)
        if not inv:
            # Nicht im Inventar
            muss_kaufen.append({'name': info['name'], 'mengen': info['mengen'], 'fehlend': info['gramm']})
        elif inv['gramm'] is not None and info['gramm'] > 0:
            if info['gramm'] > inv['gramm'] * 1.05:  # 5% Toleranz
                fehlend = info['gramm'] - inv['gramm']
                muss_kaufen.append({'name': info['name'], 'mengen': info['mengen'], 'fehlend': fehlend})
            # else: ausreichend vorhanden
        # else: Mengen nicht parsierbar -> kaufen_immer Flag entscheidet

    # Grundzutaten die man immer zuhause hat – nie kaufen
    grundzutaten = {'salz', 'pfeffer', 'öl', 'oel', 'olivenöl', 'olivenoel', 'zucker', 'wasser',
                    'butter', 'mehl', 'backpulver', 'natron', 'essig', 'senf', 'ketchup',
                    'speiseöl', 'sonnenblumenöl', 'rapsöl', 'pflanzenöl'}
    muss_kaufen = [f for f in muss_kaufen
                   if not any(g in f['name'].lower() for g in grundzutaten)]
    fehlend_fuer_ki = '\n'.join([
        f"- {f['name']} (benoetigt: {', '.join(f['mengen'])})"
        for f in muss_kaufen
    ]) or 'Keine'

    budget_text = f"Budget: {budget:.2f} EUR" if budget > 0 else "Kein Budget"

    einkauf_system_prompt = (
        "Du bist Preisschaetzer fuer Deutschland (REWE). Antworte NUR mit validem JSON.\n"
        "Du bekommst eine Liste von Zutaten die eingekauft werden MUESSEN.\n"
        "Deine Aufgaben:\n"
        "1. Fuer jede Zutat: realistische REWE-Packungsgroesse und Preis angeben\n"
        "2. Kategorie zuordnen: Obst & Gemuese, Kuehlregal, Tiefkuehl, Brot & Backwaren, Trockenwaren, Getraenke, Sonstiges\n"
        "3. 2-3 optionale Extra-Zutaten vorschlagen die konkrete Rezepte aufwerten\n"
        "Packungsgroessen: Eier=6er Packung, Milch=1L, Mehl/Nudeln=500g, Joghurt=500g, Kaese=150-200g, Fleisch=400g\n"
        'Format: {"einkaufsliste":{"Kuehlregal":[{"name":"Eier","menge":"6 Stueck (1 Packung)","preis_ca":1.99,"typ":"fehlend"}]},'
        '"extra_zutaten":[{"name":"Parmesan","menge":"100g","preis_ca":2.49,"grund":"Aufwertung","rezept":"Pasta","kategorie":"Kuehlregal","naehrstoffe_zusatz":"+8g Protein"}],'
        '"budget_verwendet":5.00,"budget_gesamt":20.00}'
    )

    einkaufsliste = {}
    extra_zutaten = []
    budget_verwendet = 0

    try:
        response = client.chat.completions.create(
            model='gpt-4o', max_tokens=1200,
            messages=[
                {"role": "system", "content": einkauf_system_prompt},
                {"role": "user", "content": (
                    f"Folgende Zutaten MUESSEN gekauft werden:\n{fehlend_fuer_ki}\n\n"
                    f"Geplante Rezepte: {', '.join(set(m['titel'] for m in plan_ohne_meal_prep))}\n"
                    f"{budget_text}\n"
                    "Bitte Packungsgroesse und REWE-Preis fuer jede Zutat angeben."
                )}
            ]
        )
        text = response.choices[0].message.content.replace('```json', '').replace('```', '').strip()
        if not text.startswith('{'):
            import re as re4
            jm = re4.search(r'\{.*\}', text, re4.DOTALL)
            if jm: text = jm.group(0)
        try:
            einkauf_data = json.loads(text)
        except json.JSONDecodeError:
            einkauf_data = {}
        einkaufsliste = einkauf_data.get('einkaufsliste', {})
        raw_extra = einkauf_data.get('extra_zutaten', [])
        # Extra-Zutaten filtern: nichts vorschlagen was bereits im Inventar ist
        inv_namen = {i.name.lower() for i in items}
        extra_zutaten = [
            e for e in raw_extra
            if e.get('name', '').lower() not in inv_namen
        ]
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
        'budget': budget, 'budget_verwendet': budget_verwendet,
        'budget_warnung': budget_warnung,
        'alle_kaufen_zutaten': [
            {'name': z['name'], 'menge': z.get('menge', ''), 'rezept': m['titel']}
            for m in plan for z in m.get('zutaten', []) if z.get('kaufen', False)
        ]
    })

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(port=port, host='0.0.0.0', debug=False)