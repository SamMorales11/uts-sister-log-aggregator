# Laporan Proyek UTS: Pub-Sub Log Aggregator

**Mata Kuliah:** Sistem Paralel dan Terdistribusi
**Nama:** Samuel Benedicto Siahaan
**NIM:** 11221064

---

## Abstrak

Proyek ini mengimplementasikan sebuah layanan agregator log (*log aggregator*) yang andal dan efisien menggunakan Python dan FastAPI. Sistem ini mengadopsi arsitektur *publish-subscribe* internal dengan antrean asinkron untuk menangani *event* log. Fitur utama meliputi *consumer* yang idempoten dan mekanisme deduplikasi berbasis SQLite untuk memastikan integritas data meskipun terjadi pengiriman *event* berulang. Desain ini mencerminkan prinsip-prinsip kunci sistem terdistribusi seperti *decoupling*, *eventual consistency*, dan penanganan kegagalan, yang dibahas dalam konteks teori dari buku Tanenbaum & Van Steen (2024). Aplikasi ini diuji menggunakan `pytest` dan dikemas dalam *container* Docker untuk portabilitas.

---

## 1. Pendahuluan

Dalam ekosistem perangkat lunak modern, terutama yang berbasis *microservices*, pemantauan dan analisis log dari berbagai layanan menjadi krusial untuk observabilitas. Mengumpulkan log dari sumber-sumber terdistribusi ke satu lokasi terpusat adalah fungsi inti dari *log aggregator*. Namun, membangun sistem agregasi yang andal menghadapi tantangan khas sistem terdistribusi, seperti potensi kehilangan atau duplikasi pesan akibat ketidakandalan jaringan.

Tujuan proyek ini adalah merancang dan mengimplementasikan prototipe layanan *log aggregator* yang:
* Menerima *event* log melalui API.
* Memproses *event* secara asinkron untuk menjaga responsivitas.
* Menjamin bahwa setiap *event* log unik hanya diproses **tepat satu kali** (idempotensi) meskipun diterima berulang kali.
* Menyimpan *event* unik secara persisten.

Implementasi ini secara praktis menerapkan konsep-konsep dasar sistem terdistribusi yang dijelaskan oleh Tanenbaum & Van Steen (2024), mencakup arsitektur (Bab 2), komunikasi (Bab 4), dan konsistensi (Bab 7), serta mempertimbangkan *trade-off* yang melekat dalam desainnya (Bab 1).

---

## 2. Desain Arsitektur

Sistem yang dibangun adalah sebuah layanan *log aggregator* mandiri (*self-contained*) yang berjalan dalam satu proses. Layanan ini mengadopsi arsitektur *asynchronous* berbasis *producer-consumer* internal.

### Komponen Utama
1.  **API Endpoint (`/publish`):** Pintu masuk FastAPI untuk menerima *event* log (tunggal/batch).
2.  **Antrean Internal (`asyncio.Queue`):** *Buffer* di memori untuk memisahkan *ingestion* dan *processing*, memastikan respons API yang cepat.
3.  **Background Worker:** *Task* `asyncio` yang mengambil *event* dari antrean, melakukan deduplikasi, dan menyimpan ke basis data.
4.  **Penyimpanan Persisten (`aiosqlite`):** Basis data SQLite asinkron untuk menyimpan *event* unik dan kunci deduplikasi (`(topic, event_id)`).

### Diagram Arsitektur

![Diagram Arsitektur Log Aggregator]("Diagram Arsitektur UTS Sister.png")

### Kaitan dengan Teori (Bab 2: Architectures)
Arsitektur ini menerapkan pola **Publish/Subscribe** yang disederhanakan dan **pemisahan komponen (*decoupling*)**. Meskipun *publisher* (API endpoint) dan *subscriber* (worker) berada dalam satu proses, antrean internal berfungsi sebagai *broker* sederhana yang memisahkan tanggung jawab dan alur kerja. Ini memungkinkan *endpoint* `/publish` tetap responsif tanpa menunggu pemrosesan selesai, sebuah karakteristik kunci dari arsitektur berbasis *event* (Tanenbaum & Van Steen, 2024, Bab 2).

---

## 3. Hubungan Implementasi dengan Teori (Bab 1-7)

