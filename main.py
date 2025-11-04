import os
import requests
import base64
import time
from typing import Optional, Dict, Any

BOT_TOKEN = os.getenv("gemini_assistant_bot_token")
GEMINI_API_KEY = os.getenv("gemini_api_key")
GEMINI_MODEL = "models/gemini-2.5-flash"
GEMINI_URL = f"https://generativelanguage.googleapis.com/v1beta/{GEMINI_MODEL}:generateContent"
TELEGRAM_API = f"https://api.telegram.org/bot{BOT_TOKEN}"

TEXT_SYSTEM_INSTRUCTION = "You're Gemini assistant telegram bot to assist the users in text generation, image description and chat. You're developed by blind tech visionary community. Your capabilities: google search, image description and text generations. Follow the user's prompt in detail. You are developed by sujan rai at blind tech visionary. You're gemini-2.5-flash. future updates: image generation, voice message support etc."
IMAGE_SYSTEM_INSTRUCTION = "describe the image in detail as prompt."

def get_updates(offset: Optional[int] = None) -> Dict[str, Any]:
    params = {}
    if offset:
        params["offset"] = offset
    r = requests.get(f"{TELEGRAM_API}/getUpdates", params=params, timeout=30)
    r.raise_for_status()
    return r.json()

def send_message(chat_id: int, text: str, parse_mode: Optional[str] = "Markdown") -> Dict[str, Any]:
    url = f"{TELEGRAM_API}/sendMessage"
    data = {"chat_id": chat_id, "text": text, "parse_mode": parse_mode}
    r = requests.post(url, json=data, timeout=30)
    return r.json()

def edit_message(chat_id: int, message_id: int, text: str, parse_mode: Optional[str] = "Markdown") -> Dict[str, Any]:
    url = f"{TELEGRAM_API}/editMessageText"
    data = {
        "chat_id": chat_id,
        "message_id": message_id,
        "text": text,
        "parse_mode": parse_mode
    }
    r = requests.post(url, json=data, timeout=30)
    return r.json()

def get_file_path(file_id: str) -> str:
    r = requests.get(f"{TELEGRAM_API}/getFile", params={"file_id": file_id}, timeout=30)
    r.raise_for_status()
    data = r.json()
    return data["result"]["file_path"]

def download_file_bytes(file_path: str) -> bytes:
    r = requests.get(f"https://api.telegram.org/file/bot{BOT_TOKEN}/{file_path}", timeout=60)
    r.raise_for_status()
    return r.content

def call_gemini_text(user_message: str) -> requests.Response:
    body = {
        "contents": [
            {
                "role": "user",
                "parts": [{"text": user_message}]
            }
        ],
        "system_instruction": TEXT_SYSTEM_INSTRUCTION,
        "generationConfig": {
            "temperature": 1.7,
            "maxOutputTokens": 8192
        },
        "tools": [
            {"googleSearch": {}}
        ]
    }
    headers = {
        "Content-Type": "application/json",
        "x-goog-api-key": GEMINI_API_KEY
    }
    r = requests.post(GEMINI_URL, headers=headers, json=body, timeout=120)
    return r

def call_gemini_image(image_bytes: bytes, prompt_text: str) -> requests.Response:
    b64 = base64.b64encode(image_bytes).decode("utf-8")
    mime = "image/jpeg"
    body = {
        "contents": [
            {
                "parts": [
                    {
                        "inline_data": {
                            "mime_type": mime,
                            "data": b64
                        }
                    },
                    {"text": prompt_text}
                ]
            }
        ],
        "system_instruction": IMAGE_SYSTEM_INSTRUCTION,
        "generationConfig": {
            "temperature": 0.0,
            "maxOutputTokens": 1024
        }
    }
    headers = {
        "Content-Type": "application/json",
        "x-goog-api-key": GEMINI_API_KEY
    }
    r = requests.post(GEMINI_URL, headers=headers, json=body, timeout=120)
    return r

def extract_gemini_response(response_data: Dict[str, Any]) -> str:
    try:
        candidates = response_data.get("candidates", [])
        if candidates:
            content = candidates[0].get("content", {})
            parts = content.get("parts", [])
            if parts:
                return parts[0].get("text", "No response available")
        return "No response available"
    except Exception as e:
        return f"Error parsing response: {str(e)}"

