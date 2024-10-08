# Import necessary libraries
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.keys import Keys
import time
import openai
import json
import logging
import os
from dotenv import load_dotenv
import requests
from PIL import Image
import io
import re
import speech_recognition as sr
from gtts import gTTS

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class WhatsAppAIBot:
    def __init__(self):
        self.driver = None
        self.wait = None
        # Initialize OpenAI API key
        openai.api_key = os.getenv('OPENAI_API_KEY')
        self.conversation_history = {}
        
    def setup_driver(self):
        """Setup Chrome WebDriver with WhatsApp Web"""
        chrome_options = webdriver.ChromeOptions()
        chrome_options.add_argument("--user-data-dir=./whatsapp-session")
        self.driver = webdriver.Chrome(options=chrome_options)
        self.wait = WebDriverWait(self.driver, 30)
        self.driver.get("https://web.whatsapp.com")
        logger.info("Please scan QR code to login to WhatsApp Web")
        
    def wait_for_login(self):
        """Wait for WhatsApp Web login"""
        try:
            self.wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, '[data-testid="chat-list"]')))
            logger.info("Successfully logged in to WhatsApp Web")
            return True
        except Exception as e:
            logger.error(f"Login failed: {str(e)}")
            return False
            
    def get_ai_response(self, message, chat_id):
        """Get response from GPT model with conversation history"""
        try:
            if chat_id not in self.conversation_history:
                self.conversation_history[chat_id] = []
                
            # Add user message to history
            self.conversation_history[chat_id].append({
                "role": "user",
                "content": message
            })
            
            # Keep last 10 messages for context
            if len(self.conversation_history[chat_id]) > 10:
                self.conversation_history[chat_id] = self.conversation_history[chat_id][-10:]
                
            response = openai.ChatCompletion.create(
                model="gpt-4",
                messages=[
                    {"role": "system", "content": "You are a highly intelligent and helpful AI assistant integrated into WhatsApp. You can understand and communicate in multiple languages, help with various tasks, and maintain engaging conversations while being ethical and safe."},
                    *self.conversation_history[chat_id]
                ],
                temperature=0.7,
                max_tokens=1000
            )
            
            ai_response = response.choices[0].message['content']
            
            # Add AI response to history
            self.conversation_history[chat_id].append({
                "role": "assistant",
                "content": ai_response
            })
            
            return ai_response
            
        except Exception as e:
            logger.error(f"Error getting AI response: {str(e)}")
            return "I apologize, but I'm having trouble processing your request at the moment. Please try again later."
            
    def process_voice_message(self, voice_message_path):
        """Convert voice message to text"""
        recognizer = sr.Recognizer()
        with sr.AudioFile(voice_message_path) as source:
            audio = recognizer.record(source)
        try:
            text = recognizer.recognize_google(audio)
            return text
        except Exception as e:
            logger.error(f"Error processing voice message: {str(e)}")
            return None
            
    def text_to_speech(self, text, output_path):
        """Convert text to speech"""
        try:
            tts = gTTS(text=text, lang='en')
            tts.save(output_path)
            return True
        except Exception as e:
            logger.error(f"Error converting text to speech: {str(e)}")
            return False
            
    def handle_message(self, message, chat_id, message_type="text"):
        """Handle incoming messages"""
        try:
            if message_type == "voice":
                # Process voice message
                text = self.process_voice_message(message)
                if not text:
                    return "Sorry, I couldn't understand the voice message."
                response = self.get_ai_response(text, chat_id)
                # Convert response to voice
                voice_response_path = f"response_{chat_id}.mp3"
                self.text_to_speech(response, voice_response_path)
                return {"type": "voice", "content": voice_response_path}
            else:
                # Handle text message
                return {"type": "text", "content": self.get_ai_response(message, chat_id)}
                
        except Exception as e:
            logger.error(f"Error handling message: {str(e)}")
            return {"type": "text", "content": "Sorry, I encountered an error while processing your message."}
            
    def send_message(self, chat_selector, response):
        """Send message in WhatsApp"""
        try:
            # Find and click on chat
            chat = self.wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, chat_selector)))
            chat.click()
            
            # Find message input and send message
            message_box = self.wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, '[data-testid="conversation-compose-box-input"]')))
            message_box.clear()
            
            if isinstance(response, dict):
                if response["type"] == "voice":
                    # Handle voice message sending
                    attachment_btn = self.driver.find_element(By.CSS_SELECTOR, '[data-testid="attach-button"]')
                    attachment_btn.click()
                    
                    # Send voice file
                    file_input = self.driver.find_element(By.CSS_SELECTOR, 'input[type="file"]')
                    file_input.send_keys(os.path.abspath(response["content"]))
                    
                    # Clean up voice file
                    os.remove(response["content"])
                else:
                    # Send text message
                    message_box.send_keys(response["content"])
            else:
                message_box.send_keys(response)
                
            message_box.send_keys(Keys.ENTER)
            time.sleep(1)  # Wait for message to send
            
        except Exception as e:
            logger.error(f"Error sending message: {str(e)}")
            
    def monitor_messages(self):
        """Monitor and respond to incoming messages"""
        try:
            while True:
                # Find unread messages
                unread_messages = self.driver.find_elements(By.CSS_SELECTOR, '[data-testid="unread-count"]')
                
                for message in unread_messages:
                    chat_selector = message.find_element(By.XPATH, './../../..')
                    chat_id = chat_selector.get_attribute('data-testid')
                    
                    # Click on chat to read message
                    chat_selector.click()
                    time.sleep(1)
                    
                    # Get last message
                    messages = self.driver.find_elements(By.CSS_SELECTOR, '[data-testid="msg-container"]')
                    last_message = messages[-1]
                    
                    # Check message type
                    if last_message.find_elements(By.CSS_SELECTOR, '[data-testid="audio-play"]'):
                        # Handle voice message
                        response = self.handle_message(None, chat_id, message_type="voice")
                    else:
                        # Handle text message
                        message_text = last_message.find_element(By.CSS_SELECTOR, '[data-testid="message-text"]').text
                        response = self.handle_message(message_text, chat_id)
                        
                    # Send response
                    self.send_message(f'[data-testid="{chat_id}"]', response)
                    
                time.sleep(1)  # Wait before checking for new messages
                
        except Exception as e:
            logger.error(f"Error monitoring messages: {str(e)}")
            self.driver.quit()
            
    def run(self):
        """Run the WhatsApp AI bot"""
        try:
            self.setup_driver()
            if self.wait_for_login():
                logger.info("Starting message monitoring...")
                self.monitor_messages()
        except Exception as e:
            logger.error(f"Error running bot: {str(e)}")
            if self.driver:
                self.driver.quit()
                
if __name__ == "__main__":
    bot = WhatsAppAIBot()
    bot.run()
