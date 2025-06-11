import pdfplumber
from openai import OpenAI
import gradio as gr
import os
from dotenv import load_dotenv

# Load the environment variables from .env file
load_dotenv()
print("Loaded API Key:", os.getenv('OPENAI_API_KEY'))

# Initialize OpenAI Client
client = OpenAI(api_key=os.getenv('OPENAI_API_KEY'))

# Function to extract text from uploaded PDF
def extract_text_from_pdf(file):
    text = ""
    with pdfplumber.open(file.name) as pdf:  # <<=== CHANGE: use file.name here
        for page in pdf.pages:
            page_text = page.extract_text()
            if page_text:
                text += page_text
    return text

# Function to ask OpenAI questions using extracted text
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

# Simple product recommendation based on user question
def product_recommendation(question):
    question = question.lower()

    if "credit card" in question:
        return "Recommended Product: JP Morgan Freedom Unlimited Credit Card."
    elif "loan" in question:
        return "Recommended Product: JP Morgan Personal Loans."
    elif "investment" in question:
        return "Recommended Product: JP Morgan Investment Services."
    elif "savings account" in question:
        return "Recommended Product: JP Morgan High Yield Savings Account."
    else:
        return None

# Gradio function to handle file upload and question answering
def chatbot(file, question):
    if file is None or question.strip() == "":
        return "Please upload a financial document and type your question."

    # Extract the text from the uploaded PDF
    extracted_text = extract_text_from_pdf(file)

    # Get AI response based on user's question
    ai_answer = ask_ai(question, extracted_text)

    # Get product recommendation if any
    recommendation = product_recommendation(question)

    if recommendation:
        final_response = f"{ai_answer}\n\n{recommendation}"
    else:
        final_response = ai_answer

    return final_response

# Set up Gradio Interface
interface = gr.Interface(
    fn=chatbot,
    inputs=[
        gr.File(label="Upload Financial Document (10-K or 10-Q)", type="filepath"),
        gr.Textbox(label="Ask your financial question here:")
    ],
    outputs="text",
    title="Financial AI Agent",
    description="Upload your financial report and ask questions about it!"
)

# Launch the app
if __name__ == "__main__":
    interface.launch()