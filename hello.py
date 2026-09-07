from foundry_local_sdk import Configuration, FoundryLocalManager

FoundryLocalManager.initialize(Configuration(app_name="ilk_test"))
manager = FoundryLocalManager.instance

# Windows'ta donanım hızlandırma sağlayıcılarını indirip kaydeder.
print("Execution provider'lar hazırlanıyor...")
manager.download_and_register_eps(
    progress_callback=lambda ad, yuzde: print(f"\r  {ad}: {yuzde:.0f}%", end="", flush=True)
)
print()

model = manager.catalog.get_model("qwen2.5-0.5b")
model.download(lambda p: print(f"\rModel indiriliyor: {p:.1f}%", end="", flush=True))
print()
model.load()
print("Model yüklendi.\n")

client = model.get_chat_client()
for chunk in client.complete_streaming_chat(
    [{"role": "user", "content": "Merhaba, kısaca kendini tanıt."}]
):
    if chunk.choices and chunk.choices[0].delta.content:
        print(chunk.choices[0].delta.content, end="", flush=True)
print()

model.unload()