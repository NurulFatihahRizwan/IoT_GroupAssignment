# ISS Tracker Dashboard

Real-time International Space Station orbital tracking system with interactive visualizations.

## Features

- 🛰️ Live ISS position tracking on interactive map
- 📊 Real-time charts for latitude, longitude, and altitude
- 📍 User geolocation
- ⏯️ Playback controls for historical data
- 📈 3-day orbital data with pagination
- 🌍 Dark-themed space UI

## Deployment on Render

1. Push this repository to GitHub
2. Create a new Web Service on Render
3. Connect your GitHub repository
4. Render will automatically detect the requirements and deploy

## Local Development
```bash
pip install -r requirements.txt
python server.py
```

Then open http://localhost:10000 in your browser.

## API Endpoints

- `GET /` - Main dashboard
- `GET /api/last3days` - Last 3 days of ISS position data
- `GET /api/current` - Current ISS position

## Technologies

- Backend: Flask (Python)
- Frontend: HTML, CSS, JavaScript
- Maps: Leaflet.js
- Charts: Chart.js
- ISS Data: Open Notify API
