import json
import logging
import litellm
from channels.generic.websocket import AsyncWebsocketConsumer
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils.translation import gettext_lazy as _

from apps.chat.utils import get_llm_kwargs
from apps.chat.models import Chat, ChatMessage, MessageTypes
from apps.chat.tasks import set_chat_name

logger = logging.getLogger(__name__)


class ChatConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        self.user = self.scope["user"]
        chat_id = self.scope["url_route"]["kwargs"].get("chat_id", None)
        if chat_id:
            self.chat = await Chat.objects.aget(user=self.user, id=chat_id)
            self.messages = [m.to_openai_dict() async for m in ChatMessage.objects.filter(chat=self.chat)]
        else:
            self.chat = None
            self.messages = []

        if self.user.is_authenticated:
            await self.accept()
        else:
            await self.close()

    async def disconnect(self, close_code):
        pass

    async def receive(self, text_data):
        text_data_json = json.loads(text_data)
        message_text = text_data_json["message"]

        # do nothing with empty messages
        if not message_text.strip():
            return

        # if no chat set, create one and set the name
        if not self.chat:
            self.chat = await Chat.objects.acreate(user=self.user)
            set_chat_name.delay(self.chat.id, message_text)
            # magic message to tell the front end to update its url
            await self.send(text_data=json.dumps({"pushURL": reverse("chat:single_chat", args=[self.chat.id])}))

        # save the user's message to the DB
        message = await self._save_message(message_text, MessageTypes.HUMAN)

        # show user's message immediately before calling OpenAI API
        user_message_html = render_to_string(
            "chat/websocket_components/user_message.html",
            {
                "message_text": message_text,
            },
        )
        await self.send(text_data=user_message_html)

        # render an empty system message where we'll stream our response
        contents_div_id = f"message-response-{message.id}"
        system_message_html = render_to_string(
            "chat/websocket_components/system_message.html",
            {
                "contents_div_id": contents_div_id,
            },
        )
        await self.send(text_data=system_message_html)

        try:
            response = await self._stream_response_text(contents_div_id, self.messages)
        except Exception as e:
            logger.exception(e)
            response = None
        if not response:
            # if we didn't get a response we should show the user an error.
            error_html = render_to_string(
                "chat/websocket_components/final_system_message.html",
                {
                    "contents_div_id": contents_div_id,
                    "message": _("Sorry, there was an error with your message. Please try again."),
                },
            )
            await self.send(text_data=error_html)

        else:
            # once we've streamed the whole response, save it to the database
            system_message = await self._save_message(response, MessageTypes.AI)

            # replace final input with fully rendered version, so we can render markdown, etc.
            final_message_html = render_to_string(
                "chat/websocket_components/final_system_message.html",
                {
                    "contents_div_id": contents_div_id,
                    "message": system_message.content,
                },
            )
            await self.send(text_data=final_message_html)

    async def _save_message(self, message_text, message_type):
        message = await ChatMessage.objects.acreate(
            chat=self.chat,
            message_type=message_type,
            content=message_text,
        )
        self.messages.append(message.to_openai_dict())
        return message

    async def _stream_response_text(self, contents_div_id, messages) -> str:
        response = await litellm.acompletion(messages=self.messages, stream=True, **get_llm_kwargs())
        chunks = []
        async for chunk in response:
            message_chunk = chunk.choices[0].delta.content
            if message_chunk:
                chunks.append(message_chunk)
                # use htmx to insert the next token at the end of our system message.
                chunk = f'<div hx-swap-oob="beforeend:#{contents_div_id}">{_format_token(message_chunk)}</div>'
                await self.send(text_data=chunk)

        return "".join(chunks)


def _format_token(token: str) -> str:
    # apply very basic formatting while we're rendering tokens in real-time
    token = token.replace("\n", "<br>")
    return token
