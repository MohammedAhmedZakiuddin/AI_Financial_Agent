"""JP Morgan Chase – Financial Assistant (rev 27 Apr 2025)
   * Conversational banking helper
   * Lightweight PDF Q&A after customer verification
   * SQLite demo back‑end (customers.db, transactions)
"""

# ───────────────────────── IMPORTS & CONFIG ────────────────────────────
import os, sqlite3, pdfplumber
from datetime import datetime
import gradio as gr
from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# ────────────────────────── GLOBAL STATE ───────────────────────────────
user_state = {"step": "start"}           # simple FSM per session
uploaded_file_path: str | None = None     # pdf currently in context

# ──────────────────────────── HELPERS ──────────────────────────────────

def db():
    """Return a row‑dict sqlite connection (call with *with*)."""
    conn = sqlite3.connect("customers.db")
    conn.row_factory = sqlite3.Row
    return conn


def extract_pdf(path: str) -> str:
    """Return first ≈8k chars of text from a PDF (token‑safe)."""
    txt_parts = []
    with pdfplumber.open(path) as pdf:
        for page in pdf.pages:
            if (p := page.extract_text()):
                txt_parts.append(p)
    return "\n".join(txt_parts)[:8_000]


def ask_llm(question: str, context: str) -> str:
    """Send *question* plus *context* to GPT and return the answer."""
    resp = client.chat.completions.create(
        model="gpt-3.5-turbo",
        temperature=0.4,
        max_tokens=512,
        messages=[
            {"role": "system", "content": "You are a helpful financial assistant."},
            {"role": "user",    "content": f"Context:\n{context}\n\nQuestion:\n{question}"},
        ],
    )
    return resp.choices[0].message.content.strip()

# ─────────────────────────── CHAT LOGIC ────────────────────────────────

