# Yerel RAG Fitness Bilgi Asistanı

Tamamen çevrimdışı çalışan, Microsoft Foundry Local üzerinde yerel bir LLM ve embedding
modeliyle çalışan bir RAG (Retrieval-Augmented Generation) soru-cevap asistanı. Kullanıcı
egzersiz/fitness hareketleri hakkında soru sorar; sistem yalnızca `docs/` klasöründeki
belgelerde geçen bilgilerle cevap verir, internete hiç bağlanmaz.

Bu proje, Microsoft Tech Community'nin ["Building Your First Local RAG Application with
Foundry Local"](https://techcommunity.microsoft.com/blog/azuredevcommunityblog/building-your-first-local-rag-application-with-foundry-local/4501968)
yazısı temel alınarak hazırlanan bir öğrenim programının (bkz. proje planı PDF'i) uygulama
projesidir.

## İçindekiler

- [Mimari](#mimari)
- [Kurulum](#kurulum)
- [Kullanım](#kullanım)
- [Proje Yapısı](#proje-yapısı)
- [Tasarım Kararları ve Öne Çıkan Özellikler](#tasarım-kararları-ve-öne-çıkan-özellikler)
- [Bilinen Sınırlamalar](#bilinen-sınırlamalar)
- [Test](#test)
- [Veri Kaynağı](#veri-kaynağı)

## Mimari

```
┌─────────────┐     ┌─────────────┐
│   app.py    │     │  arayuz.py  │   İki farkli arayuz, ayni mantigi kullanir
│    (CLI)    │     │ (Streamlit) │
└──────┬──────┘     └──────┬──────┘
       │                   │
       └─────────┬─────────┘
                  ▼
             ┌─────────┐
             │  rag.py │   Retrieval, prompt olusturma, model yukleme,
             └────┬────┘   cevap temizligi -- TEK ortak modul
                  │
         ┌────────┴────────┐
         ▼                 ▼
  ┌─────────────┐   ┌──────────────┐
  │knowledge.db │   │Foundry Local │   Embedding + sohbet modelleri,
  │  (SQLite)   │   │   (yerel)    │   tamamen cihaz uzerinde calisir
  └─────────────┘   └──────────────┘
         ▲
         │
  ┌─────────────┐
  │  ingest.py  │   docs/*.md -> parcala -> embed et -> SQLite'a yaz
  └─────────────┘
         ▲
         │
    ┌─────────┐
    │docs/*.md│   Kaynak belgeler (5 dosya, hareket bilgileri)
    └─────────┘
```

RAG akışı: **Retrieve** (soru embedding'e çevrilir, kosinüs benzerliğiyle en alakalı
parçalar bulunur) → **Augment** (bulunan parçalar sistem promptuna gömülür) →
**Generate** (yerel LLM cevabı üretir, kod tarafında doğrulanıp temizlenir).

## Kurulum

1. Python 3.11+ ve bir sanal ortam (bu projede `.venv` kullanıldı):
   ```powershell
   python -m venv .venv
   .venv\Scripts\Activate.ps1
   ```
2. Bağımlılıkları kurun:
   ```powershell
   pip install -r requirements.txt
   ```
   Foundry Local SDK ilk çalıştırmada gerekli çalışma zamanı bileşenlerini (execution
   provider'lar) otomatik indirir; bunun için tek seferlik bir internet bağlantısı
   gerekir. Model indirmeleri de ilk kullanımda otomatik yapılır (birkaç GB olabilir).

## Kullanım

**1) Veritabanını oluşturun (bir kez, ya da `docs/` değiştiğinde tekrar):**
```powershell
python ingest.py
```
Bu, `docs/` klasöründeki `.md` dosyalarını okuyup parçalara böler, her parça için
embedding üretir ve `knowledge.db` (SQLite) dosyasına yazar.

**2) Asistanı çalıştırın — iki arayüzden biriyle:**

Komut satırı:
```powershell
python app.py
```

Web arayüzü (Streamlit):
```powershell
streamlit run arayuz.py
```
Tarayıcıda otomatik olarak `http://localhost:8501` açılır.

İkisi de aynı `knowledge.db` ve aynı `rag.py` mantığını kullanır; ayarları (model,
`TOP_K`, benzerlik eşiği vb.) `rag.py`'de değiştirmek her iki arayüzü birden etkiler.

## Proje Yapısı

| Dosya | Açıklama |
|---|---|
| `rag.py` | **Ortak RAG mantığı.** Retrieval (`find_relevant`), kas grubu/ekipman filtreleri, `SYSTEM_PROMPT`, model yükleme (`load_models`), cevap üretme ve temizleme (`answer_query`, `clean_model_response`). Hem `app.py` hem `arayuz.py` buradan import eder — kod hiçbir yerde kopyalanmaz. |
| `app.py` | Komut satırı arayüzü. `rag.py`'yi kullanan ince bir girdi/çıktı döngüsü. |
| `arayuz.py` | Streamlit web arayüzü. Model ve veri yüklemesi `@st.cache_resource` / `@st.cache_data` ile önbelleklenir; aşama bazlı süre ölçümü (embedding, vektör arama, LLM üretimi, model yükleme) gösterir. |
| `ingest.py` | Veri hazırlama betiği: `docs/*.md` dosyalarını okur, başlık bazlı ve boyut sınırlı (overlap'li) parçalara böler, her parça için embedding üretir, `hedef_bolge`/`ekipman` metadata'sını ayrıştırır, hepsini `knowledge.db`'ye yazar. |
| `docs/` | Kaynak belgeler (5 dosya): `bacak-hareketleri.md`, `sirt-hareketleri.md`, `kol-hareketleri.md`, `gogus-omuz-hareketleri.md`, `karin-hareketleri.md`. |
| `knowledge.db` | `ingest.py` çıktısı — parçalar, embedding'ler ve metadata (SQLite). |
| `requirements.txt` | Python bağımlılıkları. |
| `kontrol.py` | Yardımcı araç: `knowledge.db`'deki tüm parçaları (id, kaynak, tam metin) sırayla ekrana yazdırır — veri kontrolü için. |
| `hello.py`, `models.py` | Geliştirme sürecinin başındaki keşif betikleri: Foundry Local kurulumunu doğrulayan minimal bir "Hello Model" testi (`hello.py`) ve kataloğa kayıtlı tüm modelleri listeleyen bir araç (`models.py`). Uygulamanın bir parçası değiller, öğrenme sürecinin kanıtı olarak bırakıldı. |
| `app_yedek.py` | `app.py`'nin, `rag.py`'ye bölünmeden önceki tek-dosyalı ilk hali — referans/yedek olarak saklanıyor. |
| `TEST_SONUCLARI.md` | Fonksiyonel test kayıtları ve geliştirme sürecinde bulunup düzeltilen hatalar. |

## Tasarım Kararları ve Öne Çıkan Özellikler

Bu proje, temel RAG döngüsünün (embed → ara → üret) ötesinde, **küçük yerel modellerin
güvenilirliğini artırmaya** odaklanan bir dizi ek katman içeriyor:

- **Yapılandırılmış filtreleme**: Kas grubu (`hedef_bolge`) ve ekipman (`ekipman`)
  bilgisi `ingest.py` tarafından her parçadan ayrıştırılıp ayrı sütunlarda saklanıyor.
  Kullanıcı sorusundan bu filtreler kelime-sınırı (regex `\b`) ile tespit edilip
  (`detect_target_region`, `detect_target_equipment`) saf embedding aramasından önce
  uygulanıyor — bu, sadece semantik benzerliğe güvenmekten çok daha isabetli sonuç
  veriyor.
- **Kod seviyesinde grounding (dayanak) doğrulaması**: Modelin ürettiği cevaptaki her
  hareket adı ve kaynak dosya adı, modelin kendi metnine güvenilmeden, retrieval'in
  gerçekten döndürdüğü verilerle karşılaştırılıp doğrulanıyor (`clean_model_response`,
  `_filter_ungrounded_sections`). Model tamamen uydurma bir hareket adı yazarsa, bu
  hiçbir zaman kullanıcıya gösterilmiyor.
- **Çok katmanlı tekrar/bozulma temizliği**: Küçük modeller bazen kelime öbeği
  döngülerine, kekelemeye, cümle tekrarına ya da anlamsız "kelime çorbası" üretimine
  girebiliyor. Bunların her biri için ayrı, test edilmiş bir temizleyici var (bkz.
  `TEST_SONUCLARI.md`'deki hata listesi).
- **Son çare olarak ham veri gösterimi**: Model hiçbir gerçek başlığı doğru
  kullanamazsa, kullanıcıya yanlış "bilgi yok" mesajı göstermek yerine, retrieval'in
  bulduğu gerçek veri doğrudan (modelin yorumu hiç araya girmeden) gösteriliyor
  (`_format_raw_results`).
- **İki arayüz, tek mantık**: `app.py` ve `arayuz.py`, RAG mantığının tamamını
  `rag.py`'den paylaşıyor; hiçbir işlem iki yerde ayrı ayrı yazılmadı.

## Bilinen Sınırlamalar

- **Cevap süresi**: Bu makinede (CPU, GPU hızlandırma yok) ortalama cevap süresi
  ~130-170 saniye civarında. Proje planındaki "~1-3 saniye" beklentisinin çok
  üzerinde. Nedeni: `phi-4-mini` (~3.8B parametre) modeli CPU üzerinde çalışıyor ve bu
  donanımda GPU/NPU hızlandırma seçeneği yok. Daha küçük modeller (`qwen3-0.6b`,
  `qwen2.5-0.5b`, `qwen3-1.7b`) denendi; ya kalite ciddi şekilde bozuldu (halüsinasyon,
  sistem promptunu geri kusma) ya da belirgin bir hız kazancı sağlamadı — bu yüzden
  güvenilirlik hız yerine tercih edildi. Detaylar için `TEST_SONUCLARI.md`.
- **Küçük veri kümesi için brute-force arama**: `find_relevant`, tüm parçalar
  üzerinde kosinüs benzerliğini Python döngüsüyle hesaplıyor. Bu veri boyutunda
  (117 parça) sorun değil; binlerce belgeye ölçeklenirken FAISS/Chroma/sqlite-vec
  gibi bir vektör indeksine geçmek gerekir.
- **Tek dilli, tek alanlı**: Sistem sadece Türkçe ve sadece fitness/egzersiz alanına
  özel olarak ayarlandı (anahtar kelime sözlükleri, sistem promptu).

## Test

Fonksiyonel test senaryoları, sonuçları ve geliştirme sürecinde bulunup düzeltilen
hatalar için bkz. **[TEST_SONUCLARI.md](TEST_SONUCLARI.md)**.

## Veri Kaynağı

Belgelerin içeriği [megaGymDataset](https://www.kaggle.com/datasets/niharika41298/gym-exercise-data)
(Kaggle, CC0 Public Domain) veri kümesinden alınıp Türkçeye uyarlanmıştır.
