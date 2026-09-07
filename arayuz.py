"""
arayuz.py — Yerel RAG soru-cevap asistani (Streamlit arayuzu).

Onkosul: once `python ingest.py` calistirilmis ve knowledge.db olusmus olmali.
Kullanim: streamlit run arayuz.py

RAG mantigi (retrieval, prompt olusturma, model yukleme, cevap temizligi)
rag.py modulunde -- bu dosya sadece Streamlit arayuzunu icerir. Ayni
rag.py, komut satiri araci olan app.py tarafindan da kullanilir; iki
arayuz de ayni RAG mantigini calistirir, kod hicbir yerde kopyalanmaz.
"""

import html

import streamlit as st

from rag import (
    CHAT_MODEL,
    EMBED_MODEL,
    SIMILARITY_THRESHOLD,
    TOP_K,
    answer_query,
    load_chunks,
    load_models,
)

st.set_page_config(page_title="Fitness Bilgi Asistanı", page_icon="🏋️", layout="centered")

# Cevap metnini buyuk/okunakli gostermek icin bir CSS sinifi.
st.markdown(
    """
    <style>
    .cevap-kutusu {
        font-size: 1.3rem;
        line-height: 1.7;
        padding: 1rem 1.25rem;
        border-radius: 0.5rem;
        background-color: rgba(127, 127, 127, 0.08);
        border: 1px solid rgba(127, 127, 127, 0.25);
    }
    </style>
    """,
    unsafe_allow_html=True,
)


@st.cache_resource(show_spinner="Modeller yükleniyor... (ilk çalıştırmada birkaç dakika sürebilir)")
def get_models():
    """Embedding ve sohbet modellerini indirir, belleğe yukler ve hazir
    istemcilerle bir ModelBundle dondurur.

    Parametre ALMAZ -- boylece @st.cache_resource'un onbellek anahtari
    sabit kalir ve bu fonksiyon, ne kadar "Sor" tiklanirsa tiklansin,
    Streamlit surecinin omru boyunca SADECE BIR KEZ gercekten calisir
    (FoundryLocalManager.initialize, catalog.get_model, download, load,
    get_chat_client, get_embedding_client -- hepsi sadece ilk cagrida).
    Sonraki her cagri, Streamlit'in bellekte tuttugu AYNI model
    nesnelerini aninda geri dondurur.
    """
    models = load_models(app_name="local_rag_streamlit")
    # rag.py'deki load_models() varsayilan olarak max_tokens=300 ayarlar
    # (app.py bunu degistirmeden kullanir -- olcum referansi olarak sabit
    # kalmasi gerekiyor). Bu arayuz icin, get_chat_client() ve
    # complete_streaming_chat() max_tokens'i PARAMETRE olarak KABUL
    # ETMEDIGI icin (ikisi de incelendi: get_chat_client() hic parametre
    # almiyor, complete_streaming_chat() sadece messages/tools aliyor),
    # tek gecerli yol chat_client.settings uzerinden ayarlamak -- bunu
    # burada, sadece bu arayuz icin, load_models() dondukten SONRA
    # override ediyoruz. get_models() onbelleklendigi icin bu satir da
    # sadece ilk cagrida calisir.
    models.chat_client.settings.max_tokens = 350
    return models


@st.cache_data(show_spinner=False)
def get_chunks():
    """Veritabanindaki parcalari (embedding vektorleriyle birlikte)
    onbellege alir -- st.cache_resource'tan farkli olarak, bu adi
    gecen "veri" (chunks: sozluklerden olusan bir liste) icin dogru
    onbellekleme yontemidir; SQLite'tan sadece bir kez okunur.
    """
    return load_chunks()


st.title("🏋️ Fitness Bilgi Asistanı")
st.caption("Belgelerdeki hareketler hakkında soru sorun; yalnızca kaynak belgelerdeki bilgilerle yanıtlanır.")

with st.sidebar:
    st.header("Ayarlar")
    st.write(f"**Sohbet modeli:** `{CHAT_MODEL}`")
    st.write(f"**Embedding modeli:** `{EMBED_MODEL}`")
    st.write(f"**TOP_K:** {TOP_K}")
    st.write(f"**Benzerlik eşiği:** {SIMILARITY_THRESHOLD}")

chunks = get_chunks()
models = get_models()

with st.form("soru_formu"):
    query = st.text_input(
        "Sorunuzu yazın",
        placeholder="Örn: Baldır için hangi egzersizler yapılabilir?",
    )
    ask_clicked = st.form_submit_button("Sor", type="primary", use_container_width=True)

if ask_clicked:
    if not query.strip():
        st.warning("Lütfen bir soru yazın.")
    else:
        with st.spinner("Cevap hazırlanıyor..."):
            result = answer_query(query.strip(), chunks, models.embedding_client, models.chat_client)

        st.markdown("### Cevap")
        escaped = html.escape(result.answer).replace("\n\n", "<br><br>").replace("\n", "<br>")
        st.markdown(f'<div class="cevap-kutusu">{escaped}</div>', unsafe_allow_html=True)
        st.caption(f"⏱️ Cevap süresi: {result.elapsed_seconds:.1f} saniye")

        # Asama bazli zamanlayici: model yukleme (bir kez, onbellekten
        # gelen sabit deger) + bu sorunun kendi asamalari (embedding,
        # vektor arama, LLM uretimi). Boylece hangi asamanin ne kadar
        # surdugu -- ozellikle model yuklemenin SADECE ILK SEFERDE
        # gerceklestigi -- goz onunde.
        st.markdown("**Aşama süreleri:**")
        st.write(f"- Model yükleme: {models.load_seconds:.1f} sn")
        st.write(f"- Sorunun embedding'e çevrilmesi: {result.embedding_seconds:.1f} sn")
        st.write(f"- Vektör arama: {result.search_seconds:.1f} sn")
        st.write(f"- LLM cevap üretimi: {result.generation_seconds:.1f} sn")

        with st.expander("Kullanılan parçalar ve detaylar"):
            if result.target_region:
                st.write(f"**Kas grubu filtresi:** {', '.join(result.target_region)}")
            if result.target_equipment:
                st.write(f"**Ekipman filtresi:** {', '.join(result.target_equipment)}")
            if not result.target_region and not result.target_equipment:
                st.write("**Filtre:** uygulanmadı (soruda belirli bir kas grubu/ekipman tespit edilmedi)")

            if result.results:
                st.write("**Bulunan parçalar:**")
                for score, chunk in result.results:
                    st.markdown(f"- `[{score:.3f}]` **{chunk['source']}**")
            else:
                st.write("**Bulunan parçalar:** yok")

            st.write(f"**Model çağrıldı mı:** {'Evet' if result.model_called else 'Hayır'}")
