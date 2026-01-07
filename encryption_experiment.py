import mysql.connector
from mysql.connector import Error
import pymongo
import time
import matplotlib.pyplot as plt
import numpy as np
from Crypto.Cipher import AES, PKCS1_OAEP
from Crypto.PublicKey import RSA
from Crypto.Random import get_random_bytes
from faker import Faker

# --- Config ---
SQL_CONFIG = {
    'host': 'localhost',
    'user': 'root',
    'password': '', 
    'database': 'encryption_experiment'
}

MONGO_CONFIG = {
    'host': 'localhost',
    'port': 27017,
    'db_name': 'encryption_experiment_nosql'
}

CHUNK_SIZE = 500 
BATCH_SIZES = [1000, 5000, 10000]

fake = Faker()

# --- Database Management ---

def setup_sql_database():
    """Drops and recreates MySQL tables to ensure a clean state."""
    try:
        # Create DB if missing
        conn = mysql.connector.connect(host=SQL_CONFIG['host'], user=SQL_CONFIG['user'], password=SQL_CONFIG['password'])
        cursor = conn.cursor()
        cursor.execute(f"CREATE DATABASE IF NOT EXISTS {SQL_CONFIG['database']}")
        conn.close()

        # Recreate tables
        conn = mysql.connector.connect(**SQL_CONFIG)
        cursor = conn.cursor()
        
        tables = ['patient_baseline', 'patient_aes', 'patient_hybrid']
        for t in tables:
            cursor.execute(f"DROP TABLE IF EXISTS {t}")

        # 1. Baseline (Plaintext)
        cursor.execute("""
            CREATE TABLE patient_baseline (
                id INT AUTO_INCREMENT PRIMARY KEY,
                name VARCHAR(255), email VARCHAR(255), notes TEXT
            )
        """)
        # 2. AES-Only (Binary Storage)
        cursor.execute("""
            CREATE TABLE patient_aes (
                id INT AUTO_INCREMENT PRIMARY KEY,
                name VARBINARY(512), email VARBINARY(512), notes BLOB
            )
        """)
        # 3. Hybrid (Binary + Encrypted Key Column)
        cursor.execute("""
            CREATE TABLE patient_hybrid (
                id INT AUTO_INCREMENT PRIMARY KEY,
                name VARBINARY(512), email VARBINARY(512), notes BLOB, enc_key VARBINARY(512)
            )
        """)
        conn.close()
    except Error as e:
        print(f"[SQL Setup Error] {e}")

def setup_mongo_database():
    """Drops MongoDB collections to prevent data duplication."""
    try:
        client = pymongo.MongoClient(f"mongodb://{MONGO_CONFIG['host']}:{MONGO_CONFIG['port']}/")
        db = client[MONGO_CONFIG['db_name']]
        
        for col in ['patient_baseline', 'patient_aes', 'patient_hybrid']:
            db[col].drop()
            
        client.close()
    except Exception as e:
        print(f"[Mongo Setup Error] {e}")

def get_sql_storage_size(method):
    """Returns storage size in KB (converts Decimal to float)."""
    try:
        conn = mysql.connector.connect(**SQL_CONFIG)
        cursor = conn.cursor()
        
        if method == 'Baseline':
            query = "SELECT SUM(OCTET_LENGTH(name) + OCTET_LENGTH(email) + OCTET_LENGTH(notes)) FROM patient_baseline"
        elif method == 'AES':
            query = "SELECT SUM(OCTET_LENGTH(name) + OCTET_LENGTH(email) + OCTET_LENGTH(notes)) FROM patient_aes"
        elif method == 'Hybrid':
            query = "SELECT SUM(OCTET_LENGTH(name) + OCTET_LENGTH(email) + OCTET_LENGTH(notes) + OCTET_LENGTH(enc_key)) FROM patient_hybrid"
            
        cursor.execute(query)
        result = cursor.fetchone()
        conn.close()
        
        size = result[0] if result and result[0] else 0
        return float(size) / 1024 
    except:
        return 0.0

