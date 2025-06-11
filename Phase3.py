# financial_ai_agent.py  –  27 Apr 2025
import os, sqlite3, pdfplumber
from datetime import datetime
import gradio as gr
from dotenv import load_dotenv
from openai import OpenAI

# ─────────────────────────  config  ──────────────────────────
load_dotenv()
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# ─────────────────────────  globals  ─────────────────────────
user_state = {"step": "start"}        # conversation FSM
uploaded_file_path: str | None = None

# ────────────────────────  utilities  ────────────────────────
def db():
    conn = sqlite3.connect("customers.db")
    conn.row_factory = sqlite3.Row
    return conn

def extract_pdf(path: str) -> str:
    txt = []
    with pdfplumber.open(path) as pdf:
        for pg in pdf.pages:
            if (t := pg.extract_text()):
                txt.append(t)
    # keep token-cost reasonable
    return "\n".join(txt)[:8_000]

def ask_llm(q: str, ctx: str) -> str:
    rsp = client.chat.completions.create(
        model="gpt-3.5-turbo",
        temperature=0.4,
        max_tokens=512,
        messages=[
            {"role": "system", "content": "You are a helpful financial assistant."},
            {"role": "user",    "content": f"Context:\n{ctx}\n\nQuestion:\n{q}"}
        ]
    )
    return rsp.choices[0].message.content.strip()

