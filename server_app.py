import json
import os
import subprocess
from flask import Flask, request, jsonify
from functools import wraps
import jwt
import datetime

# --- KONFIGURASI APLIKASI ---
# Menggunakan nama file config.json yang sama
CONFIG_FILE = 'config.json'
SECRET_KEY = os.urandom(24).hex() # Kunci Rahasia untuk JWT
TOKEN_LIFETIME_SECONDS = 3600 # 1 jam

# Path standar Termux
PREFIX = "/data/data/com.termux/files/usr"
NGINX_CONF_PATH = f"{PREFIX}/etc/nginx/sites-enabled"
NGINX_TEMPLATE_PATH = 'nginx_site_template.conf'

# Services yang didukung (harus sudah diinstal via pkg install)
SUPPORTED_SERVICES = {
    "nginx": f"{PREFIX}/bin/nginx",
    "mariadb": f"{PREFIX}/bin/mysqld_safe",
    "php-fpm": f"{PREFIX}/bin/php-fpm"
}

app = Flask(__name__)

# Memuat Kredensial dan State
try:
    with open(CONFIG_FILE, 'r') as f:
        config = json.load(f)
    USERNAME = config['username']
    PASSWORD = config['password']
    SERVICE_STATE = config.get('initial_services', {})
    print(f"[*] Kredensial dimuat: User '{USERNAME}'")
except FileNotFoundError:
    print(f"[FATAL] File konfigurasi {CONFIG_FILE} tidak ditemukan. Buat file ini terlebih dahulu!")
    exit(1)
except json.JSONDecodeError:
    print(f"[FATAL] Format file {CONFIG_FILE} tidak valid. Periksa JSON Anda.")
    exit(1)

# --- FUNGSI UTILITY ---

def execute_command(command, shell=True, check=False):
    """Menjalankan perintah shell dan mengembalikan output atau error."""
    try:
        # Menambahkan 'bash -c' untuk kompatibilitas Termux yang lebih baik
        result = subprocess.run(['bash', '-c', command],
                                capture_output=True, text=True, check=check,
                                timeout=10)
        output = result.stdout.strip() if result.stdout else ""
        error = result.stderr.strip() if result.stderr else ""
        return output, error, result.returncode
    except subprocess.CalledProcessError as e:
        return "", f"Perintah gagal: {e.stderr.strip()}", 1
    except FileNotFoundError:
        return "", f"Error: Perintah '{command.split()[0]}' tidak ditemukan. Pastikan sudah diinstal.", 1
    except Exception as e:
        return "", f"Error eksekusi tak terduga: {e}", 1

def update_service_state(service, status):
    """Memperbarui state layanan di memori dan config.json."""
    global SERVICE_STATE
    SERVICE_STATE[service] = status
    try:
        config['initial_services'] = SERVICE_STATE
        with open(CONFIG_FILE, 'w') as f:
            json.dump(config, f, indent=4)
    except Exception as e:
        print(f"[WARNING] Gagal menyimpan state layanan ke {CONFIG_FILE}: {e}")

# --- DEKORATOR OTENTIKASI ---

def token_required(f):
    """Dekorator untuk melindungi endpoint dengan JWT."""
    @wraps(f)
    def decorated(*args, **kwargs):
        auth_header = request.headers.get('Authorization')
        if not auth_header:
            return jsonify({'error': 'Token otentikasi hilang!'}), 401
        
        try:
            token = auth_header.split(" ")[1]
            data = jwt.decode(token, SECRET_KEY, algorithms=["HS256"])
            # Anda bisa menambahkan user check di sini jika perlu
        except Exception as e:
            return jsonify({'error': 'Token tidak valid atau kadaluwarsa.'}), 401

        return f(*args, **kwargs)
    return decorated

# --- ENDPOINT OTENTIKASI ---

