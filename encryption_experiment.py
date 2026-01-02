import mysql.connector
from mysql.connector import Error
import time
import matplotlib.pyplot as plt
import numpy as np
from Crypto.Cipher import AES, PKCS1_OAEP
from Crypto.PublicKey import RSA
from Crypto.Random import get_random_bytes
from faker import Faker

# --- Configuration ---
DB_CONFIG = {
    'host': 'localhost',
    'user': 'root',
    'password': '', 
    'database': 'encryption_experiment'
}

# Settings
CHUNK_SIZE = 500 
BATCH_SIZES = [1000, 5000, 10000]

fake = Faker()

def setup_database():
    """Resets the database and clears old tables to ensure a fresh start for every run."""
    try:
        # Connect to MySQL server to create the database if it doesn't exist
        conn = mysql.connector.connect(host=DB_CONFIG['host'], user=DB_CONFIG['user'], password=DB_CONFIG['password'])
        cursor = conn.cursor()
        cursor.execute(f"CREATE DATABASE IF NOT EXISTS {DB_CONFIG['database']}")
        conn.close()

        # Connect to the specific experiment database
        conn = mysql.connector.connect(**DB_CONFIG)
        cursor = conn.cursor()

        # Remove old tables to avoid duplicate data
        cursor.execute("DROP TABLE IF EXISTS patient_baseline")
        cursor.execute("DROP TABLE IF EXISTS patient_aes")
        cursor.execute("DROP TABLE IF EXISTS patient_hybrid")

        # 1. Baseline Table (Normal text, no encryption)
        cursor.execute("""
            CREATE TABLE patient_baseline (
                id INT AUTO_INCREMENT PRIMARY KEY,
                name VARCHAR(255),
                email VARCHAR(255),
                notes TEXT
            )
        """)

        # 2. AES-Only Table (Data stored as binary ciphertext)
        cursor.execute("""
            CREATE TABLE patient_aes (
                id INT AUTO_INCREMENT PRIMARY KEY,
                name VARBINARY(512),
                email VARBINARY(512),
                notes BLOB
            )
        """)

        # 3. Hybrid Table (Stores encrypted data + the encrypted key for that row)
        cursor.execute("""
            CREATE TABLE patient_hybrid (
                id INT AUTO_INCREMENT PRIMARY KEY,
                name VARBINARY(512),
                email VARBINARY(512),
                notes BLOB,
                enc_key VARBINARY(512)
            )
        """)
        
        conn.close()
        print(">> Database environment ready.")
        
    except Error as e:
        print(f"Error checking database: {e}")

def get_exact_storage_size(table_name, method):
    """Calculates the total size (in KB) of the actual data stored in the table."""
    try:
        conn = mysql.connector.connect(**DB_CONFIG)
        cursor = conn.cursor()
        
        # specific queries to sum up the byte length of relevant columns
        if method == 'Baseline':
            query = "SELECT SUM(OCTET_LENGTH(name) + OCTET_LENGTH(email) + OCTET_LENGTH(notes)) FROM patient_baseline"
        elif method == 'AES':
            query = "SELECT SUM(OCTET_LENGTH(name) + OCTET_LENGTH(email) + OCTET_LENGTH(notes)) FROM patient_aes"
        elif method == 'Hybrid':
            # Hybrid includes the extra 'enc_key' column size
            query = "SELECT SUM(OCTET_LENGTH(name) + OCTET_LENGTH(email) + OCTET_LENGTH(notes) + OCTET_LENGTH(enc_key)) FROM patient_hybrid"
        
        cursor.execute(query)
        result = cursor.fetchone()
        conn.close()
        
        size_bytes = result[0] if result and result[0] else 0
        return round(size_bytes / 1024, 2)
        
    except Error:
        return 0.0

def generate_dummy_data(n):
    """Generates patient data to test with."""
    data = []
    for _ in range(n):
        # Creates a tuple: (Name, Email, ~50 chars of notes)
        data.append((fake.name(), fake.email(), fake.text(max_nb_chars=50)))
    return data

# --- Scenario A: Baseline ---
def run_baseline(data):
    conn = mysql.connector.connect(**DB_CONFIG)
    cursor = conn.cursor()

    # WRITE TEST
    start = time.time()
    # Insert data in chunks to handle large datasets efficiently
    for i in range(0, len(data), CHUNK_SIZE):
        chunk = data[i:i + CHUNK_SIZE]
        cursor.executemany("INSERT INTO patient_baseline (name, email, notes) VALUES (%s, %s, %s)", chunk)
    conn.commit()
    write_ms = (time.time() - start) * 1000

    # READ TEST
    start = time.time()
    cursor.execute("SELECT * FROM patient_baseline")
    _ = cursor.fetchall() 
    read_ms = (time.time() - start) * 1000

    conn.close()
    return write_ms, read_ms

