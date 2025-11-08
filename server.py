# server.py
from flask import Flask, jsonify, send_file
from flask_cors import CORS
import requests
from datetime import datetime, timedelta
import threading
import sqlite3
import time
import os

app = Flask(__name__)
CORS(app)

DB_NAME = 'iss_data.db'
UPDATE_INTERVAL = 5  # seconds
MAX_DAYS = 3  # keep 3 days of data

# ------------------ DATABASE ------------------ #
def init_database():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS iss_positions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            latitude REAL NOT NULL,
            longitude REAL NOT NULL,
            altitude REAL NOT NULL,
            velocity REAL,
            timestamp TEXT NOT NULL,
            day TEXT NOT NULL,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_timestamp ON iss_positions(timestamp)')
    conn.commit()
    conn.close()
    print("✓ Database initialized")

def fetch_iss_position():
    try:
        url = 'https://api.wheretheiss.at/v1/satellites/25544'
        r = requests.get(url, timeout=5)
        r.raise_for_status()
        data = r.json()
        timestamp = datetime.utcfromtimestamp(data['timestamp'])
        return {
            'latitude': float(data['latitude']),
            'longitude': float(data['longitude']),
            'altitude': float(data.get('altitude', 408.0)),  # km
            'velocity': float(data.get('velocity', 0.0)),    # km/h
            'timestamp': timestamp.strftime('%Y-%m-%d %H:%M:%S'),
            'day': timestamp.strftime('%Y-%m-%d')
        }
    except Exception as e:
        print(f"Error fetching ISS position: {e}")
        return None

def save_to_database(position):
    try:
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO iss_positions (latitude, longitude, altitude, velocity, timestamp, day)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (position['latitude'], position['longitude'], position['altitude'], position['velocity'], position['timestamp'], position['day']))
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        print(f"Error saving to database: {e}")
        return False

def cleanup_old_data():
    try:
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        cutoff = (datetime.utcnow() - timedelta(days=MAX_DAYS)).strftime('%Y-%m-%d %H:%M:%S')
        cursor.execute('DELETE FROM iss_positions WHERE timestamp < ?', (cutoff,))
        deleted = cursor.rowcount
        conn.commit()
        conn.close()
        if deleted > 0:
            print(f"✓ Cleaned up {deleted} old records")
    except Exception as e:
        print(f"Error cleaning up old data: {e}")

# ------------------ BACKGROUND UPDATER ------------------ #
def background_update():
    while True:
        pos = fetch_iss_position()
        if pos:
            save_to_database(pos)
        cleanup_old_data()
        time.sleep(UPDATE_INTERVAL)

# ------------------ API ROUTES ------------------ #
@app.route('/')
def index():
    return send_file('index.html')

@app.route('/api/live')
def get_live():
    try:
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        cursor.execute('SELECT latitude, longitude, altitude, velocity, timestamp FROM iss_positions ORDER BY timestamp DESC LIMIT 1')
        row = cursor.fetchone()
        conn.close()
        if row:
            return jsonify({
                'latitude': row[0],
                'longitude': row[1],
                'altitude': row[2],
                'velocity': row[3],
                'timestamp': row[4]
            })
        else:
            return jsonify({'error': 'No data available'}), 404
    except Exception as e:
        print(f"Error fetching live data: {e}")
        return jsonify({'error': 'Unable to fetch data'}), 500

@app.route('/api/all')
def get_all_records():
    try:
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        cursor.execute('SELECT latitude, longitude, altitude, velocity, timestamp FROM iss_positions ORDER BY timestamp DESC')
        rows = cursor.fetchall()
        conn.close()
        data = [{
            'latitude': r[0],
            'longitude': r[1],
            'altitude': r[2],
            'velocity': r[3],
            'ts_utc': r[4]
        } for r in rows]
        return jsonify(data)
    except Exception as e:
        print(f"Error fetching all records: {e}")
        return jsonify({'error': 'Unable to fetch data'}), 500

@app.route('/api/stats')
def get_stats():
    try:
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        cursor.execute('SELECT COUNT(*) FROM iss_positions')
        total_count = cursor.fetchone()[0]
        conn.close()
        total_hours = total_count * UPDATE_INTERVAL / 3600
        total_days = total_hours / 24
        return jsonify({'total_records': total_count, 'total_hours': round(total_hours,2), 'total_days': round(total_days,2)})
    except Exception as e:
        print(f"Error fetching stats: {e}")
        return jsonify({'error': 'Unable to fetch stats'}), 500

# ------------------ START ------------------ #
if __name__ == '__main__':
    init_database()
    threading.Thread(target=background_update, daemon=True).start()
    port = int(os.environ.get('PORT', 10000))
    app.run(host='0.0.0.0', port=port, debug=False)

