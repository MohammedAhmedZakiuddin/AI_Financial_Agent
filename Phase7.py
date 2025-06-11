# financial_ai_agent.py  –  29 Apr 2025  (final-plus)
"""
JP Morgan Chase • Financial Assistant
• Existing-customer banking queries (balance / recent transactions / savings)
• New-user capture (name → phone → e-mail)
• Single-PDF upload + GPT-assisted Q&A
Run:  python financial_ai_agent.py
"""

# ────────────────────────── imports & config ──────────────────────────
import os, sqlite3, pdfplumber
import gradio as gr
from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

DB               = "customers.db"
MAX_CHARS        = 8_000              # max context sent to GPT
state            = {"step": "start"}  # simple FSM
pdf_text: str | None = None           # extracted text of uploaded file

# ────────────────────────── helpers ──────────────────────────
def db():
    c = sqlite3.connect(DB); c.row_factory = sqlite3.Row; return c

def extract(path: str) -> str:
    chunks = []
    with pdfplumber.open(path) as pdf:
        for p in pdf.pages:
            txt = p.extract_text()
            if txt: chunks.append(txt)
    return "\n".join(chunks)[:MAX_CHARS]

def ask_llm(question: str, context: str) -> str:
    rsp = client.chat.completions.create(
        model="gpt-3.5-turbo",
        temperature=0.4,
        max_tokens=500,
        messages=[
            {"role": "system", "content": "You are a helpful financial assistant."},
            {"role": "user",   "content": f"Context:\n{context}\n\nQuestion:\n{question}"},
        ],
    )
    return rsp.choices[0].message.content.strip()

def again() -> str:
    return ("Anything else I can help with? (balance • transactions • savings "
            "— or type **upload** to attach a PDF | **exit** to leave)")

