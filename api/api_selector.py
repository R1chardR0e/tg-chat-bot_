from config import API_PROVIDER

if API_PROVIDER == "io_net":
    from api.io_net_api import IoNetAPI as Client
elif API_PROVIDER == "mistral":
    from api.mistral_api import MistralAPI as Client
else:
    raise ValueError(f"Неизвестный провайдер API: {API_PROVIDER}")


def get_api_client():
    return Client()