# --- Scenario B: AES-Only ---
def run_aes(data):
    conn = mysql.connector.connect(**DB_CONFIG)
    cursor = conn.cursor()

    # Generate one single key used for ALL rows (Symmetric encryption)
    static_key = get_random_bytes(32) 

    # WRITE TEST
    start = time.time()
    encrypted_rows = []
    
    for row in data:
        enc_fields = []
        for text in row:
            # Encrypt each field (Name, Email, Notes)
            cipher = AES.new(static_key, AES.MODE_GCM)
            ciphertext, tag = cipher.encrypt_and_digest(text.encode('utf-8'))
            # Store Nonce + Tag + Ciphertext together
            enc_fields.append(cipher.nonce + tag + ciphertext)
        encrypted_rows.append(tuple(enc_fields))

    for i in range(0, len(encrypted_rows), CHUNK_SIZE):
        chunk = encrypted_rows[i:i + CHUNK_SIZE]
        cursor.executemany("INSERT INTO patient_aes (name, email, notes) VALUES (%s, %s, %s)", chunk)
    conn.commit()
    write_ms = (time.time() - start) * 1000

    # READ TEST
    start = time.time()
    cursor.execute("SELECT name, email, notes FROM patient_aes")
    fetched = cursor.fetchall()
    
    for row in fetched:
        try:
            for cell in row:
                # Extract the parts needed for decryption
                nonce = cell[:16]
                tag = cell[16:32]
                ciphertext = cell[32:]
                
                # Decrypt using the static key
                cipher = AES.new(static_key, AES.MODE_GCM, nonce=nonce)
                cipher.decrypt_and_verify(ciphertext, tag)
        except:
            continue
            
    read_ms = (time.time() - start) * 1000

    conn.close()
    return write_ms, read_ms

# --- Scenario C: Hybrid (AES + RSA) ---
def run_hybrid(data):
    conn = mysql.connector.connect(**DB_CONFIG)
    cursor = conn.cursor()

    # Generate RSA Key Pair (Public & Private)
    key_pair = RSA.generate(2048)
    rsa_enc = PKCS1_OAEP.new(key_pair.publickey())
    rsa_dec = PKCS1_OAEP.new(key_pair)

    # WRITE TEST
    start = time.time()
    encrypted_rows = []

    for row in data:
        # Create a unique AES key for THIS specific row
        row_key = get_random_bytes(32) 
        
        # Step 1: Encrypt the actual data using the unique AES key
        enc_fields = []
        for text in row:
            cipher = AES.new(row_key, AES.MODE_GCM)
            ciphertext, tag = cipher.encrypt_and_digest(text.encode('utf-8'))
            enc_fields.append(cipher.nonce + tag + ciphertext)
        
        # Step 2: Encrypt the AES key using the RSA Public Key
        enc_row_key = rsa_enc.encrypt(row_key)
        
        # Store encrypted data AND the encrypted key
        encrypted_rows.append(tuple(enc_fields + [enc_row_key]))

    for i in range(0, len(encrypted_rows), CHUNK_SIZE):
        chunk = encrypted_rows[i:i + CHUNK_SIZE]
        cursor.executemany("INSERT INTO patient_hybrid (name, email, notes, enc_key) VALUES (%s, %s, %s, %s)", chunk)
    conn.commit()
    write_ms = (time.time() - start) * 1000

    # READ TEST
    start = time.time()
    cursor.execute("SELECT name, email, notes, enc_key FROM patient_hybrid")
    fetched = cursor.fetchall()

    for row in fetched:
        enc_key_blob = row[3]
        try:
            # Step 1: Decrypt the unique AES key using RSA Private Key
            row_key = rsa_dec.decrypt(enc_key_blob)
            
            # Step 2: Use that recovered key to decrypt the data
            for i in range(3):
                cell = row[i]
                nonce = cell[:16]
                tag = cell[16:32]
                ciphertext = cell[32:]
                cipher = AES.new(row_key, AES.MODE_GCM, nonce=nonce)
                cipher.decrypt_and_verify(ciphertext, tag)
        except:
            continue

    read_ms = (time.time() - start) * 1000

    conn.close()
    return write_ms, read_ms

