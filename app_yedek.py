"""
app.py — Yerel RAG soru-cevap asistani (CLI).

Onkosul: once `python ingest.py` calistirilmis ve knowledge.db olusmus olmali.
Kullanim: python app.py
"""

import json
import math
import re
import sqlite3

from foundry_local_sdk import Configuration, FoundryLocalManager

DB_PATH = "knowledge.db"
EMBED_MODEL = "qwen3-embedding-0.6b"
CHAT_MODEL = "phi-4-mini"
TOP_K = 2                      # modele kac parca verilecek

# En iyi eslesmenin kosinus benzerligi bu esigin altindaysa, bulunan
# parcalar soruyla alakasiz sayilir ve model hic cagrilmadan dogrudan
# "bilgi yok" cevabi verilir. Boylece model, alakasiz baglami zorlayip
# uydurma (halusinasyon) yapma riskine girmez.
# 0.4 degil 0.38: gercek test sorgularinda ("sırt" + "ekipmansız" gibi
# hem kas grubu hem ekipman filtresinin birlikte dogru sekilde daralttigi
# durumlarda) alakali sonuclar 0.40'in az altinda (0.399) kalip yanlislikla
# reddediliyordu. Filtreler zaten konu alakasini sagladigi icin, esigi
# hafifce dusurmek guvenli -- D kategorisindeki (alakasiz) sorularin
# skorlari (~0.30-0.36) bu esigin hala rahatça altinda kaliyor.
SIMILARITY_THRESHOLD = 0.38

# Soruda gecen kas grubu kelimesini, veritabanindaki hedef_bolge
# degeriyle eslestirmek icin kullanilir. Birden fazla anahtar kelime
# ayni hedef bolgeye isaret edebilir (es anlamli / yazim varyasyonu).
# Degerler tuple: "sırt" ve "bacak" gibi genel terimler birden fazla
# alt-bolgeye (Latissimus, Trapez, Bel... / Quadriceps, Hamstring...)
# birden isaret eder -- tipki EQUIPMENT_KEYWORDS'teki gibi.
# NOT: daha spesifik anahtar kelimeler ("orta sırt", "ön bacak") dict'te
# genel olanlardan ("sırt", "bacak") ONCE geliyor -- detect fonksiyonu
# ilk eslesende durdugu icin, "orta sırt hareketleri" gibi bir soruda
# spesifik olan kazanmali, genel "sırt" filtresine dusmemeli.
MUSCLE_KEYWORDS = {
    "biceps": ("biceps",),
    "triceps": ("triceps",),
    "ön kol": ("ön kol",),
    "önkol": ("ön kol",),
    "göğüs": ("göğüs",),
    "omuz": ("omuz",),
    "trapez": ("trapez",),
    "latissimus": ("latissimus",),
    "kanat": ("latissimus",),
    "orta sırt": ("orta sırt",),
    "bel": ("bel",),
    "sırt": ("latissimus", "orta sırt", "trapez", "bel"),
    "quadriceps": ("quadriceps",),
    "ön bacak": ("quadriceps",),
    "hamstring": ("hamstring",),
    "arka bacak": ("hamstring",),
    "bacak": ("quadriceps", "hamstring", "gluteal", "baldır", "adduktor", "abduktor"),
    "gluteal": ("gluteal",),
    "kalça": ("gluteal",),
    "baldır": ("baldır",),
    "karın": ("karın",),
    "adduktor": ("adduktor",),
    "abduktor": ("abduktor",),
}

# Soruda gecen ekipman kelimesini, veritabanindaki GERCEK ekipman
# degerleriyle (bkz. "SELECT DISTINCT ekipman FROM chunks") eslestirir.
# Bir anahtar kelime birden fazla degere karsilik gelebilir -- orn.
# "barbell" hem duz barbell hem EZ bar hem de landmine aparatiyla
# yapilan hareketleri kapsasin diye uc degere birden isaret eder.
EQUIPMENT_KEYWORDS = {
    "barbell": ("Barbell", "EZ bar", "Barbell ve landmine aparatı"),
    "dambıl": ("Dambıl",),
    "kablo": ("Kablo makinesi",),
    "makine": ("Makine",),
    "kettlebell": ("Kettlebell",),
    "vücut ağırlığı": ("Vücut ağırlığı",),
    "ekipmansız": ("Vücut ağırlığı",),
}