@app.route('/login', methods=['POST'])
def login():
    data = request.get_json()
    username = data.get('username')
    password = data.get('password')

    if username == USERNAME and password == PASSWORD:
        token = jwt.encode({
            'user': username,
            'exp': datetime.datetime.utcnow() + datetime.timedelta(seconds=TOKEN_LIFETIME_SECONDS)
        }, SECRET_KEY, algorithm="HS256")
        return jsonify({'token': token})
    
    return jsonify({'error': 'Username atau Password salah'}), 401

# --- ENDPOINT UTAMA DASHBOARD ---

@app.route('/status', methods=['POST'])
@token_required
def get_status():
    status_data = {}
    
    # Uptime
    uptime_out, _, _ = execute_command(f"{PREFIX}/bin/uptime -p")
    status_data['uptime'] = uptime_out if uptime_out else "N/A"

    # CPU Usage (menggunakan top dan awk, mungkin tidak akurat di Termux)
    cpu_out, _, _ = execute_command(f"{PREFIX}/bin/top -n 1 -b | grep 'Cpu(s)' | awk '{{print $2 + $4}}'")
    status_data['cpu_usage'] = f"{cpu_out.strip()}%" if cpu_out else "N/A"

    # Memory Usage (menggunakan free)
    mem_out, _, _ = execute_command(f"{PREFIX}/bin/free -h | grep Mem | awk '{{print $3 \" / \" $2}}'")
    status_data['memory'] = f"{mem_out.strip()} Used / Total" if mem_out else "N/A"

    # Service Status Check (status nyata)
    service_status = {}
    for service, path in SUPPORTED_SERVICES.items():
        if service == 'mariadb':
            # Cek Mariadb secara khusus karena menggunakan mysqld_safe
            out, err, code = execute_command(f"{PREFIX}/bin/pgrep mysqld")
            service_status[service] = "Running (PID: " + out.split('\n')[0] + ")" if code == 0 else "Stopped"
        else:
            # Cek service lain menggunakan pgrep
            out, err, code = execute_command(f"{PREFIX}/bin/pgrep {service}")
            service_status[service] = "Running (PID: " + out.split('\n')[0] + ")" if code == 0 else "Stopped"

    status_data['service_status'] = service_status
    return jsonify(status_data)

@app.route('/service_control', methods=['POST'])
@token_required
def service_control():
    data = request.get_json()
    service = data.get('service')
    action = data.get('action') # 'start' atau 'stop'

    if service not in SUPPORTED_SERVICES:
        return jsonify({'error': f"Layanan '{service}' tidak didukung."}), 400

    if action == 'start':
        if service == 'mariadb':
            command = f"{SUPPORTED_SERVICES['mariadb']} &"
        else:
            command = f"{PREFIX}/bin/{service} &"
        
        # Cek apakah sudah berjalan
        out, err, code = execute_command(f"{PREFIX}/bin/pgrep {service}")
        if code == 0:
            return jsonify({'success': False, 'message': f"Layanan {service} sudah berjalan."})

        # Jalankan
        _, err, code = execute_command(command, shell=True)
        
        if code == 0:
            update_service_state(service, "Running")
            return jsonify({'success': True, 'message': f"Layanan {service} berhasil dimulai."})
        else:
            return jsonify({'success': False, 'error': f"Gagal memulai {service}: {err}"}), 500

    elif action == 'stop':
        # Menggunakan pkill untuk menghentikan proses
        _, err, code = execute_command(f"{PREFIX}/bin/pkill {service}", check=False)
        
        if code in [0, 1]: # 0=sukses, 1=tidak ada proses (tidak masalah)
            update_service_state(service, "Stopped")
            return jsonify({'success': True, 'message': f"Layanan {service} berhasil dihentikan."})
        else:
            return jsonify({'success': False, 'error': f"Gagal menghentikan {service}: {err}"}), 500

    return jsonify({'error': 'Aksi tidak valid.'}), 400

# --- ENDPOINT NGINX DAN SQL ---