def bot(user_msg: str, history):
    """Gradio ChatInterface callback: (message:str, history:list) → dict"""
    global uploaded_file_path
    msg   = user_msg.strip()
    lower = msg.lower()
    step  = user_state["step"]

    try:
        # ─────────────── INTRO ───────────────
        if step == "start":
            user_state["step"] = "await_type"
            return {"role": "assistant",
                    "content": ("Welcome to **JP Morgan Chase Financial Assistant**.\n"
                                "Are you an **existing customer** or a **new user**?")}

        # ──────────── EXISTING / NEW ─────────
        if step == "await_type":
            if "existing" in lower:
                user_state["step"] = "await_phone"
                return {"role": "assistant",
                        "content": "Please enter your registered **phone number**:"}
            if "new" in lower:
                user_state["step"] = "new_name"
                return {"role": "assistant",
                        "content": "Great! Let's get you started – what's your **full name**?"}
            return {"role": "assistant",
                    "content": "Kindly type **existing** or **new** to continue."}

        # ──────────── NEW‑USER MINI FLOW ─────
        if step == "new_name":
            user_state["new_name"] = msg.title()
            user_state["step"] = "new_email"
            return {"role": "assistant", "content": "Thanks! May I have your **e‑mail address**?"}

        if step == "new_email":
            # 👉 In real life you'd persist the prospect here
            name = user_state.pop("new_name", "")
            user_state.clear(); user_state["step"] = "start"
            return {"role": "assistant", "content": f"Thanks {name}! A banker will reach out soon. Have a great day."}

        # ─────────── PHONE AUTH ───────────────
        if step == "await_phone":
            with db() as conn:
                row = conn.execute("SELECT id, first_name, last_name FROM customers WHERE phone=?", (msg,)).fetchone()
            if row:
                user_state.update(customer_id=row["id"], first=row["first_name"], last=row["last_name"], step="await_zip")
                return {"role": "assistant", "content": "Thanks – now your **ZIP code**, please:"}
            return {"role": "assistant", "content": "❌ Phone not found. Try again:"}

        if step == "await_zip":
            with db() as conn:
                zip_ok = conn.execute("SELECT 1 FROM customers WHERE id=? AND zip_code=?", (user_state["customer_id"], msg)).fetchone()
            if zip_ok:
                user_state["step"] = "verified"
                return {"role": "assistant",
                        "content": (f"✅ Verified. Welcome back, {user_state['first']} {user_state['last']}!\n"
                                     "Ask me about your **balance**, **recent transactions**, **savings products**,\n"
                                     "or say **upload** to analyse a PDF.")}
            return {"role": "assistant", "content": "ZIP code incorrect – please retry:"}

        # ─────────── VERIFIED ACTIONS ─────────
        if step == "verified":
            cid = user_state["customer_id"]

            # Balance
            if "balance" in lower:
                with db() as conn:
                    bal = conn.execute("SELECT balance FROM customers WHERE id=?", (cid,)).fetchone()[0]
                return {"role": "assistant", "content": f"Your current balance is **${bal:,.2f}**."}

            # Recent transactions
            if "transaction" in lower or "recent" in lower:
                with db() as conn:
                    rows = conn.execute("""SELECT date, description, amount
                                        FROM transactions
                                        WHERE customer_id=?
                                        ORDER BY date DESC LIMIT 5""", (cid,)).fetchall()
                if not rows:
                    return {"role": "assistant", "content": "No recent transactions found."}
                lines = ["Here are your last 5 transactions:"]
                for r in rows:
                    lines.append(f"- {r['date']}: {r['description']} (${r['amount']:.2f})")
                return {"role": "assistant", "content": "\n".join(lines)}

            # Savings products
            if "saving" in lower:
                return {"role": "assistant",
                        "content": ("We offer **Basic Savings**, **High‑Yield Savings** (4.5 % APY), and **Money‑Market Accounts**.\n"
                                     "Would you like the **application link**?")}
            if lower in {"yes", "yes please", "y", "yep"}:
                return {"role": "assistant", "content": "You can start an application here → <https://www.chase.com/personal/savings>"}

            # Invite user to upload PDF
            if "upload" in lower and "pdf" in lower and not uploaded_file_path:
                return {"role": "assistant", "content": "Sure – please use the *Upload Financial Document* button below."}

            # PDF Q&A when a file is already uploaded
            if uploaded_file_path and uploaded_file_path.lower().endswith(".pdf"):
                ctx = extract_pdf(uploaded_file_path)
                answer = ask_llm(msg, ctx)
                return {"role": "assistant", "content": answer}

            # Exit gracefully
            if any(k in lower for k in ("bye", "exit", "close", "thank")):
                user_state.clear(); user_state["step"] = "start"; uploaded_file_path = None
                return {"role": "assistant", "content": "Thank you for banking with JP Morgan Chase. Good‑bye!"}

            # Fallback
            return {"role": "assistant", "content": "I'm here to help with **balance**, **transactions**, **savings**, or PDF analysis. What can I do for you?"}

        # ───────── UNKNOWN STATE SAFETY NET ──────────
        user_state.clear(); user_state["step"] = "start"; uploaded_file_path = None
        return {"role": "assistant", "content": "Something went wrong – let's start over."}

    except Exception as err:
        print("❗", err)
        user_state.clear(); user_state["step"] = "start"; uploaded_file_path = None
        return {"role": "assistant", "content": "Sorry – internal error. Please begin again."}

# ─────────────────────── FILE‑UPLOAD HANDLER ──────────────────────────

def handle_upload(file):
    """Remember the uploaded PDF path and tell user it's ready."""
    global uploaded_file_path
    if file is None:
        return  # called when user removes a file
    uploaded_file_path = getattr(file, "name", file)  # normalise tempfile ↦ path str
    return gr.update(value="✅ File uploaded! Ask me anything about it." )

# ───────────────────────────── UI ──────────────────────────────────────
with gr.Blocks(theme=gr.themes.Soft()) as demo:
    gr.Markdown("""# JP Morgan Chase • Financial Assistant
    *Your personalised banking experience awaits 🚀*""")

    chat = gr.ChatInterface(fn=bot,
                            chatbot=gr.Chatbot(type="messages"),
                            textbox=gr.Textbox(placeholder="Ask about your balance, transactions, savings, or say ‘upload pdf’…"))

    upload_box = gr.File(label="Upload Financial Document (PDF)",
                        file_types=[".pdf"], type="filepath")
    # show a small helper message when upload completes
    helper_out = gr.Textbox(show_label=False, interactive=False)
    upload_box.change(handle_upload, inputs=upload_box, outputs=helper_out)

# ──────────────────────────── MAIN ─────────────────────────────────────
if __name__ == "__main__":
    demo.launch(share=True)
