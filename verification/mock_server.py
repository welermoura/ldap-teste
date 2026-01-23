from flask import Flask, send_from_directory, jsonify
import os

app = Flask(__name__, static_folder='../frontend/dist')

# Mock Data: Asymmetric Tree
# Left: Small Leaf
# Center: Small Leaf
# Right: HUGE Branch (forces parent to shift right)
MOCK_DATA = [
    {
        "distinguishedName": "CN=CEO",
        "name": "Roberto CEO",
        "title": "CEO",
        "children": [
            { "distinguishedName": "CN=Leaf1", "name": "Leaf One", "title": "Leaf 1", "children": [] },
            { "distinguishedName": "CN=Leaf2", "name": "Leaf Two", "title": "Leaf 2", "children": [] },
            {
                "distinguishedName": "CN=HugeBranch",
                "name": "Huge Branch",
                "title": "VP Big",
                "children": [
                    # Many children to make this node wide
                    { "distinguishedName": f"CN=Sub{i}", "name": f"Sub {i}", "title": "Sub", "children": [] }
                    for i in range(1, 6) # 5 Children forces width
                ]
            }
        ]
    }
]

@app.route('/organograma')
def serve_organograma():
    return send_from_directory('../frontend/dist', 'organograma.html')

@app.route('/ad-tree/assets/<path:path>')
def serve_assets(path):
    return send_from_directory('../frontend/dist/assets', path)

@app.route('/ad-tree/vite.svg')
def serve_svg():
    return send_from_directory('../frontend/dist', 'vite.svg')

@app.route('/api/public/organogram_data')
def get_data():
    return jsonify(MOCK_DATA)

if __name__ == '__main__':
    print("Starting Mock Server on port 5001...")
    app.run(port=5001)
