"""
ingest.py — Belgeleri okur, parcalara boler, embedding uretir, SQLite'a yazar.

Bu script BIR KEZ (ya da belgeler her degistiginde) calisir.
Kullanim:  python ingest.py
"""

import json
import re
import sqlite3
from pathlib import Path

from foundry_local_sdk import Configuration, FoundryLocalManager

DB_PATH = "knowledge.db"
DOCS_DIR = Path("docs")
EMBED_MODEL = "qwen3-embedding-0.6b"

# Parca boyutu: cok kucuk olursa baglam kaybolur, cok buyuk olursa
# alakasiz metin de modele gider. 200-1000 karakter arasi deneyin.
CHUNK_SIZE = 600
CHUNK_OVERLAP = 100


def _split_into_sections(text):
    """Metni '## Baslik' seklindeki markdown basliklarina gore bolumlere ayirir.

    Ilk baslıktan once metin varsa basliksiz (heading=None) bir bolum
    olarak eklenir. Her bolum kendi basligiyla birlikte tutulur.
    """
    matches = list(re.finditer(r"^##\s+.+$", text, re.MULTILINE))

    if not matches:
        return [(None, text)]

    sections = []
    if matches[0].start() > 0:
        pre = text[:matches[0].start()].strip()
        if pre:
            sections.append((None, pre))

    for i, m in enumerate(matches):
        heading = m.group().strip()
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        body = text[start:end].strip()
        sections.append((heading, body))

    return sections


def _word_boundary_tail(text, overlap):
    """`text`in sonundan ~`overlap` karakter alir; kelimeyi ortadan
    kesmemek icin baslangic noktasini bir sonraki bosluga kaydirir.
    """
    if not overlap or len(text) <= overlap:
        return text
    cut_at = len(text) - overlap
    next_space = text.find(" ", cut_at)
    return text[next_space + 1:] if next_space != -1 else text[cut_at:]


def _chunk_section(heading, body, size, overlap):
    """Tek bir bolumu (baslik + govde) parcalara boler.

    Bolum `size` sinirini asmiyorsa tek parca olarak baslikla birlikte
    dondurulur. Asiyorsa paragraf sinirlarindan bolunur ve her parcanin
    basina bolumun basligi eklenir (baslik uzunlugu hesaba katilir).
    """
    prefix = f"{heading}\n\n" if heading else ""

    if len(prefix) + len(body) <= size:
        combined = (prefix + body).strip()
        return [combined] if combined else []

    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", body) if p.strip()]

    chunks = []
    current = ""

    for para in paragraphs:
        # Tek basina cok uzun paragraf: kaba kuvvetle bol
        while len(prefix) + len(para) > size:
            limit = max(size - len(prefix), 1)
            piece = para[:limit]
            chunks.append((prefix + piece).strip())
            # Onceki parcanin sonundan bir miktar tasiyoruz (overlap),
            # kelimeyi ortadan kesmemek icin en yakin bosluktan basliyoruz.
            tail = _word_boundary_tail(piece, overlap)
            para = tail + para[limit:]

        if not current:
            current = para
        elif len(prefix) + len(current) + len(para) + 2 <= size:
            current += "\n\n" + para
        else:
            chunks.append((prefix + current).strip())
            tail = _word_boundary_tail(current, overlap)
            current = (tail + "\n\n" + para).strip() if tail else para

    if current:
        chunks.append((prefix + current).strip())

    return chunks


def chunk_text(text, size=CHUNK_SIZE, overlap=CHUNK_OVERLAP):
    """Metni once markdown basliklarina (## ile baslayan satirlar) gore
    bolumlere ayirir, sonra her bolumu paragraf sinirlarina saygi
    gostererek parcalara boler.

    Bir bolum `size` karakterini asarsa parcalara bolunur; her parcanin
    basina, hangi bolume ait oldugu belli olsun diye o bolumun basligi
    eklenir. Parcalar arasi overlap eklenirken kelimenin ortasindan
    kesilmemesi icin en yakin bosluktan baslanir.
    """
    sections = _split_into_sections(text)

    chunks = []
    for heading, body in sections:
        chunks.extend(_chunk_section(heading, body, size, overlap))

    return chunks