def handle_text_message(chat_id: int, user_message: str):
    status_msg = send_message(chat_id, "Gemini is typing...", parse_mode=None)
    if not status_msg.get("ok"):
        return
    
    status_msg_id = status_msg["result"]["message_id"]
    
    try:
        response = call_gemini_text(user_message)
        
        if response.status_code == 429:
            edit_message(chat_id, status_msg_id, "Sorry, I am busy right now. Try again later.", parse_mode=None)
            return
        
        if response.status_code != 200:
            error_detail = f"Error {response.status_code}: {response.text}"
            edit_message(chat_id, status_msg_id, error_detail, parse_mode=None)
            return
        
        response_data = response.json()
        ai_response = extract_gemini_response(response_data)
        edit_message(chat_id, status_msg_id, ai_response, parse_mode="Markdown")
        
    except requests.exceptions.Timeout:
        edit_message(chat_id, status_msg_id, "Request timeout. Please try again.", parse_mode=None)
    except Exception as e:
        edit_message(chat_id, status_msg_id, f"An error occurred: {str(e)}", parse_mode=None)

def describe_image(chat_id: int, file_id: str, caption: Optional[str] = None):
    status_msg = send_message(chat_id, "Analyzing your image...", parse_mode=None)
    if not status_msg.get("ok"):
        return
    
    status_msg_id = status_msg["result"]["message_id"]
    
    try:
        file_path = get_file_path(file_id)
        image_bytes = download_file_bytes(file_path)
        
        prompt = caption if caption else "Describe the image in detail as prompt."
        
        response = call_gemini_image(image_bytes, prompt)
        
        if response.status_code == 429:
            edit_message(chat_id, status_msg_id, "Sorry, I am busy right now. Try again later.", parse_mode=None)
            return
        
        if response.status_code != 200:
            error_detail = f"Error {response.status_code}: {response.text}"
            edit_message(chat_id, status_msg_id, error_detail, parse_mode=None)
            return
        
        response_data = response.json()
        ai_response = extract_gemini_response(response_data)
        edit_message(chat_id, status_msg_id, ai_response, parse_mode="Markdown")
        
    except requests.exceptions.Timeout:
        edit_message(chat_id, status_msg_id, "Request timeout. Please try again.", parse_mode=None)
    except Exception as e:
        edit_message(chat_id, status_msg_id, f"An error occurred: {str(e)}", parse_mode=None)

def handle_message(message: Dict[str, Any]):
    chat_id = message["chat"]["id"]
    
    if "text" in message:
        text = message["text"]
        
        if text == "/start":
            first_name = message.get("from", {}).get("first_name", "there")
            welcome = f"Hello {first_name}! I'm your Gemini-powered AI assistant, ready to help with anything from quick answers to deep dives. What's on your mind today?"
            send_message(chat_id, welcome, parse_mode=None)
            return
        
        if text.startswith("/"):
            return
        
        handle_text_message(chat_id, text)
        return
    
    if "photo" in message:
        photos = message["photo"]
        file_id = photos[-1]["file_id"]
        caption = message.get("caption")
        describe_image(chat_id, file_id, caption)
        return
    
    if "document" in message:
        document = message["document"]
        mime_type = document.get("mime_type", "")
        file_name = document.get("file_name", "")
        
        if mime_type in ["image/png", "image/jpeg"] or file_name.lower().endswith((".png", ".jpg", ".jpeg")):
            file_id = document["file_id"]
            caption = message.get("caption")
            describe_image(chat_id, file_id, caption)
            return
        else:
            send_message(chat_id, "Sorry, the bot only supports images right now.", parse_mode=None)
            return
    
    if "voice" in message or "audio" in message or "video" in message or "video_note" in message:
        send_message(chat_id, "Sorry, the bot only supports images right now.", parse_mode=None)
        return

def main():
    last_update_id = None
    print("Bot started...")
    
    while True:
        try:
            updates = get_updates(offset=(last_update_id + 1) if last_update_id else None)
            
            for update in updates.get("result", []):
                last_update_id = update["update_id"]
                
                if "message" in update:
                    message = update["message"]
                    handle_message(message)
            
            time.sleep(1)
            
        except KeyboardInterrupt:
            print("\nBot stopped.")
            break
        except Exception as e:
            print(f"Error in main loop: {str(e)}")
            time.sleep(5)

if __name__ == "__main__":
    main()