Berikut adalah analisis bagaimana implementasi proyek ini berkaitan dengan konsep-konsep teori dari buku utama:

### T1 (Bab 1): Karakteristik Sistem Terdistribusi & Trade-off
Sistem ini menunjukkan karakteristik **transparansi akses** (klien hanya berinteraksi via API, detail penyimpanan tersembunyi) dan **skalabilitas konkurensi** (melalui pemrosesan asinkron). *Trade-off* utama adalah antara **kinerja *ingestion*** (dimaksimalkan oleh antrean) dan **konsistensi seketika** (dikorbankan demi *eventual consistency*). *Trade-off* lain adalah **reliabilitas** (dicapai via deduplikasi persisten) versus **kompleksitas sumber daya** (penggunaan basis data menambah *overhead* I/O) (Tanenbaum & Van Steen, 2024, Bab 1).

### T2 (Bab 2): Arsitektur Client-Server vs. Pub-Sub
Dibandingkan model *client-server* murni (di mana klien menunggu pemrosesan server), arsitektur Pub-Sub internal ini dipilih karena **pemisahannya (*decoupling*)**. Klien (`/publish`) tidak perlu menunggu *worker* selesai, meningkatkan **responsivitas** dan **ketahanan (*resilience*)** terhadap lonjakan beban. Jika *worker* lambat, antrean akan menampung *event*, mencegah kegagalan langsung pada klien (Tanenbaum & Van Steen, 2024, Bab 2).

### T3 (Bab 3): Semantik Pengiriman & Idempotensi
Sistem ini dirancang untuk menangani input yang mungkin berasal dari pengirim dengan semantik **`at-least-once delivery`** (karena klien mungkin melakukan *retry*). Untuk mencegah pemrosesan ganda, **`idempotent consumer`** (worker) menjadi krusial. Worker memastikan bahwa memproses *event* yang sama berkali-kali memiliki efek yang sama seperti memprosesnya sekali saja, secara efektif mencapai `exactly-once processing` pada level aplikasi (Tanenbaum & Van Steen, 2024, Bab 3).

### T4 (Bab 4): Skema Penamaan `topic` dan `event_id`
* **`topic`**: Diasumsikan menggunakan skema hierarkis (misal, `service.env.type`) untuk konteks dan fleksibilitas *query*.
* **`event_id`**: Diasumsikan unik secara global dalam konteks `topic` (misal, UUID). Keunikan `event_id` adalah **fondasi dari deduplikasi**. Jika `event_id` tidak unik, *event* yang berbeda bisa salah dibuang. Pasangan `(topic, event_id)` digunakan sebagai kunci unik di *dedup store* (Tanenbaum & Van Steen, 2024, Bab 4).

### T5 (Bab 5): Pengurutan (*Ordering*)
**`Total ordering` tidak diimplementasikan** karena dianggap tidak perlu untuk kasus penggunaan ini dan menambah kompleksitas. Sistem mengandalkan **`event_timestamp`** dari *publisher*. Pendekatan praktis ini cukup untuk banyak kasus, namun memiliki **batasan** terkait akurasi sinkronisasi jam antar *publisher* dan potensi ambiguitas urutan *event* dari sumber berbeda yang terjadi berdekatan (Tanenbaum & Van Steen, 2024, Bab 5).

### T6 (Bab 6): Mode Kegagalan & Mitigasi
* **Duplikasi Pesan:** Dimigasi oleh **`durable dedup store`** (SQLite) yang mencatat `event_id` yang sudah diproses.
* **Pesan Tidak Berurutan:** Tidak ditangani secara aktif saat *ingestion*, mengandalkan pengurutan saat *query* berdasarkan *timestamp*.
* **Kegagalan Komponen (*Crash*):** *Dedup store* yang **persisten** memastikan bahwa saat *worker* pulih dari *crash*, ia tidak akan memproses ulang *event* yang sudah selesai sebelumnya. Klien (*publisher*) dapat menggunakan **`retry`** dengan **`exponential backoff`** secara aman karena *aggregator* idempoten (Tanenbaum & Van Steen, 2024, Bab 6).

