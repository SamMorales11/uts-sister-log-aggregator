# UTS Sister: Pub-Sub Log Aggregator Sederhana 

Proyek ini adalah implementasi layanan agregator log berbasis *publish-subscribe* internal untuk Ujian Tengah Semester mata kuliah Sistem Paralel dan Terdistribusi. Layanan ini dibangun menggunakan Python dan FastAPI, berjalan di dalam *container* Docker, dan dilengkapi dengan mekanisme deduplikasi *event* serta *consumer* yang idempoten.

---

## 🚀 Menjalankan Aplikasi (Menggunakan Docker)

Pastikan Docker Desktop atau Docker Engine sudah terinstal dan berjalan di sistem Anda.

1.  **Build Docker Image:**
    Buka terminal di direktori utama proyek (tempat `Dockerfile` berada) dan jalankan perintah berikut untuk membangun *image* Docker bernama `uts-aggregator`:
    ```bash
    docker build -t uts-aggregator .
    ```

2.  **Run Docker Container:**
    Setelah *image* berhasil dibuat, jalankan *container* dari *image* tersebut:
    ```bash
    docker run -d -p 8080:8080 --name aggregator-app uts-aggregator
    ```
    * `-d`: Menjalankan *container* di latar belakang.
    * `-p 8080:8080`: Memetakan port 8080 di komputer Anda ke port 8080 di dalam *container*.
    * `--name aggregator-app`: Memberi nama pada *container* agar mudah dikelola.

3.  **Akses Aplikasi:**
    Aplikasi sekarang berjalan dan dapat diakses melalui `http://localhost:8080`.

4.  **(Opsional) Melihat Log:**
    Untuk melihat *output* log dari aplikasi di dalam *container*, gunakan:
    ```bash
    docker logs -f aggregator-app
    ```
    Tekan `Ctrl + C` untuk berhenti.

5.  **(Opsional) Menghentikan Container:**
    Untuk menghentikan dan menghapus *container*, jalankan:
    ```bash
    docker stop aggregator-app
    docker rm aggregator-app
    ```

---

## 🤔 Asumsi

Beberapa asumsi dibuat selama pengembangan sistem ini:

1.  **Keunikan `event_id`:** Diasumsikan bahwa *publisher* bertanggung jawab untuk menghasilkan `event_id` yang unik secara global (misalnya, menggunakan UUID) dalam konteks `topic` tertentu. Keunikan ini adalah dasar dari mekanisme deduplikasi.
2.  **Format Input:** Diasumsikan *publisher* mengirimkan data *event* dalam format JSON yang sesuai dengan skema yang ditentukan (memiliki *field* `topic`, `eventId`, `timestamp`, `source`, `payload`). Validasi skema dasar dilakukan oleh FastAPI/Pydantic.
3.  **Penyimpanan Lokal:** Basis data SQLite (`aggregator.db`) akan dibuat di dalam *container* Docker. Untuk persistensi data antar *run*, disarankan untuk menggunakan Docker Volumes (seperti contoh opsional di `docker-compose.yml` jika digunakan).
4.  **Skalabilitas Terbatas:** Desain *single-instance* dengan antrean internal memiliki batas skalabilitas. Untuk *throughput* yang sangat tinggi, arsitektur dengan *message broker* eksternal (seperti RabbitMQ/Kafka) dan beberapa *worker* akan lebih sesuai.
5.  **Sinkronisasi Waktu:** Pengurutan *event* secara implisit mengandalkan `timestamp` dari *publisher*. Diasumsikan ada sinkronisasi waktu yang wajar antar *publisher* jika pengurutan lintas sumber menjadi penting.

---

## 🔌 API Endpoints

Layanan ini menyediakan *endpoint* REST API berikut:

### 1. `POST /publish`
* **Deskripsi:** Menerima satu *event* atau *batch* (daftar) *event* untuk diproses.
* **Request Body:**
    * Berupa objek JSON tunggal yang sesuai skema `Event`.
    * Atau berupa array `[]` berisi objek-objek JSON skema `Event`.
    * Skema `Event`:
        ```json
        {
          "topic": "string",
          "eventId": "string-unik", 
          "timestamp": "ISO8601 string (contoh: 2025-10-20T10:00:00Z)",
          "source": "string",
          "payload": { ... } 
        }
        ```
* **Response Sukses (200 OK):**
    ```json
    {
      "status": "ok",
      "ingested_count": <jumlah_event_diterima>
    }
    ```
* **Response Error (422 Unprocessable Entity):** Jika format JSON tidak sesuai skema.

### 2. `GET /events`
* **Deskripsi:** Mengembalikan daftar *event* unik yang telah berhasil diproses, difilter berdasarkan *topic*.
* **Query Parameter:**
    * `topic` (wajib): Nama *topic* yang ingin diambil *event*-nya. (Contoh: `/events?topic=system-logs`)
* **Response Sukses (200 OK):**
    ```json
    {
      "topic": "<nama_topic_diminta>",
      "events": [
        {
          "topic": "...",
          "event_id": "...", 
          "timestamp": "...",
          "source": "...",
          "payload": { ... } 
        },
        ... 
      ]
    }
    ```
    *(Catatan: `event_id` diubah kembali dari alias `eventId` jika ada)*

### 3. `GET /stats`
* **Deskripsi:** Menampilkan statistik operasional dari layanan aggregator.
* **Response Sukses (200 OK):**
    ```json
    {
      "uptime": "<waktu_jalan_detik> seconds",
      "received": <total_event_diterima_sejak_start>,
      "unique_processed": <total_event_unik_disimpan>,
      "duplicate_dropped": <total_event_duplikat_dibuang>,
      "topics_count": <jumlah_topic_unik_yang_tersimpan>,
      "queue_size": <jumlah_event_saat_ini_di_antrean>
    }
    ```
