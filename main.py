from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
import httpx
import base64
from typing import Optional, Dict, Any

app = FastAPI()

BOT_TOKEN = "8519431229:AAGEhxZsvA02-Yr9iT_XI3FXP8AJDDS4IS0"
TELEGRAM_API = f"https://api.telegram.org/bot{BOT_TOKEN}"
GEMINI_API_KEY = "AIzaSyDCFvhS8RVWHicWe4ZjptBJvut_yDp4dJo"
GEMINI_MODEL = "models/gemini-2.5-flash"
GEMINI_URL = f"https://generativelanguage.googleapis.com/v1beta/{GEMINI_MODEL}:generateContent"

TEXT_SYSTEM_INSTRUCTION = (
    "You're Gemini assistant telegram bot to assist the users in text generation, image description and chat. "
    "You're developed by blind tech visionary community. Your capabilities: google search, image description and text generations. "
    "Follow the user's prompt in detail. You are developed by sujan rai at blind tech visionary. You're gemini-2.5-flash. "
    "future updates: image generation, voice message support etc."
)

IMAGE_SYSTEM_INSTRUCTION = "describe the image in detail as prompt."


async def send_message(chat_id: int, text: str, parse_mode: Optional[str] = "Markdown") -> Dict[str, Any]:
    url = f"{TELEGRAM_API}/sendMessage"
    data = {"chat_id": chat_id, "text": text, "parse_mode": parse_mode}
    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.post(url, json=data)
        return r.json()


async def edit_message(chat_id: int, message_id: int, text: str, parse_mode: Optional[str] = "Markdown") -> Dict[str, Any]:
    url = f"{TELEGRAM_API}/editMessageText"
    data = {"chat_id": chat_id, "message_id": message_id, "text": text, "parse_mode": parse_mode}
    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.post(url, json=data)
        return r.json()


async def get_file_path(file_id: str) -> str:
    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.get(f"{TELEGRAM_API}/getFile", params={"file_id": file_id})
        r.raise_for_status()
        return r.json()["result"]["file_path"]


async def download_file_bytes(file_path: str) -> bytes:
    async with httpx.AsyncClient(timeout=60) as client:
        r = await client.get(f"https://api.telegram.org/file/bot{BOT_TOKEN}/{file_path}")
        r.raise_for_status()
        return r.content


async def call_gemini_text(user_message: str) -> Dict[str, Any]:
    body = {
        "contents": [{"role": "user", "parts": [{"text": user_message}]}],
        "system_instruction": TEXT_SYSTEM_INSTRUCTION,
        "generationConfig": {"temperature": 1.7, "maxOutputTokens": 8192},
        "tools": [{"googleSearch": {}}]
    }
    headers = {"Content-Type": "application/json", "x-goog-api-key": GEMINI_API_KEY}
    async with httpx.AsyncClient(timeout=120) as client:
        r = await client.post(GEMINI_URL, headers=headers, json=body)
        return r.json()


async def call_gemini_image(image_bytes: bytes, prompt_text: str) -> Dict[str, Any]:
    b64 = base64.b64encode(image_bytes).decode("utf-8")
    body = {
        "contents": [
            {"parts": [{"inline_data": {"mime_type": "image/jpeg", "data": b64}}, {"text": prompt_text}]}
        ],
        "system_instruction": IMAGE_SYSTEM_INSTRUCTION,
        "generationConfig": {"temperature": 0.0, "maxOutputTokens": 1024}
    }
    headers = {"Content-Type": "application/json", "x-goog-api-key": GEMINI_API_KEY}
    async with httpx.AsyncClient(timeout=120) as client:
        r = await client.post(GEMINI_URL, headers=headers, json=body)
        return r.json()


def extract_gemini_response(response_data: Dict[str, Any]) -> str:
    try:
        candidates = response_data.get("candidates", [])
        if candidates:
            parts = candidates[0].get("content", {}).get("parts", [])
            if parts:
                return parts[0].get("text", "No response available")
        return "No response available"
    except Exception as e:
        return f"Error parsing response: {str(e)}"


async def handle_text_message(chat_id: int, user_message: str):
    status_msg = await send_message(chat_id, "Gemini is typing...", parse_mode=None)
    if not status_msg.get("ok"):
        return
    status_msg_id = status_msg["result"]["message_id"]
    try:
        response_data = await call_gemini_text(user_message)
        ai_response = extract_gemini_response(response_data)
        await edit_message(chat_id, status_msg_id, ai_response, parse_mode="Markdown")
    except Exception as e:
        await edit_message(chat_id, status_msg_id, f"An error occurred: {str(e)}", parse_mode=None)


async def describe_image(chat_id: int, file_id: str, caption: Optional[str] = None):
    status_msg = await send_message(chat_id, "Analyzing your image...", parse_mode=None)
    if not status_msg.get("ok"):
        return
    status_msg_id = status_msg["result"]["message_id"]
    try:
        file_path = await get_file_path(file_id)
        image_bytes = await download_file_bytes(file_path)
        prompt = caption if caption else "Describe the image in detail as prompt."
        response_data = await call_gemini_image(image_bytes, prompt)
        ai_response = extract_gemini_response(response_data)
        await edit_message(chat_id, status_msg_id, ai_response, parse_mode="Markdown")
    except Exception as e:
        await edit_message(chat_id, status_msg_id, f"An error occurred: {str(e)}", parse_mode=None)


async def handle_message(message: Dict[str, Any]):
    chat_id = message["chat"]["id"]

    if "text" in message:
        text = message["text"]
        if text == "/start":
            first_name = message.get("from", {}).get("first_name", "there")
            welcome = f"Hello {first_name}! I'm your Gemini-powered AI assistant, ready to help with anything from quick answers to deep dives. What's on your mind today?"
            await send_message(chat_id, welcome, parse_mode=None)
            return
        if text.startswith("/"):
            return
        await handle_text_message(chat_id, text)
        return

    if "photo" in message:
        file_id = message["photo"][-1]["file_id"]
        caption = message.get("caption")
        await describe_image(chat_id, file_id, caption)
        return

    if "document" in message:
        document = message["document"]
        mime_type = document.get("mime_type", "")
        file_name = document.get("file_name", "")
        if mime_type in ["image/png", "image/jpeg"] or file_name.lower().endswith((".png", ".jpg", ".jpeg")):
            await describe_image(chat_id, document["file_id"], message.get("caption"))
        else:
            await send_message(chat_id, "Sorry, the bot only supports images right now.", parse_mode=None)
        return

    if "voice" in message or "audio" in message or "video" in message or "video_note" in message:
        await send_message(chat_id, "Sorry, the bot only supports images right now.", parse_mode=None)
        return


@app.get("/")
async def home():
    return {"status": "ok", "message": "Gemini AI Bot is running!"}


@app.post("/webhook")
async def telegram_webhook(req: Request):
    update = await req.json()
    if "message" in update:
        await handle_message(update["message"])
    return JSONResponse({"ok": True})