def create_schema(conn):
    conn.executescript(
        """
        DROP TABLE IF EXISTS chunks;
        CREATE TABLE chunks (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            source      TEXT    NOT NULL,
            chunk_index INTEGER NOT NULL,
            content     TEXT    NOT NULL,
            embedding   TEXT    NOT NULL,
            hedef_bolge TEXT,
            ekipman     TEXT
        );
        CREATE INDEX idx_chunks_source ON chunks(source);
        """
    )
    conn.commit()


HEDEF_BOLGE_RE = re.compile(r"Hedef bölge:\s*([^.\n]+)\.")
EKIPMAN_RE = re.compile(r"Ekipman:\s*([^.\n]+)\.")


def extract_hedef_bolge(content):
    """Parca metnindeki 'Hedef bolge: X.' satirini ayristirip X degerini
    dondurur. Boyle bir satir yoksa bos metin doner.
    """
    match = HEDEF_BOLGE_RE.search(content)
    return match.group(1).strip() if match else ""


def extract_ekipman(content):
    """Parca metnindeki 'Ekipman: X.' satirini ayristirip X degerini
    dondurur. Boyle bir satir yoksa bos metin doner.
    """
    match = EKIPMAN_RE.search(content)
    return match.group(1).strip() if match else ""


def read_documents(docs_dir):
    """docs/ klasorundeki .txt ve .md dosyalarini okur."""
    files = sorted(list(docs_dir.glob("*.txt")) + list(docs_dir.glob("*.md")))
    if not files:
        raise SystemExit(
            f"'{docs_dir}/' klasorunde .txt veya .md dosyasi yok. "
            "Once bilgi tabaniniza birkac dosya koyun."
        )
    return [(f.name, f.read_text(encoding="utf-8")) for f in files]


def main():
    documents = read_documents(DOCS_DIR)
    print(f"{len(documents)} dosya bulundu.")

    # --- Butun dosyalari parcalara bol ---
    records = []  # (source, chunk_index, content, hedef_bolge, ekipman)
    for name, text in documents:
        for i, chunk in enumerate(chunk_text(text)):
            records.append(
                (name, i, chunk, extract_hedef_bolge(chunk), extract_ekipman(chunk))
            )
    print(f"Toplam {len(records)} parca olustu.")

    # --- Foundry Local'i baslat ve embedding modelini yukle ---
    FoundryLocalManager.initialize(Configuration(app_name="local_rag_ingest"))
    manager = FoundryLocalManager.instance

    model = manager.catalog.get_model(EMBED_MODEL)
    model.download(
        lambda p: print(f"\rEmbedding modeli indiriliyor: {p:.1f}%", end="", flush=True)
    )
    print()
    model.load()
    embedding_client = model.get_embedding_client()

    # --- Embedding'leri toplu halde uret ---
    # Cok fazla parca varsa RAM'i zorlamamak icin gruplar halinde gonderiyoruz.
    BATCH = 32
    embeddings = []
    for start in range(0, len(records), BATCH):
        batch = [r[2] for r in records[start:start + BATCH]]
        response = embedding_client.generate_embeddings(batch)
        embeddings.extend(item.embedding for item in response.data)
        print(f"\rEmbedding: {len(embeddings)}/{len(records)}", end="", flush=True)
    print()

    # --- SQLite'a yaz ---
    # Vektoru JSON metni olarak sakliyoruz: okunabilir ve ek kutuphane
    # gerektirmiyor. Cok buyuk veri setlerinde BLOB daha verimli olur.
    conn = sqlite3.connect(DB_PATH)
    create_schema(conn)
    conn.executemany(
        "INSERT INTO chunks (source, chunk_index, content, embedding, hedef_bolge, ekipman) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        [
            (src, idx, content, json.dumps(emb), hedef_bolge, ekipman)
            for (src, idx, content, hedef_bolge, ekipman), emb in zip(records, embeddings)
        ],
    )
    conn.commit()

    count = conn.execute("SELECT COUNT(*) FROM chunks").fetchone()[0]
    dim = len(embeddings[0])
    conn.close()

    model.unload()
    print(f"Bitti. {DB_PATH} icinde {count} parca var (vektor boyutu: {dim}).")


if __name__ == "__main__":
    main()