def get_mongo_storage_size(collection_name):
    """Returns MongoDB collection size in KB."""
    try:
        client = pymongo.MongoClient(f"mongodb://{MONGO_CONFIG['host']}:{MONGO_CONFIG['port']}/")
        db = client[MONGO_CONFIG['db_name']]
        stats = db.command("collstats", collection_name)
        return float(stats['size']) / 1024 
    except:
        return 0.0

def generate_dummy_data(n):
    data = []
    for _ in range(n):
        # Name, Email, ~50 char Note
        data.append((fake.name(), fake.email(), fake.text(max_nb_chars=50)))
    return data

# --- SQL EXPERIMENTS ---

def run_sql_baseline(data):
    conn = mysql.connector.connect(**SQL_CONFIG)
    cursor = conn.cursor()
    
    # Write
    start = time.time()
    for i in range(0, len(data), CHUNK_SIZE):
        chunk = data[i:i + CHUNK_SIZE]
        cursor.executemany("INSERT INTO patient_baseline (name, email, notes) VALUES (%s, %s, %s)", chunk)
    conn.commit()
    write_ms = (time.time() - start) * 1000
    
    # Read
    start = time.time()
    cursor.execute("SELECT * FROM patient_baseline")
    _ = cursor.fetchall()
    read_ms = (time.time() - start) * 1000
    
    conn.close()
    return write_ms, read_ms

def run_sql_aes(data):
    conn = mysql.connector.connect(**SQL_CONFIG)
    cursor = conn.cursor()
    static_key = get_random_bytes(32) # Single key for all rows
    
    # Write
    start = time.time()
    encrypted_rows = []
    for row in data:
        enc_fields = []
        for text in row:
            cipher = AES.new(static_key, AES.MODE_GCM)
            ciphertext, tag = cipher.encrypt_and_digest(text.encode('utf-8'))
            enc_fields.append(cipher.nonce + tag + ciphertext)
        encrypted_rows.append(tuple(enc_fields))
        
    for i in range(0, len(encrypted_rows), CHUNK_SIZE):
        chunk = encrypted_rows[i:i + CHUNK_SIZE]
        cursor.executemany("INSERT INTO patient_aes (name, email, notes) VALUES (%s, %s, %s)", chunk)
    conn.commit()
    write_ms = (time.time() - start) * 1000
    
    # Read
    start = time.time()
    cursor.execute("SELECT name, email, notes FROM patient_aes")
    fetched = cursor.fetchall()
    for row in fetched:
        try:
            for cell in row:
                nonce, tag, ciphertext = cell[:16], cell[16:32], cell[32:]
                cipher = AES.new(static_key, AES.MODE_GCM, nonce=nonce)
                cipher.decrypt_and_verify(ciphertext, tag)
        except: continue
    read_ms = (time.time() - start) * 1000
    
    conn.close()
    return write_ms, read_ms

def run_sql_hybrid(data):
    conn = mysql.connector.connect(**SQL_CONFIG)
    cursor = conn.cursor()
    
    # RSA Key Pair
    key_pair = RSA.generate(2048)
    rsa_enc = PKCS1_OAEP.new(key_pair.publickey())
    rsa_dec = PKCS1_OAEP.new(key_pair)
    
    # Write
    start = time.time()
    encrypted_rows = []
    for row in data:
        row_key = get_random_bytes(32) # Unique key per row
        enc_fields = []
        
        # Encrypt data with AES
        for text in row:
            cipher = AES.new(row_key, AES.MODE_GCM)
            ciphertext, tag = cipher.encrypt_and_digest(text.encode('utf-8'))
            enc_fields.append(cipher.nonce + tag + ciphertext)
            
        # Encrypt the AES key with RSA
        enc_row_key = rsa_enc.encrypt(row_key)
        encrypted_rows.append(tuple(enc_fields + [enc_row_key]))
        
    for i in range(0, len(encrypted_rows), CHUNK_SIZE):
        chunk = encrypted_rows[i:i + CHUNK_SIZE]
        cursor.executemany("INSERT INTO patient_hybrid (name, email, notes, enc_key) VALUES (%s, %s, %s, %s)", chunk)
    conn.commit()
    write_ms = (time.time() - start) * 1000
    
    # Read
    start = time.time()
    cursor.execute("SELECT name, email, notes, enc_key FROM patient_hybrid")
    fetched = cursor.fetchall()
    for row in fetched:
        try:
            # Decrypt AES key using RSA first
            row_key = rsa_dec.decrypt(row[3])
            
            # Use recovered key to decrypt data
            for i in range(3):
                cell = row[i]
                nonce, tag, ciphertext = cell[:16], cell[16:32], cell[32:]
                cipher = AES.new(row_key, AES.MODE_GCM, nonce=nonce)
                cipher.decrypt_and_verify(ciphertext, tag)
        except: continue
    read_ms = (time.time() - start) * 1000
    
    conn.close()
    return write_ms, read_ms