### T7 (Bab 7): Eventual Consistency
Sistem ini mengadopsi model **`eventual consistency`**. Ada jeda antara *event* diterima dan disimpan. Mekanisme **idempotensi + deduplikasi** adalah kunci untuk mencapai konsistensi ini secara andal. Dengan membuang duplikat, sistem memastikan bahwa *state* akhir (kumpulan *event* unik di DB) akan **konvergen** ke keadaan yang benar, meskipun ada gangguan atau pengiriman ulang di jaringan (Tanenbaum & Van Steen, 2024, Bab 7).

### T8 (Bab 1–7): Metrik Evaluasi & Keputusan Desain
* **`Throughput` & `Ingestion Latency`**: Dioptimalkan oleh **`asyncio.Queue`**.
* **`End-to-End Latency`**: Merupakan *trade-off* dari penggunaan antrean (mencerminkan *eventual consistency*).
* **`Duplicate Rate Handling`**: Keandalan dicapai melalui **`aiosqlite`** dengan *primary key constraint* untuk deduplikasi yang efisien dan atomik.

---

## 4. Keputusan Desain Tambahan

* **Idempotency & Dedup Store:** `aiosqlite` dipilih karena durabilitasnya (tahan *restart*), efisiensi deduplikasi via *primary key constraint* (atomik, cepat), dan sifat asinkronnya yang menjaga responsivitas aplikasi.
* **Ordering:** `Total ordering` tidak diimplementasikan demi kesederhanaan dan performa. Pengurutan mengandalkan `timestamp` dari *publisher*.
* **Retry:** Desain idempoten memungkinkan klien (*publisher*) melakukan *retry* dengan aman (disarankan dengan *exponential backoff*).

---

## 5. Analisis Performa dan Metrik

* **Throughput & Ingestion Latency:** Tinggi karena `asyncio.Queue` memisahkan *ingestion* (cepat) dari *processing* (lebih lambat, di *background*).
* **End-to-End Latency:** Ada jeda (variabel) antara *ingestion* dan ketersediaan data untuk *query*, mencerminkan model *eventual consistency*.
* **Deduplication Performance:** Sangat efisien karena menggunakan *primary key lookup* di SQLite, yang merupakan operasi cepat dan dioptimalkan oleh basis data.

---

## 6. Pengujian

Aplikasi ini dilengkapi dengan 7 *unit tests* menggunakan `pytest` dan `TestClient` dari FastAPI. Tes ini mencakup skenario:
1.  Pengiriman *event* tunggal (*happy path*).
2.  Logika deduplikasi (mengirim *event* unik dan duplikat).
3.  Fungsionalitas *endpoint* `GET /events`.
4.  Validasi skema input (mengirim data cacat).
5.  Pemrosesan *batch* besar dengan duplikat.
6.  Meminta *event* dari *topic* kosong.
7.  Mengirim *event* dengan *payload* kosong.

Semua tes berhasil dijalankan dan memastikan logika inti aplikasi berfungsi sesuai harapan.

---

## 7. Kesimpulan

Proyek ini berhasil mengimplementasikan layanan *log aggregator* sederhana namun andal menggunakan Python, FastAPI, dan aiosqlite. Dengan menerapkan mekanisme *consumer* idempoten dan deduplikasi persisten, sistem mampu menangani duplikasi *event* secara efektif dan mencapai *eventual consistency*. Keputusan desain yang diambil mencerminkan pemahaman tentang *trade-off* fundamental dalam sistem terdistribusi, seperti antara kinerja dan konsistensi. Aplikasi telah divalidasi melalui *unit testing* dan dikemas dalam *container* Docker.

---

## 8. Daftar Pustaka

* Tanenbaum, A. S., & Van Steen, M. (2024). *Distributed systems: Principles and paradigms* (4th ed.). Pearson.
* Coulouris, G., Dollimore, J., Kindberg, T., & Blair, G. (2012). Distributed systems: Concepts and design (5th ed.). Addison-Wesley.
* Brewer, E. (2012). CAP twelve years later: How the "rules" have changed. Computer, 45(2), 23–29.
* Vogels, W. (2009). Eventually consistent. ACM Queue, 7(6), 14–19.
* Lamport, L. (1978). Time, clocks, and the ordering of events in a distributed system. Communications of the ACM, 21(7), 558–565.
* Newman, S. (2021). Building microservices: Designing fine-grained systems (2nd ed.). O'Reilly Media.