SYSTEM_PROMPT = """Sen bir fitness bilgi asistanisin. Resmi ve dogrudan bir
uslup kullan; "bırak", "hadi", "yani" gibi gunluk konusma dili doldurma
ifadeleriyle cevaba baslama.

BAGLAM bolumu, arama sistemi tarafindan soruyla ilgili olacak sekilde
ONCEDEN filtrelenmistir. BAGLAM'da bir hareket varsa, onu soruyla ilgili
kabul et; ekipman veya kas grubu adinin kullanicinin sorusundaki kelimeyle
birebir ayni yazilip yazilmadigini kendi basina tekrar kontrol etme veya bu
yuzden reddetme (orn. "EZ bar" barbell ailesinden sayilir; "Barbell ile"
sorusuna EZ bar hareketleriyle cevap verilir, sadece tam olarak hangi
ekipmanla yapildigini belirtirsin).

Soruyla ilgili bir hareket varsa, o hareketi anlat. Baglamda tam olarak
sorulan detay olmasa bile, eldeki bilgiyi paylas. Boyle bir hareket
BAGLAM'da hic yoksa: "Bu bilgi elimdeki belgelerde yok." yaz.

Kullanici senden bir antrenman PROGRAMI, plan, rutin veya beslenme/kalori
tavsiyesi olusturmani isterse bunu YAPMA -- sen sadece BAGLAM'daki
bireysel hareketler hakkinda soruları yanitlayan bir bilgi asistanisin,
program hazirlayan bir kocsun. Boyle bir istekte: "Ben antrenman programi
hazirlayamam, sadece belgelerdeki hareketler hakkinda bilgi verebilirim."
yaz ve BAGLAM'da ne olursa olsun baska hicbir sey ekleme.

Sadece baglamda gecen hareket adlarini kullan. Baglamda olmayan hareket adi yazma.

Hangi kas grubunu veya ekipmani hedefledigini SADECE BAGLAM metninde acikca
yazandan al. "Hedef bölge:" satirinda veya aciklama metninde gecmeyen
BASKA bir kas grubu, kas adi (orn. biceps, triceps, gluteus) veya ekipman
ekleme -- bunlar dogru gibi görünse bile, BAGLAM'da yoksa uydurmadir ve
yasaktir. Genel spor bilgini kullanarak "muhtemelen bu kaslari da calistirir"
diye ek bilgi katma.

Cevabinda gecen her hareket adi, baglamda "## " ile baslayan bir baslikta
birebir yaziyor olmali. Baglamda o baslik yoksa o hareketi yazma. Hareket
adini basliktan HARF HARF, kisaltmadan veya baska bir hareketin adiyla
birlestirmeden aynen kopyala.

Cevabini tek, akici bir metin olarak, KENDI CUMLELERINLE yaz. BAGLAM'daki
"[kaynak: dosya_adi]" satirini, "Hedef bölge: ... Ekipman: ... Seviye: ..."
metadata satirini veya "## " basligini oldugu gibi kopyalayip cevabina
yapistirma -- bunlar BAGLAM'in kendi bicimlendirmesidir, senin cevabinin
bicimlendirmesi degil. Kaynagi sadece cevabinin en sonunda, TEK SEFERDE
belirt.

Ornek -- BAGLAM'da su blok varsa:
[kaynak: kol-hareketleri.md]
## EZ-Bar Skullcrusher

Hedef bölge: Triceps. Ekipman: EZ bar. Seviye: Orta.

EZ-bar skullcrusher, triceps kaslarini hedefleyen popüler bir harekettir...

YANLIS cevap (bloğu oldugu gibi kopyalamak):
"[kaynak: kol-hareketleri.md]
## EZ-Bar Skullcrusher
Hedef bölge: Triceps. Ekipman: EZ bar. Seviye: Orta. ..."

DOGRU cevap (kendi cumlelerinle ozetlemek):
"EZ-Bar Skullcrusher, EZ bar ile yapilan orta seviye bir triceps hareketidir.
[kaynak: kol-hareketleri.md]"

BAGLAM'da acikca yazmayan hicbir dosya adini kaynak olarak gosterme; sadece
BAGLAM'da gordugun dosya adlarini kullan. Kisa ve oz cevap ver.

BAGLAM:
{context}"""


def cosine_similarity(a, b):
    """Iki vektor arasindaki kosinus benzerligi. 1'e yakin = cok benzer."""
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(x * x for x in b))
    return dot / (norm_a * norm_b) if norm_a and norm_b else 0.0


def load_chunks(db_path=DB_PATH):
    """Tum parcalari ve vektorlerini bellege alir.

    Kucuk veri setleri icin bu yeterli ve en anlasilir yontem.
    Binlerce belgede calisan bir sistem icin FAISS / Chroma / sqlite-vec
    gibi bir vektor indeksine gecmek gerekir -- raporda bunu tartisin.
    """
    conn = sqlite3.connect(db_path)
    rows = conn.execute(
        "SELECT id, source, content, embedding, hedef_bolge, ekipman FROM chunks"
    ).fetchall()
    conn.close()

    if not rows:
        raise SystemExit("Veritabani bos. Once 'python ingest.py' calistirin.")

    return [
        {
            "id": r[0],
            "source": r[1],
            "content": r[2],
            "embedding": json.loads(r[3]),
            "hedef_bolge": r[4] or "",
            "ekipman": r[5] or "",
        }
        for r in rows
    ]


def _find_keyword_match(query, keyword_map):
    """query icinde keyword_map anahtarlarindan KELIME SINIRI ile eslesen
    ilkini bulup karsilik gelen degeri dondurur. Eslesme yoksa None doner.

    Kelime siniri (\\b) onemli: basit bir "substring iceriyor mu" kontrolu
    ("keyword in query") kisa anahtar kelimelerde yanlis pozitiflere yol
    aciyordu -- orn. "bel" (bel/alt sirt) kelimesi "barbell" kelimesinin
    ICINDE geciyor (bar-BEL-l), bu yuzden "Barbell curl ne ise yarar?"
    gibi bir soru yanlislikla "bel" bolgesine filtrelenip tamamen alakasiz
    (deadlift/rack pull gibi) sonuclar donduruyordu. \\b bu tur "bir
    kelimenin ortasina sikismis anahtar kelime" durumlarini engeller.
    """
    query_lower = query.lower()
    for keyword, value in keyword_map.items():
        if re.search(rf"\b{re.escape(keyword)}\b", query_lower):
            return value
    return None


def detect_target_region(query):
    """Sorudaki kas grubu anahtar kelimesini bulup MUSCLE_KEYWORDS uzerinden
    karsilik gelen hedef_bolge deger(ler)ini (tuple) dondurur. Eslesme
    yoksa None doner.
    """
    return _find_keyword_match(query, MUSCLE_KEYWORDS)


def detect_target_equipment(query):
    """Sorudaki ekipman anahtar kelimesini bulup EQUIPMENT_KEYWORDS uzerinden
    karsilik gelen ekipman deger(ler)ini (tuple) dondurur. Eslesme yoksa
    None doner.
    """
    return _find_keyword_match(query, EQUIPMENT_KEYWORDS)


# Kullanicinin bir antrenman programi/plani, beslenme veya kalori
# tavsiyesi istedigini tespit etmek icin kullanilir (bkz. is_program_request).
# Yaygin cekimli halleri ACIKCA listeliyoruz (genel bir on-ek/prefix kurali
# yerine) -- cunku prefix eslesmesi "plan" gibi kisa bir kok icin "Plank"
# (gercek bir hareket adi!) ile carpisiyordu. Her biri asagida TAM kelime
# siniriyla (\\b...\\b) aranir, bu yuzden "Plank" kelimesindeki "plan" onekine
# yanlislikla eslesmez.
PROGRAM_REQUEST_KEYWORDS = (
    "program", "programı", "programa", "programlar", "programını",
    "plan", "planı", "planlar", "planlama",
    "rutin", "rutini", "rutinler",
    "diyet", "diyeti",
    "beslenme", "beslenmesi",
    "kalori", "kalorisi",
)