# --- NOSQL (MONGODB) EXPERIMENTS ---

def run_mongo_baseline(data):
    client = pymongo.MongoClient(f"mongodb://{MONGO_CONFIG['host']}:{MONGO_CONFIG['port']}/")
    db = client[MONGO_CONFIG['db_name']]
    collection = db['patient_baseline']
    
    docs = [{'name': d[0], 'email': d[1], 'notes': d[2]} for d in data]
    
    # Write
    start = time.time()
    if docs:
        collection.insert_many(docs)
    write_ms = (time.time() - start) * 1000
    
    # Read
    start = time.time()
    _ = list(collection.find()) # Iterate cursor to measure fetching speed
    read_ms = (time.time() - start) * 1000
    
    client.close()
    return write_ms, read_ms

def run_mongo_aes(data):
    client = pymongo.MongoClient(f"mongodb://{MONGO_CONFIG['host']}:{MONGO_CONFIG['port']}/")
    db = client[MONGO_CONFIG['db_name']]
    collection = db['patient_aes']
    static_key = get_random_bytes(32)
    
    # Write
    start = time.time()
    docs = []
    for row in data:
        enc_doc = {}
        # Encrypt each field, store as binary
        for idx, field in enumerate(['name', 'email', 'notes']):
            cipher = AES.new(static_key, AES.MODE_GCM)
            ct, tag = cipher.encrypt_and_digest(row[idx].encode('utf-8'))
            enc_doc[field] = cipher.nonce + tag + ct 
        docs.append(enc_doc)
        
    if docs:
        collection.insert_many(docs)
    write_ms = (time.time() - start) * 1000
    
    # Read
    start = time.time()
    cursor = collection.find()
    for doc in cursor:
        try:
            for field in ['name', 'email', 'notes']:
                raw = doc[field]
                nonce, tag, ciphertext = raw[:16], raw[16:32], raw[32:]
                cipher = AES.new(static_key, AES.MODE_GCM, nonce=nonce)
                cipher.decrypt_and_verify(ciphertext, tag)
        except: continue
    read_ms = (time.time() - start) * 1000
    
    client.close()
    return write_ms, read_ms

def run_mongo_hybrid(data):
    client = pymongo.MongoClient(f"mongodb://{MONGO_CONFIG['host']}:{MONGO_CONFIG['port']}/")
    db = client[MONGO_CONFIG['db_name']]
    collection = db['patient_hybrid']
    
    key_pair = RSA.generate(2048)
    rsa_enc = PKCS1_OAEP.new(key_pair.publickey())
    rsa_dec = PKCS1_OAEP.new(key_pair)
    
    # Write
    start = time.time()
    docs = []
    for row in data:
        row_key = get_random_bytes(32)
        enc_doc = {}
        
        # Encrypt data with AES
        for idx, field in enumerate(['name', 'email', 'notes']):
            cipher = AES.new(row_key, AES.MODE_GCM)
            ct, tag = cipher.encrypt_and_digest(row[idx].encode('utf-8'))
            enc_doc[field] = cipher.nonce + tag + ct
            
        # Encrypt AES key with RSA
        enc_doc['enc_key'] = rsa_enc.encrypt(row_key)
        docs.append(enc_doc)
        
    if docs:
        collection.insert_many(docs)
    write_ms = (time.time() - start) * 1000
    
    # Read
    start = time.time()
    cursor = collection.find()
    for doc in cursor:
        try:
            # RSA Decrypt key
            row_key = rsa_dec.decrypt(doc['enc_key'])
            
            # AES Decrypt data
            for field in ['name', 'email', 'notes']:
                raw = doc[field]
                nonce, tag, ciphertext = raw[:16], raw[16:32], raw[32:]
                cipher = AES.new(row_key, AES.MODE_GCM, nonce=nonce)
                cipher.decrypt_and_verify(ciphertext, tag)
        except: continue
    read_ms = (time.time() - start) * 1000
    
    client.close()
    return write_ms, read_ms


