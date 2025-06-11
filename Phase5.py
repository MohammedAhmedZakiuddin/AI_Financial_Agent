# financial_ai_agent.py  –  v2 (27 Apr 2025)
"""
JP Morgan Chase Financial Assistant
· existing‑customer banking queries (balance / recent txns / savings)
· light new‑user capture
· multi‑PDF upload + GPT‑assisted Q&A
The script is self‑contained – run `python financial_ai_agent.py`.
"""

# ───────────────────────── imports & config ─────────────────────────
import os, sqlite3, pdfplumber
from datetime import datetime
import gradio as gr
from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# ─────────────────────────── globals ───────────────────────────────
user_state: dict = {"step": "start"}                    # FSM
uploaded_files: list[str] = []                            # multiple PDFs
MAX_PDFS = 3                                              # soft limit

# ────────────────────────── utilities ─────────────────────────────

def db():
    conn = sqlite3.connect("customers.db")
    conn.row_factory = sqlite3.Row
    return conn


def extract_pdf(path: str) -> str:
    """Return <= 8k chars of raw text from the PDF."""
    txt = []
    with pdfplumber.open(path) as pdf:
        for pg in pdf.pages:
            if (t := pg.extract_text()):
                txt.append(t)
    return "\n".join(txt)[:8_000]


def ask_llm(question: str, context: str) -> str:
    rsp = client.chat.completions.create(
        model="gpt-3.5-turbo",
        temperature=0.4,
        max_tokens=512,
        messages=[
            {"role": "system", "content": "You are a helpful financial assistant."},
            {"role": "user", "content": f"Context:\n{context}\n\nQuestion:\n{question}"},
        ],
    )
    return rsp.choices[0].message.content.strip()


def follow_up() -> str:
    """Standard follow‑up prompt after most answers."""
    parts = [
        "I'm here to help with **balance**, **transactions**, **savings**,",
        "or **PDF analysis**.  What can I do for you?",
    ]
    if len(uploaded_files) < MAX_PDFS:
        parts.append(" _(Tip: type **upload** to attach a PDF.)_")
    return " ".join(parts)

# ─────────────────────── chat handler (FSM) ───────────────────────

