from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
from openai import OpenAI
import json

app = Flask(__name__)
CORS(app, origins="*", allow_headers=["Content-Type"], methods=["POST", "OPTIONS"])

@app.route('/')
def index():
    return send_from_directory(os.path.dirname(os.path.abspath(__file__)), 'index.html')

@app.after_request
def after_request(response):
    response.headers.add('Access-Control-Allow-Origin', '*')
    response.headers.add('Access-Control-Allow-Headers', 'Content-Type')
    response.headers.add('Access-Control-Allow-Methods', 'POST, OPTIONS')
    return response

@app.route('/rezepte', methods=['POST', 'OPTIONS'])
def rezepte():
    if request.method == 'OPTIONS':
        return jsonify({'ok': True}), 200

    data = request.json
    api_key = data.get('api_key')
    inventory_text = data.get('inventory_text')

    if not api_key or not inventory_text:
        return jsonify({'error': 'api_key und inventory_text erforderlich'}), 400

    client = OpenAI(api_key=api_key)

    system_prompt = """Du bist ein Küchenchef der für eine einzelne Person kocht.
Generiere genau 3 leckere Rezeptvorschläge basierend auf dem Inventar.
Wichtig:
- Priorisiere Zutaten die bald weg müssen
- Mengen in natürlichen Einheiten (nicht Gramm): "die Hälfte der Tüte Spinat", "2 von den 6 Eiern"
- Rezepte müssen realistisch und wirklich lecker sein
- Antworte NUR mit validem JSON Array, kein Text davor oder danach

Format:
[{"titel":"Name","zeit":"20 Min","beschreibung":"Kurze appetitliche Beschreibung","verwendet_dringend":true,"zutaten":[{"name":"Spinat","menge":"die ganze Tüte"}],"zubereitung":"Kurze Schritte in 2-3 Sätzen"}]"""

    try:
        response = client.chat.completions.create(
            model="gpt-4o",
            max_tokens=1500,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": f"Mein Inventar:\n{inventory_text}\n\nGeneriere 3 leckere Rezepte."}
            ]
        )
        text = response.choices[0].message.content
        text = text.replace('```json', '').replace('```', '').strip()
        recipes = json.loads(text)
        return jsonify({'recipes': recipes})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

import os

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(port=port, host='0.0.0.0', debug=False)