# ───────────────────────  chat handler  ──────────────────────
def bot(user_msg: str, history):
    """Gradio ChatInterface fn(message:str, history:list[dict]) -> dict"""
    msg = user_msg.strip()
    lower = msg.lower()
    step = user_state["step"]

    try:
        # ──────────  step: start  ──────────
        if step == "start":
            user_state["step"] = "await_type"
            return {"role": "assistant",
                    "content": ("Welcome to JP Morgan Chase Financial Assistant.\n"
                                "Are you an **existing customer** or a **new user**?")}

        # ──────────  step: existing / new  ──────────
        if step == "await_type":
            if "existing" in lower:
                user_state["step"] = "await_phone"
                return {"role": "assistant",
                        "content": "Great!  Please enter your registered phone number:"}
            if "new" in lower:
                user_state["step"] = "new_name"
                return {"role": "assistant",
                        "content": "Welcome aboard!  What is your full name?"}
            return {"role": "assistant",
                    "content": "Please type **existing** or **new** to continue."}

        # ──────────  new-user mini-flow  ──────────
        if step == "new_name":
            user_state["new_name"] = msg
            user_state["step"] = "new_email"
            return {"role": "assistant",
                    "content": "Thanks.  And your e-mail address?"}

        if step == "new_email":
            # (in a real app you'd insert into a prospects table here)
            name = user_state.get("new_name", "")
            user_state.clear(); user_state["step"] = "start"
            return {"role": "assistant",
                    "content": (f"Thanks {name}!  A banker will reach out soon to "
                                "finish onboarding.  Have a great day!")}

        # ──────────  existing-customer auth  ──────────
        if step == "await_phone":
            with db() as conn:
                cur = conn.execute(
                    "SELECT id, first_name, last_name FROM customers WHERE phone=?",
                    (msg,))
                row = cur.fetchone()
            if row:
                user_state.update(
                    customer_id=row["id"],
                    first=row["first_name"],
                    last=row["last_name"],
                    step="await_zip",
                )
                return {"role": "assistant",
                        "content": "Thanks.  Now, please enter your ZIP code:"}
            return {"role": "assistant",
                    "content": "Phone number not found.  Please try again:"}

        if step == "await_zip":
            with db() as conn:
                cur = conn.execute("SELECT zip_code FROM customers WHERE id=?",
                                (user_state["customer_id"],))
                zip_code = cur.fetchone()["zip_code"]
            if msg == zip_code:
                user_state["step"] = "verified"
                return {"role": "assistant",
                        "content":
                        (f"✅ Verified.  Welcome back {user_state['first']} "
                        f"{user_state['last']}!\n"
                         "Ask me about your **balance**, **recent transactions**, "
                         "or **savings products**.")}
            return {"role": "assistant",
                    "content": "❌ ZIP code incorrect.  Please try again:"}

        # ──────────  verified customer actions  ──────────
        if step == "verified":
            cid = user_state["customer_id"]

            # balance
            if "balance" in lower:
                with db() as conn:
                    bal = conn.execute("SELECT balance FROM customers WHERE id=?",
                                    (cid,)).fetchone()["balance"]
                return {"role": "assistant",
                        "content": f"Your current balance is **${bal:,.2f}**."}

            # recent transactions
            if "transaction" in lower or "recent" in lower:
                with db() as conn:
                    rows = conn.execute(
                        """SELECT date, description, amount
                        FROM transactions
                        WHERE customer_id=?
                        ORDER BY date DESC LIMIT 5""", (cid,)).fetchall()
                if not rows:
                    return {"role": "assistant",
                            "content": "No recent transactions found."}
                lines = ["Here are your last 5 transactions:"]
                for r in rows:
                    lines.append(f"- {r['date']}: {r['description']} "
                                f"(${r['amount']:.2f})")
                return {"role": "assistant", "content": "\n".join(lines)}

            # savings products
            if "saving" in lower:
                return {"role": "assistant",
                        "content":
                        ("We offer Basic Savings, **High-Yield Savings** (up to 4.5 % APY), "
                        "and Money-Market Accounts.\n"
                         "Would you like the **application link**?")}

            # user says "yes" after savings offer
            if lower in ("yes", "yes please", "yes, please", "yep"):
                return {"role": "assistant",
                        "content":
                        "You can start an application here: "
                        "<https://www.chase.com/personal/savings>"}

            # PDF Q&A
            if uploaded_file_path and uploaded_file_path.lower().endswith(".pdf"):
                if any(k in lower for k in ("what", "how much", "profit", "revenue",
                                            "summary", "explain", "detail")):
                    ctx = extract_pdf(uploaded_file_path)
                    answer = ask_llm(msg, ctx)
                    return {"role": "assistant", "content": answer}

            # polite exit
            if any(x in lower for x in ("bye", "thank", "thanks", "exit", "close")):
                user_state.clear(); user_state["step"] = "start"
                return {"role": "assistant",
                        "content": "Thank you for banking with JP Morgan Chase.  Goodbye!"}

            # fallback
            return {"role": "assistant",
                    "content":
                    "I'm here to help with **balance**, **transactions**, or "
                    "**savings products**.  What would you like to know?"}

        # ──────────  unknown state fallback  ──────────
        user_state.clear(); user_state["step"] = "start"
        return {"role": "assistant",
                "content": "Something went wrong.  Let's start over."}

    except Exception as err:
        print("❗", err)
        user_state.clear(); user_state["step"] = "start"
        return {"role": "assistant",
                "content": "Sorry, an internal error occurred.  Please start again."}

# ─────────────────────────  file upload  ─────────────────────
def handle_upload(file):
    global uploaded_file_path
    uploaded_file_path = file
    # returning None avoids the “too many outputs” warning
    return

# ───────────────────────────  UI  ────────────────────────────
with gr.Blocks(theme=gr.themes.Soft()) as demo:
    gr.Markdown("# JP Morgan Chase • Financial Assistant\n"
                "Your personalised banking experience awaits 🚀")

    chat = gr.ChatInterface(fn=bot,
                            chatbot=gr.Chatbot(type="messages"),
                            textbox=gr.Textbox(
                                placeholder="Ask about your balance, "
                                            "transactions, or savings products…"))

    gr.File(label="Upload Financial Document (PDF)",
            file_types=[".pdf"],
            type="filepath").change(handle_upload, None, None)

if __name__ == "__main__":
    demo.launch(share=True)