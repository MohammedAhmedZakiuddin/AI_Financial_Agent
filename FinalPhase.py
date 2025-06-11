# financial_ai_agent.py  –  29 Apr 2025 (refined)
"""
JP Morgan Chase • Financial Assistant
• Existing‑customer banking queries (balance / recent transactions / savings)
• New‑user capture (name → phone → e‑mail)
• Single‑PDF upload + GPT‑assisted Q&A
Run: python financial_ai_agent.py
"""

# ───────────────────────── imports & config ─────────────────────────
import os, sqlite3, pdfplumber, re
import gradio as gr
from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

DB = "customers.db"
MAX_CHARS = 8_000  # max context sent to GPT
state = {"step": "start"}  # conversation FSM
pdf_text: str | None = None  # extracted text of uploaded file

# ────────────────────────── helpers ──────────────────────────

def db():
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    return conn

def extract(path: str) -> str:
    parts: list[str] = []
    with pdfplumber.open(path) as pdf:
        for pg in pdf.pages:
            txt = pg.extract_text()
            if txt:
                parts.append(txt)
    return "\n".join(parts)[:MAX_CHARS]

def ask_llm(question: str, context: str) -> str:
    rsp = client.chat.completions.create(
        model="gpt-3.5-turbo",
        temperature=0.4,
        max_tokens=500,
        messages=[
            {"role": "system", "content": "You are a helpful financial assistant."},
            {"role": "user", "content": f"Context:\n{context}\n\nQuestion:\n{question}"},
        ],
    )
    return rsp.choices[0].message.content.strip()

def again() -> str:
    return ("Anything else I can help with? (balance • transactions • savings "
            "— or type **upload** to attach a PDF | **exit** to leave)")

# tiny fuzzy‑match helpers -------------------------------------------------
re_existing = re.compile(r"\b(exist|current|old|return)\w*", re.I)
re_new = re.compile(r"\b(new|sign|open|join)\w*", re.I)

def looks_like_existing(text: str) -> bool:
    return bool(re_existing.search(text))

def looks_like_new(text: str) -> bool:
    return bool(re_new.search(text))

# ────────────────────────── chat handler ──────────────────────────

