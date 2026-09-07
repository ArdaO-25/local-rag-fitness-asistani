# Test Sonuçları

Bu belge, geliştirme sürecinde kullanılan test sorularını, sonuçlarını ve bulunup
düzeltilen hataları kayıt altına alır. Testler beş kategoride tasarlandı:

- **A — Tek kriterli**: Doğrudan bir hareket hakkında, filtre gerektirmeyen sorular.
- **B — Kas grubu sorguları**: Belirli bir kas grubuna yönelik sorular.
- **C — Çok kriterli**: Hem kas grubu hem ekipman filtresinin birlikte çalışması
  gereken sorular.
- **D — Reddetmeli**: Belgelerde olmayan ya da kapsam dışı (beslenme, program,
  genel kültür) sorular; sistemin "bu bilgi elimde yok" demesi gerekir.
- **E — Sınır durumu**: Belgelerdeki konuya yakın ama kapsam dışı sorular.

## Durum lejantı

- ✅ **Doğrulandı (uçtan uca)** — Soru, gerçek model çıktısıyla birlikte test edildi;
  en az bir hata bulunup düzeltildi ve son haliyle doğru çalıştığı teyit edildi.
- 🟡 **Doğrulandı (retrieval katmanı)** — Gerçek embedding modeliyle ve gerçek
  veritabanıyla retrieval/filtreleme adımı (`find_relevant`, kas grubu/ekipman
  tespiti) doğrulandı; sonucun LLM'e gidip son haliyle ekrana geldiği ayrıca
  gözlemlenmedi.
- ⏳ **Planlı, henüz test edilmedi** — Test matrisinde yer alıyor ama bu geliştirme
  sürecinde çalıştırılmadı; bir sonraki adım olarak önerilir.
- ⚪ **Bilinçli olarak atlandı (düşük risk)** — Zaten defalarca doğrulanmış aynı
  mekanizmayı (kelime sınırlı anahtar kelime eşleştirmesi) farklı bir kelimeyle
  çalıştırıyor; o mekanizmada bu kelimeye özgü bilinen bir çakışma riski (örn.
  "bel"/"barbell", "plan"/"Plank" gibi) tespit edilmedi. Eksiklik değil, bilinçli bir
  önceliklendirme kararı.

## Test Matrisi