def bot(user_msg: str, history):
    msg = user_msg.strip()
    lower = msg.lower()
    step = user_state.get("step", "start")

    try:
        # ───────────── start ─────────────
        if step == "start":
            user_state["step"] = "await_type"
            return {
                "role": "assistant",
                "content": (
                    "Welcome to JP Morgan Chase Financial Assistant.\n"
                    "Are you an **existing customer** or a **new user**?"
                ),
            }

        # ───────────── customer type ─────────────
        if step == "await_type":
            if "existing" in lower:
                user_state["step"] = "await_phone"
                return {"role": "assistant", "content": "Please enter your registered phone number:"}
            if "new" in lower:
                user_state["step"] = "new_name"
                return {"role": "assistant", "content": "Great – what's your full name?"}
            return {
                "role": "assistant",
                "content": "Please type **existing** or **new** to continue.",
            }

        # ───────────── new‑user mini‑flow ─────────────
        if step == "new_name":
            user_state["tmp_name"] = msg
            user_state["step"] = "new_email"
            return {"role": "assistant", "content": "Thanks.  Your e‑mail address?"}

        if step == "new_email":
            name = user_state.pop("tmp_name", "")
            # (a real app would persist the lead here)
            user_state.clear(); user_state["step"] = "start"
            return {
                "role": "assistant",
                "content": f"Thanks, {name}!  A banker will contact you shortly.  Have a great day!",
            }

        # ───────────── existing‑customer auth ─────────────
        if step == "await_phone":
            with db() as conn:
                row = conn.execute(
                    "SELECT id, first_name, last_name FROM customers WHERE phone = ?",
                    (msg,),
                ).fetchone()
            if not row:
                return {"role": "assistant", "content": "Phone not found.  Please try again:"}
            user_state.update(
                customer_id=row["id"],
                first=row["first_name"],
                last=row["last_name"],
                step="await_zip",
            )
            return {"role": "assistant", "content": "Thanks.  Now your ZIP code:"}

        if step == "await_zip":
            with db() as conn:
                zip_code = conn.execute(
                    "SELECT zip_code FROM customers WHERE id = ?",
                    (user_state["customer_id"],),
                ).fetchone()["zip_code"]
            if msg != zip_code:
                return {"role": "assistant", "content": "❌ ZIP incorrect.  Try again:"}
            user_state["step"] = "verified"
            return {
                "role": "assistant",
                "content": (
                    f"✅ Verified.  Welcome back {user_state['first']} {user_state['last']}!\n"
                    "Ask me about your **balance**, **recent transactions**, **savings products**,\n"
                    "or say **upload** to analyse a PDF."
                ),
            }

        # ───────────── verified user actions ─────────────
        if step == "verified":
            cid = user_state["customer_id"]

            # prompt to upload
            if lower == "upload":
                return {
                    "role": "assistant",
                    "content": (
                        "Sure – click the **Upload** button below to attach a PDF (up to "
                        f"{MAX_PDFS} files)."
                    ),
                }

            # balance
            if "balance" in lower:
                with db() as conn:
                    bal = conn.execute("SELECT balance FROM customers WHERE id=?", (cid,)).fetchone()["balance"]
                return {
                    "role": "assistant",
                    "content": f"Your current balance is **${bal:,.2f}**.\n\n{follow_up()}",
                }

            # recent transactions
            if "transaction" in lower or "recent" in lower:
                with db() as conn:
                    rows = conn.execute(
                        """SELECT date, description, amount FROM transactions
                        WHERE customer_id=? ORDER BY date DESC LIMIT 5""",
                        (cid,),
                    ).fetchall()
                if not rows:
                    return {"role": "assistant", "content": "No recent transactions found.\n\n" + follow_up()}
                lines = ["Here are your last 5 transactions:"]
                lines += [f"- {r['date']}: {r['description']} (${r['amount']:.2f})" for r in rows]
                return {"role": "assistant", "content": "\n".join(lines) + "\n\n" + follow_up()}

            # offer savings products
            if "saving" in lower:
                return {
                    "role": "assistant",
                    "content": (
                        "We offer Basic Savings, **High‑Yield Savings** (up to 4.5 % APY), "
                        "and Money‑Market Accounts.  Interested in an **application link**?\n\n"
                        + follow_up()
                    ),
                }

            # user says yes to link
            if lower in ("yes", "yes please", "yes, please", "yep"):
                return {"role": "assistant", "content": "You can start an application here: <https://www.chase.com/personal/savings>\n\n" + follow_up()}

            # PDF question / analysis
            if uploaded_files and any(k in lower for k in ("pdf", "report", "profit", "revenue", "expense", "summary", "detail")):
                # build combined context (truncate each to 8k chars)
                ctx_chunks = [extract_pdf(p) for p in uploaded_files]
                ctx = "\n\n".join(ctx_chunks)
                answer = ask_llm(msg, ctx)
                return {"role": "assistant", "content": answer + "\n\n" + follow_up()}

            # exit
            if any(w in lower for w in ("bye", "exit", "close", "thank")):
                user_state.clear(); user_state["step"] = "start"
                return {"role": "assistant", "content": "Thanks for banking with JP Morgan Chase.  Goodbye!"}

            # fallback
            return {"role": "assistant", "content": follow_up()}

        # ───────────── unknown state fallback ─────────────
        user_state.clear(); user_state["step"] = "start"
        return {"role": "assistant", "content": "Something went wrong – let's start over."}

    except Exception as err:
        print("❗", err)
        user_state.clear(); user_state["step"] = "start"
        return {"role": "assistant", "content": "Sorry, an internal error occurred.  Please start again."}

# ───────────────────────── file upload ───────────────────────────

def handle_upload(file_path):
    if not file_path:
        return gr.update()
    if len(uploaded_files) >= MAX_PDFS:
        return gr.update(value="❌ Maximum PDF limit reached (3).  Remove a file first.")
    uploaded_files.append(file_path)
    short = os.path.basename(file_path)
    return gr.update(value=f"✅ {short} uploaded.  Ask me a question when ready.")

# ─────────────────────────── UI build ────────────────────────────
with gr.Blocks(theme=gr.themes.Soft()) as demo:
    gr.Markdown("# JP Morgan Chase • Financial Assistant\nYour personalised banking experience awaits 🚀")

    chat = gr.ChatInterface(
        fn=bot,
        chatbot=gr.Chatbot(type="messages"),
        textbox=gr.Textbox(placeholder="Ask about your balance, transactions, savings, or say 'upload'…"),
    )

    status = gr.Textbox(label="Upload status", interactive=False)

    gr.File(
        label="Upload Financial Document (PDF)",
        file_types=[".pdf"],
        type="filepath",
    ).change(handle_upload, outputs=status)

if __name__ == "__main__":
    demo.launch(share=True)