def main():
    print("--- Initiating Performance Benchmarks ---")
    setup_database()

    results = {
        'Baseline': {'w': [], 'r': [], 's': []},
        'AES':      {'w': [], 'r': [], 's': []},
        'Hybrid':   {'w': [], 'r': [], 's': []}
    }

    for count in BATCH_SIZES:
        print(f"\n[ Processing Batch: {count} Records ]")
        # Ensure consistency: Use the exact same random data for all 3 methods
        data = generate_dummy_data(count)

        # 1. Run Baseline Experiment
        print("   > Running Baseline...")
        w, r = run_baseline(data)
        s = get_exact_storage_size('patient_baseline', 'Baseline')
        results['Baseline']['w'].append(w)
        results['Baseline']['r'].append(r)
        results['Baseline']['s'].append(s)

        # 2. Run AES Experiment
        print("   > Running AES-Only...")
        w, r = run_aes(data)
        s = get_exact_storage_size('patient_aes', 'AES')
        results['AES-Only']['w'].append(w)
        results['AES-Only']['r'].append(r)
        results['AES-Only']['s'].append(s)

        # 3. Run Hybrid Experiment
        print("   > Running Hybrid (AES-RSA)...")
        w, r = run_hybrid(data)
        s = get_exact_storage_size('patient_hybrid', 'Hybrid')
        results['Hybrid']['w'].append(w)
        results['Hybrid']['r'].append(r)
        results['Hybrid']['s'].append(s)
        
        # Clean up tables so the next batch size starts empty
        conn = mysql.connector.connect(**DB_CONFIG)
        c = conn.cursor()
        c.execute("TRUNCATE TABLE patient_baseline")
        c.execute("TRUNCATE TABLE patient_aes")
        c.execute("TRUNCATE TABLE patient_hybrid")
        conn.close()

    # --- Print Final Results Table ---
    print("\n" + "="*95)
    print(f"{'FINAL EXPERIMENTAL RESULTS':^95}")
    print("="*95)
    print(f"| {'BATCH':^10} | {'METHOD':<12} | {'WRITE (ms)':>12} | {'READ (ms)':>12} | {'TPS':>10} | {'SIZE (KB)':>10} |")
    print("-" * 95)

    for i, count in enumerate(BATCH_SIZES):
        for m in ['Baseline', 'AES', 'Hybrid']:
            w = results[m]['w'][i]
            r = results[m]['r'][i]
            s = results[m]['s'][i]
            # TPS = Transactions Per Second
            tps = count / (w/1000) if w > 0 else 0
            
            print(f"| {count:^10} | {m:<12} | {w:>12.2f} | {r:>12.2f} | {tps:>10.2f} | {s:>10.2f} |")
        
        if i < len(BATCH_SIZES) - 1:
            print("-" * 95)
            
    print("="*95)
    
    # --- Create Graphs 1 (Bar Charts) ---
    x = np.arange(len(BATCH_SIZES))
    width = 0.25 
    
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(15, 6))
    c_base, c_aes, c_hyb = '#2E8B57', '#4682B4', '#CD5C5C'

    # Plot 1: Write Speed
    rects1 = ax1.bar(x - width, results['Baseline']['w'], width, label='Baseline', color=c_base)
    rects2 = ax1.bar(x, results['AES']['w'], width, label='AES-Only', color=c_aes)
    rects3 = ax1.bar(x + width, results['Hybrid']['w'], width, label='Hybrid', color=c_hyb)

    ax1.set_ylabel('Latency (ms)')
    ax1.set_title('Write Performance (Encryption + Insert)')
    ax1.set_xticks(x)
    ax1.set_xticklabels(BATCH_SIZES)
    ax1.set_xlabel('Batch Size (Records)')
    ax1.legend()
    ax1.grid(axis='y', alpha=0.3)

    # Plot 2: Read Speed
    rects4 = ax2.bar(x - width, results['Baseline']['r'], width, label='Baseline', color=c_base)
    rects5 = ax2.bar(x, results['AES']['r'], width, label='AES-Only', color=c_aes)
    rects6 = ax2.bar(x + width, results['Hybrid']['r'], width, label='Hybrid', color=c_hyb)

    ax2.set_ylabel('Latency (ms)')
    ax2.set_title('Read Performance (Select + Decryption)')
    ax2.set_xticks(x)
    ax2.set_xticklabels(BATCH_SIZES)
    ax2.set_xlabel('Batch Size (Records)')
    ax2.legend()
    ax2.grid(axis='y', alpha=0.3)

    def label_bars(ax, rects):
        """Helper to add number labels on top of the bars."""
        for rect in rects:
            height = rect.get_height()
            ax.annotate(f'{int(height)}',
                        xy=(rect.get_x() + rect.get_width() / 2, height),
                        xytext=(0, 3), 
                        textcoords="offset points",
                        ha='center', va='bottom', fontsize=8)

    for r in [rects1, rects2, rects3]: label_bars(ax1, r)
    for r in [rects4, rects5, rects6]: label_bars(ax2, r)

    fig.suptitle('Database Encryption Performance Comparison', fontsize=16)
    plt.tight_layout()
    
    # Show Bar Charts first
    plt.show() 

    # --- Create Graphs 2 (Pie Chart) ---
    
    # FIX: Explicitly convert Decimal/String to Float to avoid TypeError
    sizes = [
        float(results['Baseline']['s'][-1]),
        float(results['AES']['s'][-1]),
        float(results['Hybrid']['s'][-1])
    ]
    labels = ['Baseline', 'AES-Only', 'Hybrid']
    colors = [c_base, c_aes, c_hyb]
    explode = (0, 0, 0.1)  # slightly "explode" the Hybrid slice to highlight it

    plt.figure(figsize=(8, 8))
    plt.pie(sizes, explode=explode, labels=labels, colors=colors,
            autopct=lambda p: f'{p:.1f}%\n({p*sum(sizes)/100:.0f} KB)',
            shadow=True, startangle=140)
    
    plt.title(f'Storage Overhead Comparison\n(Batch Size: {BATCH_SIZES[-1]} Records)', fontsize=14)
    plt.axis('equal')  # Equal aspect ratio ensures that pie is drawn as a circle.
    
    plt.show()

if __name__ == "__main__":
    main()