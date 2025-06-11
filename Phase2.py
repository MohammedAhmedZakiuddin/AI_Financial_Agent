import pdfplumber
from openai import OpenAI
import gradio as gr
import sqlite3
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()
api_key = os.getenv('OPENAI_API_KEY')
print("Loaded API Key:", api_key)
client = OpenAI(api_key=api_key)

# Initialize session state
customer_info = {}
uploaded_file = None

# Save customer info into database
def save_customer_info(name, phone, email):
    conn = sqlite3.connect('customers.db')
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO customers (name, phone, email) VALUES (?, ?, ?)
    ''', (name, phone, email))
    conn.commit()
    conn.close()

# Extract text from PDF
def extract_text_from_pdf(file_path):
    text = ""
    with pdfplumber.open(file_path) as pdf:
        for page in pdf.pages:
            page_text = page.extract_text()
            if page_text:
                text += page_text
    return text

# Ask AI model
def ask_ai(question, context_text):
    response = client.chat.completions.create(
        model="gpt-3.5-turbo",
        messages=[
            {"role": "system", "content": "You are a helpful financial assistant."},
            {"role": "user", "content": f"Context:\n{context_text}\n\nQuestion: {question}"}
        ],
        temperature=0.5,
        max_tokens=500
    )
    return response.choices[0].message.content

# User Info Tracker
user_info = {
    "name": None,
    "phone": None,
    "email": None,
    "completed": False
}

# Chatbot Logic
def chatbot(message, history):
    global uploaded_file, user_info
    
    if not user_info["completed"]:
        if user_info["name"] is None:
            user_info["name"] = message
            return "Please enter your phone number:"
        
        elif user_info["phone"] is None:
            user_info["phone"] = message
            return "Please enter your email address (optional):"
        
        elif user_info["email"] is None:
            user_info["email"] = message
            user_info["completed"] = True

            # ✅ Save to Database after collecting all
            save_customer_info(user_info["name"], user_info["phone"], user_info["email"])
            return f"Thank you {user_info['name']}! You can now ask your financial questions or upload a document."

    # Normal conversation AFTER collecting info
    if uploaded_file:
        extracted_text = extract_text_from_pdf(uploaded_file)
        ai_answer = ask_ai(message, extracted_text)
        return ai_answer
    else:
        return "Please upload a financial document (PDF) first."

# Upload file handler
def upload_file(file):
    global uploaded_file
    uploaded_file = file
    return "File uploaded successfully! Now you can ask your financial questions."

# Setup Gradio App
with gr.Blocks() as app:
    gr.Markdown("<h1>Financial AI Agent</h1><p>Welcome to JP Morgan Chase Financial Assistant!</p>")

    chatbot_component = gr.ChatInterface(
        fn=chatbot,
        chatbot=gr.Chatbot(),   # ✅ Corrected here
        textbox=gr.Textbox(placeholder="Type your response or financial question...")
    )

    file_upload = gr.File(label="Upload Financial Document (PDF)", type="filepath")
    file_upload.change(upload_file, inputs=file_upload)

# Launch
if __name__ == "__main__":
    app.launch()