def is_program_request(query):
    """Kullanici bir antrenman programi/plani/rutini veya beslenme-kalori
    tavsiyesi istiyorsa True doner.

    Boyle bir istekte modeli hic cagirmadan dogrudan "bilgi yok" mesaji
    gosteririz (main()'de SIMILARITY_THRESHOLD kontrolüyle ayni sekilde).
    Bunun nedeni: SYSTEM_PROMPT'a "boyle bir istegi reddet" diye bir kural
    eklemistik, ama model reddederken bile kendi cumlelerini kurarken
    bozuk/tekrarli metin uretebiliyordu (orn. "Baglam'da 4 günlük antren"
    diye yarida kesilen bir cumle). Niyeti sorunun kendisinden -- modele
    hic sormadan -- tespit etmek, tutarli ve her zaman ayni (sabit)
    NO_INFO_MESSAGE'i gostermemizi saglar.
    """
    query_lower = query.lower()
    return any(
        re.search(rf"\b{re.escape(kw)}\b", query_lower) for kw in PROGRAM_REQUEST_KEYWORDS
    )


def find_relevant(
    query_embedding, chunks, top_k=TOP_K, target_region=None, target_equipment=None
):
    """Sorguya en yakin top_k parcayi (skoruyla birlikte) dondurur.

    target_region verilmisse, arama sadece hedef_bolge alaninda bu
    deger(ler)den EN AZ BIRINI iceren parcalarla sinirlanir (Latissimus
    dorsi (kanat kasi) gibi parantezli varyasyonlar da eslessin diye
    "icerir" karsilastirmasi kullanilir). target_region bir tuple'dir --
    "sırt" gibi genel bir terim birden fazla alt-bolgeye (Latissimus,
    Orta sırt, Trapez, Bel) birden isaret edebilir.

    target_equipment verilmisse, bu filtre kas grubu filtresinin
    SONUCU uzerine uygulanir -- yani ikisi birlikte calisir.
    target_equipment, EQUIPMENT_KEYWORDS'ten gelen ve veritabanindaki
    gercek ekipman degerlerinden olusan bir tuple'dir; parcanin ekipman
    degeri bu tuple'daki degerlerden biriyle BIREBIR eslesmelidir
    ("icerir" degil "esittir" karsilastirmasi -- boylece "makine"
    arandiginda "Kablo makinesi" gibi baska bir deger yanlislikla
    eslesmez).

    Herhangi bir filtre uygulandiginda hicbir parcayla eslesmezse,
    o filtre uygulanmamis gibi bir onceki (daha genis) parca kumesine
    donulur -- boylece sonuc hicbir zaman bossuz kalmaz.
    """
    # hedef_bolge'si bos olan parcalar, dokumanin basindaki basliksiz
    # bolumlerdir (orn. "# Bacak Hareketleri\n\nKaynak: megaGymDataset...")
    # -- gercek bir hareketle ilgili degil, sadece dosya basligi/atif
    # metni. Bunlar hicbir zaman gecerli bir "cevap" olamaz, ama genel/
    # belirsiz sorularda (orn. "bana antrenman programi hazir") bazen
    # kisa ve genel olduklari icin yuksek skor alip gercek hareketlerin
    # onune gecebiliyorlardi. Bastan eliyoruz.
    candidates = [c for c in chunks if c["hedef_bolge"]]

    if target_region:
        region_matches = [
            c
            for c in candidates
            if any(sub in c["hedef_bolge"].lower() for sub in target_region)
        ]
        if region_matches:
            candidates = region_matches

    if target_equipment:
        equipment_set = {e.lower() for e in target_equipment}
        equipment_matches = [
            c for c in candidates if c["ekipman"].lower() in equipment_set
        ]
        if equipment_matches:
            candidates = equipment_matches

    scored = [
        (cosine_similarity(query_embedding, c["embedding"]), c) for c in candidates
    ]
    scored.sort(key=lambda pair: pair[0], reverse=True)
    return scored[:top_k]


def build_context(results):
    """Bulunan parcalari prompt'a gomulecek metne cevirir."""
    return "\n\n".join(
        f"[kaynak: {chunk['source']}]\n{chunk['content']}" for _, chunk in results
    )


CONTENT_HEADING_RE = re.compile(r"^[ \t]*#{1,6}[ \t]+(.+)$", re.MULTILINE)


def build_heading_source_map(results):
    """find_relevant'in dondurdugu parcalarin GERCEK icinden "## Baslik"
    satirlarini cikarip, her basligin hangi kaynak dosyadan geldigini
    gosteren bir sozluk dondurur (orn. {"EZ-Bar Skullcrusher": "kol-hareketleri.md"}).

    Bu sozlugun iki kullanim amaci var: (1) anahtarlari, modelin
    cevabinda gecen hareket adlarini dogrulamak icin kullanilan "izin
    verilen basliklar" listesi; (2) degerleri, cevabin sonundaki
    [kaynak: ...] etiketini modelin kendi yazdigina degil GERCEK
    veriye dayandirmak icin kullanilir -- model "kol-hareketleri.md"
    gibi hic kullanilmayan bir dosyayi uydursa bile bu goz ardi edilir.
    """
    mapping = {}
    for _, chunk in results:
        for heading in CONTENT_HEADING_RE.findall(chunk["content"]):
            mapping[heading.strip()] = chunk["source"]
    return mapping


def build_heading_region_map(results):
    """Her gercek basligin GERCEK hedef_bolge degerini gosteren bir
    sozluk dondurur (orn. {"Hammer Curl (Çekiç Curl)": "Biceps"}).

    Model bazen dogru bir basligin altina, retrieval'in getirdigi
    BASKA bir parcanin (farkli bir hareketin) icerigini -- yeni bir
    baslik acmadan -- yapistirabiliyor (orn. "Hammer Curl" basligi
    altinda "Lying Leg Curl" parcasindan Hamstring aciklamasi). Bu
    sozluk, aktif basligin GERCEKTE hangi kas grubuna ait oldugunu
    bilip, altindaki govde metninde CELISEN bir kas grubu kelimesi
    gecip gecmedigini kontrol etmek icin kullanilir.
    """
    mapping = {}
    for _, chunk in results:
        for heading in CONTENT_HEADING_RE.findall(chunk["content"]):
            mapping[heading.strip()] = chunk.get("hedef_bolge", "")
    return mapping


THINK_TAG_RE = re.compile(r"<think>.*?</think>", re.DOTALL | re.IGNORECASE)