# ────────────────────────── chat handler ──────────────────────────
def chat(user, hist):
    global pdf_text
    msg, low = user.strip(), user.strip().lower()
    step = state.get("step", "start")

    try:
        # ────────── start ──────────
        if step == "start":
            state["step"] = "type"
            return {"role": "assistant",
                    "content": "Welcome! Are you an **existing customer** or a **new user**?"}

        # ────────── choose customer type ──────────
        if step == "type":
            if "existing" in low:
                state["step"] = "phone"
                return {"role": "assistant", "content": "Phone number please:"}
            if "new" in low:
                state["step"] = "new_name"
                return {"role": "assistant", "content": "Great! What's your **first and last name**?"}
            return {"role": "assistant", "content": "Please reply **existing** or **new**."}

        # ────────── new-user capture ──────────
        if step == "new_name":
            state["prospect_name"] = msg
            state["step"] = "new_phone"
            return {"role": "assistant", "content": "Thanks. May I have a **phone number** to reach you?"}

        if step == "new_phone":
            state["prospect_phone"] = msg
            state["step"] = "new_email"
            return {"role": "assistant", "content": "And finally, your **e-mail address**?"}

        if step == "new_email":
            # (insert into a leads table here if desired)
            name = state.pop("prospect_name")
            state.clear(); state["step"] = "ok_new"
            return {"role": "assistant",
                    "content": (f"Thanks {name}! A banker will contact you soon.\n\n{again()}")}

        # ────────── phone verification ──────────
        if step == "phone":
            with db() as c:
                row = c.execute(
                    "SELECT id, first_name, last_name FROM customers WHERE phone=?",
                    (msg,)).fetchone()
            if not row:
                return {"role": "assistant", "content": "Number not found — try again:"}
            state.update(cid=row["id"], fn=row["first_name"], ln=row["last_name"], step="zip")
            return {"role": "assistant", "content": "ZIP code:"}

        # ────────── ZIP verification ──────────
        if step == "zip":
            with db() as c:
                true_zip = c.execute("SELECT zip_code FROM customers WHERE id=?", (state["cid"],)).fetchone()["zip_code"]
            if msg != true_zip:
                return {"role": "assistant", "content": "❌ Wrong ZIP — try again:"}
            state["step"] = "ok_exist"
            return {"role": "assistant",
                    "content": f"✅ Verified. Welcome back {state['fn']}!\n{again()}"}

        # ────────── main assistant actions ──────────
        if step in ("ok_exist", "ok_new"):

            # quick exit flow
            if low in ("bye", "exit", "close", "thanks", "thank you"):
                state["step"] = "confirm_exit"
                return {"role": "assistant", "content": "Are you sure you want to end the chat? (yes / no)"}

            # upload prompt
            if low == "upload":
                return {"role": "assistant",
                        "content": "Click **Upload** below, then ask me about the file."}

            # balance / transactions available only for verified existing customers
            if step == "ok_exist":
                if "balance" in low:
                    with db() as c:
                        bal = c.execute("SELECT balance FROM customers WHERE id=?", (state["cid"],)).fetchone()["balance"]
                    return {"role": "assistant", "content": f"Your balance is **${bal:,.2f}**.\n\n{again()}"}

                if "transaction" in low or "recent" in low:
                    with db() as c:
                        tx = c.execute(
                            """SELECT date, description, amount
                            FROM transactions
                            WHERE customer_id=? ORDER BY date DESC LIMIT 5""",
                            (state["cid"],)).fetchall()
                    if not tx:
                        return {"role": "assistant", "content": "No recent transactions.\n\n"+again()}
                    lines = ["Here are the last 5 transactions:"]
                    lines += [f"- {t['date']}: {t['description']} (${t['amount']:.2f})" for t in tx]
                    return {"role": "assistant", "content": "\n".join(lines)+"\n\n"+again()}

            # savings products (anyone can ask)
            if "saving" in low:
                return {"role": "assistant",
                        "content": ("We offer Basic Savings, **High-Yield Savings** (4.5 % APY) "
                                    "and Money-Market Accounts. Reply **yes** for the link.\n\n"+again())}

            if low == "yes":
                return {"role": "assistant",
                        "content": "Apply here → https://www.chase.com/personal/savings\n\n"+again()}

            # PDF question
            if pdf_text:
                answer = ask_llm(msg, pdf_text)
                return {"role": "assistant", "content": answer+"\n\n"+again()}

            # fallback
            return {"role": "assistant", "content": again()}

        # ────────── exit confirmation ──────────
        if step == "confirm_exit":
            if low.startswith("y"):
                state.clear(); state["step"] = "start"; pdf_text = None
                return {"role": "assistant", "content": "Session closed. Have a great day!"}
            state["step"] = "ok_exist" if "cid" in state else "ok_new"
            return {"role": "assistant", "content": "No problem — continuing. "+again()}

        # unknown state fallback
        state.clear(); state["step"] = "start"; pdf_text = None
        return {"role": "assistant", "content": "Something went wrong — let's start again."}

    except Exception as e:
        print("❗", e)
        state.clear(); state["step"] = "start"; pdf_text = None
        return {"role": "assistant", "content": "Internal error — please start again."}

# ────────────────────────── upload handler ──────────────────────────
def upload(path):
    global pdf_text
    if not path:
        pdf_text = None
        return ""
    pdf_text = extract(path)
    return (f"✅ {os.path.basename(path)} uploaded successfully! "
            "Ask me anything about it.")

# ────────────────────────── UI build ──────────────────────────
with gr.Blocks(theme=gr.themes.Soft()) as demo:
    gr.Markdown("# JP Morgan Chase • Financial Assistant")

    chat_ui = gr.ChatInterface(
        fn=chat,
        chatbot=gr.Chatbot(type="messages"),
        textbox=gr.Textbox(
            placeholder="Ask about balance, transactions, savings… or type upload"),
    )

    status = gr.Textbox(label="Upload status", interactive=False)

    uploader = gr.File(label="Upload Financial Document (PDF)",
                    file_types=[".pdf"], type="filepath")
    uploader.change(upload, inputs=uploader, outputs=status)

if __name__ == "__main__":
    demo.launch(share=True)
