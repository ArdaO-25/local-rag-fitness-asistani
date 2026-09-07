from foundry_local_sdk import Configuration, FoundryLocalManager

FoundryLocalManager.initialize(Configuration(app_name="model_listesi"))
manager = FoundryLocalManager.instance

for m in manager.catalog.list_models():
    print(m.alias, "|", m.id)
    