# "Thinking Process:" basligini ve hemen ardindan gelen numarali
# ("1.", "2)" gibi) analiz satirlarini yakalar. Numarali olmayan bir
# satira gelindiginde durur, cunku orasi artik asil cevabin basladigi yerdir.
THINKING_PROCESS_RE = re.compile(
    r"Thinking Process:\s*\n(?:[ \t]*\d+[.)][^\n]*\n?)+", re.IGNORECASE
)

# SYSTEM_PROMPT modelden BAGLAM'daki "Hedef bölge/Ekipman/Seviye" metadata
# satirlarini, "## " basliklarini ve "[kaynak: ...]" blogunu kopyalamamasini
# istiyor -- ama kucuk modeller (orn. phi-4-mini) bunu guvenilir sekilde
# uygulamiyor, BAGLAM'i oldugu gibi kopyalayabiliyor. Bu yuzden ayni
# temizligi kod tarafinda da bir guvenlik agi olarak tekrar yapiyoruz.
METADATA_LINE_RE = re.compile(
    r"^[ \t]*(Hedef bölge|Ekipman|Seviye):.*$\n?", re.MULTILINE
)
HEADING_MARKER_RE = re.compile(r"^#{1,6}[ \t]+", re.MULTILINE)
KAYNAK_TAG_RE = re.compile(r"\[kaynak:\s*([^\]]+)\]")

# Model bazen SYSTEM_PROMPT'un kendi yapisal isaretcilerini ("BAGLAM:"
# gibi -- prompt'un en sonunda "BAGLAM:\n{context}" olarak gecer)
# gercek bir cevap uretecegine oldugu gibi geri kusuyor (orn.
# qwen3-0.6b ile daha once sistem promptunun son cumlelerini birebir
# yazmisti). Bu bilinen, spesifik sizintiyi satirin basindan siliyoruz
# -- ayni satirda ardindan gercek bir metin geliyorsa o korunur.
PROMPT_LEAK_RE = re.compile(r"(?im)^[ \t]*ba[ğg]lam[ \t]*:[ \t]*")

NO_INFO_MESSAGE = "Bu bilgi elimdeki belgelerde yok."


def _truncate_repetition(text, max_phrase_len=40):
    """Ayni kelime grubunun ust uste tekrarlandigi noktayi bulup metni
    oradan keser (orn. "dizlerin etekleriyle, ellerin dizlerin
    etekleriyle veya ayaklarla barla," diye sonsuza kadar suren bir
    dongu). frequency_penalty/presence_penalty bunu AZALTIYOR ama garanti
    etmiyor -- bu, bir dongu yine de olusursa devreye giren son bir
    guvenlik agi.

    Tekrar eden ifadenin kac kelime oldugu onceden bilinmez (2 kelime de
    olabilir, 30 kelime de) -- bu yuzden 2'den max_phrase_len'e kadar her
    olasi uzunlugu dener. Kisa ifadeler (2-4 kelime) dogal metinde de
    tesadufen 2 kez gecebilir (orn. "cok cok"), o yuzden onlarda en az 3
    tekrar ariyoruz; 5+ kelimelik bir ifadenin TESADUFEN iki kez birebir
    ayni sekilde ust uste gecmesi pratikte imkansiza yakindir, o yuzden
    orada 2 tekrar bile yeterli kanittir.
    """
    words = text.split()
    n = len(words)
    earliest_cut = None

    for phrase_len in range(2, max_phrase_len + 1):
        min_repeats = 3 if phrase_len < 5 else 2
        i = 0
        while i + phrase_len * min_repeats <= n:
            phrase = words[i:i + phrase_len]
            repeats = 1
            j = i + phrase_len
            while words[j:j + phrase_len] == phrase:
                repeats += 1
                j += phrase_len
            if repeats >= min_repeats:
                if earliest_cut is None or i < earliest_cut:
                    earliest_cut = i
                break
            i += 1

    if earliest_cut is None:
        return text
    return " ".join(words[:earliest_cut]).strip()


_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+")


def _drop_degenerate_sentences(text, min_words=8, max_unique_ratio=0.55):
    """Bir cumlenin essiz kelime orani (essiz kelime sayisi / toplam
    kelime sayisi) cok dusukse -- yani kelimelerinin BUYUK KISMI kendi
    icinde tekrar ediyorsa -- o cumleyi BUTUNUYLE atar.

    Diger tekrar-temizleyicilerin (_truncate_repetition,
    _trim_trailing_partial_repeat) hepsi ARDISIK, BIREBIR ayni uzunlukta
    tekrarlari arar. Ama model bazen "X'in ust kopyalamasini, Y'nin ust
    kopyalamasini, Z'nin ust kopyalamasini..." gibi, arada farkli
    (anlamsiz) doldurma kelimeleri gecen, hicbir zaman tam olarak ayni
    olmayan ama ayni kaliba sikisip kalmis bir "kelime curbagi"
    uretebiliyor -- bu, hicbir exact-match kontrolunu tetiklemez.

    Ilk denemede "tek bir ifade 3+ kez geciyor mu" diye bakmistik, ama bu
    yanlis pozitif verdi: "ayaklar geniş ve eller dizlerin icinde... ayaklar
    geniş ve eller dizlerin dışında... ayaklar geniş olmayan..." gibi,
    farkli durus varyasyonlarini karsilastiran GERCEK/anlamli bir cumle de
    "ayaklar geniş" ifadesini 3 kez dogal olarak kullanabiliyor. Essiz
    kelime orani daha guvenilir bir ayrac: curbag cumlede kelimelerin
    yaklasik yarisi tekrar iken (orn. ~0.46), gercek cumlede cogu kelime
    farklidir (orn. ~0.65) -- cunku curbagda TUM cumle bir kalibin
    etrafinda donup duruyor, sadece tek bir ifade degil.

    Boyle bir cumlenin hangi kisminin anlamli hangi kisminin curbaga
    ait oldugunu guvenilir sekilde ayirmak mumkun degil, o yuzden
    cumleyi kismen "kurtarmaya" calismak yerine BUTUNUYLE atiyoruz.
    """
    sentences = _SENTENCE_SPLIT_RE.split(text.strip())
    kept = []
    for s in sentences:
        words = re.findall(r"\w+", s.lower())
        if len(words) >= min_words:
            unique_ratio = len(set(words)) / len(words)
            if unique_ratio < max_unique_ratio:
                continue  # cumleyi at
        kept.append(s)
    return " ".join(kept)