def chat(user, hist):
    global pdf_text
    msg = user.strip()
    low = msg.lower()
    step = state.get("step", "start")

    try:
        # ────────── start ──────────
        if step == "start":
            state["step"] = "type"
            return {"role": "assistant",
                    "content": ("👋 **Welcome to JP Morgan Chase Digital Banking Assistant!**\n"
                                "Are you an **existing customer** or a **new user** wishing to open an account?")}

        # ────────── choose customer type ──────────
        if step == "type":
            if looks_like_existing(low):
                state["step"] = "phone"
                return {"role": "assistant", "content": "Great – please enter your registered **phone number**:"}
            if looks_like_new(low):
                state["step"] = "new_name"
                return {"role": "assistant", "content": "Let's get to know you. What's your **first and last name**?"}
            return {"role": "assistant", "content": "Please type **existing** or **new** to continue."}

        # ────────── new‑user capture ──────────
        if step == "new_name":
            state["prospect_name"] = msg.title()
            state["step"] = "new_phone"
            return {"role": "assistant", "content": "Thanks. May I have a **phone number** to reach you?"}

        if step == "new_phone":
            state["prospect_phone"] = msg
            state["step"] = "new_email"
            return {"role": "assistant", "content": "And finally, your **e‑mail address**?"}

        if step == "new_email":
            name = state.pop("prospect_name")
            # potential DB insert for lead capture could go here
            state.clear()
            state["step"] = "ok_new"
            return {"role": "assistant",
                    "content": (f"Thanks {name}! A banker will contact you soon.\n\n" + again())}

        # ────────── phone verification ──────────
        if step == "phone":
            with db() as c:
                row = c.execute("SELECT id, first_name, last_name FROM customers WHERE phone=?", (msg,)).fetchone()
            if not row:
                return {"role": "assistant", "content": "Number not found — please try again:"}
            state.update(cid=row["id"], fn=row["first_name"], ln=row["last_name"], step="zip")
            return {"role": "assistant", "content": "Thank you. Now enter your **ZIP code**:"}

        # ────────── ZIP verification ──────────
        if step == "zip":
            with db() as c:
                real_zip = c.execute("SELECT zip_code FROM customers WHERE id=?", (state["cid"],)).fetchone()["zip_code"]
            if msg != real_zip:
                return {"role": "assistant", "content": "❌ ZIP doesn't match our records — try again:"}
            state["step"] = "ok_exist"
            return {"role": "assistant", "content": f"✅ Welcome back {state['fn']}!\n\n" + again()}

        # ────────── main assistant actions ──────────
        if step in ("ok_exist", "ok_new"):
            if low in ("exit", "quit", "leave"):
                state["step"] = "confirm_exit"
                return {"role": "assistant", "content": "Are you sure you want to end the chat? (yes / no)"}
            if low in ("bye", "thanks", "thank you"):
                state.clear()
                state["step"] = "start"
                pdf_text = None
                return {"role": "assistant", "content": "It was a pleasure assisting you – goodbye!"}

            if low == "upload":
                return {"role": "assistant", "content": "Click **Upload** below, then ask me about the document."}

            if step == "ok_exist":
                if "balance" in low:
                    with db() as c:
                        bal = c.execute("SELECT balance FROM customers WHERE id=?", (state["cid"],)).fetchone()["balance"]
                    return {"role": "assistant", "content": f"Your balance is **${bal:,.2f}**.\n\n" + again()}

                if "transaction" in low or "recent" in low:
                    with db() as c:
                        rows = c.execute(
                            """SELECT date, description, amount FROM transactions
                            WHERE customer_id=? ORDER BY date DESC LIMIT 5""",
                            (state["cid"],)).fetchall()
                    if not rows:
                        return {"role": "assistant", "content": "No recent transactions.\n\n" + again()}
                    out = ["Here are your last 5 transactions:"]
                    out += [f"- {r['date']}: {r['description']} (${r['amount']:.2f})" for r in rows]
                    return {"role": "assistant", "content": "\n".join(out) + "\n\n" + again()}

            if "saving" in low:
                return {"role": "assistant",
                        "content": ("We offer Basic Savings, **High‑Yield Savings** (4.5% APY) "
                                    "and Money‑Market Accounts. Reply **yes** for the link.\n\n" + again())}

            if low == "yes":
                return {"role": "assistant",
                        "content": "Apply here → https://www.chase.com/personal/savings\n\n" + again()}

            if pdf_text:
                return {"role": "assistant", "content": ask_llm(msg, pdf_text) + "\n\n" + again()}

            return {"role": "assistant", "content": again()}

        if step == "confirm_exit":
            if low.startswith("y"):
                state.clear()
                state["step"] = "start"
                pdf_text = None
                return {"role": "assistant", "content": "Session closed. Have a great day!"}
            state["step"] = "ok_exist" if "cid" in state else "ok_new"
            return {"role": "assistant", "content": "No worries – we're still connected. " + again()}

        state.clear()
        state["step"] = "start"
        pdf_text = None
        return {"role": "assistant", "content": "Something went wrong – let's start from the top."}

    except Exception as err:
        print("❗", err)
        state.clear()
        state["step"] = "start"
        pdf_text = None
        return {"role": "assistant", "content": "Internal error – please begin again."}

# ───────────────────────── upload handler ─────────────────────────

def upload(path: str):
    global pdf_text
    if not path:
        pdf_text = None
        return ""
    pdf_text = extract(path)
    return f"✅ {os.path.basename(path)} uploaded successfully! Ask away."

# ───────────────────────── UI build ─────────────────────────
with gr.Blocks(theme=gr.themes.Soft()) as demo:
    gr.Markdown("# JP Morgan Chase • Financial Assistant")
    chat_ui = gr.ChatInterface(
        fn=chat,
        chatbot=gr.Chatbot(type="messages"),
        textbox=gr.Textbox(placeholder="Say hello, or type upload / exit …")
    )
    status = gr.Textbox(label="Upload status", interactive=False)
    uploader = gr.File(label="Upload Financial Document (PDF)", file_types=[".pdf"], type="filepath")
    uploader.change(upload, inputs=uploader, outputs=status)

if __name__ == "__main__":
    demo.launch(share=True)