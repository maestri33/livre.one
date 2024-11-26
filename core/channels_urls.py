from apps.chat.routing import websocket_urlpatterns as chat_patterns
from apps.group_chat.routing import websocket_urlpatterns as group_chat_patterns


urlpatterns = chat_patterns + group_chat_patterns
