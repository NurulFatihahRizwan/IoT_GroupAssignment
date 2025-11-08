from flask import Flask, jsonify, send_file, request
from flask_cors import CORS
import requests
from datetime import datetime, timedelta
import time
import threading
import sqlite3

app = Flask(__name__)
CORS(app)

DB_NAME = 'iss_data.db'
UPDATE_INTERVAL = 1  # 1 second
MAX_DAYS = 3  # Keep 3 days of data

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
        response = requests.get('http://api.open-notify.org/iss-now.json', timeout=5)
        data = response.json()
        if data['message'] == 'success':
            timestamp = datetime.utcfromtimestamp(int(data['timestamp']))
            position = data['iss_position']
            return {
                'latitude': float(position['latitude']),
                'longitude': float(position['longitude']),
                'altitude': 408.0,
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
            INSERT INTO iss_positions (latitude, longitude, altitude, timestamp, day)
            VALUES (?, ?, ?, ?, ?)
        ''', (position['latitude'], position['longitude'], position['altitude'], position['timestamp'], position['day']))
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
        cutoff_date = (datetime.utcnow() - timedelta(days=MAX_DAYS)).strftime('%Y-%m-%d %H:%M:%S')
        cursor.execute('DELETE FROM iss_positions WHERE timestamp < ?', (cutoff_date,))
        deleted = cursor.rowcount
        conn.commit()
        conn.close()
        if deleted > 0:
            print(f"✓ Cleaned up {deleted} old records")
    except Exception as e:
        print(f"Error cleaning up old data: {e}")

def get_record_count():
    try:
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        cursor.execute('SELECT COUNT(*) FROM iss_positions')
        count = cursor.fetchone()[0]
        conn.close()
        return count
    except Exception as e:
        print(f"Error getting record count: {e}")
        return 0

def update_historical_data():
    position = fetch_iss_position()
    if position:
        if save_to_database(position):
            record_count = get_record_count()
            if record_count % 3600 == 0:
                hours = record_count / 3600
                days = hours / 24
                print(f"✓ Collected {record_count:,} records ({days:.2f} days of data)")

def background_update():
    cleanup_counter = 0
    while True:
        try:
            update_historical_data()
            cleanup_counter += 1
            if cleanup_counter >= 3600:
                cleanup_old_data()
                cleanup_counter = 0
            time.sleep(UPDATE_INTERVAL)
        except Exception as e:
            print(f"Error in background update: {e}")
            time.sleep(UPDATE_INTERVAL)

# ------------------ API ROUTES ------------------ #
@app.route('/')
def index():
    return send_file('index.html')

@app.route('/api/last3days')
def get_last_3_days():
    try:
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        cursor.execute('SELECT latitude, longitude, altitude, timestamp, day FROM iss_positions ORDER BY timestamp ASC')
        rows = cursor.fetchall()
        conn.close()
        data = [{'latitude': r[0],'longitude': r[1],'altitude': r[2],'ts_utc': r[3],'day': r[4]} for r in rows]
        return jsonify(data)
    except Exception as e:
        print(f"Error fetching data: {e}")
        return jsonify({'error': 'Unable to fetch data'}), 500

@app.route('/api/current')
def get_current():
    try:
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        cursor.execute('SELECT latitude, longitude, altitude, timestamp, day FROM iss_positions ORDER BY timestamp DESC LIMIT 1')
        row = cursor.fetchone()
        conn.close()
        if row:
            return jsonify({'latitude': row[0],'longitude': row[1],'altitude': row[2],'ts_utc': row[3],'day': row[4]})
        return jsonify({'error': 'No data available'}), 404
    except Exception as e:
        print(f"Error fetching current position: {e}")
        return jsonify({'error': 'Unable to fetch position'}), 500

@app.route('/api/stats')
def get_stats():
    try:
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        cursor.execute('SELECT COUNT(*) FROM iss_positions')
        total_count = cursor.fetchone()[0]
        cursor.execute('SELECT day, COUNT(*) as count FROM iss_positions GROUP BY day ORDER BY day DESC')
        day_counts = {row[0]: row[1] for row in cursor.fetchall()}
        conn.close()
        total_hours = total_count / 3600
        total_days = total_hours / 24
        return jsonify({'total_records': total_count,'total_hours': round(total_hours,2),'total_days': round(total_days,2),'records_per_day': day_counts,'collection_rate': f'{UPDATE_INTERVAL} second per request','max_retention_days': MAX_DAYS,'records_per_table_page': 86400})
    except Exception as e:
        print(f"Error getting stats: {e}")
        return jsonify({'error': 'Unable to fetch stats'}), 500

# ------------------ DATABASE VIEWER ------------------ #
@app.route('/database')
def database_view():
    return send_file('database.html')

@app.route('/api/all-records')
def get_all_records():
    try:
        page = request.args.get('page', 1, type=int)
        per_page = request.args.get('per_page', 1000, type=int)
        day_filter = request.args.get('day', None)
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        if day_filter:
            cursor.execute('SELECT latitude, longitude, altitude, timestamp, day, id FROM iss_positions WHERE day = ? ORDER BY timestamp DESC', (day_filter,))
        else:
            cursor.execute('SELECT latitude, longitude, altitude, timestamp, day, id FROM iss_positions ORDER BY timestamp DESC')
        all_rows = cursor.fetchall()
        total_records = len(all_rows)
        start = (page - 1) * per_page
        end = start + per_page
        rows = all_rows[start:end]
        cursor.execute('SELECT DISTINCT day FROM iss_positions ORDER BY day DESC')
        days = [row[0] for row in cursor.fetchall()]
        conn.close()
        data = [{'id': r[5],'latitude': r[0],'longitude': r[1],'altitude': r[2],'ts_utc': r[3],'day': r[4]} for r in rows]
        return jsonify({'records': data,'total': total_records,'page': page,'per_page': per_page,'total_pages': (total_records + per_page - 1)//per_page,'available_days': days})
    except Exception as e:
        print(f"Error fetching all records: {e}")
        return jsonify({'error': 'Unable to fetch records'}), 500

# ------------------ START ------------------ #
if __name__ == '__main__':
    init_database()
    if get_record_count() == 0:
        print("Generating sample data for testing...")
    threading.Thread(target=background_update, daemon=True).start()
    import os
    port = int(os.environ.get('PORT', 10000))
    app.run(host='0.0.0.0', port=port, debug=False)
