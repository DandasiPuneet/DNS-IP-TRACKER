from flask import Flask, request, jsonify, render_template
from flask_cors import CORS
import socket
import requests
import sqlite3
from datetime import datetime
import json
import os

app = Flask(__name__, template_folder='templates')
@app.route('/')
CORS(app)

# Database setup
DATABASE = 'dns_lookup_history.db'

def init_db():
    """Initialize the database with the lookup history table"""
    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS lookup_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            domain TEXT NOT NULL,
            ip_address TEXT,
            country TEXT,
            city TEXT,
            region TEXT,
            isp TEXT,
            ttl INTEGER,
            lookup_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    conn.commit()
    conn.close()

def get_dns_info(domain):
    """Get DNS information for a domain"""
    try:
        # Try using dnspython first for TTL info
        try:
            import dns.resolver
            result = dns.resolver.resolve(domain, 'A')
            ip_address = str(result[0])
            ttl = result.ttl
            return {
                'ip_address': ip_address,
                'ttl': ttl,
                'error': None
            }
        except ImportError:
            # Fallback to socket if dnspython not available
            ip_address = socket.gethostbyname(domain)
            return {
                'ip_address': ip_address,
                'ttl': 300,  # Default TTL when dnspython not available
                'error': None
            }
    except Exception as e:
        return {
            'ip_address': None,
            'ttl': None,
            'error': str(e)
        }

def get_geo_info(ip_address):
    """Get geographical information for an IP address"""
    try:
        # Using ipapi.co for geolocation (free tier)
        response = requests.get(f'https://ipapi.co/{ip_address}/json/', timeout=10)
        
        if response.status_code == 200:
            data = response.json()
            return {
                'country': data.get('country_name', 'Unknown'),
                'city': data.get('city', 'Unknown'),
                'region': data.get('region', 'Unknown'),
                'isp': data.get('org', 'Unknown'),
                'error': None
            }
        else:
            return {
                'country': 'Unknown',
                'city': 'Unknown',
                'region': 'Unknown',
                'isp': 'Unknown',
                'error': 'Geolocation service unavailable'
            }
    except Exception as e:
        return {
            'country': 'Unknown',
            'city': 'Unknown',
            'region': 'Unknown',
            'isp': 'Unknown',
            'error': str(e)
        }

def save_lookup_history(domain, dns_info, geo_info):
    """Save lookup result to database"""
    try:
        conn = sqlite3.connect(DATABASE)
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO lookup_history 
            (domain, ip_address, country, city, region, isp, ttl)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (
            domain,
            dns_info.get('ip_address'),
            geo_info.get('country'),
            geo_info.get('city'),
            geo_info.get('region'),
            geo_info.get('isp'),
            dns_info.get('ttl')
        ))
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        print(f"Error saving to database: {e}")
        return False

@app.route('/')
def index():
    """Serve the main HTML page"""
    return render_template('index.html')

@app.route('/api/lookup', methods=['POST'])
def dns_lookup():
    """API endpoint for DNS lookup"""
    try:
        data = request.get_json()
        domain = data.get('domain', '').strip().lower()
        
        if not domain:
            return jsonify({'error': 'Domain name is required'}), 400
        
        # Remove protocol if present
        domain = domain.replace('http://', '').replace('https://', '').split('/')[0]
        
        # Get DNS information
        dns_info = get_dns_info(domain)
        
        if dns_info['error']:
            return jsonify({
                'error': f'DNS lookup failed: {dns_info["error"]}',
                'domain': domain
            }), 400
        
        # Get geolocation information
        geo_info = get_geo_info(dns_info['ip_address'])
        
        # Prepare response
        result = {
            'domain': domain,
            'ip_address': dns_info['ip_address'],
            'ttl': dns_info['ttl'],
            'country': geo_info['country'],
            'city': geo_info['city'],
            'region': geo_info['region'],
            'isp': geo_info['isp'],
            'lookup_time': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        }
        
        # Save to database
        save_lookup_history(domain, dns_info, geo_info)
        
        return jsonify(result)
        
    except Exception as e:
        return jsonify({'error': f'Server error: {str(e)}'}), 500

@app.route('/api/history', methods=['GET'])
def get_history():
    """API endpoint to get lookup history"""
    try:
        limit = request.args.get('limit', 50, type=int)
        
        conn = sqlite3.connect(DATABASE)
        cursor = conn.cursor()
        cursor.execute('''
            SELECT domain, ip_address, country, city, region, isp, ttl, lookup_time
            FROM lookup_history
            ORDER BY lookup_time DESC
            LIMIT ?
        ''', (limit,))
        
        rows = cursor.fetchall()
        conn.close()
        
        history = []
        for row in rows:
            history.append({
                'domain': row[0],
                'ip_address': row[1],
                'country': row[2],
                'city': row[3],
                'region': row[4],
                'isp': row[5],
                'ttl': row[6],
                'lookup_time': row[7]
            })
        
        return jsonify({'history': history})
        
    except Exception as e:
        return jsonify({'error': f'Failed to retrieve history: {str(e)}'}), 500

@app.route('/api/domain/<domain_name>')
def get_domain_info(domain_name):
    """API endpoint to get domain info in JSON format"""
    try:
        domain = domain_name.strip().lower()
        domain = domain.replace('http://', '').replace('https://', '').split('/')[0]
        
        # Get DNS information
        dns_info = get_dns_info(domain)
        
        if dns_info['error']:
            return jsonify({
                'error': f'DNS lookup failed: {dns_info["error"]}',
                'domain': domain
            }), 400
        
        # Get geolocation information
        geo_info = get_geo_info(dns_info['ip_address'])
        
        # Prepare response
        result = {
            'domain': domain,
            'ip_address': dns_info['ip_address'],
            'ttl': dns_info['ttl'],
            'location': {
                'country': geo_info['country'],
                'city': geo_info['city'],
                'region': geo_info['region']
            },
            'isp': geo_info['isp'],
            'lookup_time': datetime.now().strftime('%Y-%m-%d %H:%M:%S UTC')
        }
        
        # Save to database
        save_lookup_history(domain, dns_info, geo_info)
        
        return jsonify(result)
        
    except Exception as e:
        return jsonify({'error': f'Server error: {str(e)}'}), 500

if __name__ == '__main__':
    # Create templates directory if it doesn't exist
    os.makedirs('templates', exist_ok=True)
    
    # Initialize database
    init_db()
    
    # Run the app
    port = int(os.environ.get('PORT', 5000))

    app.run(debug=True, host='0.0.0.0', port=5000)

