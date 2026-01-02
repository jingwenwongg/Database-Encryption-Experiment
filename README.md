# Database Encryption Experiment: Performance Analysis

![Python](https://img.shields.io/badge/Python-3.x-blue.svg)
![MySQL](https://img.shields.io/badge/MySQL-8.0-orange.svg)
![Library](https://img.shields.io/badge/PyCryptodome-Latest-red.svg)

## 📌 Project Overview

This project is a quantitative research experiment designed to benchmark and analyze the performance trade-offs of different database encryption techniques within a MySQL environment. It was developed to evaluate the impact of cryptographic complexity on **system latency (Read/Write)**, **throughput (TPS)**, and **storage scalability**.

The experiment compares three distinct architectural scenarios using a dataset of synthetic medical records (PHI) generated via the `Faker` library:

1.  **Baseline (No Encryption):** A control group measuring raw database performance without cryptographic overhead.
2.  **AES-Only (Symmetric):** Uses a single static key for high-speed encryption/decryption, representing standard "at-rest" encryption.
3.  **Hybrid (AES + RSA):** Implements a "Zero-Trust" row-level architecture where each record is encrypted with a unique AES key, which is subsequently secured via RSA-2048 public key encryption.

The findings aim to determine the optimal balance between data security and operational efficiency for real-time vs. archival systems.

---

## 🛠️ Methodologies Tested

### 1. Baseline (No Encryption)
* **Description:** Data is stored in plain text formats (`VARCHAR`, `TEXT`).
* **Mechanism:** Direct SQL `INSERT` and `SELECT` operations.
* **Purpose:** Establishes a "zero-latency" benchmark to calculate the precise millisecond overhead of encryption libraries.
* **Security:** None (Vulnerable to direct data breaches).

### 2. AES-Only (Symmetric Encryption)
* **Description:** Sensitive fields are encrypted using **AES-256-GCM** with a single static master key held in memory.
* **Mechanism:** Data is encrypted before insertion and decrypted immediately upon retrieval using the `PyCryptodome` library.
* **Purpose:** Represents standard industry practice where processing speed is prioritized over granular key management.
* **Security:** High, but carries a "Single Point of Failure" risk (Master Key compromise).

### 3. Hybrid Architecture (AES + RSA)
* **Description:** A unique **AES-256** key is generated for **every single row**. This unique key is then encrypted using an **RSA-2048** Public Key and stored in a dedicated `enc_key` column (`VARBINARY`) alongside the record.
* **Mechanism:**
    * *Write:* Generate Random AES Key $\rightarrow$ Encrypt Data $\rightarrow$ Encrypt AES Key with RSA Public Key $\rightarrow$ Commit to DB.
    * *Read:* Fetch Row $\rightarrow$ Decrypt AES Key with RSA Private Key $\rightarrow$ Decrypt Data.
* **Purpose:** To test a high-security model where compromising one row's key does not compromise the rest of the database.
* **Security:** Maximum (Zero-Trust / Granular Access Control).

---

## ⚙️ Installation & Setup

### Prerequisites
* **Python 3.x**
* **MySQL Server** (Running locally on default port 3306)
* **Git**

### Step 1: Clone the Repository
```bash
git clone [https://github.com/jingwenwongg/Database-Encryption-Experiment.git](https://github.com/jingwenwongg/Database-Encryption-Experiment.git)
cd Database-Encryption-Experiment
```

### Step 2: Install Dependencies
This project relies on PyCryptodome for encryption and MySQL-Connector for database interaction. Install the required libraries:
```bash
pip install -r requirements.txt
```

### Step 3: Database Configuration
Open the encryption_experiment.py file and update the DB_CONFIG dictionary to match your local MySQL credentials:
```bash
DB_CONFIG = {
    'host': 'localhost',
    'user': 'root',       # Your MySQL Username
    'password': '',       # Your MySQL Password
    'database': 'encryption_experiment'
}
```

## 🚀 Running the Experiment
To execute the benchmark, run the main script. The script is self-contained: it will automatically reset the database environment, create tables, and generate fresh dummy data for every batch size.
```bash
python encryption_experiment.py
```
What to Expect:
1. Terminal Output: Real-time logging of the batch processing (1,000, 5,000, and 10,000 records).
2. Performance Visualization: A window will pop up displaying side-by-side Bar Charts comparing Write vs. Read Latency.
3. Storage Analysis: After closing the bar charts, a Pie Chart will appear showing the Storage Overhead distribution for the largest dataset.

## 📊 Experimental Results (Sample)
Note: Results may vary based on hardware (CPU/RAM). Below is a sample.
```bash
===============================================================================================
                                  FINAL EXPERIMENTAL RESULTS
===============================================================================================
|   BATCH    | METHOD       |   WRITE (ms) |    READ (ms) |        TPS |  SIZE (KB) |
-----------------------------------------------------------------------------------------------
|    1000    | Baseline     |        28.36 |         2.86 |   35264.63 |      68.85 |
|    1000    | AES-Only     |       188.41 |       147.64 |    5307.51 |     162.60 |
|    1000    | Hybrid       |       633.67 |      2674.35 |    1578.11 |     412.60 |
-----------------------------------------------------------------------------------------------
|    5000    | Baseline     |       122.74 |        12.44 |   40735.64 |     342.99 |
|    5000    | AES-Only     |      1979.74 |      2306.10 |    2525.59 |     811.74 |
|    5000    | Hybrid       |      5734.97 |     37519.23 |     871.84 |    2061.74 |
-----------------------------------------------------------------------------------------------
|   10000    | Baseline     |       270.79 |        37.47 |   36928.39 |     685.45 |
|   10000    | AES-Only     |      4017.89 |      4581.04 |    2488.87 |    1622.95 |
|   10000    | Hybrid       |     14503.40 |     52410.19 |     689.49 |    4122.95 |
===============================================================================================
```

## 📈 Key Findings
- AES-Only is approximately 3.6x faster in writing and 11.4x faster in reading compared to the Hybrid architecture.
- Hybrid Encryption introduces a massive bottleneck in SELECT operations due to the computational cost of RSA decryption for every row.
- Storage Overhead: The Hybrid model increases database size by roughly 2.5x compared to AES-Only due to the storage of encrypted keys.
