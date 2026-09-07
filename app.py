"""
app.py — Yerel RAG soru-cevap asistani (CLI).

Onkosul: once `python ingest.py` calistirilmis ve knowledge.db olusmus olmali.
Kullanim: python app.py

RAG mantigi (retrieval, prompt olusturma, model yukleme, cevap temizligi)
rag.py modulunde -- bu dosya sadece CLI arayuzunu (girdi/cikti dongusu)
icerir. Ayni rag.py, Streamlit arayuzu olan arayuz.py tarafindan da
kullanilir; iki arayuz de ayni RAG mantigini calistirir.
"""

from rag import load_chunks, load_models, answer_query


def main():
    chunks = load_chunks()
    print(f"{len(chunks)} parca yuklendi.")

    models = load_models(
        app_name="local_rag_app",
        chat_progress_callback=lambda p: print(f"\rSohbet modeli indiriliyor: {p:.1f}%", end="", flush=True),
    )
    print()

    print("\nHazir. Sorunuzu yazin ('cikis' ile kapatin).\n")

    try:
        while True:
            query = input("Soru: ").strip()
            if not query:
                continue
            if query.lower() in ("cikis", "quit", "exit"):
                break

            result = answer_query(query, chunks, models.embedding_client, models.chat_client)

            if result.target_region:
                print(f"  (kas grubu filtresi: {result.target_region})")
            if result.target_equipment:
                print(f"  (ekipman filtresi: {result.target_equipment})")

            # Hata ayiklama icin: hangi parcalar secildi, skorlari ne?
            # Retrieval kotuyse sorun genelde chunk boyutunda ya da
            # embedding modelindedir -- model degil.
            for score, chunk in result.results:
                print(f"  [{score:.3f}] {chunk['source']} — {chunk['content'][:60]}...")

            print(f"\nCevap: {result.answer}\n")

    except (KeyboardInterrupt, EOFError):
        print()

    models.unload()
    print("Modeller bellekten kaldirildi.")


if __name__ == "__main__":
    main()