# Cumle-benzerligi olcerken gorulmezden gelinen, cok sik gecen Turkce
# baglac/edat/yardimci kelimeler. Bunlar cikarilmazsa iki alakasiz
# cumle bile sirf "ve", "bir", "ile" gibi ortak kelimeler yuzunden
# "benzer" gorunebilir.
_STOPWORDS = {
    "ve", "bir", "bu", "şu", "o", "ile", "için", "gibi", "da", "de",
    "ki", "ise", "ya", "veya", "ancak", "fakat", "daha", "en", "kadar",
    "göre", "olan", "olarak",
}


def _content_words(sentence):
    tokens = re.findall(r"\w+", sentence.lower())
    return {t for t in tokens if t not in _STOPWORDS and len(t) > 2}


def _dedupe_near_sentences(text, min_words=5, threshold=0.75):
    """Bir paragraf icinde, ONCEKI bir cumleyle BIREBIR ayni olmasa da
    icerik kelimelerinin (yaygin baglaclar/edatlar cikarilmis) buyuk
    kismi ortusen cumleleri atar.

    _truncate_repetition kisa ifade dongulerini, _trim_trailing_partial_repeat
    kesilmis kuyruk tekrarlarini yakalar; ama model bazen ayni birkac
    bilgiyi FARKLI oznelerle yeniden birlestirip ("Deadlift, X hareketidir.
    ... Barbell ile yapilan bu hareket, X hareketidir." gibi) esasen ayni
    seyi tekrar tekrar uretebiliyor -- bu birebir string esitligi olmadigi
    icin salt "tam ayni cumle" kontrolunu atlatiyordu. Bu fonksiyon onun
    yerine "icerigin BUYUK KISMI ayni mi" diye bakiyor.

    Benzerlik "containment" ile olculur: kesisim / (iki cumleden KISA
    olaninin kelime sayisi). Bu, kisa bir cumlenin butun icerigi zaten
    daha once baska bir cumlede gecmisse onu yakalamak icin Jaccard'dan
    (kesisim/birlesim) daha uygun. min_words, cok kisa cumlelerde
    tesadufi kelime ortusmesinin yanlislikla "tekrar" sayilmasini
    onleyen bir guvenlik alt siniri.
    """
    sentences = _SENTENCE_SPLIT_RE.split(text.strip())
    kept = []
    kept_word_sets = []
    for s in sentences:
        words = _content_words(s)
        if len(words) < min_words:
            kept.append(s)
            continue
        is_dup = any(
            len(words & prev) / min(len(words), len(prev)) >= threshold
            for prev in kept_word_sets
        )
        if is_dup:
            continue
        kept.append(s)
        kept_word_sets.append(words)
    return " ".join(kept)


_LEADING_PUNCT_RE = re.compile(r"^\W+")
_TRAILING_PUNCT_RE = re.compile(r"\W+$")


def _split_punct(word):
    """Bir kelimeyi (basindaki noktalama, oz kelime, sonundaki noktalama)
    olarak ucler. Orn. "(sumu" -> ("(", "sumu", "")."""
    lead_match = _LEADING_PUNCT_RE.match(word)
    lead = lead_match.group() if lead_match else ""
    rest = word[len(lead):]
    trail_match = _TRAILING_PUNCT_RE.search(rest)
    trail = trail_match.group() if trail_match else ""
    core = rest[: len(rest) - len(trail)] if trail else rest
    return lead, core, trail


def _fix_stutter_typos(text):
    """Modelin bir kelimeyi yazip HEMEN ARDINDAN duzeltilmis/farkli bir
    haliyle tekrar yazdigi "kekeleme" hatalarini temizler (orn. "(sumu
    sumo deadlift)" -> "(sumo deadlift)"; ilk, yanlis yazilan "sumu"
    atilir, ama basindaki "(" gibi bir noktalama varsa kaybolmasin diye
    dogru kelimenin basina tasinir).

    Karsilastirma, kelimenin basindaki/sonundaki noktalama isaretlerini
    (parantez, virgul, vb.) ayirip sadece OZ kelimeye bakar; sadece AYNI
    UZUNLUKTAKI, birbirinden TEK BIR HARFLE ayrilan oz kelime ciftlerini
    hedefler. Bu dar kural bilerek boyle secildi: Turkce'de ek almis
    kelimeler neredeyse hep UZUNLUK degistirir (orn. "kas" -> "kasi" ->
    "kaslari"), bu yuzden "ayni uzunluk + tek harf farki" kombinasyonunun
    dogal, anlamli iki farkli kelimede rastlantiyla olusmasi cok dusuk
    ihtimal -- yanlislikla gramer varyasyonlarini silme riski dusuk kalir.

    NOT: "kistilendiği" gibi, yaninda duzeltilmis bir esi OLMAYAN, tek
    basina uydurulmus/bozuk bir kelimeyi bu fonksiyon YAKALAYAMAZ --
    boyle bir seyi guvenilir sekilde tespit etmek gercek bir Turkce
    sozluk/yazim denetleyicisi gerektirir, bu projenin kapsami disinda.
    """
    words = text.split()
    if len(words) < 2:
        return text

    result = []
    i = 0
    carry_prefix = ""
    while i < len(words):
        word = carry_prefix + words[i] if carry_prefix else words[i]
        carry_prefix = ""
        if i + 1 < len(words):
            lead1, core1, _ = _split_punct(word)
            _, core2, _ = _split_punct(words[i + 1])
            if core1 and core2 and len(core1) == len(core2) and core1 != core2:
                diff = sum(1 for a, b in zip(core1, core2) if a != b)
                if diff == 1:
                    carry_prefix = lead1  # onceki kelimenin basindaki
                    i += 1                # noktalamayi (orn. "(") kaybetme
                    continue
        result.append(word)
        i += 1
    return " ".join(result)


