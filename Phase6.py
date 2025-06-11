# financial_ai_agent.py  –  29 Apr 2025  (final)
"""
JP Morgan Chase • Financial Assistant
• Existing-customer banking queries (balance / recent transactions / savings)
• Light new-user capture
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
    c = sqlite3.connect(DB)
    c.row_factory = sqlite3.Row
    return c

def extract(path: str) -> str:
    ct = []
    with pdfplumber.open(path) as pdf:
        for p in pdf.pages:
            t = p.extract_text()
            if t:
                ct.append(t)
    return "\n".join(ct)[:MAX_CHARS]

def ask_llm(question: str, context: str) -> str:
    rsp = client.chat.completions.create(
        model="gpt-3.5-turbo",
        temperature=0.4,
        max_tokens=500,
        messages=[
            {"role": "system", "content": "You are a helpful financial assistant."},
            {"role": "user",
            "content": f"Context:\n{context}\n\nQuestion:\n{question}"}
        ],
    )
    return rsp.choices[0].message.content.strip()

def again() -> str:
    return ("Anything else I can help with? "
            "(type **upload** to attach a PDF | **exit** to leave)")

# ────────────────────────── chat handler ──────────────────────────
def chat(user, hist):
    global pdf_text
    msg = user.strip()
    low = msg.lower()
    step = state["step"]

    try:
        # ────────── start ──────────
        if step == "start":
            state["step"] = "type"
            return {"role": "assistant",
                    "content":
                    "Welcome! Are you an **existing customer** or a **new user**?"}

        # ────────── choose customer type ──────────
        if step == "type":
            if "existing" in low:
                state["step"] = "phone"
                return {"role": "assistant", "content": "Phone number please:"}
            if "new" in low:
                state["step"] = "start"
                return {"role": "assistant",
                        "content":
                        "Thanks for your interest! A banker will contact you soon — "
                        "have a great day!"}
            return {"role": "assistant",
                    "content": "Please reply **existing** or **new**."}

        # ────────── phone verification ──────────
        if step == "phone":
            with db() as c:
                row = c.execute(
                    "SELECT id, first_name, last_name FROM customers WHERE phone=?",
                    (msg,)
                ).fetchone()
            if not row:
                return {"role": "assistant",
                        "content": "Number not found — try again:"}
            state.update(cid=row["id"], fn=row["first_name"], ln=row["last_name"],
                        step="zip")
            return {"role": "assistant", "content": "ZIP code:"}

        # ────────── ZIP verification ──────────
        if step == "zip":
            with db() as c:
                true = c.execute(
                    "SELECT zip_code FROM customers WHERE id=?",
                    (state["cid"],)
                ).fetchone()["zip_code"]
            if msg != true:
                return {"role": "assistant",
                        "content": "❌ Wrong ZIP — try again:"}
            state["step"] = "ok"
            return {"role": "assistant",
                    "content":
                    f"✅ Verified. Welcome back {state['fn']}!\n{again()}"}

        # ────────── main assistant actions ──────────
        if step == "ok":

            # exit flow
            if low in ("bye", "exit", "close", "thanks", "thank you"):
                state["step"] = "confirm_exit"
                return {"role": "assistant",
                        "content": "Are you sure you want to end the chat? (yes / no)"}

            # upload prompt
            if low == "upload":
                return {"role": "assistant",
                        "content":
                        "Click **Upload** below, then ask me about the file."}

            # balance
            if "balance" in low:
                with db() as c:
                    bal = c.execute(
                        "SELECT balance FROM customers WHERE id=?",
                        (state["cid"],)
                    ).fetchone()["balance"]
                return {"role": "assistant",
                        "content": f"Your balance is **${bal:,.2f}**.\n\n{again()}"}

            # recent transactions
            if "transaction" in low or "recent" in low:
                with db() as c:
                    tx = c.execute(
                        """SELECT date, description, amount
                        FROM transactions
                        WHERE customer_id=?
                        ORDER BY date DESC LIMIT 5""",
                        (state["cid"],)
                    ).fetchall()
                if not tx:
                    return {"role": "assistant",
                            "content": "No recent transactions.\n\n"+again()}
                lines = ["Here are the last 5 transactions:"]
                lines += [f"- {t['date']}: {t['description']} "
                        f"(${t['amount']:.2f})" for t in tx]
                return {"role": "assistant",
                        "content": "\n".join(lines)+"\n\n"+again()}

            # savings products
            if "saving" in low:
                return {"role": "assistant",
                        "content":
                        ("We offer Basic Savings, **High-Yield Savings** (4.5 % APY) "
                         "and Money-Market Accounts. Reply **yes** for the "
                        "application link.\n\n"+again())}

            if low == "yes":
                return {"role": "assistant",
                        "content":
                        "Apply here → https://www.chase.com/personal/savings\n\n"+again()}

            # PDF question
            if pdf_text:
                ans = ask_llm(msg, pdf_text)
                return {"role": "assistant",
                        "content": ans+"\n\n"+again()}

            # fallback
            return {"role": "assistant", "content": again()}

        # ────────── exit confirmation ──────────
        if step == "confirm_exit":
            if low.startswith("y"):
                state.clear(); state["step"] = "start"; pdf_text = None
                return {"role": "assistant",
                        "content": "Session closed. Have a great day!"}
            state["step"] = "ok"
            return {"role": "assistant",
                    "content": "No problem — continuing. "+again()}

        # unknown
        state.clear(); state["step"] = "start"; pdf_text = None
        return {"role": "assistant",
                "content": "Something went wrong — let's start again."}

    except Exception as e:
        print("❗", e)
        state.clear(); state["step"] = "start"; pdf_text = None
        return {"role": "assistant",
                "content": "Internal error — please start again."}

# ────────────────────────── upload handler ──────────────────────────
def upload(path):
    global pdf_text
    if not path:
        pdf_text = None
        return ""
    pdf_text = extract(path)
    return f"✅ {os.path.basename(path)} uploaded successfully! " \
        "Ask me about the document whenever you're ready."

# ────────────────────────── UI build ──────────────────────────
with gr.Blocks(theme=gr.themes.Soft()) as demo:
    gr.Markdown("# JP Morgan Chase • Financial Assistant")

    chat_ui = gr.ChatInterface(
        fn=chat,
        chatbot=gr.Chatbot(type="messages"),
        textbox=gr.Textbox(
            placeholder="Ask about your balance, transactions… or type upload"),
    )

    status = gr.Textbox(label="Upload status", interactive=False)

    uploader = gr.File(
        label="Upload Financial Document (PDF)",
        file_types=[".pdf"],
        type="filepath",
    )
    # the two lines below were the *only* missing piece
    uploader.change(
        upload,           # callback function
        inputs=uploader,  # component whose value is passed in
        outputs=status,   # component to update with callback return
    )

if __name__ == "__main__":
    demo.launch(share=True)