def main():
    print("--- Initiating Benchmarks (SQL vs NoSQL) ---")
    setup_sql_database()
    setup_mongo_database()

    # Data holders
    res_sql = {'Baseline': {'w':[],'r':[],'s':[]}, 'AES-Only': {'w':[],'r':[],'s':[]}, 'Hybrid': {'w':[],'r':[],'s':[]}}
    res_nosql = {'Baseline': {'w':[],'r':[],'s':[]}, 'AES-Only': {'w':[],'r':[],'s':[]}, 'Hybrid': {'w':[],'r':[],'s':[]}}

    for count in BATCH_SIZES:
        print(f"\n[ Processing Batch: {count} Records ]")
        data = generate_dummy_data(count)

        # 1. SQL Tests
        print("   > Running SQL...", end="\r")
        
        w, r = run_sql_baseline(data)
        res_sql['Baseline']['w'].append(w); res_sql['Baseline']['r'].append(r); res_sql['Baseline']['s'].append(get_sql_storage_size('Baseline'))
        
        w, r = run_sql_aes(data)
        res_sql['AES-Only']['w'].append(w); res_sql['AES-Only']['r'].append(r); res_sql['AES-Only']['s'].append(get_sql_storage_size('AES'))
        
        w, r = run_sql_hybrid(data)
        res_sql['Hybrid']['w'].append(w); res_sql['Hybrid']['r'].append(r); res_sql['Hybrid']['s'].append(get_sql_storage_size('Hybrid'))
        
        # Reset SQL tables
        conn = mysql.connector.connect(**SQL_CONFIG)
        c = conn.cursor()
        c.execute("TRUNCATE TABLE patient_baseline"); c.execute("TRUNCATE TABLE patient_aes"); c.execute("TRUNCATE TABLE patient_hybrid")
        conn.close()

        # 2. NoSQL Tests
        print("   > Running NoSQL...      ")
        
        w, r = run_mongo_baseline(data)
        res_nosql['Baseline']['w'].append(w); res_nosql['Baseline']['r'].append(r); res_nosql['Baseline']['s'].append(get_mongo_storage_size('patient_baseline'))

        w, r = run_mongo_aes(data)
        res_nosql['AES-Only']['w'].append(w); res_nosql['AES-Only']['r'].append(r); res_nosql['AES-Only']['s'].append(get_mongo_storage_size('patient_aes'))

        w, r = run_mongo_hybrid(data)
        res_nosql['Hybrid']['w'].append(w); res_nosql['Hybrid']['r'].append(r); res_nosql['Hybrid']['s'].append(get_mongo_storage_size('patient_hybrid'))

        # Reset Mongo collections
        setup_mongo_database()

    # --- Print Terminal Tables ---
    def print_table(title, results):
        print("\n" + "="*95)
        print(f"{title:^95}")
        print("="*95)
        print(f"| {'BATCH':^10} | {'METHOD':<12} | {'WRITE (ms)':>12} | {'READ (ms)':>12} | {'TPS':>10} | {'SIZE (KB)':>10} |")
        print("-" * 95)
        for i, count in enumerate(BATCH_SIZES):
            for m in ['Baseline', 'AES-Only', 'Hybrid']:
                w = results[m]['w'][i]
                r = results[m]['r'][i]
                s = results[m]['s'][i]
                tps = count / (w/1000) if w > 0 else 0
                print(f"| {count:^10} | {m:<12} | {w:>12.2f} | {r:>12.2f} | {tps:>10.2f} | {s:>10.2f} |")
            if i < len(BATCH_SIZES) - 1: print("-" * 95)
        print("="*95)

    print_table("RESULTS: Relational DBMS (MySQL)", res_sql)
    print_table("RESULTS: NoSQL DBMS (MongoDB)", res_nosql)

    # --- FULL COMPARISON PLOTTING (SQL + NoSQL) ---
    plt.rcParams.update({'font.size': 8})
    
    # Increased figsize to ensure labels are not cut off
    fig, axes = plt.subplots(2, 3, figsize=(15, 9))
    fig.suptitle('Encryption Performance Analysis: SQL vs NoSQL', fontsize=16, fontweight='bold', y=0.98)
    
    x = np.arange(len(BATCH_SIZES))
    width = 0.25
    c_base, c_aes, c_hyb = '#2E8B57', '#4682B4', '#CD5C5C' # Green, Blue, Red
    
    def label_bars(ax, rects):
        """Helper to add number labels."""
        for rect in rects:
            height = rect.get_height()
            ax.annotate(f'{int(height)}', xy=(rect.get_x() + rect.get_width() / 2, height),
                        xytext=(0, 3), textcoords="offset points", ha='center', va='bottom', fontsize=7)

    def set_headroom(ax, val_lists):
        """Dynamic Y-limit so numbers don't touch the top border."""
        max_val = max([item for sublist in val_lists for item in sublist])
        ax.set_ylim(0, max_val * 1.25) 

    # --- Row 1: SQL Graphs ---
    
    # 1. SQL Write
    rects1 = axes[0, 0].bar(x - width, res_sql['Baseline']['w'], width, label='Baseline', color=c_base)
    rects2 = axes[0, 0].bar(x, res_sql['AES-Only']['w'], width, label='AES-Only', color=c_aes)
    rects3 = axes[0, 0].bar(x + width, res_sql['Hybrid']['w'], width, label='Hybrid', color=c_hyb)
    axes[0, 0].set_ylabel('Latency (ms)', fontsize=10, fontweight='bold')
    axes[0, 0].set_title('SQL: Write Latency', fontsize=11, fontweight='bold')
    axes[0, 0].set_xticks(x); axes[0, 0].set_xticklabels(BATCH_SIZES)
    axes[0, 0].legend()
    label_bars(axes[0, 0], rects1); label_bars(axes[0, 0], rects2); label_bars(axes[0, 0], rects3)
    set_headroom(axes[0, 0], [res_sql['Baseline']['w'], res_sql['AES-Only']['w'], res_sql['Hybrid']['w']])

    # 2. SQL Read
    rects4 = axes[0, 1].bar(x - width, res_sql['Baseline']['r'], width, label='Baseline', color=c_base)
    rects5 = axes[0, 1].bar(x, res_sql['AES-Only']['r'], width, label='AES-Only', color=c_aes)
    rects6 = axes[0, 1].bar(x + width, res_sql['Hybrid']['r'], width, label='Hybrid', color=c_hyb)
    axes[0, 1].set_ylabel('Latency (ms)', fontsize=10, fontweight='bold')
    axes[0, 1].set_title('SQL: Read Latency', fontsize=11, fontweight='bold')
    axes[0, 1].set_xticks(x); axes[0, 1].set_xticklabels(BATCH_SIZES)
    axes[0, 1].legend()
    label_bars(axes[0, 1], rects4); label_bars(axes[0, 1], rects5); label_bars(axes[0, 1], rects6)
    set_headroom(axes[0, 1], [res_sql['Baseline']['r'], res_sql['AES-Only']['r'], res_sql['Hybrid']['r']])

    # 3. SQL Storage Pie
    sizes_sql = [
        float(res_sql['Baseline']['s'][-1]), 
        float(res_sql['AES-Only']['s'][-1]), 
        float(res_sql['Hybrid']['s'][-1])
    ]
    axes[0, 2].pie(sizes_sql, labels=['Baseline', 'AES', 'Hybrid'], 
                   autopct=lambda p: f'{p:.1f}%\n({p*sum(sizes_sql)/100:.0f} KB)', 
                   colors=[c_base, c_aes, c_hyb], explode=(0,0,0.1), 
                   textprops={'fontsize': 9}, shadow=True)
    axes[0, 2].set_title(f'SQL Storage Overhead\n(Batch: {BATCH_SIZES[-1]})', fontsize=11, fontweight='bold')

    # --- Row 2: NoSQL Graphs ---
    
    # 4. NoSQL Write
    rects7 = axes[1, 0].bar(x - width, res_nosql['Baseline']['w'], width, label='Baseline', color=c_base)
    rects8 = axes[1, 0].bar(x, res_nosql['AES-Only']['w'], width, label='AES-Only', color=c_aes)
    rects9 = axes[1, 0].bar(x + width, res_nosql['Hybrid']['w'], width, label='Hybrid', color=c_hyb)
    axes[1, 0].set_ylabel('Latency (ms)', fontsize=10, fontweight='bold')
    axes[1, 0].set_title('NoSQL: Write Latency', fontsize=11, fontweight='bold')
    axes[1, 0].set_xticks(x); axes[1, 0].set_xticklabels(BATCH_SIZES)
    axes[1, 0].legend()
    label_bars(axes[1, 0], rects7); label_bars(axes[1, 0], rects8); label_bars(axes[1, 0], rects9)
    set_headroom(axes[1, 0], [res_nosql['Baseline']['w'], res_nosql['AES-Only']['w'], res_nosql['Hybrid']['w']])

    # 5. NoSQL Read
    rects10 = axes[1, 1].bar(x - width, res_nosql['Baseline']['r'], width, label='Baseline', color=c_base)
    rects11 = axes[1, 1].bar(x, res_nosql['AES-Only']['r'], width, label='AES-Only', color=c_aes)
    rects12 = axes[1, 1].bar(x + width, res_nosql['Hybrid']['r'], width, label='Hybrid', color=c_hyb)
    axes[1, 1].set_ylabel('Latency (ms)', fontsize=10, fontweight='bold')
    axes[1, 1].set_title('NoSQL: Read Latency', fontsize=11, fontweight='bold')
    axes[1, 1].set_xticks(x); axes[1, 1].set_xticklabels(BATCH_SIZES)
    axes[1, 1].legend()
    label_bars(axes[1, 1], rects10); label_bars(axes[1, 1], rects11); label_bars(axes[1, 1], rects12)
    set_headroom(axes[1, 1], [res_nosql['Baseline']['r'], res_nosql['AES-Only']['r'], res_nosql['Hybrid']['r']])

    # 6. NoSQL Storage Pie
    sizes_mongo = [
        float(res_nosql['Baseline']['s'][-1]), 
        float(res_nosql['AES-Only']['s'][-1]), 
        float(res_nosql['Hybrid']['s'][-1])
    ]
    axes[1, 2].pie(sizes_mongo, labels=['Baseline', 'AES', 'Hybrid'], 
                   autopct=lambda p: f'{p:.1f}%\n({p*sum(sizes_mongo)/100:.0f} KB)', 
                   colors=[c_base, c_aes, c_hyb], explode=(0,0,0.1), 
                   textprops={'fontsize': 9}, shadow=True)
    axes[1, 2].set_title(f'NoSQL Storage Overhead\n(Batch: {BATCH_SIZES[-1]})', fontsize=11, fontweight='bold')

    # Apply tight layout with padding to ensure Y-axis labels are visible
    plt.tight_layout(rect=[0, 0.03, 1, 0.95])
    plt.show()

if __name__ == "__main__":
    main()