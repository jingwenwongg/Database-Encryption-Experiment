# Comparative Performance Analysis of Database Encryption: SQL (MySQL) vs. NoSQL (MongoDB)

![Python](https://img.shields.io/badge/Python-3.x-blue.svg)
![MySQL](https://img.shields.io/badge/MySQL-8.0-orange.svg)
![MongoDB](https://img.shields.io/badge/MongoDB-Latest-green.svg)
![Library](https://img.shields.io/badge/PyCryptodome-Latest-red.svg)

## 📌 Project Overview

This project is a quantitative research experiment designed to benchmark and analyze the performance trade-offs of database encryption techniques across two distinct database paradigms: Relational (MySQL) and NoSQL (MongoDB).

The study evaluates the impact of cryptographic complexity on system latency (Read/Write), throughput (TPS), and storage scalability. By testing identical encryption logic on both SQL and NoSQL backends, this experiment isolates the computational overhead of cryptography from the database's internal processing mechanisms.

The experiment compares three distinct architectural scenarios using a dataset of synthetic medical records (PHI) generated via the `Faker` library:

1.  **Baseline (No Encryption):** A control group measuring raw database performance without cryptographic overhead.
2.  **AES-Only (Symmetric):** Uses a single static key for high-speed encryption/decryption, representing standard "at-rest" encryption.
3.  **Hybrid (AES + RSA):** Implements a "Zero-Trust" row-level architecture where each record is encrypted with a unique AES key, which is subsequently secured via RSA-2048 public key encryption.

The findings aim to determine the optimal balance between data security and operational efficiency, validating whether NoSQL architectures can mitigate the latency introduced by complex encryption.

---

## 🛠️ Methodologies Tested

### 1. Baseline (No Encryption)
* **Description:** Data is stored in plain text formats (Tables for MySQL, Collections for MongoDB).
* **Mechanism:** Direct insertion and retrieval operations.
* **Purpose:** Establishes a "zero-latency" benchmark to isolate encryption overhead.
* **Security:** None (Vulnerable to direct data breaches).

### 2. AES-Only (Symmetric Encryption)
* **Description:** Sensitive fields are encrypted using **AES-256-GCM** with a single static master key held in memory.
* **Mechanism:** Data is encrypted before insertion and decrypted immediately upon retrieval using `PyCryptodome`.
* **Purpose:** Represents standard industry practice where processing speed is prioritized.
* **Security:** High, but carries a "Single Point of Failure" risk (Master Key compromise).

### 3. Hybrid Architecture (AES + RSA)
* **Description:** A unique AES-256 key is generated for every single row/document. This unique key is then encrypted using an RSA-2048 Public Key and stored in a dedicated enc_key field (VARBINARY in SQL, BinData in NoSQL).
* **Mechanism:**
    * *Write:* Generate Random AES Key $\rightarrow$ Encrypt Data $\rightarrow$ Encrypt AES Key with RSA Public Key $\rightarrow$ Commit.
    * *Read:* Fetch Document $\rightarrow$ Decrypt AES Key with RSA Private Key $\rightarrow$ Decrypt Data.
* **Purpose:** To test a high-security model where compromising one row's key does not compromise the rest of the database.
* **Security:** Maximum (Zero-Trust / Granular Access Control).

---

## ⚙️ Installation & Setup

### Prerequisites
* **Python 3.x**
* **MySQL Server** (Running locally on port 3306)
* **MongoDB Server** (Running locally on port 27017)
* **Git**

### Step 1: Clone the Repository
```bash
git clone [https://github.com/jingwenwongg/Database-Encryption-Experiment.git](https://github.com/jingwenwongg/Database-Encryption-Experiment.git)
cd Database-Encryption-Experiment
```

### Step 2: Install Dependencies
This project relies on PyCryptodome for encryption, MySQL-Connector for SQL, and PyMongo for NoSQL. Install the required libraries:
```bash
pip install -r requirements.txt
```

### Step 3: Database Configuration
Open the `encryption_experiment.py` file update the configurations if your local setup differs:
```bash
SQL_CONFIG = {
    'host': 'localhost',
    'user': 'root',      # Your MySQL Username
    'password': '',      # Your MySQL Password
    'database': 'encryption_experiment'
}

MONGO_CONFIG = {
    'host': 'localhost',
    'port': 27017,
    'db_name': 'encryption_experiment_nosql'
}
```

## 🚀 Running the Experiment
To execute the benchmark, run the main script. The script is self-contained: it will automatically reset the database environment, create tables, and generate fresh dummy data for every batch size.
```bash
python encryption_experiment.py
```
What to Expect:
1. **Terminal Output:** Real-time logging of batch processing for both MySQL and MongoDB (1,000, 5,000, and 10,000 records).
2. **Full Comparison Visualization:** A window will pop up displaying a 2x3 Grid of charts. This includes side-by-side Bar Charts for Write/Read Latency and Pie Charts for Storage Overhead, allowing immediate visual comparison between Relational (MySQL) and NoSQL (MongoDB) performance.

## 📊 Experimental Results (Sample)
Note: Results may vary based on hardware (CPU/RAM). Below is a sample output.

SQL Results (Relational):
```bash
===============================================================================================
                               RESULTS: Relational DBMS (MySQL)
===============================================================================================
|   BATCH    | METHOD       |   WRITE (ms) |    READ (ms) |        TPS |  SIZE (KB) |
-----------------------------------------------------------------------------------------------
|    1000    | Baseline     |        33.62 |         4.89 |   29740.09 |      68.53 |
|    1000    | AES-Only     |       164.16 |       141.63 |    6091.65 |     162.28 |
|    1000    | Hybrid       |       615.33 |      2574.73 |    1625.15 |     412.28 |
-----------------------------------------------------------------------------------------------
|    5000    | Baseline     |       139.02 |        10.14 |   35965.63 |     343.71 |
|    5000    | AES-Only     |       680.68 |       674.07 |    7345.57 |     812.46 |
|    5000    | Hybrid       |      2867.96 |     13020.47 |    1743.40 |    2062.46 |
-----------------------------------------------------------------------------------------------
|   10000    | Baseline     |       193.15 |        24.52 |   51772.01 |     685.24 |
|   10000    | AES-Only     |      1427.05 |      1382.90 |    7007.44 |    1622.74 |
|   10000    | Hybrid       |      5822.17 |     26594.48 |    1717.57 |    4122.74 |
===============================================================================================
```
NoSQL Results (MongoDB):
```bash
===============================================================================================
                                 RESULTS: NoSQL DBMS (MongoDB)
===============================================================================================
|   BATCH    | METHOD       |   WRITE (ms) |    READ (ms) |        TPS |  SIZE (KB) |
-----------------------------------------------------------------------------------------------
|    1000    | Baseline     |        34.28 |         2.06 |   29171.48 |     124.19 |
|    1000    | AES-Only     |       117.69 |       134.63 |    8496.60 |     217.94 |
|    1000    | Hybrid       |       557.92 |      2622.15 |    1792.39 |     481.61 |
-----------------------------------------------------------------------------------------------
|    5000    | Baseline     |        71.70 |        14.28 |   69735.15 |     622.03 |
|    5000    | AES-Only     |       580.59 |       683.50 |    8611.99 |    1090.78 |
|    5000    | Hybrid       |      2761.31 |     13324.90 |    1810.74 |    2409.14 |
-----------------------------------------------------------------------------------------------
|   10000    | Baseline     |       122.45 |        22.06 |   81664.00 |    1241.88 |
|   10000    | AES-Only     |      1204.33 |      1420.28 |    8303.40 |    2179.38 |
|   10000    | Hybrid       |      5542.03 |     35073.38 |    1804.39 |    4816.10 |
===============================================================================================
```

## 📈 Key Findings
- **Encryption Bottleneck is Universal:** The experiments confirm that the Hybrid architecture causes a significant read latency spike in both MySQL and MongoDB. This indicates that the bottleneck is primarily the CPU-intensive RSA decryption process rather than the database architecture itself.
- **Performance Comparison:** While MongoDB showed improved processing times for the heavy Hybrid workload compared to MySQL, the Hybrid method remained significantly slower than the AES-Only method in both environments. This suggests that Hybrid encryption is best suited for archival storage rather than real-time transactional systems.
- **Storage Trade-offs:** The results indicate that the NoSQL implementation (MongoDB) generally consumes more storage space compared to the SQL implementation (MySQL) for the same dataset. This is attributed to the document-based BSON format, which explicitly stores field names for every record, adding overhead to the encrypted data.