@app.route('/nginx_deploy', methods=['POST'])
@token_required
def nginx_deploy():
    data = request.get_json()
    host_name = data.get('host_name')
    root_path = data.get('root_path')
    
    if not os.path.exists(NGINX_TEMPLATE_PATH):
        return jsonify({'success': False, 'error': f"Template Nginx tidak ditemukan di {NGINX_TEMPLATE_PATH}"}), 500

    # Baca template dan ganti variabel
    try:
        with open(NGINX_TEMPLATE_PATH, 'r') as f:
            template = f.read()
        
        conf_content = template.replace('$HOST_NAME', host_name).replace('$ROOT_PATH', root_path)
        
        target_file = os.path.join(NGINX_CONF_PATH, f"{host_name}.conf")

        with open(target_file, 'w') as f:
            f.write(conf_content)
            
    except Exception as e:
        return jsonify({'success': False, 'error': f"Gagal menulis file konfigurasi: {e}"}), 500

    # Muat ulang Nginx
    out, err, code = execute_command(f"{PREFIX}/bin/nginx -s reload", check=False)
    
    if code == 0:
        return jsonify({'success': True, 'output': f"File konfigurasi {host_name}.conf berhasil dibuat dan Nginx berhasil dimuat ulang."})
    else:
        # Jika Nginx gagal reload, hapus file yang baru dibuat dan tampilkan error
        os.remove(target_file)
        return jsonify({'success': False, 'error': f"Nginx gagal dimuat ulang. Coba start Nginx. Error: {err}"}), 500

@app.route('/db_cli', methods=['POST'])
@token_required
def db_cli():
    command = request.get_json().get('command')
    
    # Jalankan perintah SQL
    # Kami menggunakan MariaDB client path dari Termux
    
    # Peringatan: Akses CLI database tanpa password root di Termux
    full_command = f'{PREFIX}/bin/mysql -e "{command}"'
    
    out, err, code = execute_command(full_command, check=False)

    if code == 0:
        return jsonify({'success': True, 'output': out})
    else:
        return jsonify({'success': False, 'error': f"Error SQL: {err}"}), 500

# --- ENDPOINT FIREWALL ---

@app.route('/firewall_cli', methods=['POST'])
@token_required
def firewall_cli():
    command = request.get_json().get('command')
    
    # Jalankan perintah iptables
    
    # Pastikan perintah yang dijalankan adalah iptables
    if not command.strip().lower().startswith('iptables'):
        return jsonify({'success': False, 'error': "Perintah harus diawali dengan 'iptables'"}), 400
    
    out, err, code = execute_command(command, check=False)

    if code == 0:
        return jsonify({'success': True, 'output': out})
    else:
        # iptables sering memberikan error jika gagal, penting untuk menampilkan error secara lengkap
        return jsonify({'success': False, 'error': f"Error iptables: {err}"}), 500

if __name__ == '__main__':
    # Pastikan file konfigurasi Nginx ada sebelum memulai
    if not os.path.exists(NGINX_CONF_PATH):
        print(f"[FATAL] Direktori Nginx {NGINX_CONF_PATH} tidak ditemukan. Pastikan Anda sudah menginstal 'pkg install nginx'.")
        exit(1)

    print("\n======================================================================")
    print("  ⚡ XipserCloud PRODUCTION SERVER BERJALAN (Host 0.0.0.0) ⚡  ")
    print(f"  Login: User '{USERNAME}' | Password: (dari config.json)")
    print("======================================================================")
    print(f"  Akses Dashboard di Browser: http://[IP_LOKAL_ANDA]:8080")
    print("  Gunakan 'ip addr' di Termux untuk mengetahui IP Anda.")
    print("----------------------------------------------------------------------")

    # HOST DIUBAH MENJADI '0.0.0.0' agar dapat diakses dari IP lokal (192.168.x.x)
    app.run(host='0.0.0.0', port=8080)