def _trim_trailing_partial_repeat(text, min_prefix_len=4):
    """max_tokens siniri, model tam bir onceki cumleyi yeniden baslatip
    tekrarlarken devreye girip metni ortasinda keserse ("...kabul edilir.
    Deadlift, gluteus, hamstring, ... kas gr" gibi), bu yarim kalan
    tekrari atar.

    _dedupe_near_sentences TAMAMLANMIS tekrar eden cumleleri yakalar; bu
    fonksiyon ise son cumlenin bir oncekinin sadece BASI olup TAMAMLANAMADAN
    kesildigi durumu yakalar. Son kelime de tam kesilmis (orn. "grubu"
    yerine "gr") olabilecegi icin, son karsilastirilan kelime icin "esittir"
    yerine "biri digerinin on-eki mi" kontrolu yapiyoruz.
    """
    sentences = re.split(r"(?<=[.!?])\s+", text.strip())
    if len(sentences) < 2:
        return text

    tail = sentences[-1].strip()
    prev = sentences[-2].strip()
    if not tail or tail.endswith((".", "!", "?")):
        return text

    tail_words = tail.split()
    prev_words = prev.split()
    n = min(len(tail_words), len(prev_words))
    if n < min_prefix_len:
        return text

    if tail_words[:n - 1] != prev_words[:n - 1]:
        return text
    last_tail, last_prev = tail_words[n - 1], prev_words[n - 1]
    if not (last_prev.startswith(last_tail) or last_tail.startswith(last_prev)):
        return text

    return " ".join(sentences[:-1])


def _normalize_heading(text):
    return re.sub(r"\s+", " ", text).strip().lower()


def _looks_like_heading(paragraph):
    """Bir paragrafin BAGLAM'daki "## Hareket Adi" satirlarina benzer bir
    "baslik" olup olmadigini tahmin eder: bu veri setinde basliklar hep
    tek satirlik, kisa ve noktalama ile bitmeyen, kelimelerinin cogu
    Buyuk Harfle Baslayan ifadelerdir (orn. "EZ-Bar Skullcrusher").
    Aciklamalar ise noktayla biten, tam cumlelerden olusan uzun metinlerdir.
    """
    stripped = paragraph.strip()
    if not stripped or "\n" in stripped or len(stripped) > 80:
        return False
    if stripped.endswith((".", ":", "!", "?")):
        return False
    words = [w for w in stripped.split() if len(w) >= 3]
    if not words:
        return False
    capitalized = sum(1 for w in words if w[0].isupper())
    return capitalized / len(words) >= 0.6


def _mentions_conflicting_region(sentence, current_region):
    """Bir cumlenin, aktif basligin GERCEK hedef_bolge'siyle CELISEN bir
    kas grubu kelimesi (MUSCLE_KEYWORDS'ten) icerip icermedigini kontrol
    eder.

    Orn. aktif baslik "Biceps" bolgesindeyken bir cumle "hamstring"
    kelimesini geciriyorsa, bu -- retrieval'in getirdigi BASKA bir
    parcadan (farkli bir hareketten) sizmis, yanlis hareketle karisik
    icerik oldugunun guclu bir isaretidir. current_region bossa (bilinmiyorsa)
    hicbir zaman celiski bulunmaz -- yanlis pozitif riskini onlemek icin.
    """
    if not current_region:
        return False
    current_lower = current_region.lower()
    sentence_lower = sentence.lower()
    for keyword, region_values in MUSCLE_KEYWORDS.items():
        if not re.search(rf"\b{re.escape(keyword)}\b", sentence_lower):
            continue
        if any(v in current_lower or current_lower in v for v in region_values):
            continue  # bu kelime zaten aktif bolgeyle uyumlu
        return True
    return False


def _strip_conflicting_sentences(paragraph, current_region):
    """_mentions_conflicting_region'i CUMLE seviyesinde uygular: bir
    govde paragrafinin butununu degil, sadece celisen kas grubu
    kelimesi iceren TEK TEK cumleleri atar. Boylece ayni paragraf
    icinde hem dogru (Hammer Curl'un gercek aciklamasi) hem sizmis
    (Lying Leg Curl'dan Hamstring aciklamasi) cumleler bir aradaysa,
    sadece sizan cumle gider -- dogru kisim korunur.
    """
    if not current_region:
        return paragraph
    sentences = _SENTENCE_SPLIT_RE.split(paragraph.strip())
    kept = [s for s in sentences if not _mentions_conflicting_region(s, current_region)]
    return " ".join(kept)


def _filter_ungrounded_sections(paragraphs, allowed_headings, heading_region_map=None):
    """Baslik-gibi gorunen ama find_relevant'in getirdigi hicbir gercek
    baslikla eslesmeyen paragraflari -- ve onlari takip eden aciklamayi --
    atar. Modelin uydurdugu hareketleri (halusinasyon) burada temizleriz.

    heading_region_map verilirse, aktif basligin GERCEK hedef_bolge'siyle
    celisen bir kas grubu kelimesi iceren TEK TEK cumleler de govde
    paragraflarindan atilir (bkz. _strip_conflicting_sentences) --
    bu, modelin dogru bir basligin altina BASKA bir parcanin (farkli bir
    hareketin) icerigini, yeni bir baslik acmadan yapistirdigi durumu
    yakalar (bkz. build_heading_region_map).

    allowed_headings bossa (BAGLAM'da hic baslik bulunamadiysa) hicbir
    seyi filtrelemeden (paragraphs, []) olarak dondurur.

    Iki deger dondurur: (kalan paragraflar, dogrulanan gercek basliklarin
    listesi). Ikinci deger, cevabin sonundaki kaynak etiketini modelin
    kendi yazdigina degil GERCEK veriye dayandirmak icin kullanilir.
    """
    if not allowed_headings:
        return paragraphs, []

    heading_region_map = heading_region_map or {}
    normalized_allowed = {_normalize_heading(h): h for h in allowed_headings}
    kept = []
    matched_headings = []
    skipping_ungrounded_section = False
    current_region = None
    for p in paragraphs:
        if _looks_like_heading(p):
            norm = _normalize_heading(p)
            match = next(
                (
                    original
                    for allowed_norm, original in normalized_allowed.items()
                    if norm in allowed_norm or allowed_norm in norm
                ),
                None,
            )
            skipping_ungrounded_section = match is None
            current_region = heading_region_map.get(match) if match else None
            if match:
                kept.append(p)
                if match not in matched_headings:
                    matched_headings.append(match)
            continue
        if skipping_ungrounded_section:
            continue
        cleaned = _strip_conflicting_sentences(p, current_region)
        if cleaned.strip():
            kept.append(cleaned)
    return kept, matched_headings