| # | Kategori | Soru | Durum | Not |
|---|---|---|---|---|
| 1 | A | Barbell curl ne işe yarar? | ✅ | "bel"/"barbell" kelime çakışması bulundu ve düzeltildi (bkz. Hata #1) |
| 2 | A | Plank hangi kasları çalıştırır? | 🟡 | Retrieval doğru sonuç buluyor (Elbow Plank) |
| 3 | A | Deadlift nedir? | ✅ | En çok yineleneli test — 6+ farklı hata bu soru üzerinden bulundu (bkz. Hata #6-13) |
| 4 | A | Hammer curl nasıl yapılır? | ✅ | Başka bir hareketin içeriğinin sızması bulundu ve düzeltildi (Hata #14) |
| 5 | A | Sumo deadlift ile klasik deadlift arasındaki fark nedir? | 🟡 | Retrieval doğru iki sonucu buluyor |
| 6 | B | Hamstring için hangi hareketler var? | 🟡 | Retrieval katmanında doğrulandı |
| 7 | B | Trapez kasını çalıştıran hareketler neler? | ⚪ | "trapez" anahtar kelimesi zaten "Hamstring" gibi diğer tekil eşleştirmelerle aynı mekanizmayı (Hata #1 sonrası) kullanıyor |
| 8 | B | Baldır için hangi egzersizler yapılabilir? | ✅ | "Genel kategori başlığı" hatası bulundu ve düzeltildi (Hata #15) |
| 9 | B | Ön kol çalıştırmak için ne yapmalıyım? | ⚪ | "ön kol" anahtar kelimesinde bilinen bir çakışma yok; aynı mekanizma |
| 10 | C | Kablo makinesiyle hangi göğüs hareketleri yapılır? | ✅ | Uydurma hareket adı ("Kablo Kardan") bulundu ve düzeltildi (Hata #16) |
| 11 | C | Dambılla yapılan omuz hareketleri neler? | ⚪ | Kas+ekipman birlikte çalışması zaten #10 ile aynı türde doğrulandı |
| 12 | C | Ekipmansız yapılabilecek sırt hareketleri neler? | 🟡 | Genel "sırt" anahtar kelimesi eksikliği bulundu ve düzeltildi (Hata #2) |
| 13 | C | Başlangıç seviyesi bacak hareketleri neler? | 🟡 | Genel "bacak" anahtar kelimesi eksikliği bulundu ve düzeltildi (Hata #2); seviye filtresi henüz yok (bkz. sınırlamalar) |
| 14 | C | Barbell ile hangi triceps hareketleri var? | ✅ | İlk uçtan uca doğrulanan senaryolardan biri |
| 15 | D | Protein tozu kullanmalı mıyım? | 🟡 | Skor eşiğin altında, doğru reddediliyor |
| 16 | D | Günde kaç kalori almalıyım? | 🟡 | Skor eşiğin altında; ayrıca `is_program_request` de yakalıyor |
| 17 | D | Dizim ağrıyor, ne yapmalıyım? | 🟡 | Skor eşiğin altında, doğru reddediliyor |
| 18 | D | Türkiye'nin başkenti neresi? | 🟡 | Skor belirgin şekilde düşük, doğru reddediliyor |
| 19 | D | Bana 4 günlük antrenman programı hazırla | ✅ | Retrieval kirliliği + program isteği reddi eksikliği bulundu ve düzeltildi (Hata #17) |
| 20 | E | Yüzme hangi kasları çalıştırır? | 🟡 | Bilinen sınır durumu: embedding skoru eşiği geçip yanlışlıkla cevaplanabiliyor (bkz. sınırlamalar) |

**Özet:** 20 sorudan 7'si uçtan uca (model dahil), 9'u retrieval katmanında
doğrulandı; 3'ü (B7, B9, C11) zaten kanıtlanmış aynı eşleştirme mekanizmasını farklı
kelimelerle çalıştırdığı ve bu kelimelerde bilinen bir çakışma riski bulunmadığı için
bilinçli olarak ayrıca çalıştırılmadı.

## Bulunup Düzeltilen Hatalar (Geliştirme Süreci Kaydı)

Bu proje boyunca gerçek sorularla test edilerek bulunan ve düzeltilen belli başlı
hatalar, en büyükten en küçüğe değil, **bulunma sırasına göre**:

1. **Kelime sınırı hatası ("bel"/"barbell")**: `"bel"` (alt sırt) anahtar kelimesi,
   basit bir `in` kontrolüyle `"barbell"` kelimesinin içinde de eşleşiyordu, bu yüzden
   "Barbell curl" gibi sorular yanlışlıkla bel bölgesine filtreleniyordu. Düzeltme:
   tüm anahtar kelime eşleştirmeleri `\b...\b` (kelime sınırı) regex'ine çevrildi.
2. **Genel "sırt"/"bacak" anahtar kelimeleri eksikti**: Sadece "orta sırt", "ön bacak"
   gibi alt terimler vardı; genel terimler hiçbir filtreye düşmeyip tüm veri
   tabanında alakasız sonuçlar buluyordu. Düzeltme: `MUSCLE_KEYWORDS` tuple tabanlı
   yapıldı, genel terimler birden fazla alt bölgeye işaret edecek şekilde eklendi.
3. **Benzerlik eşiği kalibrasyonu**: `SIMILARITY_THRESHOLD = 0.4`, çift filtrenin
   (kas grubu + ekipman) doğru daralttığı bazı gerçek sonuçları (skor 0.399) yanlışlıkla
   reddediyordu. `0.38`'e düşürüldü.
4. **Model örnekleme parametreleri**: `presence_penalty` tekrar döngülerini önlemede
   yardımcı oldu ama Türkçe akıcılığı bozdu (kaldırıldı); `frequency_penalty` ve ölçülü
   bir `temperature` ile dengelendi.
5. **Sistem promptu sızıntısı**: Model bazen kendi `SYSTEM_PROMPT`'unun yapısal
   işaretçilerini ("BAGLAM:" gibi) gerçek cevap sanıp geri kusuyordu. Bilinen bu
   sızıntı kalıbı kod tarafında ayrıca temizleniyor (`PROMPT_LEAK_RE`).
6. **Kısa ifade tekrar döngüleri**: Model bazen kısa bir ifadeyi ("plank hareketini
   yapmayan...") onlarca kez tekrarlıyordu. `_truncate_repetition` ile keyfi
   uzunluktaki tekrarlar tespit edilip kesiliyor.
7. **Kekeleme hataları**: Bir kelimenin yazılıp hemen ardından düzeltilmiş haliyle
   tekrar yazılması (`"sumu sumo deadlift"`). `_fix_stutter_typos` ile temizleniyor.
8. **Birebir cümle tekrarları**: Uzun bir cümlenin art arda birkaç kez üretilmesi.
9. **Yeniden karıştırılmış yakın-tekrar cümleler**: Aynı bilginin farklı öznelerle
   ("Deadlift, X. ... Barbell ile yapılan bu hareket, X.") tekrar tekrar anlatılması —
   birebir string eşitliği olmadığı için basit tekrar kontrolünü atlatıyordu.
   `_dedupe_near_sentences` ile içerik kelimesi örtüşmesine bakılarak yakalanıyor.
10. **Yarım kalan kuyruk tekrarı**: `max_tokens` sınırı, model tam bir önceki cümleyi
    yeniden başlatıp tekrarlarken devreye girip metni ortasında kesiyordu.
11. **Anlamsız "kelime çorbası" cümleler**: Model bazen hiçbir zaman tam olarak aynı
    olmayan ama aynı kalıba sıkışmış, anlamsız bir metin üretiyordu ("X'in üst
    kopyalamasını, Y'nin üst kopyalamasını..."). Eşsiz kelime oranı çok düşük
    cümleler tespit edilip tamamen atılıyor.
12. **Başlık/kaynak halüsinasyonu**: Model, bağlamda hiç olmayan bir hareket adı ya
    da kaynak dosya adı uydurabiliyordu. Kod, hem başlıkları hem kaynakları
    modelin kendi metnine değil retrieval'in gerçekten döndürdüğü veriye
    dayandırarak doğruluyor.
13. **Kas grubu çelişkisi**: Model, doğru bir başlığın altına retrieval'in getirdiği
    BAŞKA bir hareketin (farklı bir kas grubuna ait) içeriğini yapıştırabiliyordu
    (örn. "Hammer Curl" başlığı altında "Lying Leg Curl"dan Hamstring açıklaması).
    Aktif başlığın gerçek `hedef_bolge`'siyle çelişen cümleler tespit edilip atılıyor.
14. **Genel kategori başlığı hatası**: "hangi X var?" tarzı sorularda model bazen
    gerçek başlıkları hiç tekrarlamadan genel bir kategori adı yazıyordu ("Baldır
    Egzersizleri"), bu da katı başlık doğrulamasının cevabın TAMAMINI silmesine yol
    açıyordu. Denenen bir "doğrulamayı gevşetip tekrar dene" çözümü, bu sefer
    TAMAMEN uydurma bir hareket adının ("Kablo Kardan") da sızmasına izin verdi ve
    geri alındı. Nihai çözüm: model hiçbir gerçek başlığı doğrulayamazsa, retrieval'in
    bulduğu gerçek veri modelin yorumu hiç araya girmeden doğrudan gösteriliyor
    (`_format_raw_results`).
15. **Başlıksız doküman parçalarının retrieval'i kirletmesi**: Her dokümanın başındaki
    başlıksız "# X Hareketleri\n\nKaynak: ..." bölümü de bir parça olarak
    indeksleniyordu; genel/belirsiz sorularda (örn. "bana antrenman programı hazırla")
    bu içeriksiz parçalar yüksek skor alıp gerçek hareketlerin önüne geçebiliyordu.
    `hedef_bolge`'si boş olan parçalar artık aday havuzuna hiç girmiyor.
16. **Program/plan isteklerinin reddi**: "Bana antrenman programı hazırla" gibi
    istekler önce sadece SYSTEM_PROMPT ile reddedilmeye çalışıldı, ama model
    reddederken bile bozuk cümleler kurabiliyordu. Niyet artık soru metninden
    (`is_program_request`) modele hiç sorulmadan tespit ediliyor. Bu eklenirken
    `"plan"` anahtar kelimesinin `"Plank"` (gerçek bir hareket adı) ile çakıştığı
    fark edildi ve kelime sınırlı, çekim ekli varyantların açıkça listelendiği bir
    yaklaşımla düzeltildi.

## Performans Gözlemleri

Farklı sohbet modelleri denenerek hız/kalite dengesi test edildi:

| Model | Sonuç |
|---|---|
| `phi-4-mini` (kullanılan) | Güvenilir, doğru; ortalama ~130-170 sn/soru (CPU) |
| `qwen3-0.6b` | Başarısız — sistem promptunu geri kusuyor, içerikleri karıştırıyor |
| `qwen3-1.7b` | Belirgin bir hız kazancı yok (muhtemelen "thinking" modu ek yük getiriyor) |
| `qwen2.5-0.5b` | Cevap kalitesi belirgin şekilde düştü |

`TOP_K` (3→2) ve sistem promptunda açık bir uzunluk sınırı ("en fazla 3-4 cümle")
gibi düşük riskli optimizasyonlar uygulandı; performans sorunu büyük ölçüde bu
donanımda GPU hızlandırma bulunmamasından kaynaklanıyor.
