from flask import Flask, send_from_directory, jsonify
import json
import os

# Set static folder to where the built assets are
app = Flask(__name__, static_folder='frontend/dist')

@app.route('/api/public/organogram_data')
def get_data():
    with open('mock_data.json', 'r') as f:
        return jsonify(json.load(f))

# Serve assets with the correct base path
@app.route('/ad-tree/assets/<path:path>')
def send_assets(path):
    return send_from_directory('frontend/dist/assets', path)

# Serve the specific HTML file for the organogram
@app.route('/organograma')
def serve_organogram():
    return send_from_directory('frontend/dist', 'organograma.html')

if __name__ == '__main__':
    print("Starting mock server on port 5001...")
    app.run(port=5001)