def _format_raw_results(results):
    """results'taki parcalari, MODEL HIC ARAYA GIRMEDEN dogrudan
    kullaniciya gostermek icin bicimlendirir -- sadece "Hedef bölge/
    Ekipman/Seviye" metadata satirini ve "## " isaretini kaldirir.

    clean_model_response'ta, model hicbir gercek basligi dogru
    kullanamadiginda (baslik dogrulamasi tamamen bos donduğunde) son
    care olarak devreye girer. Bu, retrieval'in GERCEKTEN buldugu veriyi
    oldugu gibi sundugu icin tanim geregi %100 dogrudur -- "bu bilgi
    elimde yok" demekten (ki bilgi aslinda var) daha dogru bir secim.
    """
    blocks = []
    for _, chunk in results:
        content = METADATA_LINE_RE.sub("", chunk["content"])
        content = HEADING_MARKER_RE.sub("", content)
        content = re.sub(r"\n{3,}", "\n\n", content)  # silinen metadata satirinin biraktigi fazla bosluk
        blocks.append(content.strip())
    sources = list(dict.fromkeys(chunk["source"] for _, chunk in results))
    return "\n\n".join(blocks) + f"\n\n[kaynak: {', '.join(sources)}]"


def clean_model_response(text, results=None):
    """Modelin urettigi cevabi kullaniciya gosterilecek hale getirir.

    Bazi modeller asil cevaptan once <think>...</think> etiketleri
    arasinda ya da "Thinking Process:" basligiyla baslayan numarali bir
    analiz listesi halinde ic muhakeme metni uretir -- bu siliniyor.

    Ayrica bazi modeller SYSTEM_PROMPT'un aksine BAGLAM'daki ham metni
    (metadata satirlari, "## " basliklari, tekrar eden bloklar/cumleler
    ve birden fazla "[kaynak: ...]" etiketi) oldugu gibi kopyalayabiliyor,
    hatta BAGLAM'da hic olmayan hareketler ve kaynak dosya adlari
    uydurabiliyor. Bunlarin hepsini kod tarafinda temizliyoruz: modele
    guvenmek yerine, hem hareket basliklarini hem kaynak dosya adlarini
    results (find_relevant'in gercekten getirdigi parcalar) ile
    karsilastirip dogruluyoruz.

    NOT (kasitli tasarim karari): burada bir ara bir "baslik dogrulamasi
    tamamen bos donerse, dogrulamayi kapatip tekrar dene" fallback'i
    denenmisti (orn. model "Baldır Egzersizleri" gibi genel bir kategori
    basligi yazip gercek basliklari hic tekrarlamadiginda). Ama bu, ayni
    guvenlik agindan modelin TAMAMEN UYDURDUGU bir hareket adinin
    ("Kablo Kardan" gibi) da faydalanip ekrana cikmasina yol acti --
    kelime-ortusmesi tabanli bir kontrol, "gercek icerigi farkli
    yapida anlatmak" ile "gercek kelimeleri kullanarak uydurmak"
    arasinda guvenilir bir ayrim yapamiyor. Bu yuzden bilerek GERI
    ALINDI: yanlis bir hareket adini kendinden emin sekilde gostermek,
    "bu bilgi elimde yok" demekten cok daha kotu bir hata.

    Baslik dogrulamasi HER ZAMAN sikidir. Ama bosa donerse, dogrudan
    "bu bilgi elimde yok" demek de YANLIS olurdu -- cunku bilgi
    GERCEKTEN var (retrieval zaten bulmus, results dolu), sadece model
    onu dogru ifade edemedi. Bu durumda modelin metnine hic guvenmeden,
    retrieval'in bulduğu GERCEK parcalari dogrudan gosteririz (bkz.
    _format_raw_results) -- bu, tanim geregi %100 dogru, cunku modelin
    hicbir yorumu araya girmiyor.
    """
    heading_source_map = build_heading_source_map(results) if results else {}
    heading_region_map = build_heading_region_map(results) if results else {}
    allowed_headings = set(heading_source_map.keys())

    text = THINK_TAG_RE.sub("", text)
    text = THINKING_PROCESS_RE.sub("", text)
    text = METADATA_LINE_RE.sub("", text)
    text = HEADING_MARKER_RE.sub("", text)
    text = KAYNAK_TAG_RE.sub("", text)
    text = PROMPT_LEAK_RE.sub("", text)

    # Birebir tekrar eden paragraflari tekille (model bazen ayni bilgiyi
    # (baslik + aciklama) art arda iki kez uretiyor; baslik ile aciklama
    # ayri paragraflar oldugu icin tekrarlar birbirine bitisik olmayabilir
    # -- o yuzden sadece "ardisik" degil, tum metin genelinde tekilliyoruz).
    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]

    # Bir paragrafin ICINDE tekrar olusan iki farkli olcekteki dongu
    # turune karsi guvenlik agi: kisa ifade dongusu ("plank hareketini
    # yapmayan plank hareketini yapmayan ...") ve tam cumle dongusu
    # (uzun bir tanim cumlesinin birebir 2-3 kez uretilmesi). Yukaridaki
    # paragraf-dedup'i bunlari yakalayamaz, cunku tek bir paragrafin
    # kendi icinde olan bir tekrar.
    paragraphs = [_fix_stutter_typos(p) for p in paragraphs]
    paragraphs = [_drop_degenerate_sentences(p) for p in paragraphs]
    paragraphs = [_dedupe_near_sentences(p) for p in paragraphs]
    paragraphs = [_trim_trailing_partial_repeat(p) for p in paragraphs]
    paragraphs = [_truncate_repetition(p) for p in paragraphs]
    paragraphs = [p for p in paragraphs if p.strip()]

    seen = set()
    deduped = []
    for p in paragraphs:
        if p not in seen:
            seen.add(p)
            deduped.append(p)

    grounded, matched_headings = _filter_ungrounded_sections(
        deduped, allowed_headings, heading_region_map
    )
    text = "\n\n".join(grounded)

    if not text.strip():
        return _format_raw_results(results) if results else NO_INFO_MESSAGE

    # Kaynak etiketi: modelin kendi yazdigi [kaynak: ...] metnine
    # guvenmiyoruz (yukarida zaten silindi) -- onun yerine, dogrulanmis
    # basliklarin GERCEKTEN hangi dosyadan geldigini kullaniyoruz. Hicbir
    # baslik eslesmediyse (model duz nesir yazip hic baslik satiri
    # uretmediyse) BAGLAM'a giren tum kaynaklari gosteririz -- boylece
    # ekranda asla modelin uydurdugu bir dosya adi cikmaz.
    real_sources = []
    for heading in matched_headings:
        src = heading_source_map.get(heading)
        if src and src not in real_sources:
            real_sources.append(src)
    if not real_sources and results:
        real_sources = list(dict.fromkeys(chunk["source"] for _, chunk in results))

    if real_sources:
        text = f"{text}\n\n[kaynak: {', '.join(real_sources)}]"

    return text.strip()


