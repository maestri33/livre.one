import litellm
from celery import shared_task
from apps.chat.utils import get_llm_kwargs
from apps.chat.models import Chat


@shared_task
def set_chat_name(chat_id: int, message: str):
    chat = Chat.objects.get(id=chat_id)
    if not message:
        return
    elif len(message) < 20:
        # for short messages, just use them as the chat name. the summary won't help
        chat.name = message
        chat.save()
    else:
        # set the name with openAI
        system_naming_prompt = """
    You are SummaryBot. When I give you an input, your job is to summarize the intent of that input.
    Provide only the summary of the input and nothing else.
    Summaries should be less than 100 characters long.
    """
        messages = [
            {"role": "system", "content": system_naming_prompt},
            {"role": "user", "content": f"Summarize the following text: '{message}'"},
        ]
        response = litellm.completion(messages=messages, **get_llm_kwargs())
        chat.name = response.choices[0].message.content[:100].strip()
        chat.save()