def main():
    chunks = load_chunks()
    print(f"{len(chunks)} parca yuklendi.")

    FoundryLocalManager.initialize(Configuration(app_name="local_rag_app"))
    manager = FoundryLocalManager.instance

    embed_model = manager.catalog.get_model(EMBED_MODEL)
    embed_model.download()
    embed_model.load()
    embedding_client = embed_model.get_embedding_client()

    chat_model = manager.catalog.get_model(CHAT_MODEL)
    chat_model.download(
        lambda p: print(f"\rSohbet modeli indiriliyor: {p:.1f}%", end="", flush=True)
    )
    print()
    chat_model.load()
    chat_client = chat_model.get_chat_client()
    # temperature: model daha az "yaratici" olsun, baglamda olmayan detay
    # uydurma riski azalsin -- ama COK dusuk tutmuyoruz, cunku asiri dusuk
    # sicaklik kucuk modellerde model neredeyse deterministik hale gelince
    # ayni kelime zincirini tekrar tekrar uretme (repetition loop) riski
    # tasir; tam da bu yuzden asagida frequency_penalty de ekliyoruz.
    # frequency_penalty: az once cikan kelimelere, kac kez gectiyse o
    # kadar artan bir ceza verir -- "plank hareketini yapmayan" gibi bir
    # ifadeyi bir kere tekrarlamaya baslayinca cezasi katlanarak artar.
    # NOT: presence_penalty (bir kelime SADECE bir kere gecmis olsa bile
    # sabit ceza uygulayan, kac kez gectigine bakmayan parametre) burada
    # KASITLI olarak KULLANILMIYOR. Denedik: presence_penalty=0.4 ile
    # birlikte model, Turkce gibi zengin cekim yapili bir dilde dogal
    # cumle kurmak icin gereken kelimeleri (kas, hareket, kaslari gibi)
    # bile tekrar kullanmaktan cekindigi icin bozuk/anlamsiz cumleler
    # kurmaya basladi ("dizlerin etekleriyle veya ayaklar ile barla..."
    # gibi). Yani dongu riskini akiciligi feda ederek "cozmus" olduk --
    # kabul edilebilir bir takas degil. Dongu onleme yukunu artik buradan
    # (orneklem parametreleri) degil, clean_model_response'taki
    # _truncate_repetition / _dedupe_near_sentences fonksiyonlarindan (kod
    # seviyesi, keyfi uzunluktaki tekrarlari yakalayabilen guvenlik agi)
    # alıyoruz -- onlar akiciligi bozmadan calisiyor, cunku sadece
    # GERCEKTEN tekrar eden kismi kesiyorlar.
    # max_tokens: cevap suresine bir tavan koyar (hem dongu ihtimaline
    # karsi hem gecikmeyi sinirlamak icin). Not: 300 daha once birden
    # fazla hareket anlatilirken cevabin ortadan kesilmesine yol acmisti;
    # o riski bilerek tekrar kabul ediyoruz (hiz onceligi), yarim kalan
    # cumleler clean_model_response'tan gecip kullanicinin karsisina cikabilir.
    chat_client.settings.temperature = 0.4
    chat_client.settings.frequency_penalty = 0.4
    chat_client.settings.max_tokens = 300

    print("\nHazir. Sorunuzu yazin ('cikis' ile kapatin).\n")

    try:
        while True:
            query = input("Soru: ").strip()
            if not query:
                continue
            if query.lower() in ("cikis", "quit", "exit"):
                break

            if is_program_request(query):
                print("\nCevap: Bu bilgi elimdeki belgelerde yok.\n")
                continue

            # 1) RETRIEVE — soruyu vektore cevir, en yakin parcalari bul
            target_region = detect_target_region(query)
            target_equipment = detect_target_equipment(query)
            if target_region:
                print(f"  (kas grubu filtresi: {target_region})")
            if target_equipment:
                print(f"  (ekipman filtresi: {target_equipment})")

            query_embedding = embedding_client.generate_embedding(query).data[0].embedding
            results = find_relevant(
                query_embedding,
                chunks,
                target_region=target_region,
                target_equipment=target_equipment,
            )

            # Hata ayiklama icin: hangi parcalar secildi, skorlari ne?
            # Retrieval kotuyse sorun genelde chunk boyutunda ya da
            # embedding modelindedir -- model degil.
            for score, chunk in results:
                print(f"  [{score:.3f}] {chunk['source']} — {chunk['content'][:60]}...")

            # En iyi eslesme bile esigin altindaysa baglam alakasizdir --
            # modeli hic cagirmadan direkt "bilgi yok" de.
            if results[0][0] < SIMILARITY_THRESHOLD:
                print("\nCevap: Bu bilgi elimdeki belgelerde yok.\n")
                continue

            # 2) AUGMENT — bulunan metni system prompt'a goem
            messages = [
                {"role": "system", "content": SYSTEM_PROMPT.format(
                    context=build_context(results))},
                {"role": "user", "content": query},
            ]

            # 3) GENERATE — yerel modelden cevabi al, sonra temizleyip yazdir
            raw_response = ""
            for piece in chat_client.complete_streaming_chat(messages):
                if not piece.choices:
                    continue
                content = piece.choices[0].delta.content
                if content:
                    raw_response += content

            print(f"\nCevap: {clean_model_response(raw_response, results)}\n")

    except (KeyboardInterrupt, EOFError):
        print()

    embed_model.unload()
    chat_model.unload()
    print("Modeller bellekten kaldirildi.")


if __name__ == "__main__":
    main()
